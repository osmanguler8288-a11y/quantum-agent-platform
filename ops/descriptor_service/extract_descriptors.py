"""Linux adapter for the TiCl4 package. No Gaussian execution is performed."""
import argparse
import csv
import importlib.util
import json
import math
import os
import re
import subprocess
from pathlib import Path

from atom_selection import select_titanium, select_oxygens

FLOAT = r'[-+]?\d*\.?\d+(?:[DEde][-+]?\d+)?'
HARTREE_EV = 27.211386245988
BOHR_A = 0.529177210903
MW = Path(os.environ.get('MULTIWFN_DIR', '/opt/multiwfn/Multiwfn_2026.10.18_bin_Linux_noGUI'))
LEGACY = Path('/root/workspace/equiformer_v2/aeverything/06_skill_descriptor/scripts/compute_charges.py')


def number(value):
    value = float(value.replace('D', 'E').replace('d', 'e'))
    if not math.isfinite(value):
        raise ValueError('Non-finite input value')
    return value


def fchk_fields(path):
    lines = path.read_text(errors='replace').splitlines()
    fields = {}
    wanted = {'Number of atoms', 'Atomic numbers', 'Current cartesian coordinates',
              'Charge', 'Multiplicity', 'Number of alpha electrons', 'Number of beta electrons',
              'Total Energy', 'Alpha Orbital Energies', 'Beta Orbital Energies',
              'NPA Charges', 'Dipole Moment', 'Polarizability'}
    for i, line in enumerate(lines):
        key = line[:43].strip()
        if key not in wanted:
            continue
        tail = line[43:]
        size = re.search(r'N=\s*(\d+)', tail)
        if size:
            count = int(size.group(1))
            if count > 200000:
                raise ValueError('Input array exceeds supported size')
            values = []
            for following in lines[i + 1:]:
                if len(values) >= count:
                    break
                values.extend(number(token) for token in following.split())
            if len(values) != count:
                raise ValueError('Incomplete fchk array: ' + key)
            fields[key] = values
        else:
            tokens = tail.split()
            fields[key] = number(tokens[-1])
    if not 1 <= fields.get('Number of atoms', 0) <= 200:
        raise ValueError('fchk atom count must be between 1 and 200')
    return fields


def run_mw(directory, name, commands):
    settings = (MW / 'settings.ini').read_text()
    settings = re.sub(r'(?m)^\s*nthreads\s*=.*$', 'nthreads= 1', settings)
    settings = re.sub(r'(?m)^\s*isilent\s*=.*$', 'isilent= 1', settings)
    (directory / 'settings.ini').write_text(settings)
    env = dict(os.environ, Multiwfnpath=str(MW), OMP_STACKSIZE='64M', OMP_NUM_THREADS='1')
    log = directory / (name + '.log')
    with log.open('w') as output:
        proc = subprocess.run(
            [str(MW / 'Multiwfn_noGUI'), str(directory / 'input.fchk')],
            input=commands, text=True, stdout=output, stderr=subprocess.STDOUT,
            cwd=str(directory), env=env, timeout=600,
        )
    if proc.returncode:
        raise RuntimeError('Multiwfn exited unsuccessfully')
    return log.read_text(errors='replace')


def selected_geometry(fields, ti=0, oxygens=None):
    numbers = [int(v) for v in fields.get('Atomic numbers', [])]
    coords = fields.get('Current cartesian coordinates', [])
    natoms = int(fields['Number of atoms'])
    if len(numbers) != natoms or len(coords) != natoms * 3:
        raise ValueError('Incomplete atom identity or coordinates')
    ti = select_titanium(numbers, ti)
    oxygens = select_oxygens(numbers, coords, ti, oxygens)
    geometry = {'Ti_index': ti} if ti else {}
    if ti and oxygens:
        points = [coords[i:i+3] for i in range(0, len(coords), 3)]
        center = points[ti-1]
        vectors = [[a-b for a,b in zip(points[i-1],center)] for i in oxygens]
        lengths = [math.sqrt(sum(a*a for a in v)) for v in vectors]
        if min(lengths) <= 0:
            raise ValueError('Overlapping Ti/O coordinates')
        geometry.update({'O_indices': oxygens,
                         'Ti_O1_A': lengths[0] * BOHR_A, 'Ti_O2_A': lengths[1] * BOHR_A,
                         'O_Ti_O_deg': math.degrees(math.acos(max(-1,min(1,sum(a*b for a,b in zip(*vectors))/(lengths[0]*lengths[1])))))})
    return ti, oxygens, geometry


def parse_mayer_pairs(output, ti, oxygens):
    pairs = {}
    for match in re.finditer(r'(\d+)\s*\([A-Za-z]+\s*\)\s*-?\s*(\d+)\s*\([A-Za-z]+\s*\)\s*[:=]?\s*(' + FLOAT + ')', output):
        pairs[(int(match[1]), int(match[2]))] = number(match[3])
    selected = {}
    for index, oxygen in enumerate(oxygens, 1):
        value = pairs.get((ti, oxygen), pairs.get((oxygen, ti)))
        if value is None:
            raise ValueError('Selected Mayer bond not present in output')
        selected['Mayer_Ti_O' + str(index)] = value
    return selected


def extract(directory, ti=0, oxygens=None, methods=None):
    directory = Path(directory).resolve()
    result = {'engine': 'Gaussian output parsing + Multiwfn 2026.10.18 noGUI',
              'units': {'energy': 'Hartree', 'orbital_energy': 'eV', 'distance': 'angstrom',
                        'dipole': 'Debye', 'polarizability': 'bohr^3'},
              'descriptors': {}, 'methods': {}, 'warnings': []}
    desc = result['descriptors']
    fields = {}
    fchk = directory / 'input.fchk'
    natoms = None
    if fchk.exists():
        fields = fchk_fields(fchk)
        natoms = int(fields['Number of atoms'])
        desc['natoms'] = natoms
        desc['charge'] = fields.get('Charge')
        desc['multiplicity'] = fields.get('Multiplicity')
        desc['E_scf_Ha'] = fields.get('Total Energy')
        for spin, key, occupied in (
            ('alpha', 'Alpha Orbital Energies', 'Number of alpha electrons'),
            ('beta', 'Beta Orbital Energies', 'Number of beta electrons'),
        ):
            energies = fields.get(key, [])
            nocc = int(fields.get(occupied, 0))
            if 0 < nocc < len(energies):
                desc[spin + '_HOMO_eV'] = energies[nocc - 1] * HARTREE_EV
                desc[spin + '_LUMO_eV'] = energies[nocc] * HARTREE_EV
                desc[spin + '_gap_eV'] = (energies[nocc] - energies[nocc - 1]) * HARTREE_EV
        if 'Beta Orbital Energies' not in fields:
            for key in ('HOMO_eV', 'LUMO_eV', 'gap_eV'):
                if 'alpha_' + key in desc:
                    desc[key] = desc['alpha_' + key]
        if 'Dipole Moment' in fields:
            desc['dipole_D'] = math.sqrt(sum(v * v for v in fields['Dipole Moment'])) * 2.541746473
        if 'Polarizability' in fields:
            p = fields['Polarizability']
            if len(p) == 6:
                desc['polar_iso_bohr3'] = (p[0] + p[2] + p[5]) / 3
        ti, oxygens, geometry = selected_geometry(fields, ti, oxygens)
        desc.update(geometry)
    out = directory / 'input.out'
    if out.exists():
        text = out.read_text(errors='replace')
        result['gaussian_normal_termination'] = 'Normal termination' in text
        energies = re.findall(r'SCF Done:.*?=\s*(' + FLOAT + ')', text)
        if energies:
            energy = number(energies[-1])
            if desc.get('E_scf_Ha') is not None and abs(desc['E_scf_Ha'] - energy) > 1e-5:
                raise ValueError('out and fchk energies differ; upload files from the same calculation')
            desc['E_scf_Ha'] = energy
        dipoles = re.findall(r'X=\s*(' + FLOAT + r')\s+Y=\s*(' + FLOAT + r')\s+Z=\s*(' + FLOAT + r')\s+Tot=\s*(' + FLOAT + ')', text)
        if dipoles:
            desc['dipole_D'] = number(dipoles[-1][3])
        pol = re.findall(r'Isotropic polarizability.*?(' + FLOAT + r')\s+Bohr', text)
        if pol:
            desc['polar_iso_bohr3'] = number(pol[-1])
    if not fields and not desc:
        raise ValueError('No supported descriptors found')
    if 'polar_iso_bohr3' in desc:
        desc['polar_iso_A3'] = desc['polar_iso_bohr3'] * BOHR_A ** 3
    if not fields:
        result['warnings'].append('Only out provided: wavefunction analyses and fchk orbital parsing skipped')
    charges = {}
    npa = fields.get('NPA Charges', [])
    if len(npa) == natoms:
        charges['npa'] = {i+1:v for i,v in enumerate(npa)}
    if fields and methods:
        sequences = {}
        if any(method in methods for method in ('hirshfeld', 'cm5', 'chelpg')):
            spec = importlib.util.spec_from_file_location('legacy_charges', str(LEGACY))
            legacy = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(legacy)
            sequences = {
                'hirshfeld': ('7\n1\n1\nn\n0\nq\n', legacy.parse_hirshfeld),
                'cm5': ('7\n16\n1\nn\n0\nq\n', legacy.parse_cm5),
                'chelpg': ('7\n12\n1.7\n1\nn\n0\n0\nq\n', legacy.parse_chelpg),
            }
        for method in methods:
            try:
                if method in sequences:
                    commands, parser = sequences[method]
                    parsed = parser(run_mw(directory, method, commands))
                    if len(parsed) != natoms or not all(math.isfinite(v) for v in parsed.values()):
                        raise ValueError('Could not parse a complete charge table')
                    charges[method] = parsed
                    result['methods'][method] = {'status':'success','charge_sum':sum(parsed.values())}
                elif method == 'mayer':
                    if not ti or not oxygens:
                        result['methods'][method] = {'status': 'skipped', 'reason': '该结构不存在可分析的 Ti–O 原子对'}
                        continue
                    output = run_mw(directory, method, '9\n1\nn\n0\nq\n')
                    desc.update(parse_mayer_pairs(output, ti, oxygens))
                    result['methods'][method] = {'status':'success'}
                else:
                    raise ValueError('Unsupported method')
            except Exception as error:
                result['methods'][method] = {'status':'failed','reason':str(error) if isinstance(error,ValueError) else type(error).__name__}
    result['charges'] = {str(i):{method:table.get(i) for method,table in charges.items()} for i in range(1,(natoms or 0)+1)}
    if oxygens and ti:
        for label, index in [('Ti',ti),('O1',oxygens[0]),('O2',oxygens[1])]:
            for method, table in charges.items():
                desc[label + '_' + method] = table.get(index)
    result['parameters'] = {'ti_index':ti,'o_indices':oxygens,'chelpg_Ti_radius_A':1.7}
    result['warnings'].append('No binding energy calculated: compatible donor and TiCl4 reference calculations are required')
    (directory / 'descriptors.json').write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
    with (directory / 'summary.csv').open('w',newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['descriptor','value'])
        for key,value in desc.items():
            writer.writerow([key,json.dumps(value) if isinstance(value,list) else value])
    with (directory / 'charges.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=['atom_index']+list(charges))
        writer.writeheader()
        for i in range(1,(natoms or 0)+1):
            writer.writerow(dict(atom_index=i,**{name:table.get(i) for name,table in charges.items()}))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--ti',type=int,default=0)
    parser.add_argument('--o',type=int,nargs=2)
    parser.add_argument('--methods',default='hirshfeld,cm5,chelpg,mayer')
    args = parser.parse_args()
    extract(args.directory,args.ti,args.o,[m for m in args.methods.split(',') if m])
