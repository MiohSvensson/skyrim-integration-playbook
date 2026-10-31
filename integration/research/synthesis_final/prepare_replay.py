"""Prepare a fresh official-DLL replay from an immutable physical expectation."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from vfs_common import controls, injected, key
from catalogue_official_replay import sha, pin

SIDECAR = 'skse/plugins/experience/races/generatedexperiencepatch.ini'
IMPLICIT = {'skyrim.esm', 'update.esm', 'dawnguard.esm', 'hearthfires.esm', 'dragonborn.esm'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--expect', required=True)
    p.add_argument('--job', required=True, help='Fresh directory name below this research directory/runs')
    p.add_argument('--private-sidecar', required=True, help='Existing private nlink1 physical winner in UnifiedSkyrim/mods')
    a = p.parse_args()
    assert not injected(), 'Preparation must occur outside the injected runtime'
    assert re.fullmatch(r'[A-Za-z0-9_.-]+', a.job) and a.job not in ('.', '..')
    expectation = Path(a.expect).resolve()
    db = sqlite3.connect(expectation.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    expect = json.loads(db.execute("select value from metadata where key='expectations'").fetchone()[0])
    assert not expect['errors'], expect['errors']
    target, profile = Path(expect['target']), Path(expect['profile'])
    assert target.resolve() == (BASE / 'UnifiedSkyrim').resolve()
    assert controls(target, profile) == expect['control_hashes']
    catalogue_path = OWN / 'official_replay_catalogue.json'
    catalogue = json.loads(catalogue_path.read_text(encoding='utf-8'))
    assert catalogue['schema'] == 'skyrim.official_synthesis_dll_replay.v1'
    assert catalogue['driver_count'] == len(catalogue['drivers']) == 6
    sidecar = Path(a.private_sidecar).resolve(strict=True)
    assert sidecar.is_relative_to((target / 'mods').resolve())
    assert sidecar.is_file() and sidecar.stat().st_nlink == 1 and sidecar.stat().st_size <= 1024 * 1024
    row = db.execute('select * from files where path_key=?', (SIDECAR,)).fetchone()
    assert row and Path(row['physical_path']).resolve() == sidecar
    dummy_key = key('deleteThisEspIfYouSeeIt-itsEmpty.esp')
    assert db.execute('select 1 from files where path_key=?', (dummy_key,)).fetchone() is None, 'Existing dummy must not be exposed to the Experience deletion'
    excluded = {key(x) for x in catalogue['original_blacklist']} | {key(catalogue['group'] + '.esp')}
    included = [x for x in expect['plugins'] if key(x['name']) not in excluded]
    included_names = {key(x['name']) for x in included}
    assert 'synthesis.esp' not in included_names, 'Old Synthesis0.20.2 internally trims at Synthesis.esp; another legacy output must not be an input'
    missing = [{'plugin': x['name'], 'master': m} for x in included for m in x['masters'] if key(m) not in included_names]
    assert not missing, ('Group blacklist creates a missing-master input context', missing)
    assert IMPLICIT <= included_names
    for x in expect['plugins']:
        assert sha(x['physical_path']) == x['sha256'], x['name']
    root = OWN / 'runs' / a.job
    root.mkdir(parents=True, exist_ok=False)
    output = root / 'output'
    output.mkdir()
    work = root / 'work'
    work.mkdir()
    entries = [x['name'] for x in included if key(x['name']) not in IMPLICIT]
    plugins = root / 'Plugins.txt'
    plugins.write_text(''.join('*' + name + '\n' for name in entries), encoding='utf-8')
    seed = root / 'seed' / (catalogue['group'] + '.esp')
    seed.parent.mkdir()
    assert sha(catalogue['empty_seed']['path']) == catalogue['empty_seed']['sha256']
    seed.write_bytes(bytes.fromhex(catalogue['empty_seed']['bytes_hex']))
    assert sha(seed) == catalogue['empty_seed']['sha256']
    stages = []
    source = seed
    for driver in catalogue['drivers']:
        extra = root / 'settings' / driver['name']
        extra.mkdir(parents=True)
        for setting in driver['settings_files']:
            assert sha(setting['path']) == setting['sha256']
            destination = extra / setting['relative_path']
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(setting['path'], destination)
        stage_output = output / f'{driver["index"]:02d}-{driver["name"]}' / (catalogue['group'] + '.esp')
        stage_output.parent.mkdir()
        replacements = {'{DATA_PATH}': str(target / 'Game/Data'), '{EXTRA_DATA}': str(extra),
            '{LOAD_ORDER}': str(plugins), '{OUTPUT}': str(stage_output), '{SOURCE}': str(source)}
        command = [replacements.get(token, token) for token in driver['replay_argv_template']]
        assert not any(token.startswith('{') for token in command)
        stages.append({'index': driver['index'], 'name': driver['name'], 'argv': command,
            'source': str(source), 'output': str(stage_output), 'extra_data': str(extra),
            'settings_pins': [pin(extra / x['relative_path']) for x in driver['settings_files']],
            'experience_side_effect': driver['name'] == 'ExperienceMutagenPatcher'})
        source = stage_output
    config = {'schema': 'skyrim.prepared_official_synthesis_replay.v1',
        'status': 'PREPARED_NOT_EXECUTED', 'catalogue': pin(catalogue_path), 'expectations': pin(expectation),
        'job_root': str(root), 'target': str(target), 'profile': str(profile), 'control_hashes': expect['control_hashes'],
        'data_path': str(target / 'Game/Data'), 'plugins_file': pin(plugins), 'seed': pin(seed),
        'input_plugins': expect['plugins'], 'included_input_plugins': [x['name'] for x in included],
        'excluded_active_plugins': [x['name'] for x in expect['plugins'] if key(x['name']) in excluded],
        'absent_optional_ccc_entries': expect['absent_optional_ccc_entries'],
        'load_order_policy': {'scope': catalogue['final_scope_authorization'], 'implicit_stock_removed_from_text': sorted(IMPLICIT),
            'creation_club_policy': 'Only installed active CC plugins are retained explicitly. Newer versions consume their recorded --LoadOrderIncludesCreationClub flag; oldest0.20.2 has only implicit and explicit load-order providers and does not add a CCC provider. See pinned legacy source evidence.',
            'text_entry_count': len(entries), 'effective_plugin_count': len(included)},
        'private_sidecar': {**pin(sidecar), 'relative_path': SIDECAR, 'provider': row['provider'],
            'link_count': sidecar.stat().st_nlink,
            'policy': 'Actual injected runtime FileID must equal this private file. Backup exact original bytes to this job; capture generated sidecar then restore the private original in finally. No source/base layer is writable by this protocol.'},
        'experience_dummy_absence': {'path_key': dummy_key, 'expectation_files_table_checked_absent': True,
            'runtime_method': 'CreateFileW via file_identity, accepting only Windows errors2/3 as absence; never Path.exists on virtual Data.'},
        'stages': stages, 'final_plugin_candidate': str(source),
        'final_sidecar_candidate': str(output / 'sidecar' / SIDECAR),
        'runner': pin(OWN / 'run_official_replay.py')}
    (root / 'prepared.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': config['status'], 'prepared': str(root / 'prepared.json'),
        'input_plugins': len(included), 'text_entries': len(entries), 'excluded': config['excluded_active_plugins']}))


if __name__ == '__main__':
    main()
