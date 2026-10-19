"""Atom selection and recovery regression tests; no remote calls or Multiwfn execution."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from tools.multiwfn import atom_selection

SERVICE = Path(__file__).resolve().parents[2] / 'ops' / 'descriptor_service'
sys.modules['atom_selection'] = atom_selection


def load(name):
    spec = importlib.util.spec_from_file_location(name, SERVICE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extractor = load('extract_descriptors')
recovery = load('repair_mayer')


def source(numbers, coordinates):
    text = 'test molecule\nSP B3LYP\n'
    for key, kind, values in [('Number of atoms', 'I', len(numbers)), ('Charge', 'I', 0),
                               ('Total Energy', 'R', -123.456), ('Atomic numbers', 'I', numbers),
                               ('Current cartesian coordinates', 'R', coordinates)]:
        if isinstance(values, list):
            text += f'{key:<43}{kind} N= {len(values)}\n' + ' '.join(map(str, values)) + '\n'
        else:
            text += f'{key:<43}{kind} {values}\n'
    return text.encode()


NUMBERS = [6, 8, 22, 8]
COORDINATES = [10, 10, 10, 2, 0, 0, 0, 0, 0, 0, 3, 0]
MAYER_LOG = '2(O ) - 3(Ti ) : 0.25\n3(Ti ) 4(O ) : 0.20\n'


class AtomSelectionTests(unittest.TestCase):
    def test_unique_ti_is_selected_independent_of_atom_order(self):
        ti, oxygen, geometry = extractor.selected_geometry({'Number of atoms': 4, 'Atomic numbers': NUMBERS,
                                                           'Current cartesian coordinates': COORDINATES})
        self.assertEqual((ti, oxygen), (3, [2, 4]))
        self.assertAlmostEqual(geometry['Ti_O1_A'], 2 * extractor.BOHR_A)
        self.assertAlmostEqual(geometry['O_Ti_O_deg'], 90)
        self.assertEqual(extractor.parse_mayer_pairs(MAYER_LOG, ti, oxygen), {'Mayer_Ti_O1': 0.25, 'Mayer_Ti_O2': 0.2})

    def test_explicit_wrong_elements_and_ambiguous_ti_are_rejected(self):
        for numbers, selected in [([6, 8, 22, 8], 1), ([22, 8, 22, 8], 0), ([6, 8], 3)]:
            with self.assertRaises(ValueError):
                atom_selection.select_titanium(numbers, selected)
        with self.assertRaises(ValueError):
            atom_selection.validate_oxygens(NUMBERS, 3, [1, 2])
        self.assertEqual(atom_selection.select_titanium([22, 8, 22, 8], 3), 3)

    def test_fchk_reader_and_incomplete_array(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.fchk'
            path.write_bytes(source(NUMBERS, COORDINATES))
            self.assertEqual(atom_selection.read_atomic_numbers(path), NUMBERS)
            path.write_text(f"{'Atomic numbers':<43}I N= 4\n6 8\n")
            with self.assertRaises(ValueError):
                atom_selection.read_atomic_numbers(path)

    def test_no_ti_or_insufficient_oxygen_skips_mayer_without_running_it(self):
        for numbers in [[6, 8, 8, 1], [6, 8, 22, 1]]:
            with self.subTest(numbers=numbers), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)
                (path / 'input.fchk').write_bytes(source(numbers, COORDINATES))
                with patch.object(extractor, 'run_mw', side_effect=AssertionError('must not run')):
                    result = extractor.extract(path, methods=['mayer'])
                self.assertEqual(result['methods']['mayer']['status'], 'skipped')
                self.assertNotIn('Mayer_Ti_O1', result['descriptors'])


class RecoveryTests(unittest.TestCase):
    def test_recovery_uses_existing_log_and_refreshes_cached_files_with_backups(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job_id = str(uuid4())
            remote = root / 'remote' / job_id
            local = root / 'platform' / uuid4().hex
            remote.mkdir(parents=True)
            local.mkdir(parents=True)
            original = source(NUMBERS, COORDINATES)
            (remote / 'input.fchk').write_bytes(original)
            (remote / 'mayer.log').write_text(MAYER_LOG)
            result = {'descriptors': {'gap_eV': 4.2, 'E_scf_Ha': -123.456},
                      'methods': {'hirshfeld': {'status': 'success'}, 'mayer': {'status': 'failed', 'reason': 'Ti and O indices required for selected Mayer bonds'}},
                      'charges': {'3': {'hirshfeld': 0.4}, '2': {'hirshfeld': -0.2}, '4': {'hirshfeld': -0.3}},
                      'parameters': {'ti_index': 1}}
            state = {'status': 'completed', 'result': result, 'partial': True, 'failed_methods': ['mayer']}
            for path, data in [(remote / 'status.json', state), (remote / 'descriptors.json', result),
                               (local / 'job.json', dict(state, remote_id=job_id, ti_index=1)),
                               (local / 'descriptors.json', result)]:
                path.write_text(json.dumps(data))
            (remote / 'summary.csv').write_text('old remote csv')
            (local / 'summary.csv').write_text('old cached csv')
            with patch.object(extractor, 'run_mw', side_effect=AssertionError('must not recompute')):
                recovery.repair(UUID(job_id), root / 'remote', root / 'platform')
                self.assertTrue(json.loads((remote / 'status.json').read_text())['partial'])
                recovery.repair(job_id, root / 'remote', root / 'platform', apply=True)
            repaired = json.loads((local / 'job.json').read_text())
            self.assertFalse(repaired['partial'])
            self.assertEqual(repaired['failed_methods'], [])
            self.assertEqual(repaired['ti_index'], 3)
            self.assertEqual(repaired['result']['descriptors']['Ti_hirshfeld'], 0.4)
            self.assertEqual(repaired['result']['descriptors']['gap_eV'], 4.2)
            self.assertEqual((remote / 'input.fchk').read_bytes(), original)
            self.assertEqual((remote / 'mayer.log').read_text(), MAYER_LOG)
            self.assertEqual(json.loads((local / 'descriptors.json').read_text())['descriptors']['Mayer_Ti_O1'], 0.25)
            self.assertIn('Mayer_Ti_O1', (local / 'summary.csv').read_text())
            self.assertTrue(list((local / 'mayer_fix_backups').glob('*/job.json')))
            self.assertTrue(list((remote / 'mayer_fix_backups').glob('*/status.json')))


if __name__ == '__main__':
    unittest.main()
