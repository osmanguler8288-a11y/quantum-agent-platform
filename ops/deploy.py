"""Build locally, transfer via SSH, deploy Compose releases. No credentials in code."""
import argparse
from datetime import datetime
import getpass
import io
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo

import paramiko
from dotenv import dotenv_values

LOCAL = Path(__file__).resolve().parents[1]
REMOTE = '/opt/quantum-agent-platform'


def run_local(args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def remote(client, command):
    channel = client.get_transport().open_session()
    channel.exec_command(command)
    last_output = time.monotonic()
    while True:
        for ready, receive in [(channel.recv_ready, channel.recv), (channel.recv_stderr_ready, channel.recv_stderr)]:
            if ready():
                print(receive(32768).decode('utf-8', 'replace'), end='', flush=True)
                last_output = time.monotonic()
        if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
            break
        if time.monotonic() - last_output > 30:
            print('[deploy] Remote operation still running...', flush=True)
            last_output = time.monotonic()
        time.sleep(0.1)
    if channel.recv_exit_status() != 0:
        raise RuntimeError('Remote command failed; see output above')


def write_secret(sftp, path, contents):
    with sftp.file(path, 'w') as f:
        f.write(contents)
    sftp.chmod(path, 0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='139.196.11.38')
    parser.add_argument('--user', default='root')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--rollback', action='store_true')
    parser.add_argument('--sync-env', action='store_true', help='Explicitly replace server app.env with local configuration')
    args = parser.parse_args()
    password = os.getenv('QAP_SSH_PASSWORD') or getpass.getpass('SSH password (not saved): ')
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    # Pin the first server key locally; changed keys are rejected on later updates.
    known_hosts = Path.home() / '.ssh' / 'qap_known_hosts'
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.touch(exist_ok=True)
    client.load_host_keys(str(known_hosts))
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(args.host, username=args.user, password=password, timeout=20, auth_timeout=20, look_for_keys=False, allow_agent=False)
    client.get_transport().set_keepalive(20)
    client.save_host_keys(str(known_hosts))
    try:
        if args.status:
            remote(client, f'cd {REMOTE}/current && docker compose --env-file {REMOTE}/shared/compose.env --env-file release.env -f ops/compose.yml ps')
            return
        if args.rollback:
            # Run the currently installed deployment routine against the previous release.
            remote(client, f'test -L {REMOTE}/previous && bash {REMOTE}/current/ops/release.sh "$(basename "$(readlink -f {REMOTE}/previous)")"')
            return

        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise RuntimeError('npm is required for the frontend build')
        if not (LOCAL / 'frontend/node_modules').exists():
            run_local([npm, 'ci'], cwd=LOCAL / 'frontend')
        run_local([npm, 'run', 'type-check'], cwd=LOCAL / 'frontend')
        run_local([npm, 'run', 'build'], cwd=LOCAL / 'frontend')
        sha = subprocess.check_output(['git', 'rev-parse', '--short=8', 'HEAD'], cwd=LOCAL, text=True).strip()
        release = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d-%H%M%S') + '-' + sha
        print('[deploy] Release:', release, flush=True)
        with tempfile.TemporaryDirectory(prefix='qap-release-') as folder:
            folder = Path(folder)
            binary = folder / 'auth-server'
            env = dict(os.environ, GOOS='linux', GOARCH='amd64', CGO_ENABLED='0')
            print('[deploy] Compiling Linux gateway...', flush=True)
            run_local(['go', 'build', '-trimpath', '-ldflags=-s -w', '-o', str(binary), '.'], cwd=LOCAL / 'backend/auth', env=env)
            archive = folder / 'release.tgz'
            files = subprocess.check_output(['git', 'ls-files', '-z', '--', 'backend'], cwd=LOCAL).decode('utf-8').split('\0')
            with tarfile.open(archive, 'w:gz') as tar:
                for name in files:
                    p = LOCAL / name
                    if not name or not p.is_file() or p.suffix in {'.db', '.sqlite3', '.pyc', '.exe'} or name == 'backend/auth/auth':
                        continue
                    tar.add(p, arcname=name)
                for name in ['ops', 'frontend/dist']:
                    tar.add(LOCAL / name, arcname=name, filter=lambda item: None if '__pycache__' in item.name else item)
                tar.add(binary, arcname='ops/bin/auth-server')
                content = f'QAP_RELEASE={release}\n'.encode()
                info = tarfile.TarInfo('release.env'); info.size = len(content); info.mode = 0o600
                tar.addfile(info, io.BytesIO(content))
            target = f'{REMOTE}/releases/{release}'
            remote(client, f'mkdir -p {shlex.quote(target)} {REMOTE}/shared/data/vectors {REMOTE}/shared/logs; chmod 700 {REMOTE}/shared')
            with client.open_sftp() as sftp:
                app_env = f'{REMOTE}/shared/app.env'
                try:
                    sftp.stat(app_env)
                    exists = True
                except FileNotFoundError:
                    exists = False
                if not exists or args.sync_env:
                    values = {**dotenv_values(LOCAL / '.env'), **dotenv_values(LOCAL / 'backend/.env')}
                    prefixes = ('LLM_', 'EMBED_', 'EQV2_', 'MAX_', 'CHUNK_', 'TOP_K', 'ATTACHMENT_MAX_BYTES')
                    values = {k: v for k, v in values.items() if v is not None and k.startswith(prefixes)}
                    if not values.get('LLM_API_KEY') or not values.get('EQV2_API_KEY'):
                        raise RuntimeError('Local LLM_API_KEY and EQV2_API_KEY must be configured')
                    # dotenv double quotes support escaped newlines, quotes and backslashes.
                    def quote(value):
                        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('$', '\\$') + '"'
                    if exists:
                        sftp.posix_rename(app_env, app_env + '.previous')
                    write_secret(sftp, app_env, ''.join(f'{k}={quote(v)}\n' for k, v in values.items()))
                try:
                    sftp.stat(f'{REMOTE}/shared/compose.env')
                except FileNotFoundError:
                    values = {k: secrets.token_hex(32) for k in ['QAP_MYSQL_ROOT_PASSWORD', 'QAP_MYSQL_PASSWORD', 'QAP_JWT_SECRET']}
                    write_secret(sftp, f'{REMOTE}/shared/compose.env', ''.join(f'{k}={v}\n' for k, v in values.items()))
                print(f'[deploy] Uploading {archive.stat().st_size / 1024 / 1024:.1f} MB...', flush=True)
                sftp.put(str(archive), target + '/release.tgz')
            remote(client, f'tar xzf {target}/release.tgz -C {target} && chmod 755 {target}/ops/bin/auth-server && bash {target}/ops/release.sh {release}')
        print(f'[deploy] Ready: http://{args.host}:8889', flush=True)
    finally:
        client.close()


if __name__ == '__main__':
    main()
