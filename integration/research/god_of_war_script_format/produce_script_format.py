"""Produce two exact MGEF overrides through MO2 without normalizing source fields."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
TARGET = BASE / 'UnifiedSkyrim'
sys.path.insert(0, str(BASE / 'integration'))
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
sys.path.insert(0, str(BASE / 'rootcause'))
import runtime_inventory as runtime
import vfs_common as vfs
from plugin_binary import read, encode_subs

IDS = {0x03000881, 0x030008A7}
SOURCE_SHA = '24916470123ad3cf8d4ac05fa7ee4d7b2eb2390f0a24733c94cdbc9440682e3b'
MARKER = 'GOW_SCRIPT_FORMAT_PRODUCER_PASS'
CONTROL_NAMES = ['modlist.txt', 'plugins.txt', 'loadorder.txt', 'Skyrim.ini', 'SkyrimCustom.ini',
                 'skyrimprefs.ini', 'initweaks.ini', 'archives.txt', 'settings.ini']


def sha(path):
    with open(vfs.lp(path), 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def controls(profile):
    return {name: sha(profile / name) for name in CONTROL_NAMES if (profile / name).is_file()}


def serialize(source, source_records):
    data = source.read_bytes()
    tes4_fields = dict(source_records[0]['fields'])
    version = struct.unpack_from('<f', tes4_fields['HEDR'], 0)[0]
    masters = read(source)[0] + ['God of War.esp']
    fields = [('HEDR', struct.pack('<fII', version, 2, 0))]
    fields.extend(('MAST', name.encode('utf-8') + b'\0') for name in masters)
    payload = encode_subs(fields)
    header = bytearray(data[:24])
    struct.pack_into('<I', header, 4, len(payload))
    struct.pack_into('<I', header, 8, header[8] | 0x200)
    output = bytearray(header + payload)
    records = []
    for record in source_records:
        if record['sig'] != 'MGEF' or record['fid'] not in IDS:
            continue
        body = bytearray(encode_subs(record['fields']))
        position = 0
        for tag, value in record['fields']:
            if tag == 'XXXX':
                position += 8
                continue
            if tag == 'VMAD':
                assert struct.unpack_from('<H', body, position + 8)[0] == 0
                struct.pack_into('<H', body, position + 8, 2)
            position += 6 + len(value)
        assert position == len(body)
        if record['flags'] & 0x40000:
            body = struct.pack('<I', len(body)) + zlib.compress(body)
        record_header = bytearray(data[record['offset']:record['offset'] + 24])
        struct.pack_into('<I', record_header, 4, len(body))
        records.append(bytes(record_header + body))
    assert len(records) == 2
    group_offset = next(r for r in source_records if r['sig'] == 'MGEF' and r['fid'] in IDS)['groups'][0][2]
    group = bytearray(data[group_offset:group_offset + 24])
    struct.pack_into('<I', group, 4, 24 + sum(map(len, records)))
    output.extend(group)
    for record in records:
        output.extend(record)
    return bytes(output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--candidate', required=True)
    args = parser.parse_args()
    task = Path(args.task).resolve()
    candidate = Path(args.candidate).resolve()
    if not task.is_relative_to(TARGET / 'validation') or (task / 'prepared.json').exists() or (task / 'result.json').exists():
        raise ValueError('Use a fresh task under UnifiedSkyrim/validation')
    if not candidate.is_relative_to(HERE) or candidate.exists():
        raise ValueError('Use a fresh candidate in god_of_war_script_format')
    if not vfs.injected():
        raise RuntimeError('Actual usvfs injection is required')
    if shutil.disk_usage(BASE).free < 32 * 1024**3 + 1024**2:
        raise RuntimeError('Disk reserve would be crossed')
    profile = TARGET / 'profiles/Unified Build'
    runtime.PROFILE = profile
    inventory = runtime.inventory()
    assert not inventory['missing_plugins'] and not inventory['missing_masters'] and inventory['within_slot_limits']
    assert len(inventory['plugins']) == 1078
    before_controls = controls(profile)
    for row in inventory['plugins']:
        assert sha(row['path']) == row['sha256'], row['name']
    source_row = next(row for row in inventory['plugins'] if row['name'] == 'God of War.esp')
    source = TARGET / 'Game/Data/God of War.esp'
    assert vfs.file_identity(source) == vfs.file_identity(source_row['path'])
    assert sha(source) == source_row['sha256'] == SOURCE_SHA
    (task / 'logs').mkdir(parents=True)
    (task / 'input_inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (task / 'file_map.json').write_text(json.dumps({row['name']: row['path'] for row in inventory['plugins']}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    script = Path(__file__).resolve()
    prepared = {'schema': 'skyrim.binary_vfs_producer.v1', 'source_script': str(script), 'source_script_sha256': sha(script),
                'script': str(script), 'script_sha256': sha(script), 'pass_marker': MARKER,
                'patch_name': candidate.name, 'candidate': str(candidate), 'profile': str(profile),
                'profile_controls': before_controls, 'game_not_selected': True,
                'context_plugins': len(inventory['plugins']), 'producer_kind': 'bounded raw VMAD writer inside actual MO2 VFS'}
    (task / 'prepared.json').write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    masters, records = read(source)
    assert masters == ['Skyrim.esm', 'Dawnguard.esm', 'Dragonborn.esm']
    candidate.parent.mkdir(parents=True, exist_ok=True)
    with candidate.open('xb') as stream:
        stream.write(serialize(source, records))
    candidate_sha = sha(candidate)
    for row in inventory['plugins']:
        assert sha(row['path']) == row['sha256'], row['name']
    assert sha(source) == SOURCE_SHA and controls(profile) == before_controls
    log = task / 'logs/xedit.log'
    log.write_text('Bounded raw VMAD writer inside actual MO2 VFS; no xEdit field normalization.\n' + MARKER + '\n', encoding='utf-8')
    result = {'status': 'PASS', 'usvfs': True, 'return_code': 0, 'timed_out': False,
              'pass_marker': MARKER, 'marker_seen': True, 'log_sha256': sha(log),
              'candidate_sha256': candidate_sha, 'changed_input_plugins': [], 'changed_profile_controls': [],
              'native_loaded_context': {'kind': 'MO2 inventory, not an xEdit module-loader claim',
                                        'expected_profile_plugins': len(inventory['plugins']),
                                        'input_sha_verified': True},
              'producer_kind': prepared['producer_kind'], 'module_selection_confirmation': False,
              'source_sha256': SOURCE_SHA, 'own_records': 0, 'format_changes': 2}
    (task / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
