"""Independently verify only the VMAD object-format header changes."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
from plugin_binary import read, encode_subs

IDS = [0x03000881, 0x030008A7]
EXPECTED_MASTERS = ['Skyrim.esm', 'Dawnguard.esm', 'Dragonborn.esm', 'God of War.esp']


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}


def header(path, offset):
    data = Path(path).read_bytes()
    return data[offset + 16:offset + 24].hex()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--producer', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    candidate = Path(args.candidate).resolve(strict=True)
    if not candidate.is_relative_to(BASE / 'integration/research') and not candidate.is_relative_to(BASE / 'UnifiedSkyrim/mods'):
        raise ValueError('Candidate must be a research or private integration file')
    task = Path(args.producer).resolve(strict=True)
    mapping = json.loads((task / 'file_map.json').read_text('utf-8'))
    source = Path(mapping['God of War.esp']).resolve(strict=True)
    if sha(source) != '24916470123ad3cf8d4ac05fa7ee4d7b2eb2390f0a24733c94cdbc9440682e3b':
        raise ValueError('God of War source changed')
    source_masters, source_records = read(source)
    candidate_masters, candidate_records = read(candidate)
    assert source_masters == EXPECTED_MASTERS[:3]
    assert candidate_masters == EXPECTED_MASTERS
    assert len(candidate_records) == 3 and candidate_records[0]['flags'] & 0x200
    originals = {r['fid']: r for r in source_records if r['sig'] == 'MGEF' and r['fid'] in IDS}
    assert set(originals) == set(IDS)
    rows = []
    for record in candidate_records[1:]:
        assert record['sig'] == 'MGEF' and record['fid'] in originals
        source_record = originals[record['fid']]
        assert record['flags'] == source_record['flags']
        assert header(candidate, record['offset']) == header(source, source_record['offset'])
        source_fields = dict(source_record['fields'])
        candidate_fields = dict(record['fields'])
        assert list(source_fields) == list(candidate_fields)
        changed = []
        for tag, source_value in source_record['fields']:
            candidate_value = candidate_fields[tag]
            if tag != 'VMAD':
                assert candidate_value == source_value
                continue
            assert len(source_value) == len(candidate_value) == 63
            assert source_value[:2] == candidate_value[:2]
            assert source_value[4:] == candidate_value[4:]
            assert struct.unpack_from('<HHH', source_value, 0) == (0, 0, 1)
            assert struct.unpack_from('<HHH', candidate_value, 0) == (0, 2, 1)
            assert struct.unpack_from('<H', source_value, 36)[0] == 1
            name_length = struct.unpack_from('<H', candidate_value, 38)[0]
            assert candidate_value[40:40 + name_length] == b'CastSpellName'
            assert candidate_value[53] == 1 and candidate_value[54] == 1
            assert struct.unpack_from('<H', candidate_value, 55)[0] == 0
            assert struct.unpack_from('<h', candidate_value, 57)[0] == -1
            form_id = struct.unpack_from('<I', candidate_value, 59)[0]
            assert form_id == struct.unpack_from('<I', source_value, 59)[0]
            changed = [2, 3]
        rows.append({'signature': 'MGEF', 'raw_form_id': f'{record["fid"]:08X}',
                     'source_object_format': 0, 'candidate_object_format': 2,
                     'changed_offsets': changed, 'object_data_and_other_fields_preserved': True})
    assert len(rows) == 2
    report = {'status': 'BINARY_PASS_TYPED_RELOAD_REQUIRED', 'source': pin(source),
              'candidate': {**pin(candidate), 'records': rows, 'own_records': 0,
                            'masters': candidate_masters, 'script_semantics_preserved': True},
              'scope': 'Exactly two VMAD object-format header values change from 0 to 2; no spell reference, script flag, property, metadata or other payload changes.'}
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Report must stay in god_of_war_script_format')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'records': len(rows), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
