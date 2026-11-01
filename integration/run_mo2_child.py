"""Run a Database Python validation/producer through the new MO2 instance.

The command selects Python explicitly. It never selects SKSE or the game.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from materialize import BASE, TARGET, utc
from mo2_controls import normalize_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', default='Unified Skyrim', choices=['Unified Skyrim', 'Unified Build', 'FC Diagnostic', 'FC Diagnostic 2'])
    parser.add_argument('task_name')
    parser.add_argument('script')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.task_name.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Task name must be a simple identifier')
    script = Path(args.script).resolve(strict=True)
    if not (TARGET/'profiles'/args.profile/'modlist.txt').is_file():
        raise ValueError('Prepared integration profile required')
    if not script.is_relative_to(BASE/'integration') or script.suffix != '.py':
        raise ValueError('Only task-local Python children may be launched by this wrapper')
    task = TARGET/'validation'/args.task_name
    task.mkdir(parents=True, exist_ok=True)
    normalization = normalize_profile(TARGET/'profiles'/args.profile, task/'launch_control_normalization')
    arguments = [str((BASE/arg).resolve()) if arg.startswith(('integration/', 'integration\\')) else arg for arg in args.arguments]
    env = os.environ.copy()
    for name in ['TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA']:
        directory = TARGET/'sandbox'/name
        directory.mkdir(parents=True, exist_ok=True)
        env[name] = str(directory)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    exe = TARGET/'MO2/ModOrganizer.exe'
    command = [str(exe), '--logs', '--profile', args.profile, 'run',
               '--arguments', subprocess.list2cmdline([str(script)]+arguments), sys.executable]
    record = {'utc': utc(), 'command': command, 'child_script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
              'selected_program': sys.executable, 'game_not_selected': True,
              'profile_control_normalization': normalization}
    (task/'command.json').write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    with (task/'mo2_console.log').open('w', encoding='utf-8') as output:
        child = subprocess.Popen(command, cwd=exe.parent, env=env, stdout=output, stderr=subprocess.STDOUT)
        print(json.dumps({'pid': child.pid, 'task': str(task)}), flush=True)
        code = child.wait()
    child_code = None
    if script.name == 'logged_child.py':
        bootstrap = json.loads((task/'bootstrap_exit.json').read_text('utf-8'))
        child_code = bootstrap['return_code']
        if not isinstance(child_code, int) or isinstance(child_code, bool):
            raise ValueError('Logged child returned an invalid exit code')
    (task/'mo2_exit.json').write_text(json.dumps({'utc': utc(), 'return_code': code, 'child_return_code': child_code})+'\n', encoding='utf-8')
    print('MO2 exit', code, 'child exit', child_code, flush=True)
    sys.exit(code or (child_code or 0))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
