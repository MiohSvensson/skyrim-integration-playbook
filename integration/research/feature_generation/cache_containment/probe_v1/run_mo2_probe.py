"""Launch only the D3D11 probe through the private debug MO2 instance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[4]
sys.path.insert(0, str(BASE / 'integration'))
from materialize import utc
from mo2_controls import normalize_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-name', default='pg_cache_probe_vfs_v1')
    args = parser.parse_args()
    assert args.task_name.replace('_', '').isalnum()
    report = json.loads((HERE / 'debug_mo2_manifest.json').read_text('utf-8'))
    debug_exe = HERE / 'mo2_debug_full/ModOrganizer.exe'
    assert hashlib.sha256(debug_exe.read_bytes()).hexdigest() == report['debug_exe_sha256']
    assert hashlib.sha256((BASE / 'UnifiedSkyrim/MO2/ModOrganizer.ini').read_bytes()).hexdigest() == report['original_config_sha256']
    assert 'log_level=0' in (HERE / 'mo2_debug_full/ModOrganizer.ini').read_text('utf-8-sig')
    profile = BASE / 'UnifiedSkyrim/profiles/Unified Build'
    task = BASE / 'UnifiedSkyrim/validation' / args.task_name
    task.mkdir(exist_ok=False)
    normalization = normalize_profile(profile, task / 'control_normalization')
    script = BASE / 'integration/logged_child.py'
    child = BASE / 'integration/research/feature_generation/cache_containment/probe_v1/pg_probe_child.py'
    command = [str(debug_exe), '--logs', '--profile', 'Unified Build', 'run',
               '--arguments', subprocess.list2cmdline([str(script), args.task_name, str(child)]), sys.executable]
    environment = os.environ.copy()
    for name in ['TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA']:
        directory = BASE / 'UnifiedSkyrim/sandbox' / name
        directory.mkdir(parents=True, exist_ok=True)
        environment[name] = str(directory)
    environment['PATH'] = str(BASE / 'UnifiedSkyrim/MO2') + os.pathsep + environment['PATH']
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    (task / 'command.json').write_text(json.dumps({'command': command, 'profile_control_normalization': normalization,
                                                   'game_not_selected': True, 'pg_not_selected': True}, indent=2) + '\n', encoding='utf-8')
    with (task / 'mo2_console.log').open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(command, cwd=debug_exe.parent, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        print(json.dumps({'pid': process.pid, 'task': str(task)}), flush=True)
        code = process.wait()
    bootstrap = json.loads((task / 'bootstrap_exit.json').read_text('utf-8'))
    (task / 'mo2_exit.json').write_text(json.dumps({'utc': utc(), 'return_code': code,
                                                     'child_return_code': bootstrap['return_code']}, indent=2) + '\n', encoding='utf-8')
    print('MO2 exit', code, 'child exit', bootstrap['return_code'], flush=True)
    if code or bootstrap['return_code']:
        raise RuntimeError('Private D3D11 probe failed')


if __name__ == '__main__':
    main()
