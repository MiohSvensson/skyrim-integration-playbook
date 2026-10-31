"""Pin the six recorded official GUI DLL invocations without executing them."""
import ctypes
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
GUI = BASE / 'repairs/Synthesis_GUI_v2'
sys.path.insert(0, str(BASE / 'rootcause'))
from plugin_binary import read


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def pin(path):
    path = Path(path)
    return {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}


def argv(command):
    shell = ctypes.WinDLL('shell32')
    shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
    kernel = ctypes.WinDLL('kernel32')
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    count = ctypes.c_int()
    result = shell.CommandLineToArgvW(command, ctypes.byref(count))
    assert result
    try:
        return [result[i] for i in range(count.value)]
    finally:
        kernel.LocalFree(result)


def main():
    OWN.mkdir(parents=True, exist_ok=True)
    log = GUI / 'logs/Current.log'
    settings_path = GUI / 'PipelineSettings.json'
    pipeline = json.loads(settings_path.read_text(encoding='utf-8'))
    profile = pipeline['Profiles'][0]
    groups = [g for g in profile['Groups'] if g['On']]
    assert len(groups) == 1 and groups[0]['Name'] == 'Synthesis - Patch'
    group = groups[0]
    enabled = [p for p in group['Patchers'] if p['On']]
    assert len(enabled) == 6
    provenance_path = GUI / 'compiled_patcher_provenance.json'
    provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
    metadata = {Path(x['path']).parent.name: x for x in provenance}
    commands = {}
    interpreted = {}
    for line_no, line in enumerate(log.read_text(encoding='utf-8-sig').splitlines(), 1):
        marker = '(): dotnet '
        if marker not in line or ' run-patcher ' not in line:
            continue
        command = argv('dotnet ' + line.split(marker, 1)[1])
        name = command[command.index('--PatcherName') + 1]
        assert name not in commands
        commands[name] = {'line_number': line_no, 'argv': command}
    for line_no, line in enumerate(log.read_text(encoding='utf-8-sig').splitlines(), 1):
        if ' run-patcher ' not in line or ' --ExtraDataFolder ' not in line or '(): dotnet ' in line:
            continue
        command = argv('run-patcher ' + line.split(' run-patcher ', 1)[1])
        name = command[command.index('--PatcherName') + 1]
        assert name not in interpreted
        interpreted[name] = {'line_number': line_no, 'argv': command}
    assert set(commands) == {p['Nickname'] for p in enabled}
    drivers = []
    mutable_options = {'--DataFolderPath': '{DATA_PATH}', '--ExtraDataFolder': '{EXTRA_DATA}',
                       '--LoadOrderFilePath': '{LOAD_ORDER}', '--OutputPath': '{OUTPUT}', '--SourcePath': '{SOURCE}'}
    for index, patcher in enumerate(enabled, 1):
        old = commands[patcher['Nickname']]
        command = old['argv']
        source = metadata[patcher['ID']]
        meta = source['metadata']
        assert meta['Sha'] == patcher['TargetCommit']
        executable = Path(meta['ExecutablePath'])
        assert command[0] == 'dotnet' and command[1] == str(executable) and command[2] == 'run-patcher'
        current_meta = json.loads(Path(source['path']).read_text(encoding='utf-8'))
        metadata_drift = {k: {'archived': meta.get(k), 'current': current_meta.get(k)}
                         for k in set(meta) | set(current_meta) if meta.get(k) != current_meta.get(k)}
        assert set(metadata_drift) <= {'DoesNotHaveRunnability'}, metadata_drift
        template = command[:]
        template[0] = str(BASE / 'tools/dotnet/dotnet.exe')
        for option, placeholder in mutable_options.items():
            assert template.count(option) == 1
            template[template.index(option) + 1] = placeholder
        assert '--PersistencePath' not in command and '--TargetLanguage' not in command
        extra = Path(command[command.index('--ExtraDataFolder') + 1])
        bin_files = [pin(p) for p in sorted(executable.parent.rglob('*')) if p.is_file()]
        extra_files = []
        if extra.is_dir():
            extra_files = [{**pin(p), 'relative_path': p.relative_to(extra).as_posix()} for p in sorted(extra.rglob('*')) if p.is_file()]
        code_root = Path(source['path']).parent / 'Runner'
        code = [pin(p) for p in sorted(code_root.rglob('*.cs')) if not {'obj', 'bin'} & set(p.relative_to(code_root).parts)]
        drivers.append({'index': index, 'name': patcher['Nickname'], 'patcher_id': patcher['ID'],
            'repository': patcher['RemoteRepoPath'], 'source_commit': patcher['TargetCommit'],
            'Build_meta': pin(source['path']), 'Build_metadata': meta, 'current_Build_metadata': current_meta,
            'metadata_drift_since_archived_provenance': metadata_drift,
            'recorded_gui_host_command': old, 'driver_interpreted_command': interpreted[patcher['Nickname']],
            'replay_argv_template': template,
            'compiled_runtime_files': bin_files, 'settings_source_directory': str(extra),
            'settings_files': extra_files, 'source_code_files': code,
            'side_effect': 'Writes Data/SKSE/Plugins/Experience/Races/GeneratedExperiencePatch.ini; creates directory and deletes the empty-name dummy ESP if present.' if patcher['Nickname'] == 'ExperienceMutagenPatcher' else None})
    seed = GUI / f'work/{profile["ID"]}/Workspace/Seed Mod/Synthesis - Patch.esp'
    masters, records = read(seed)
    assert masters == [] and len(records) == 1 and records[0]['sig'] == 'TES4'
    assert records[0]['flags'] == 0 and records[0]['fid'] == 0
    assert len(records[0]['fields']) == 1 and records[0]['fields'][0][0] == 'HEDR'
    version, count, next_id = struct.unpack('<fII', records[0]['fields'][0][1])
    assert count == 0 and next_id == 0 and seed.stat().st_size == 42
    assert profile['FormIdPersistence'] == 'None' and profile['FormIDRangeMode'] == 'Auto'
    source_paths = [
        'Running/Runner/CreateEmptyPatch.cs', 'Running/Runner/GroupRunPreparer.cs',
        'Running/Runner/RunPersistencePreparer.cs', 'Running/Runner/LoadOrderForRunProvider.cs',
        'Running/Runner/GroupRunLoadOrderPreparer.cs', 'Running/Runner/RunArgsConstructor.cs',
        'Running/Runner/RunAPatcher.cs', 'Running/Runner/FinalizePatcherRun.cs']
    execution = BASE / 'sources/Synthesis/Synthesis.Bethesda.Execution'
    sources = [pin(execution / p) for p in source_paths]
    result = {'schema': 'skyrim.official_synthesis_dll_replay.v1', 'status': 'PINNED_REPLAY_PLAN_NOT_EXECUTED',
        'group': group['Name'], 'release': profile['TargetRelease'],
        'provenance': [pin(log), pin(settings_path), pin(provenance_path), pin(GUI / 'official_release_provenance.json')],
        'dotnet_host': pin(BASE / 'tools/dotnet/dotnet.exe'), 'driver_count': len(drivers), 'drivers': drivers,
        'disabled_groups': [{'name': g['Name'], 'patchers': [p['Nickname'] for p in g['Patchers']]} for g in profile['Groups'] if not g['On']],
        'original_blacklist': group['BlacklistedMods'],
        'final_scope_authorization': 'All active gameplay inputs in Unified Build, excluding the old group output and original group blacklist. Parent explicitly corrects source ordering that left fifteen active plugins after the old synthesis output. Final new Synthesis is placed after gameplay plugins and before generated LOD. No old prefix trimming is performed.',
        'empty_seed': {**pin(seed), 'bytes_hex': seed.read_bytes().hex(), 'header_version': version,
            'header_record_count': count, 'next_form_id': next_id, 'masters': [], 'payload_records': 0,
            'reuse_policy': 'Copy these author-GUI-created 42 header-only bytes into a fresh seed path; they contain no persistent record IDs or masters. Never reuse a prior generated payload patch as seed.',
            'reason': 'Official GroupRunPreparer creates an empty patch each run; PersistenceMode.None returns no persistence file. Each driver SourcePath is the prior freshly generated stage output.'},
        'pipeline_equivalence_evidence': sources,
        'legacy_option_evidence': pin(OWN/'legacy_option_compatibility_evidence.json') if (OWN/'legacy_option_compatibility_evidence.json').exists() else None,
        'old_generated_identity_evidence': pin(OWN/'old_output_identity_evidence.json') if (OWN/'old_output_identity_evidence.json').exists() else None,
        'runtime_constraints': ['Must run as a Python child of the final MO2 profile and prove usvfs_x64.dll injection.',
            'DataFolderPath is exactly UnifiedSkyrim/Game/Data; compiled DLLs and original settings remain pinned and unmodified.',
            'Only recorded GUI host argv options are replayed; replace only data, extra-data, load-order, source and output paths.',
            'No compilation, GUI launcher, security-policy change, registry change, or game process is invoked.',
            'Every output path is fresh; each stage is independently recorded. Unexpected split outputs stop the sequential replay for explicit review.',
            'Experience sidecar requires a private physical winning file under UnifiedSkyrim/mods with nlink1, exact VFS FileID match, small backup, capture and finally restoration.'],
        'validation_status': 'Static preparation only. Execution, generated-plugin semantic checks, xEdit and final VFS still required.'}
    output = OWN / 'official_replay_catalogue.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(output), 'sha256': sha(output), 'drivers': len(drivers), 'runtime_files': sum(len(x['compiled_runtime_files']) for x in drivers), 'seed_sha256': sha(seed)}))


if __name__ == '__main__':
    main()
