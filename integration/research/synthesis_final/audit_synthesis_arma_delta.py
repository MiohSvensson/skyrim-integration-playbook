"""Create a source-stable ARMA delta for the pinned six-stage Synthesis replay."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
from plugin_binary import read
from synthesis_arma_diff import delta, read_verified_stage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    replay_path = Path(args.replay).resolve(strict=True)
    replay = json.loads(replay_path.read_text('utf-8'))
    assert len(replay['stages']) == 6
    stage_pins = []
    for row in replay['stages']:
        path, _, _ = read_verified_stage(row, read)
        stage_pins.append({'index': row['index'], 'name': row['name'], 'path': str(path),
                           'sha256': row['output']['sha256'], 'verified': True})
    before = next(row for row in replay['stages'] if row['index'] == 2)
    after = next(row for row in replay['stages'] if row['index'] == 3)
    _, old_masters, old_records = read_verified_stage(before, read)
    _, new_masters, new_records = read_verified_stage(after, read)
    result = delta(old_masters, old_records, new_masters, new_records)
    candidate = Path(replay['final_plugin_candidate']['path']).resolve(strict=True)
    assert hashlib.sha256(candidate.read_bytes()).hexdigest() == replay['final_plugin_candidate']['sha256']
    assert not result['removed_source_records'], 'Armor patcher removed an existing ARMA source record'
    assert all(row['field'] in ('MOD2', 'MOD3') or row.get('new_override_record') for row in result['model_changes']), 'Unexpected first-person model change in an existing override'
    report = {'schema': 'skyrim.synthesis.arma_delta.v1',
              'status': 'ARMA_DELTA_READY_FOR_SCOPED_RUNTIME_AUDIT',
              'replay_result_sha256': hashlib.sha256(replay_path.read_bytes()).hexdigest(),
              'candidate': {'path': str(candidate), 'sha256': replay['final_plugin_candidate']['sha256']},
              'stage_outputs_verified': stage_pins,
              'identity': 'Case-folded source plugin name plus the original 24-bit record object ID; no raw load-order FormID comparison',
              'before_stage': before['name'], 'after_stage': after['name'],
              **result, 'game_launched': False,
              'scope': 'MOD2/MOD3 changes and every model in newly overridden ARMA records; inherited-only gaps remain separately inventoried'}
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Output must stay in synthesis_final')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'added_source_records': len(result['added_source_records']),
                      'changed_model_fields': len(result['model_changes']),
                      'affected_records': len(result['affected_source_keys']), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
