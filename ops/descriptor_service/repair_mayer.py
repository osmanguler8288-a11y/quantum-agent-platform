"""Recover selected Ti-O bonds from completed Mayer logs, without rerunning calculations."""
import argparse
import copy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from uuid import UUID, uuid4

from extract_descriptors import fchk_fields, selected_geometry, parse_mayer_pairs


def write_json(path, value):
    temporary = path.with_name(uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def repair(job_id, jobs_root, platform_root, apply=False):
    job_id = str(UUID(str(job_id)))
    directory = Path(jobs_root) / job_id
    state = json.loads((directory / 'status.json').read_text(encoding='utf-8'))
    result = json.loads((directory / 'descriptors.json').read_text(encoding='utf-8'))
    old_mayer = result.get('methods', {}).get('mayer', {})
    if state['status'] != 'completed' or old_mayer.get('status') != 'failed' or old_mayer.get('reason') != 'Ti and O indices required for selected Mayer bonds':
        raise ValueError('Only completed jobs with the known atom-selection failure can be repaired')
    ti, oxygen, geometry = selected_geometry(fchk_fields(directory / 'input.fchk'))
    if not ti or not oxygen:
        raise ValueError('No unique Ti and two O atoms found; manual review required')
    bonds = parse_mayer_pairs((directory / 'mayer.log').read_text(errors='replace'), ti, oxygen)
    updated = copy.deepcopy(result)
    desc = updated['descriptors']
    desc.update(geometry)
    desc.update(bonds)
    for label, index in [('Ti', ti), ('O1', oxygen[0]), ('O2', oxygen[1])]:
        for method, value in updated.get('charges', {}).get(str(index), {}).items():
            desc[label + '_' + method] = value
    updated['methods']['mayer'] = {'status': 'success', 'recovered_from_existing_log': True}
    updated['parameters'].update(ti_index=ti, o_indices=oxygen)
    failed = [name for name, value in updated['methods'].items() if value['status'] not in ('success', 'skipped')]
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
    print(json.dumps({'job_id': job_id, 'Ti': ti, 'O': oxygen, 'bonds': bonds, 'apply': apply}))
    if not apply:
        return updated
    backup = directory / 'mayer_fix_backups' / timestamp
    backup.mkdir(parents=True)
    for name in ['status.json', 'descriptors.json', 'summary.csv']:
        if (directory / name).exists():
            shutil.copy2(directory / name, backup / name)
    write_json(directory / 'descriptors.json', updated)
    with (directory / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow(['descriptor', 'value'])
        writer.writerows((key, json.dumps(value) if isinstance(value, list) else value) for key, value in desc.items())
    state.update(result=updated, partial=bool(failed), failed_methods=failed,
                 corrected_at=datetime.now(timezone.utc).isoformat())
    write_json(directory / 'status.json', state)
    for path in Path(platform_root).glob('*/job.json'):
        local = json.loads(path.read_text(encoding='utf-8'))
        if local.get('remote_id') != job_id:
            continue
        local_backup = path.parent / 'mayer_fix_backups' / timestamp
        local_backup.mkdir(parents=True)
        shutil.copy2(path, local_backup / path.name)
        for name in ['descriptors.json', 'summary.csv']:
            cached = path.parent / name
            if cached.exists():
                shutil.copy2(cached, local_backup / name)
                shutil.copy2(directory / name, cached)
        local.update(result=updated, partial=bool(failed), failed_methods=failed,
                     ti_index=ti, o_indices=','.join(map(str, oxygen)), corrected_at=state['corrected_at'])
        write_json(path, local)
    return updated


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job_ids', nargs='+', type=UUID)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--jobs-root', type=Path, default=Path(__file__).resolve().parent / 'jobs')
    parser.add_argument('--platform-root', type=Path, default=Path('/opt/quantum-agent-platform/shared/data/descriptors'))
    args = parser.parse_args()
    for job in args.job_ids:
        repair(job, args.jobs_root, args.platform_root, args.apply)
