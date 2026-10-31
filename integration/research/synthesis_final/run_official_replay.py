"""MO2-only sequential replay of pinned original patcher DLLs; no GUI or game."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from vfs_common import injected, file_identity, controls, plugin_header, owned_id_range
from catalogue_official_replay import sha, pin


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def assert_absent_through_win32(path):
    try:
        identity = file_identity(path)
    except OSError as ex:
        if getattr(ex, 'winerror', None) in (2, 3):
            return
        raise
    raise AssertionError(('Must not permit Experience deletion of an existing file', str(path), identity))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', required=True)
    a = p.parse_args()
    prepared_path = Path(a.prepared).resolve(strict=True)
    assert prepared_path.is_relative_to(OWN / 'runs') and prepared_path.name == 'prepared.json'
    config = json.loads(prepared_path.read_text(encoding='utf-8'))
    root = Path(config['job_root']).resolve()
    assert root == prepared_path.parent and root.is_relative_to(OWN / 'runs')
    result_path = root / 'result.json'
    assert not result_path.exists() and not (root / 'started.json').exists(), 'Each prepared replay is single-use'
    assert config['schema'] == 'skyrim.prepared_official_synthesis_replay.v1'
    assert injected(), 'Actual MO2 Python child usvfs_x64.dll injection is mandatory'
    assert sha(__file__) == config['runner']['sha256']
    target, profile = Path(config['target']), Path(config['profile'])
    assert target.resolve() == (BASE / 'UnifiedSkyrim').resolve()
    data = Path(config['data_path'])
    assert data.resolve() == (target / 'Game/Data').resolve()
    assert controls(target, profile) == config['control_hashes']
    for name in ('catalogue', 'expectations', 'plugins_file', 'seed'):
        assert sha(config[name]['path']) == config[name]['sha256'], name
    catalogue = json.loads(Path(config['catalogue']['path']).read_text(encoding='utf-8'))
    assert len(config['stages']) == len(catalogue['drivers']) == 6
    assert 'synthesis.esp' not in {n.lower() for n in config['included_input_plugins']}
    for driver in catalogue['drivers']:
        for entry in driver['compiled_runtime_files'] + [driver['Build_meta']]:
            assert sha(entry['path']) == entry['sha256'], entry['path']
    assert sha(catalogue['dotnet_host']['path']) == catalogue['dotnet_host']['sha256']
    for plugin in config['input_plugins']:
        assert sha(data / plugin['name']) == plugin['sha256'], ('VFS input SHA', plugin['name'])
    side = config['private_sidecar']
    private = Path(side['path']).resolve(strict=True)
    assert private.is_relative_to((target / 'mods').resolve()) and private.stat().st_nlink == 1
    assert private.stat().st_size <= 1024 * 1024 and sha(private) == side['sha256']
    runtime_side = data / side['relative_path']
    original_identity = file_identity(private)
    assert file_identity(runtime_side) == original_identity and sha(runtime_side) == side['sha256']
    dummy_name = 'deleteThisEspIfYouSeeIt-itsEmpty.esp'
    assert config['experience_dummy_absence']['expectation_files_table_checked_absent']
    assert_absent_through_win32(data / dummy_name)
    assert_absent_through_win32(Path(root.anchor) / dummy_name)
    backup = root / 'sidecar_backup.bin'
    assert not backup.exists()
    original = private.read_bytes()
    backup.write_bytes(original)
    before_stat = private.stat()
    started = {'utc': utc(), 'usvfs_x64_injected': True, 'pid': os.getpid(),
        'prepared': pin(prepared_path), 'private_sidecar_original_identity': original_identity,
        'private_sidecar_backup': pin(backup)}
    write(root / 'started.json', started)
    env = os.environ.copy()
    env.update({'DOTNET_ROOT': str(BASE / 'tools/dotnet'), 'DOTNET_ROLL_FORWARD': 'Major',
        'DOTNET_CLI_TELEMETRY_OPTOUT': '1', 'DOTNET_NOLOGO': '1'})
    for variable, folder in {'DOTNET_CLI_HOME': 'cache/dotnet_home', 'NUGET_PACKAGES': 'cache/nuget',
        'NUGET_HTTP_CACHE_PATH': 'cache/nuget_http', 'TEMP': 'cache/temp', 'TMP': 'cache/temp',
        'APPDATA': 'cache/appdata', 'LOCALAPPDATA': 'cache/localappdata',
        'DOTNET_BUNDLE_EXTRACT_BASE_DIR': 'cache/bundles'}.items():
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        env[variable] = str(path)
    env['PATH'] = str(BASE / 'tools/dotnet') + os.pathsep + env.get('PATH', '')
    rows = []
    errors = []
    generated_sidecar = None
    restored = False
    process = None
    def restore():
        nonlocal restored
        assert private.stat().st_nlink == 1 and file_identity(runtime_side) == file_identity(private)
        with private.open('wb') as stream:
            stream.write(original)
            stream.flush()
            os.fsync(stream.fileno())
        os.utime(private, ns=(before_stat.st_atime_ns, before_stat.st_mtime_ns))
        assert sha(private) == side['sha256'] == sha(runtime_side)
        restored = True
    try:
        for stage, driver in zip(config['stages'], catalogue['drivers']):
            assert stage['index'] == driver['index'] and stage['name'] == driver['name']
            output = Path(stage['output'])
            source = Path(stage['source'])
            assert output.is_relative_to(root / 'output') and not output.exists()
            assert list(output.parent.iterdir()) == []
            assert source.is_relative_to(root) and source.is_file()
            for setting in stage['settings_pins']:
                assert sha(setting['path']) == setting['sha256']
            source_before = pin(source)
            command = stage['argv']
            assert command[0] == catalogue['dotnet_host']['path']
            replacements = {'{DATA_PATH}': str(data), '{EXTRA_DATA}': stage['extra_data'],
                '{LOAD_ORDER}': config['plugins_file']['path'], '{OUTPUT}': str(output), '{SOURCE}': str(source)}
            assert command == [replacements.get(x, x) for x in driver['replay_argv_template']]
            log = root / f'{stage["index"]:02d}-{stage["name"]}.log'
            print('Official Synthesis DLL stage', stage['index'], '/', 6, stage['name'], flush=True)
            beginning = time.monotonic()
            with log.open('wb') as stream:
                process = subprocess.Popen(command, cwd=root / 'work', env=env, stdout=stream, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                write(root / 'current_process.json', {'stage': stage['index'], 'name': stage['name'], 'pid': process.pid, 'argv': command, 'log': str(log)})
                code = process.wait()
            row = {'index': stage['index'], 'name': stage['name'], 'return_code': code,
                'seconds': round(time.monotonic() - beginning, 3), 'source': source_before, 'log': pin(log)}
            rows.append(row)
            assert sha(source) == source_before['sha256'], 'A driver modified the preceding fresh output/source'
            assert code == 0, ('Original patcher failed', stage['name'], code)
            assert output.is_file(), ('No stage output', stage['name'])
            emitted = [x for x in output.parent.iterdir() if x.is_file() and x.suffix.lower() in ('.esp', '.esm', '.esl')]
            assert emitted == [output], ('Unexpected split output needs review before older-driver chaining', [str(x) for x in emitted])
            header = plugin_header(output)
            row['output'] = {**pin(output), **header, 'owned_id_range': owned_id_range(output, len(header['masters']), header['is_light'])}
            assert row['output']['owned_id_range']['light_owned_id_range_valid']
            missing = [m for m in header['masters'] if m.lower() not in {n.lower() for n in config['included_input_plugins']}]
            assert not missing, ('Generated master outside the frozen included context', missing)
            if stage['experience_side_effect']:
                assert sha(output) == source_before['sha256'], 'Experience is an INI-only driver; its source payload must remain byte-identical, as in the official GUI artifact'
                assert file_identity(runtime_side) == file_identity(private)
                capture = Path(config['final_sidecar_candidate'])
                capture.parent.mkdir(parents=True, exist_ok=True)
                assert not capture.exists()
                payload = private.read_bytes()
                assert payload and len(payload) <= 1024 * 1024
                capture.write_bytes(payload)
                generated_sidecar = pin(capture)
                restore()
            elif sha(private) != side['sha256']:
                raise AssertionError(('Unexpected sidecar writer outside the Experience stage', stage['name']))
            write(root / 'stage_results.json', rows)
        for plugin in config['input_plugins']:
            assert sha(data / plugin['name']) == plugin['sha256'], ('Input plugin changed during replay', plugin['name'])
        assert controls(target, profile) == config['control_hashes']
    except BaseException as ex:
        if process is not None and process.poll() is None:
            process.terminate()
            process.wait()
        errors.append({'kind': 'official_replay_failed', 'error': repr(ex), 'traceback': traceback.format_exc()})
    finally:
        try:
            restore()
        except Exception as ex:
            restored = False
            errors.append({'kind': 'private_sidecar_restoration_failed', 'error': repr(ex), 'backup': str(backup), 'private': str(private)})
    for driver in catalogue['drivers']:
        for entry in driver['compiled_runtime_files'] + [driver['Build_meta']]:
            if sha(entry['path']) != entry['sha256']:
                errors.append({'kind': 'compiled_driver_or_metadata_modified', 'path': entry['path']})
    result = {'utc': utc(), 'status': 'FAIL' if errors else 'REPLAY_COMPLETED_OUTPUT_NOT_DEPLOYED_NEEDS_SEMANTIC_AND_XEDIT_VALIDATION',
        'usvfs_x64_injected': injected(), 'prepared': pin(prepared_path), 'stages': rows,
        'input_plugins_checked': len(config['input_plugins']), 'included_gameplay_input_plugins': len(config['included_input_plugins']),
        'private_sidecar_restored': restored, 'original_sidecar_sha256': side['sha256'],
        'generated_sidecar': generated_sidecar,
        'final_plugin_candidate': pin(config['final_plugin_candidate']) if Path(config['final_plugin_candidate']).is_file() else None,
        'scope_change': config['load_order_policy'], 'errors': errors,
        'limitations': ['No game or GUI started. Official patcher execution alone does not prove semantic correctness or stability.',
            'All generated plugins and the captured Experience sidecar remain research candidates. No generated output is deployed by this runner.',
            'Final input-aware record comparison, known upstream diagnostic review, complete xEdit and final actual-MO2 VFS validation remain required.']}
    write(result_path, result)
    print(json.dumps({'status': result['status'], 'stages': len(rows), 'errors': len(errors), 'sidecar_restored': restored, 'result': str(result_path)}), flush=True)
    return 2 if errors else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
