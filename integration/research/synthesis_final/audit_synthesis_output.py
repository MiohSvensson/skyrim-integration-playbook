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
    parser.add_argument('--arma-delta', required=True)
    parser.add_argument('--input-models', required=True)
    parser.add_argument('--production-receipt')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual usvfs injection is required'
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Validation report must stay in synthesis_final')
    replay_path = Path(args.replay).resolve(strict=True)
    replay = json.loads(replay_path.read_text('utf-8'))
    assert replay['status'] == 'REPLAY_COMPLETED_OUTPUT_NOT_DEPLOYED_NEEDS_SEMANTIC_AND_XEDIT_VALIDATION'
    assert len(replay['stages']) == 6 and all(row['return_code'] == 0 for row in replay['stages'])
    receipt_path = Path(args.diagnostic_receipt).resolve(strict=True)
    receipt = json.loads(receipt_path.read_text('utf-8'))
    assert receipt['status'] == 'DIAGNOSTIC_PROFILE_READY_NOT_PRODUCTION_INSTALLATION'
    delta_path = Path(args.arma_delta).resolve(strict=True)
    armor_delta = json.loads(delta_path.read_text('utf-8'))
    assert armor_delta['schema'] == 'skyrim.synthesis.arma_delta.v1'
    assert armor_delta['status'] == 'ARMA_DELTA_READY_FOR_SCOPED_RUNTIME_AUDIT'
    assert armor_delta['replay_result_sha256'] == vfs.digest(replay_path)
    assert armor_delta['candidate']['sha256'] == replay['final_plugin_candidate']['sha256']
    assert not armor_delta['removed_source_records']
    affected = set(armor_delta['affected_source_keys'])
    task = Path(args.task).resolve(strict=True)
    result = json.loads((task / 'result.json').read_text('utf-8'))
    prepared = json.loads((task / 'prepared.json').read_text('utf-8'))
    assert result['status'] == 'PASS' and result['usvfs'] and not result['timed_out']
    assert result['changed_input_plugins'] == result['changed_profile_controls'] == []
    assert result['native_loaded_context']['exact_order_match']
    assert result['native_loaded_context']['expected_profile_plugins'] == 1080
    assert result['native_loaded_context']['expected_native_entries'] == 1081
    assert prepared['pass_marker'] in {'SYNTHESIS_NATIVE_CHECK_PASS', 'SYNTHESIS_RELOAD_TYPED_PASS'}
    candidate = Path(receipt['candidate']['path']).resolve(strict=True)
    assert vfs.digest(candidate) == receipt['candidate']['sha256'] == replay['final_plugin_candidate']['sha256']
    sidecar = Path(receipt['sidecar']['path']).resolve(strict=True)
    assert vfs.digest(sidecar) == receipt['sidecar']['sha256'] == replay['generated_sidecar']['sha256']
    production_receipt = None
    if args.production_receipt:
        production_path = Path(args.production_receipt).resolve(strict=True)
        production_receipt = json.loads(production_path.read_text('utf-8'))
        assert production_receipt['status'] == 'INSTALLED_PENDING_FRESH_TYPED_RELOAD'
        assert production_receipt['accepted'] is False
        assert production_receipt['candidate_name'] == candidate.name
        assert production_receipt['candidate_sha256'] == receipt['candidate']['sha256']
        assert prepared['profile'].endswith('Unified Build')
        plugin_row, sidecar_row = production_receipt['files'][:2]
        installed_plugin = Path(plugin_row['path']).resolve(strict=True)
        installed_sidecar = Path(sidecar_row['path']).resolve(strict=True)
        assert installed_plugin.name == candidate.name and vfs.digest(installed_plugin) == plugin_row['sha256'] == receipt['candidate']['sha256']
        assert installed_sidecar.name == 'GeneratedExperiencePatch.ini' and vfs.digest(installed_sidecar) == sidecar_row['sha256'] == receipt['sidecar']['sha256']
        assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / candidate.name) == vfs.file_identity(installed_plugin)
        assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data/skse/plugins/experience/races/generatedexperiencepatch.ini') == vfs.file_identity(installed_sidecar)
    else:
        assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / candidate.name) == vfs.file_identity(candidate)
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
    from synthesis_source_models import SourceModels, origin
    from synthesis_input_models import load_verified
    input_fields, input_report = load_verified(args.input_models, delta_path, vfs.digest)
    source_models = SourceModels(None, None, input_fields=input_fields)
    model_checks = []
    missing = []
    seen_affected = set()
    for record in records:
        if record['sig'] != 'ARMA':
            continue
        key = f'{masters[record["fid"] >> 24].casefold()}:{record["fid"] & 0xffffff:06X}'
        source_fields = None
        if key in affected:
            seen_affected.add(key)
            source_fields = source_models.fields_for(masters, record)
        for tag, value in record['fields']:
            if tag not in ('MOD2', 'MOD3', 'MOD4', 'MOD5') or not value:
                continue
            source_origin = origin(source_fields, tag, value) if source_fields is not None else 'outside_synthesis_scope'
            path = vfs.asset_key(value.rstrip(b'\0').decode('utf-8'), kind='model')
            if not path:
                raise ValueError('Unsafe or unsupported ARMA model path: ' + value.decode('utf-8', errors='replace'))
            runtime = vfs.DEFAULT_TARGET / 'Game/Data' / path
            try:
                identity = vfs.file_identity(runtime)
            except OSError as exc:
                if getattr(exc, 'winerror', None) not in (2, 3):
                    raise
                missing.append({'source_key': key, 'record': f'{record["fid"]:08X}', 'field': tag, 'path': path, 'origin': source_origin})
                continue
            if key in affected:
                model_checks.append({'source_key': key, 'record': f'{record["fid"]:08X}', 'field': tag, 'path': path, 'origin': source_origin, 'file_id': identity})
    assert seen_affected == affected, 'Final candidate lost an affected ARMA source record'
    checked_log = (task / 'logs/xedit.log').read_text('utf-8-sig', errors='replace')
    assert f'SYNTHESIS_NATIVE_CHECKED|{len(records) - 1}|ERRORS=0' in checked_log
    assert 'SYNTHESIS_NATIVE_CHECK_PASS' in checked_log and prepared['pass_marker'] in checked_log
    generated_missing = [row for row in missing if row['origin'] == 'changed_by_synthesis']
    inherited_missing = [row for row in missing if row['origin'] != 'changed_by_synthesis']
    common = {
        'candidate': {'path': str(candidate), 'sha256': vfs.digest(candidate), 'bytes': candidate.stat().st_size,
                      'records': len(records) - 1, 'masters': len(masters), 'full_plugin': True, 'own_records': 0},
        'native_check': {'task': str(task), 'result_sha256': vfs.digest(task / 'result.json'),
                         'records': len(records) - 1, 'diagnostics': 0,
                         'native_plugin_order_sha256': result['native_loaded_context']['order_sha256']},
        'affected_arma_record_count': len(affected),
        'available_affected_model_reference_count': len(model_checks),
        'generated_missing_references': generated_missing,
        'inherited_missing_reference_count': len(inherited_missing),
        'inherited_missing_references': inherited_missing,
        'arma_delta_sha256': vfs.digest(delta_path),
        'input_models': {'path': str(Path(args.input_models).resolve()), 'sha256': vfs.digest(args.input_models),
                         'native_task': input_report['native_task']},
        'diagnostic_receipt_sha256': vfs.digest(receipt_path),
        'replay_result_sha256': vfs.digest(replay_path),
        'production_receipt': {'path': str(Path(args.production_receipt).resolve()),
                               'sha256': vfs.digest(args.production_receipt)} if production_receipt else None,
        'original_packs_modified': False, 'game_launched': False
    }
    if generated_missing:
        report = {'schema': 'skyrim.synthesis_candidate.generated_arma_resource_blocker.v1',
                  'status': 'SYNTHESIS_GENERATED_ARMA_RESOURCE_BLOCKER', **common,
                  'scope': 'Generated ARMA dependencies block installation; inherited-only gaps require separate final disposition'}
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        raise ValueError('Missing generated ARMA models; see ' + str(output))
    report = {
        'schema': 'skyrim.synthesis_candidate.validation.v2',
        'status': 'SYNTHESIS_INSTALLED_SCOPED_STATIC_PASS_PENDING_ACCEPTANCE' if production_receipt else 'SYNTHESIS_CANDIDATE_SCOPED_STATIC_PASS_PENDING_INSTALLATION', **common,
        'record_signatures': dict(collections.Counter(record['sig'] for record in records[1:])),
        'stages': [{'index': row['index'], 'name': row['name'], 'return_code': row['return_code'],
                    'output_sha256': row['output']['sha256']} for row in replay['stages']],
        'armor_model_references': model_checks,
        'sidecar': {'path': str(sidecar), 'sha256': vfs.digest(sidecar), 'original_restored': True,
                    'original_sha256': replay['original_sidecar_sha256']},
        'next': 'Run Synthesis acceptance and final consumer/resource disposition; inherited gaps remain open.' if production_receipt else 'Install the reviewed plugin and captured sidecar, then repeat native and actual VFS checks. Inherited-only gaps still require final consumer/resource disposition.'
    }
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'records': len(records) - 1,
                      'masters': len(masters), 'affected_model_references': len(model_checks),
                      'inherited_missing_references': len(inherited_missing), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
