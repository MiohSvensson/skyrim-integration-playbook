"""Bind the native pre-Synthesis model context to the exact candidate and delta."""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    parser.add_argument('--arma-delta', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    import hashlib
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    task = Path(args.task).resolve(strict=True)
    delta_path = Path(args.arma_delta).resolve(strict=True)
    delta = json.loads(delta_path.read_text('utf-8'))
    result_path = task / 'result.json'
    log_path = task / 'logs/xedit.log'
    result = json.loads(result_path.read_text('utf-8'))
    prepared = json.loads((task / 'prepared.json').read_text('utf-8'))
    assert result['status'] == 'PASS' and result['return_code'] == 0 and result['usvfs'] and not result['timed_out']
    assert result['native_loaded_context']['exact_order_match']
    assert result['native_loaded_context']['expected_profile_plugins'] == 1079
    assert result['native_loaded_context']['expected_native_entries'] == 1080
    assert result['changed_input_plugins'] == result['changed_profile_controls'] == []
    assert prepared['pass_marker'] == 'SYNTHESIS_INPUT_MODELS_COMPLETE'
    assert prepared['profile'].endswith('Unified Build')
    assert digest(log_path) == result['log_sha256']
    log = log_path.read_text('utf-8-sig', errors='replace')
    assert 'SYNTHESIS_INPUT_NO_SYNTHESIS' in log and 'SYNTHESIS_INPUT_MODELS_COMPLETE' in log
    fields = {}
    for line in log.splitlines():
        if not line.startswith('SYNTHESIS_INPUT_MODEL|'):
            continue
        _, key, tag, value = line.split('|', 3)
        fields.setdefault(key, {})[tag] = value
    expected = set(delta['affected_source_keys'])
    assert set(fields) == expected and all(set(row) == {'MOD2', 'MOD3', 'MOD4', 'MOD5'} for row in fields.values())
    report = {'schema': 'skyrim.synthesis.input_models.v1', 'status': 'INPUT_MODEL_CONTEXT_VERIFIED',
              'candidate_sha256': delta['candidate']['sha256'], 'arma_delta_sha256': digest(delta_path),
              'profile': prepared['profile'], 'source_key_count': len(fields),
              'model_field_count': sum(len(row) for row in fields.values()), 'source_fields': fields,
              'native_task': str(task), 'native_result_sha256': digest(result_path),
              'native_log_sha256': digest(log_path), 'native_prepared_sha256': digest(task / 'prepared.json'),
              'input_inventory_sha256': digest(task / 'input_inventory.json'),
              'synthesis_not_loaded': True, 'game_launched': False}
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Input model report must stay in synthesis_final')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'source_records': len(fields), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
