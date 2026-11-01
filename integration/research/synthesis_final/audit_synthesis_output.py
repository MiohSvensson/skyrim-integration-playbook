"""Validate a staged Synthesis candidate through the actual MO2 VFS."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from plugin_binary import read
import vfs_common as vfs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True)
    parser.add_argument('--diagnostic-receipt', required=True)
    parser.add_argument('--task', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual usvfs injection is required'
    replay_path = Path(args.replay).resolve(strict=True)
    replay = json.loads(replay_path.read_text('utf-8'))
    assert replay['status'] == 'REPLAY_COMPLETED_OUTPUT_NOT_DEPLOYED_NEEDS_SEMANTIC_AND_XEDIT_VALIDATION'
    assert len(replay['stages']) == 6 and all(row['return_code'] == 0 for row in replay['stages'])
    receipt_path = Path(args.diagnostic_receipt).resolve(strict=True)
    receipt = json.loads(receipt_path.read_text('utf-8'))
    assert receipt['status'] == 'DIAGNOSTIC_PROFILE_READY_NOT_PRODUCTION_INSTALLATION'
    task = Path(args.task).resolve(strict=True)
    result = json.loads((task / 'result.json').read_text('utf-8'))
    prepared = json.loads((task / 'prepared.json').read_text('utf-8'))
    assert result['status'] == 'PASS' and result['usvfs'] and not result['timed_out']
    assert result['changed_input_plugins'] == result['changed_profile_controls'] == []
    assert result['native_loaded_context']['exact_order_match']
    assert result['native_loaded_context']['expected_profile_plugins'] == 1080
    assert result['native_loaded_context']['expected_native_entries'] == 1081
    assert prepared['pass_marker'] == 'SYNTHESIS_NATIVE_CHECK_PASS'
    candidate = Path(receipt['candidate']['path']).resolve(strict=True)
    assert vfs.digest(candidate) == receipt['candidate']['sha256'] == replay['final_plugin_candidate']['sha256']
    assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / candidate.name) == vfs.file_identity(candidate)
    sidecar = Path(receipt['sidecar']['path']).resolve(strict=True)
    assert vfs.digest(sidecar) == receipt['sidecar']['sha256'] == replay['generated_sidecar']['sha256']
    assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data/skse/plugins/experience/races/generatedexperiencepatch.ini') == vfs.file_identity(sidecar)
    original_sidecar = Path(replay['prepared']['path']).parent / 'prepared.json'
    prepared_replay = json.loads(original_sidecar.read_text('utf-8'))
    original = Path(prepared_replay['private_sidecar']['path']).resolve(strict=True)
    assert replay['private_sidecar_restored'] and vfs.digest(original) == replay['original_sidecar_sha256']
    masters, records = read(candidate)
    included = {name.casefold() for name in prepared_replay['included_input_plugins']}
    assert all(master.casefold() in included for master in masters)
    assert len(masters) <= 253
    assert not (records[0]['flags'] & 0x200), 'Synthesis must remain a full plugin'
    for record in records[1:]:
        assert (record['fid'] >> 24) < len(masters), ('Own record outside allowed override scope', record['fid'])
    model_checks = []
    missing = []
    for record in records:
        if record['sig'] != 'ARMA':
            continue
        for tag, value in record['fields']:
            if tag not in ('MOD2', 'MOD3', 'MOD4', 'MOD5') or not value:
                continue
            path = vfs.asset_key(value.rstrip(b'\0').decode('utf-8'), kind='model')
            if not path:
                raise ValueError('Unsafe or unsupported ARMA model path: ' + value.decode('utf-8', errors='replace'))
            runtime = vfs.DEFAULT_TARGET / 'Game/Data' / path
            try:
                identity = vfs.file_identity(runtime)
            except OSError as exc:
                if getattr(exc, 'winerror', None) not in (2, 3):
                    raise
                missing.append({'record': f'{record["fid"]:08X}', 'field': tag, 'path': path})
                continue
            model_checks.append({'record': f'{record["fid"]:08X}', 'field': tag, 'path': path, 'file_id': identity})
    if missing:
        raise ValueError('Missing generated ARMA models: ' + json.dumps(missing))
    checked_log = (task / 'logs/xedit.log').read_text('utf-8-sig', errors='replace')
    assert f'SYNTHESIS_NATIVE_CHECKED|{len(records) - 1}|ERRORS=0' in checked_log
    assert 'SYNTHESIS_NATIVE_CHECK_PASS' in checked_log
    report = {
        'schema': 'skyrim.synthesis_candidate.validation.v1',
        'status': 'SYNTHESIS_CANDIDATE_STATIC_PASS_PENDING_INSTALLATION',
        'candidate': {'path': str(candidate), 'sha256': vfs.digest(candidate), 'bytes': candidate.stat().st_size,
                      'records': len(records) - 1, 'masters': len(masters), 'full_plugin': True, 'own_records': 0},
        'record_signatures': dict(collections.Counter(record['sig'] for record in records[1:])),
        'stages': [{'index': row['index'], 'name': row['name'], 'return_code': row['return_code'],
                    'output_sha256': row['output']['sha256']} for row in replay['stages']],
        'native_check': {'task': str(task), 'result_sha256': vfs.digest(task / 'result.json'),
                         'records': len(records) - 1, 'diagnostics': 0,
                         'native_plugin_order_sha256': result['native_loaded_context']['order_sha256']},
        'armor_model_references': model_checks,
        'armor_model_reference_count': len(model_checks),
        'sidecar': {'path': str(sidecar), 'sha256': vfs.digest(sidecar), 'original_restored': True,
                    'original_sha256': replay['original_sidecar_sha256']},
        'diagnostic_receipt_sha256': vfs.digest(receipt_path),
        'replay_result_sha256': vfs.digest(replay_path),
        'original_packs_modified': False, 'game_launched': False,
        'next': 'Install the reviewed generated plugin and captured sidecar with rollback, disable the temporary ZZ88 workspace, then repeat the actual VFS checks before acceptance.'
    }
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Validation report must stay in synthesis_final')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'records': len(records) - 1,
                      'masters': len(masters), 'model_references': len(model_checks), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
