"""Offline contract tests: exact file preservation, ownership, remote failures and downloads.

Run from backend/: python -m unittest discover -s tests -p test_descriptors.py -v
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import requests

from app.routes import descriptors as routes
from config.settings import settings
from tools.multiwfn.client import DescriptorClient, DescriptorServiceError

REMOTE_ID = '99a25d11-b635-456c-940d-2b8427c6ff0c'
def fchk_source(numbers):
    return (f"Original wavefunction\r\n{'Atomic numbers':<43}I   N= {len(numbers)}\r\n" +
            ' '.join(map(str, numbers)) + '\r\n').encode()


SOURCE = fchk_source([22, 8, 8]) + b'Original trailing bytes\r\n\xff\x00'


class Download:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield b'{"descriptors":'
        yield b'{"gap_eV":4.2}}'


class FakeService:
    def __init__(self):
        self.submissions = 0
        self.downloads = 0
        self.polls = 0
        self.failure = None
        self.received = {}
        self.parameters = None

    def submit(self, sources, ti_index, o_indices, methods):
        self.submissions += 1
        self.received = {key: (name, path.read_bytes()) for key, (name, path) in sources.items()}
        self.parameters = (ti_index, o_indices, methods)
        if self.failure:
            raise self.failure
        return {'job_id': REMOTE_ID, 'status': 'queued'}

    def status(self, remote_id):
        assert remote_id == REMOTE_ID
        self.polls += 1
        return {'status': 'completed', 'partial': True, 'failed_methods': ['chelpg'],
                'result': {'descriptors': {'gap_eV': 4.2}, 'methods': {'chelpg': {'status': 'failed'}}}}

    def download(self, remote_id, filename):
        assert remote_id == REMOTE_ID
        self.downloads += 1
        return Download()


class DescriptorRoutesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = patch.object(settings, 'DESCRIPTOR_DATA_DIR', self.temp.name)
        self.settings.start()
        self.service = FakeService()
        self.factory = patch.object(routes, 'DescriptorClient', return_value=self.service)
        self.factory.start()
        app = FastAPI()
        app.include_router(routes.router, prefix='/api/descriptors')
        self.client = TestClient(app)
        self.headers = {'X-User-ID': 'alice'}
        self.base = '/api/descriptors'

    def tearDown(self):
        self.client.close()
        self.factory.stop()
        self.settings.stop()
        self.temp.cleanup()

    def submit(self, **kwargs):
        return self.client.post(self.base, headers=self.headers,
                                files=kwargs.pop('files', {'fchk': ('sample.fchk', SOURCE)}), **kwargs)

    def test_original_bytes_and_optional_output_are_preserved(self):
        response = self.submit(files={'fchk': ('C:\\private\\sample.fchk', SOURCE), 'out': ('same.log', b'output\r\n')})
        self.assertEqual(response.status_code, 202)
        job = response.json()
        self.assertNotIn('remote_id', job)
        self.assertNotIn('stored_name', job['uploads']['fchk'])
        self.assertEqual(self.service.received['fchk'], ('sample.fchk', SOURCE))
        self.assertEqual(self.service.received['out'][1], b'output\r\n')
        self.assertEqual(self.client.get(f"{self.base}/{job['id']}/source/fchk", headers=self.headers).content, SOURCE)
        self.assertEqual(self.client.get(self.base, headers=self.headers).json()['items'][0]['id'], job['id'])

    def test_jobs_and_files_are_user_scoped(self):
        job_id = self.submit().json()['id']
        for path in ['', '/source/fchk', '/files/descriptors.json']:
            self.assertEqual(self.client.get(f'{self.base}/{job_id}{path}', headers={'X-User-ID': 'bob'}).status_code, 404)
        self.assertEqual(self.client.get(self.base, headers={'X-User-ID': 'bob'}).json(), {'items': []})
        self.assertEqual(self.client.get(self.base).status_code, 401)
        self.assertEqual(self.client.get(f'{self.base}/{job_id}/source/fchk').status_code, 401)
        self.assertEqual(self.client.post(self.base, files={'fchk': ('a.fchk', SOURCE)}).status_code, 401)
        self.assertEqual(self.service.polls, 0)
        self.assertEqual(self.service.downloads, 0)

    def test_poll_partial_results_and_cache_download(self):
        job_id = self.submit().json()['id']
        for _ in range(2):
            result = self.client.get(f'{self.base}/{job_id}', headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()['partial'])
            self.assertEqual(result.json()['result']['descriptors']['gap_eV'], 4.2)
            download = self.client.get(f'{self.base}/{job_id}/files/descriptors.json', headers=self.headers)
            self.assertEqual(download.json(), {'descriptors': {'gap_eV': 4.2}})
        self.assertEqual(self.service.polls, 1)
        self.assertEqual(self.service.downloads, 1)
        self.assertEqual(self.client.get(f'{self.base}/{job_id}/files/job.json', headers=self.headers).status_code, 404)

    def test_timeout_keeps_original_and_does_not_resubmit(self):
        self.service.failure = DescriptorServiceError('submission uncertain', uncertain=True)
        response = self.submit()
        self.assertEqual(response.status_code, 502)
        job = response.json()['job']
        self.assertEqual(job['status'], 'submission_unknown')
        self.assertEqual(self.client.get(f"{self.base}/{job['id']}", headers=self.headers).json()['status'], 'submission_unknown')
        self.assertEqual(self.client.get(f"{self.base}/{job['id']}/source/fchk", headers=self.headers).content, SOURCE)
        self.assertEqual(self.service.submissions, 1)
        self.assertEqual(self.service.polls, 0)

    def test_queue_rejection_is_saved_for_history(self):
        self.service.failure = DescriptorServiceError('queue full', 429)
        response = self.submit()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['job']['status'], 'submission_failed')
        self.assertEqual(self.client.get(self.base, headers=self.headers).json()['items'][0]['status'], 'submission_failed')

    def test_validation_does_not_contact_remote_or_leave_partial_files(self):
        for files in [{'fchk': ('binary.chk', SOURCE)}, {'fchk': ('empty.fchk', b'')},
                      {'fchk': ('valid.fch', SOURCE), 'out': ('wrong.txt', b'x')}]:
            self.assertEqual(self.submit(files=files).status_code, 422)
        for data in [{'ti_index': -1}, {'o_indices': '1,1'}, {'methods': 'basic,mayer'}, {'methods': 'unknown'}]:
            self.assertEqual(self.submit(data=data).status_code, 400)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(self.service.submissions, 0)

    def test_auto_selects_titanium_away_from_first_atom(self):
        response = self.submit(files={'fchk': ('moved.fchk', fchk_source([6, 8, 22, 8]))})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()['ti_index'], 3)
        self.assertEqual(self.service.parameters[0], 3)

    def test_multiple_titaniums_require_selection_and_manual_index_must_be_ti(self):
        source = fchk_source([6, 22, 8, 22, 8])
        for data in [{}, {'ti_index': 1}, {'ti_index': 2, 'o_indices': '1,3'}]:
            response = self.submit(files={'fchk': ('multi.fchk', source)}, data=data)
            self.assertEqual(response.status_code, 422)
        self.assertEqual(self.service.submissions, 0)
        response = self.submit(files={'fchk': ('multi.fchk', source)}, data={'ti_index': 4, 'o_indices': '3,5'})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.service.parameters[:2], (4, '3,5'))

    def test_no_titanium_is_forwarded_as_auto_without_false_first_atom(self):
        response = self.submit(files={'fchk': ('ligand.fchk', fchk_source([6, 8, 8]))})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.service.parameters[0], 0)

    def test_file_and_combined_limits(self):
        with patch.object(routes, 'MAX_FILE', 10), patch.object(routes, 'MAX_TOTAL', 14):
            self.assertEqual(self.submit(files={'fchk': ('large.fchk', b'x' * 11)}).status_code, 413)
            self.assertEqual(self.submit(files={'fchk': ('a.fchk', b'x' * 8), 'out': ('a.out', b'x' * 8)}).status_code, 413)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(self.service.submissions, 0)

    def test_interrupted_submission_is_not_polled_forever(self):
        job_id = self.submit().json()['id']
        folder, record = routes._load(job_id, 'alice')
        record.pop('remote_id')
        record.update(status='submitting', created_at='2020-01-01T00:00:00+00:00')
        routes._write(folder, record)
        response = self.client.get(f'{self.base}/{job_id}', headers=self.headers)
        self.assertEqual(response.json()['status'], 'submission_unknown')
        self.assertEqual(self.service.polls, 0)

    def test_interrupted_download_does_not_cache_partial_file(self):
        job_id = self.submit().json()['id']
        class BrokenDownload(Download):
            def iter_content(self, size):
                yield b'partial data'
                raise requests.ConnectionError('interrupted')
        with patch.object(self.service, 'download', return_value=BrokenDownload()):
            response = self.client.get(f'{self.base}/{job_id}/files/summary.csv', headers=self.headers)
        self.assertEqual(response.status_code, 502)
        self.assertEqual({p.name for p in (Path(self.temp.name) / job_id).iterdir()}, {'job.json', 'source_fchk.fchk'})


class DescriptorClientTests(unittest.TestCase):
    def test_incomplete_submission_response_is_uncertain(self):
        response = requests.Response()
        response.status_code = 202
        response._content = b'{}'
        response._content_consumed = True
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.fchk'
            path.write_bytes(SOURCE)
            with patch.object(settings, 'EQV2_API_KEY', 'test-secret'), patch('tools.multiwfn.client.requests.request', return_value=response) as request:
                with self.assertRaises(DescriptorServiceError) as caught:
                    DescriptorClient().submit({'fchk': ('sample.fchk', path)}, 1, '', 'basic')
                self.assertTrue(caught.exception.uncertain)
                self.assertEqual(request.call_count, 1)

    def test_multipart_preserves_bytes_and_never_retries_timeout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.fchk'
            path.write_bytes(SOURCE)
            captured = {}
            def post(*args, **kwargs):
                captured.update(kwargs)
                self.assertEqual(kwargs['files']['fchk'][1].read(), SOURCE)
                raise requests.Timeout('test-secret')
            with patch.object(settings, 'EQV2_API_KEY', 'test-secret'), patch('tools.multiwfn.client.requests.request', side_effect=post) as request:
                with self.assertRaises(DescriptorServiceError) as caught:
                    DescriptorClient().submit({'fchk': ('sample.fchk', path)}, 1, '', 'basic')
                self.assertTrue(caught.exception.uncertain)
                self.assertNotIn('test-secret', str(caught.exception))
                self.assertEqual(request.call_count, 1)
                self.assertNotIn('Content-Type', captured['headers'])

    def test_remote_error_redacts_key(self):
        response = requests.Response()
        response.status_code = 422
        response._content = json.dumps({'detail': 'bad test-secret'}).encode()
        response._content_consumed = True
        with patch.object(settings, 'EQV2_API_KEY', 'test-secret'), patch('tools.multiwfn.client.requests.request', return_value=response):
            with self.assertRaises(DescriptorServiceError) as caught:
                DescriptorClient().status(REMOTE_ID)
            self.assertNotIn('test-secret', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
