"""Authenticated upload/analysis endpoints, behind the existing :8888 proxy."""
import csv
import json
import logging
import os
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import hmac
from atom_selection import select_titanium, validate_oxygens
from extract_descriptors import fchk_fields

ROOT = Path(__file__).resolve().parent
JOBS = ROOT / 'jobs'
JOBS.mkdir(exist_ok=True)
KEY = os.environ['EQV2_API_KEY']
MAX_FILE = 40 * 1024 * 1024
pool = ThreadPoolExecutor(max_workers=1)
guard = threading.Lock()
pending = 0
logging.basicConfig(level=logging.INFO)
auth = HTTPBearer(auto_error=False)


def require_key(credentials: Optional[HTTPAuthorizationCredentials] = Depends(auth)):
    if credentials is None or credentials.scheme.lower() != 'bearer' or not hmac.compare_digest(credentials.credentials,KEY):
        raise HTTPException(401,detail='invalid API key')


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2))
    temp.replace(path)


def location(job_id):
    return JOBS / str(job_id)


def work(job_id,ti,oxygen,methods):
    global pending
    directory = location(job_id)
    state = json.loads((directory / 'status.json').read_text())
    state.update(status='running',started_at=now())
    save(directory / 'status.json',state)
    try:
        cmd = [sys.executable,str(ROOT / 'extract_descriptors.py'),str(directory),
               '--ti',str(ti),'--methods',','.join(methods)]
        if oxygen:
            cmd += ['--o'] + [str(i) for i in oxygen]
        with (directory / 'worker.log').open('w') as log:
            result = subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=2700)
        if result.returncode != 0:
            raise RuntimeError('Analysis failed; inspect uploaded files and authenticated worker log')
        data = json.loads((directory / 'descriptors.json').read_text())
        failed = [name for name,value in data['methods'].items() if value['status'] not in ('success', 'skipped')]
        state.update(status='completed',result=data,partial=bool(failed),failed_methods=failed)
    except Exception as error:
        logging.exception('descriptor job failed: %s',job_id)
        state.update(status='failed',error=str(error) if isinstance(error,RuntimeError) else type(error).__name__)
    finally:
        state['completed_at'] = now()
        save(directory / 'status.json',state)
        with guard:
            pending -= 1


# On restart, explicitly label jobs that cannot be resumed.
for status_file in JOBS.glob('*/status.json'):
    saved = json.loads(status_file.read_text())
    if saved.get('status') in ('queued','running'):
        saved.update(status='interrupted',completed_at=now())
        save(status_file,saved)

app = FastAPI(title='TiCl4 Gaussian/Multiwfn descriptor API',version='1.0.0',
              docs_url='/v1/descriptors/docs',openapi_url='/v1/descriptors/openapi.json',redoc_url=None)


@app.get('/v1/descriptors/health')
def health():
    return {'status':'ok','multiwfn':'2026.10.18 noGUI','pending':pending}


@app.get('/v1/descriptors/tools',dependencies=[Depends(require_key)])
def tools():
    return {'inputs':['Gaussian .out/.log','.fchk/.fch'],
            'methods':['hirshfeld','cm5','chelpg','mayer'],
            'direct':['SCF energy','HOMO/LUMO/gap','dipole','NPA from fchk','polarizability','Ti-O geometry'],
            'not_enabled':['ESP surface extrema','NMR','binding energy','Gaussian calculations'],
            'limits':{'file_MB':40,'atoms':200,'queued_and_running':3,'threads':1},
            'note':'Upload matching out/fchk from the same calculation. Ti CHELPG radius is 1.7 angstrom.'}


async def store_upload(upload,destination,extensions):
    if not upload.filename or Path(upload.filename).suffix.lower() not in extensions:
        raise HTTPException(422,detail='unsupported file extension')
    total = 0
    with destination.open('wb') as stream:
        while True:
            chunk = await upload.read(1024*1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE:
                raise HTTPException(413,detail='file exceeds 40 MB limit')
            if b'\x00' in chunk:
                raise HTTPException(422,detail='binary files are not supported; upload formatted fchk')
            stream.write(chunk)
    await upload.close()
    if not total:
        raise HTTPException(422,detail='empty file')


@app.post('/v1/descriptors',status_code=202,dependencies=[Depends(require_key)])
async def submit(
    out: Optional[UploadFile] = File(None), fchk: Optional[UploadFile] = File(None),
    ti_index: int = Form(0,ge=0,le=200), o_indices: str = Form(''),
    methods: str = Form('hirshfeld,cm5,chelpg,mayer'),
):
    global pending
    if out is None and fchk is None:
        raise HTTPException(422,detail='upload out or fchk or both')
    selected = [] if methods.strip() == 'basic' else [m.strip() for m in methods.split(',') if m.strip()]
    if any(m not in ('hirshfeld','cm5','chelpg','mayer') for m in selected):
        raise HTTPException(422,detail='unsupported method')
    try:
        oxygen = [int(v.strip()) for v in o_indices.split(',')] if o_indices else None
        if oxygen is not None and (len(oxygen) != 2 or len(set(oxygen)) != 2 or min(oxygen)<1):
            raise ValueError()
    except ValueError:
        raise HTTPException(422,detail='o_indices must be two distinct 1-based atom indices, e.g. 8,9')
    with guard:
        if pending >= 3:
            raise HTTPException(429,detail='descriptor queue is full')
        pending += 1
    job_id = str(uuid.uuid4())
    directory = location(job_id)
    directory.mkdir(mode=0o700)
    try:
        if out is not None:
            await store_upload(out,directory / 'input.out',('.out','.log'))
        if fchk is not None:
            await store_upload(fchk,directory / 'input.fchk',('.fchk','.fch'))
            try:
                fields = fchk_fields(directory / 'input.fchk')
                numbers = [int(value) for value in fields['Atomic numbers']]
                ti_index = select_titanium(numbers, ti_index) or 0
                validate_oxygens(numbers, ti_index or None, oxygen)
            except (ValueError, KeyError) as error:
                raise HTTPException(422, detail=str(error)) from error
        save(directory / 'status.json',{'job_id':job_id,'status':'queued','created_at':now()})
        pool.submit(work,job_id,ti_index,oxygen,selected if fchk is not None else [])
    except Exception:
        with guard:
            pending -= 1
        # Retain a small audit record, rather than reporting an accepted job.
        save(directory / 'status.json',{'job_id':job_id,'status':'rejected','created_at':now()})
        raise
    return {'job_id':job_id,'status':'queued','status_url':'/v1/descriptors/jobs/' + job_id}


@app.get('/v1/descriptors/jobs/{job_id}',dependencies=[Depends(require_key)])
def status(job_id: uuid.UUID):
    path = location(job_id) / 'status.json'
    if not path.is_file():
        raise HTTPException(404,detail='job not found')
    return json.loads(path.read_text())


@app.get('/v1/descriptors/jobs/{job_id}/files/{filename}',dependencies=[Depends(require_key)])
def download(job_id: uuid.UUID,filename: str):
    allowed = {'descriptors.json','summary.csv','charges.csv','worker.log',
               'hirshfeld.log','cm5.log','chelpg.log','mayer.log'}
    if filename not in allowed:
        raise HTTPException(404,detail='file not available')
    path = location(job_id) / filename
    if not path.is_file():
        raise HTTPException(404,detail='file not available')
    return FileResponse(str(path),filename=filename)
