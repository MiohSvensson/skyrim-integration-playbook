"""Independently re-evaluate a completed native xEdit context; never installs a candidate."""
import argparse
import json
from pathlib import Path

from materialize import TARGET, sha, utc
import native_xedit_context


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('task')
    parser.add_argument('--output', default='native_context_review.json')
    args = parser.parse_args()
    task = Path(args.task).resolve(strict=True)
    if not task.is_relative_to(TARGET / 'validation'):
        raise ValueError('Task must be under the private validation directory')
    prepared = json.loads((task / 'prepared.json').read_text('utf-8'))
    inputs = json.loads((task / 'input_inventory.json').read_text('utf-8'))
    result = json.loads((task / 'result.json').read_text('utf-8'))
    context = native_xedit_context.evaluate(task, prepared, inputs, task / 'logs/xedit.log')
    unchanged_inputs = [r['name'] for r in inputs['plugins'] if sha(r['path']) != r['sha256']]
    changed_controls = [name for name, expected in prepared.get('profile_controls', {}).items()
                        if sha(Path(prepared['profile']) / name) != expected]
    passed = (result.get('return_code') == 0 and context['exact_order_match'] and
              context['script_done_marker_seen'] and context['marker_seen'] and
              not unchanged_inputs and not changed_controls)
    report = {'utc': utc(), 'status': 'NATIVE_CONTEXT_PASS' if passed else 'NATIVE_CONTEXT_FAIL',
              'task': str(task), 'native_context': context, 'changed_input_plugins': unchanged_inputs,
              'changed_profile_controls': changed_controls, 'process_return_code': result.get('return_code'),
              'prior_result_status': result.get('status'), 'prior_result_sha256': sha(task / 'result.json'),
              'evaluator_sha256': sha(native_xedit_context.__file__), 'reviewer_sha256': sha(__file__),
              'scope': 'Diagnostic native-context review only. No candidate installation or in-game acceptance.',
              'game_launched': False}
    if Path(args.output).name != args.output or not args.output.endswith('.json'):
        raise ValueError('Review output must be a JSON filename inside the task')
    output = task / args.output
    if output.exists():
        raise FileExistsError('Preserve prior review; use a new review filename or task')
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == '__main__':
    raise SystemExit(main())
