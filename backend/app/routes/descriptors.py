"""Independent wavefunction uploads; user-scoped durable job records and downloads."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from uuid import uuid4

import requests

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from config.settings import settings
from tools.multiwfn.client import DescriptorClient, DescriptorServiceError
from tools.multiwfn.atom_selection import read_atomic_numbers, select_titanium, validate_oxygens

router = APIRouter()
MAX_FILE = 40 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
RESULT_FILES = {'descriptors.json', 'summary.csv', 'charges.csv', 'worker.log',
                'hirshfeld.log', 'cm5.log', 'chelpg.log', 'mayer.log'}
TERMINAL = {'completed', 'failed', 'interrupted', 'rejected', 'submission_failed', 'submission_unknown'}


def _error(message, status=400, code='DESCRIPTOR_ERROR', **extra):
    return JSONResponse({'error': message, 'code': code, **extra}, status_code=status)


def _owner(request):
    # Same trusted gateway header as the conversation routes; never accept ownership from form data.
    return (request.headers.get('X-User-ID') or '').strip() or None


def _root():
    root = Path(settings.DESCRIPTOR_DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _write(folder, record):
    # Unique temporary names make concurrent status refreshes safe from truncated JSON.
    temp = folder / (uuid4().hex + '.tmp')
    try:
        temp.write_text(json.dumps(record, ensure_ascii=False), encoding='utf-8')
        os.replace(temp, folder / 'job.json')
    finally:
        temp.unlink(missing_ok=True)


def _load(job_id, user):
    if not re.fullmatch(r'[0-9a-f]{32}', job_id):
        return None
    folder = _root() / job_id
    try:
        record = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    return (folder, record) if record['user_id'] == user else None


def _public(record):
    public = {k: v for k, v in record.items() if k not in {'user_id', 'remote_id'}}
    public['uploads'] = {kind: {'filename': item['filename'], 'size': item['size']}
                         for kind, item in record['uploads'].items()}
    return public


@router.get('')
def list_jobs(request: Request):
    user = _owner(request)
    if user is None:
        return _error('请先登录', 401)
    records = []
    for path in _root().glob('*/job.json'):
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            if record['user_id'] == user:
                records.append(_public(record))
        except (OSError, ValueError, KeyError):
            continue
    return {'items': sorted(records, key=lambda item: item['created_at'], reverse=True)[:50]}


@router.post('')
def submit(request: Request, fchk: UploadFile = File(...), out: UploadFile | None = File(None),
           ti_index: int = Form(0), o_indices: str = Form(''),
           methods: str = Form('hirshfeld,cm5,chelpg,mayer')):
    user = _owner(request)
    if user is None:
        return _error('请先登录', 401)
    chosen = methods.split(',')
    if not chosen or len(chosen) != len(set(chosen)) or not set(chosen) <= {'basic', 'hirshfeld', 'cm5', 'chelpg', 'mayer'} or ('basic' in chosen and len(chosen) != 1):
        return _error('请选择基础解析或有效的 Multiwfn 分析方法')
    if not 0 <= ti_index <= 200:
        return _error('Ti 原子编号应在 1–200 之间；0 表示自动识别')
    if o_indices:
        if not re.fullmatch(r'\d+,\d+', o_indices):
            return _error('O 原子编号应为两个以逗号分隔的整数，例如 8,9')
        indices = [int(i) for i in o_indices.split(',')]
        if len(set([ti_index, *indices])) != 3 or any(not 1 <= i <= 200 for i in indices):
            return _error('Ti 和两个 O 的编号应各不相同，且在 1–200 之间')

    job_id = uuid4().hex
    folder = _root() / job_id
    folder.mkdir()
    sources, uploads, total = {}, {}, 0
    # Save exact bytes. Do not parse, normalize, decode, or turn these files into XYZ.
    try:
        for kind, upload, allowed in [('fchk', fchk, {'.fchk', '.fch'}), ('out', out, {'.out', '.log'})]:
            if upload is None:
                continue
            name = Path((upload.filename or '').replace('\\', '/')).name
            name = ''.join(c for c in name if ord(c) >= 32)[:180]
            suffix = Path(name).suffix.lower()
            if suffix not in allowed:
                raise ValueError('波函数文件仅支持 .fchk/.fch；附加输出文件仅支持 .out/.log，不支持二进制 .chk')
            path = folder / ('source_' + kind + suffix)
            size = 0
            with path.open('wb') as target:
                while chunk := upload.file.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FILE or total > MAX_TOTAL:
                        raise OverflowError('每个文件最多 40 MB，两个文件合计最多 64 MB')
                    target.write(chunk)
            if not size:
                raise ValueError('上传文件不能为空')
            sources[kind] = (name, path)
            uploads[kind] = {'filename': name, 'size': size, 'stored_name': path.name}
        numbers = read_atomic_numbers(sources['fchk'][1])
        ti_index = select_titanium(numbers, ti_index) or 0
        validate_oxygens(numbers, ti_index or None, [int(i) for i in o_indices.split(',')] if o_indices else None)
    except (ValueError, OverflowError) as exc:
        shutil.rmtree(folder)
        return _error(str(exc), 413 if isinstance(exc, OverflowError) else 422)
    except BaseException:
        shutil.rmtree(folder)
        raise
    record = {'id': job_id, 'user_id': user, 'created_at': datetime.now(timezone.utc).isoformat(),
              'status': 'submitting', 'uploads': uploads, 'ti_index': ti_index,
              'o_indices': o_indices, 'methods': chosen}
    _write(folder, record)
    try:
        result = DescriptorClient().submit(sources, ti_index, o_indices, methods)
        record.update(remote_id=result['job_id'], status=result.get('status', 'queued'))
    except DescriptorServiceError as exc:
        record.update(status='submission_unknown' if exc.uncertain else 'submission_failed', error=str(exc))
        _write(folder, record)
        return _error(str(exc), exc.status_code, job=_public(record))
    _write(folder, record)
    return JSONResponse(_public(record), status_code=202)


@router.get('/{job_id}')
def job_status(job_id: str, request: Request):
    if _owner(request) is None:
        return _error('请先登录', 401)
    loaded = _load(job_id, _owner(request))
    if loaded is None:
        return _error('任务不存在', 404)
    folder, record = loaded
    if record['status'] == 'submitting' and not record.get('remote_id'):
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(record['created_at'])).total_seconds()
        if age > 300:
            record.update(status='submission_unknown', error='提交未完成或服务重启，无法确认远程任务；原文件已保留，请联系管理员核对，勿重复提交')
            _write(folder, record)
    if record['status'] not in TERMINAL and record.get('remote_id'):
        try:
            result = DescriptorClient().status(record['remote_id'])
            if not isinstance(result, dict) or result.get('status') not in {'queued', 'running', 'completed', 'failed', 'interrupted', 'rejected'}:
                return _error('描述符服务返回了无效任务状态', 502)
            for key in ['status', 'result', 'partial', 'failed_methods', 'error', 'started_at', 'completed_at']:
                if key in result:
                    record[key] = result[key]
            # A concurrent, slower poll must not overwrite an already terminal result.
            latest = _load(job_id, _owner(request))
            if latest and latest[1]['status'] in TERMINAL:
                record = latest[1]
            else:
                _write(folder, record)
        except DescriptorServiceError as exc:
            return _error(str(exc), exc.status_code)
    return _public(record)


@router.get('/{job_id}/source/{kind}')
def original(job_id: str, kind: str, request: Request):
    if _owner(request) is None:
        return _error('请先登录', 401)
    loaded = _load(job_id, _owner(request))
    if loaded is None or kind not in loaded[1]['uploads']:
        return _error('文件不存在', 404)
    folder, record = loaded
    upload = record['uploads'][kind]
    return FileResponse(folder / upload['stored_name'], filename=upload['filename'], media_type='application/octet-stream')


@router.get('/{job_id}/files/{filename}')
def result_file(job_id: str, filename: str, request: Request):
    if _owner(request) is None:
        return _error('请先登录', 401)
    loaded = _load(job_id, _owner(request))
    if loaded is None or filename not in RESULT_FILES or not loaded[1].get('remote_id'):
        return _error('文件不存在', 404)
    folder, record = loaded
    cached = folder / filename
    if not cached.exists():
        temporary = None
        try:
            with DescriptorClient().download(record['remote_id'], filename) as response:
                with tempfile.NamedTemporaryFile(dir=folder, delete=False) as target:
                    temporary = Path(target.name)
                    size = 0
                    for chunk in response.iter_content(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_TOTAL:
                            raise DescriptorServiceError('结果文件超过下载上限')
                        target.write(chunk)
            os.replace(temporary, cached)
        except DescriptorServiceError as exc:
            return _error(str(exc), exc.status_code)
        except requests.RequestException:
            return _error('结果下载中断，请重试', 502)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return FileResponse(cached, filename=filename, media_type='application/octet-stream')
