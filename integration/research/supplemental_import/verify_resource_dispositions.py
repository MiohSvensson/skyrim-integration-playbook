"""Bind raw source declarations to the typed consumer audit and explicit limitations."""
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


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    task = Path(args.task).resolve(strict=True)
    if not task.is_relative_to(BASE / 'UnifiedSkyrim/validation'):
        raise ValueError('Typed consumer task must be in the private validation tree')
    prepared = json.loads((task / 'prepared.json').read_text('utf-8'))
    result = json.loads((task / 'result.json').read_text('utf-8'))
    assert result['status'] == 'PASS' and result['usvfs'] and not result['timed_out']
    assert result['changed_input_plugins'] == result['changed_profile_controls'] == []
    assert result['native_loaded_context']['exact_order_match']
    assert result['native_loaded_context']['expected_profile_plugins'] == 1078
    assert result['native_loaded_context']['expected_native_entries'] == 1079
    assert prepared['pass_marker'] == 'RESOURCE_STATIC_CONSUMERS_PASS'
    assert result['xedit_exception'] is None
    inventory = json.loads((task / 'input_inventory.json').read_text('utf-8'))['plugins']
    paths = {row['name']: row['path'] for row in inventory}
    expected_plugin_sha = {
        'Glenmoril.esm': 'b1e649406bfebf9485db799d285b1620b07fe776394b32a03e291fa05e862761',
        'ForgottenCity.esp': '25e4dc1cf2763523bfec6ac3dcb08c83d4c1fe54be719865688c38122eda34f2',
    }
    for name, digest in expected_plugin_sha.items():
        assert sha(paths[name]) == digest and next(row for row in inventory if row['name'] == name)['sha256'] == digest
    masters, records = read(paths['Glenmoril.esm'])
    glen = {(r['sig'], r['fid']): r for r in records}
    masters, records = read(paths['ForgottenCity.esp'])
    fc = {(r['sig'], r['fid']): r for r in records}
    expected = [
        (glen, 'MATO', 0x0400C8CD, '296e7ea7e2768e3f3e19929dfec2fbe33a006e4a3803ea8c6e4db864b821672a'),
        (glen, 'ARMA', 0x0400F5DF, 'd3b1e34e5ff1ec03d77cc6994b10fde9a605f69d71a3273469969cfe7c4fb010'),
        (fc, 'SNDR', 0x010E2673, 'f348e3b881c7259bd84f8b8d191578b98d2f895b2dbcefc1cfceb0947faef87b'),
        (fc, 'INFO', 0x010C38B4, 'eb18701789cecc3fb7c8338729e8f33e57103852acb55cf7ef3cf22d6ab04f99'),
    ]
    raw = []
    for records, signature, form_id, digest in expected:
        record = records[(signature, form_id)]
        payload = encode_subs(record['fields'])
        assert hashlib.sha256(payload).hexdigest() == digest
        raw.append({'signature': signature, 'raw_form_id': f'{form_id:08X}', 'decompressed_payload_sha256': digest})
    fields = dict(glen[('MATO', 0x0400C8CD)]['fields'])
    assert fields['MODL'].rstrip(b'\0').decode().casefold() == 'shadertests\\shaderbox.nif'
    fields = dict(glen[('ARMA', 0x0400F5DF)]['fields'])
    assert fields['MOD3'].rstrip(b'\0').decode().casefold() == 'actors\\witchhunt\\etonnir\\dwarvensoldier.nif'
    fields = dict(fc[('SNDR', 0x010E2673)]['fields'])
    assert fields['ANAM'].rstrip(b'\0').decode().casefold() == 'data\\sound\\fx\\forgottencity\\fcarbitermotifsound.wav'
    responses = [value for tag, value in fc[('INFO', 0x010C38B4)]['fields']
                 if tag == 'TRDT' and len(value) >= 20 and struct.unpack_from('<I', value, 16)[0] == 0x010E2673]
    assert len(responses) == 1
    source_script = Path(prepared['source_script']).resolve(strict=True)
    assert sha(source_script) == prepared['source_script_sha256']
    grass_path = BASE / 'integration/research/lod_update/known_missing_grass.json'
    grass = json.loads(grass_path.read_text('utf-8'))
    assert grass['occurrences'] == 9 and grass['unique_canonical_GRAS'] == 4
    assert grass['status'] == 'EXACT_PREEXISTING_SOURCE_LIMIT_ALLOWLIST_NOT_REPAIRED'
    assert all(row['original_GRAS_payload_sha256'] == row['final_GRAS_payload_sha256'] and row['not_repaired'] for row in grass['entries'])
    moon_path = BASE / 'integration/research/feature_generation/moonstar_conversion/effective_bs82_contract.json'
    moon = json.loads(moon_path.read_text('utf-8'))
    assert sha(moon_path) == '0fa0b6f710fbf777af3eb3f1095c67649eb9295633e5fe63730480d3394d23a8'
    assert moon['status'] == 'EXACT_TWO_EFFECTIVE_ORIGINAL_BS82_FORMAT_EXCEPTIONS_NOT_REPAIRED'
    assert set(moon['profile_controls']) == {'plugins.txt', 'modlist.txt', 'loadorder.txt'}
    assert all(prepared['profile_controls'][name] == digest for name, digest in moon['profile_controls'].items())
    assert moon['CAO_result'].startswith('Only resaved stream82')
    report = {
        'schema': 'skyrim.bounded_resource_dispositions.v1',
        'status': 'STATIC_DISPOSITION_PASS_SOURCE_LIMITATIONS_NOT_REPAIRED',
        'typed_consumer_task': {'path': str(task), 'result_sha256': sha(task / 'result.json'),
                                'native_plugin_order_sha256': result['native_loaded_context']['order_sha256']},
        'consumer_script': pin(source_script),
        'raw_record_guards': raw,
        'source_limitations': [
            {'case': 'nine grass-source omissions', 'disposition': 'Retain only exact GRAS/world/LTEX omission contracts; never substitute similar models. Whole-world regeneration and final graph remain required.', 'evidence': pin(grass_path)},
            {'case': 'Glen female DwarvenSoldier.nif', 'disposition': 'Source female branch is unused by the current eight male NPC consumers and non-player race. Do not create a female alias; dynamic or future female use is not certified.', 'typed_consumers': 'RACE=1, MALE_NPC=8, FEMALE_NPC=0, playable race mask=0'},
            {'case': 'Glen shaderbox.nif MATO stub', 'disposition': 'Retain exact authored material payload and missing stock preview model; do not substitute a snow/sand mesh.', 'stock_evidence': pin(HERE / 'shaderbox_stock_material_evidence.json')},
            {'case': 'Forgotten City response motif', 'disposition': 'Exact response TRDT sound link and descriptor remain, but the authored motif WAV/XWM is unrepaired. Retain an explicit active source-audio limitation; do not synthesize or alias audio.', 'evidence': pin(HERE / 'new_feature_resource_gap_evidence.json')},
            {'case': 'Moon and Star BS82 meshes', 'disposition': 'Keep the two exact original BS82 meshes and reject CAO resaving. Their 35 LAND changes require whole-Tamriel grass/LOD handling, not a mesh conversion.', 'evidence': pin(moon_path)}
        ],
        'original_packs_modified': False,
        'game_launched': False,
        'no_alias_or_invented_asset': True,
        'required_next': 'Proceed to six-stage Synthesis. Recheck source limitations in final QEX, full VFS/resource closure and whole-world grass/LOD; this is not a zero-gap or in-game claim.'
    }
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Disposition report must stay in supplemental_import')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'raw_records': len(raw), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
