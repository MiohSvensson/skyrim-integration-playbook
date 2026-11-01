"""Exercise Synthesis sidecar replacement, rollback and crash recovery in fixtures."""
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
from research.verified_patch_install import install_verified_patch as base
import install_synthesis as synthesis

LAYER = synthesis.LAYER
SIDECAR = synthesis.SIDECAR


def prepare_fixture(root, mode):
    runtime = root / mode / 'runtime'
    runtime.mkdir(parents=True)
    mat.TARGET, mat.DB, mat.RESERVE = runtime, root / mode / 'journal.sqlite', 0
    (runtime / '.integration-managed.json').write_text(json.dumps({'journal': str(mat.DB)}) + '\n', encoding='utf-8')
    job = root / mode / 'job'
    job.mkdir(parents=True)
    destinations = [f'mods/{LAYER}/Synthesis - Patch.esp', f'mods/{LAYER}/{SIDECAR}']
    destinations += [f'profiles/{profile}/{name}' for profile in base.PROFILES for name in base.CONTROLS[:3]]
    old_sources, mappings, prior = [], [], {}
    for index, destination in enumerate(destinations):
        old = job / f'old_{index}.bin'
        old.write_bytes(f'old {index}'.encode())
        old_sources.append(old)
        new = job / f'new_{index}.bin'
        new.write_bytes(f'new {index}'.encode())
        mappings.append({'source': str(new), 'destination': destination, 'storage': 'private', 'bytes': new.stat().st_size})
        target = runtime / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(old.read_bytes())
        prior[destination] = target.read_bytes()
    connection = mat.connect()
    mat.add_file_mapping(connection, 'fixture_old',
                         [{'source': str(source), 'destination': row['destination'], 'storage': 'private'}
                          for source, row in zip(old_sources, mappings)], 'Synthesis fixture original rows')
    for source, row in zip(old_sources, mappings):
        connection.execute("update files set status='materialized',sha256=? where dest_key=?",
                           (mat.sha(source), mat.key(row['destination'])))
    connection.commit()
    old_rows = [dict(row) for row in connection.execute('select * from files order by id')]
    old_units = [dict(row) for row in connection.execute('select * from units order by id')]
    connection.close()
    plan = {'schema': 'skyrim.verified_patch_install.v1', 'layer': LAYER,
            'candidate_name': 'Synthesis - Patch.esp', 'candidate_sha256': mat.sha(mappings[0]['source']),
            'replace_sha256': mat.sha(old_sources[0]),
            'extra_replacements': {destinations[1]: mat.sha(old_sources[1])},
            'producer_candidate_required': False, 'profiles': [], 'source_pins': [], 'staged_pins': [],
            'mappings': mappings, 'synthesis_proof': {}}
    prepared = job / 'prepared.json'
    base.save_new(prepared, plan)
    return job, plan, prior, old_rows, old_units


def assert_original(job, prior, old_rows, old_units):
    for destination, blob in prior.items():
        assert (mat.TARGET / destination).read_bytes() == blob
    connection = mat.connect()
    assert [dict(row) for row in connection.execute('select * from files order by id')] == old_rows
    assert [dict(row) for row in connection.execute('select * from units order by id')] == old_units
    assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
    connection.close()


def main():
    saved = mat.TARGET, mat.DB, mat.RESERVE, base.check_plan, base.mat.make_private
    root = HERE / 'fixtures' / uuid.uuid4().hex
    base.check_plan = lambda plan, verify_current=True: None
    try:
        job, plan, prior, old_rows, old_units = prepare_fixture(root, 'success')
        base.install_unlocked(SimpleNamespace(prepared=job / 'prepared.json'))
        receipt = json.loads((job / 'installed.json').read_text('utf-8'))
        assert receipt['status'] == 'INSTALLED_PENDING_FRESH_TYPED_RELOAD' and not receipt['accepted']
        assert len(receipt['files']) == 8
        assert [Path(row['path']).name for row in receipt['files'][:2]] == ['Synthesis - Patch.esp', 'GeneratedExperiencePatch.ini']
        for row in plan['mappings']:
            assert mat.sha(mat.TARGET / row['destination']) == mat.sha(row['source'])
        job, plan, prior, old_rows, old_units = prepare_fixture(root, 'rollback')
        calls = [0]

        def fail_third(source, destination, stat):
            calls[0] += 1
            if calls[0] == 3:
                raise RuntimeError('Deliberate failure after Synthesis sidecar')
            return saved[4](source, destination, stat)

        base.mat.make_private = fail_third
        try:
            base.install_unlocked(SimpleNamespace(prepared=job / 'prepared.json'))
        except RuntimeError as exc:
            assert 'Deliberate failure after Synthesis sidecar' in str(exc)
        else:
            raise AssertionError('Injected sidecar failure was not raised')
        assert_original(job, prior, old_rows, old_units)
        base.mat.make_private = saved[4]
        job, plan, prior, old_rows, old_units = prepare_fixture(root, 'crash')
        child = '''import os,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path.cwd().parents[1]))
from research.verified_patch_install import install_verified_patch as m
m.LAYER = 'T5861 Synthesis Patch (1.01)'
m.check_plan = lambda plan, verify_current=True: None
m.mat.TARGET = Path(sys.argv[1])
m.mat.DB = Path(sys.argv[2])
m.mat.RESERVE = 0
original = m.mat.make_private
calls = [0]
def crash(source, destination, stat):
    calls[0] += 1
    if calls[0] == 3:
        os._exit(48)
    return original(source, destination, stat)
m.mat.make_private = crash
m.install_unlocked(SimpleNamespace(prepared=Path(sys.argv[3])))
'''
        with (root / 'crash.log').open('w', encoding='utf-8') as stream:
            completed = subprocess.run([sys.executable, '-B', '-c', child, str(mat.TARGET), str(mat.DB), str(job / 'prepared.json')],
                                       cwd=HERE, stdout=stream, stderr=subprocess.STDOUT)
        assert completed.returncode == 48
        assert (job / 'install_started.json').is_file() and not (job / 'installed.json').exists()
        base.recover_unlocked(SimpleNamespace(prepared=job / 'prepared.json'))
        assert_original(job, prior, old_rows, old_units)
        assert (job / 'recovered.json').is_file()
        text = b'# comment\r\n+Other\r\n+T5861 Synthesis Patch (1.01)\r\n+ZZ88 Private synthesis sidecar workspace\r\n'
        changed = synthesis.edit_modlist(text)
        assert changed.startswith(b'# comment\r\n+' + LAYER.encode() + b'\r\n+Other\r\n')
        assert changed.endswith(b'-ZZ88 Private synthesis sidecar workspace\r\n')
        called = []
        original_install = base.install
        try:
            base.install = lambda args: called.append(base.check_plan is synthesis.check_plan)
            synthesis.install(SimpleNamespace())
        finally:
            base.install = original_install
        assert called == [True], 'Synthesis entry point bypassed its scoped check'
        result = {'status': 'PASS_SYNTHESIS_SIDECAR_ROLLBACK_AND_RECOVERY', 'fixture': str(root),
                  'production_files_modified': False,
                  'checks': ['plugin and captured sidecar precede profile controls',
                             'post-sidecar failure restores all old bytes and journal rows',
                             'actual crash recovery restores sidecar and profile controls',
                             'ZZ88 disabled while other mod order is preserved']}
        print(json.dumps(result, indent=2))
    finally:
        mat.TARGET, mat.DB, mat.RESERVE, base.check_plan, base.mat.make_private = saved


if __name__ == '__main__':
    main()
