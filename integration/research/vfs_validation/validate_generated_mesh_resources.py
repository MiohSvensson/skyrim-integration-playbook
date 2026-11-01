"""Exercise the 23-file resource installer, duplicate guard and crash recovery."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
from install_generated_meshes import install_generated, MANIFEST, UNIT
from recover_private_resources import recover


def fixture(root, name):
    mat.TARGET = root / name / 'runtime'
    mat.DB = root / name / 'journal.sqlite'
    mat.TARGET.mkdir(parents=True)
    (mat.TARGET / '.integration-managed.json').write_text(json.dumps({'journal': str(mat.DB)}) + '\n', encoding='utf-8')
    for profile in ['Unified Skyrim', 'Unified Build']:
        folder = mat.TARGET / 'profiles' / profile
        folder.mkdir(parents=True)
        for filename in ['modlist.txt', 'plugins.txt', 'loadorder.txt']:
            (folder / filename).write_bytes(b'')


def main():
    original = mat.TARGET, mat.DB, mat.RESERVE
    root = HERE / 'fixtures' / uuid.uuid4().hex
    report = json.loads(MANIFEST.read_text('utf-8'))
    expected = {Path(row['destination']).relative_to(mat.BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets').as_posix(): row
                for row in report['private_resource_mapping']}
    try:
        mat.RESERVE = 0
        fixture(root, 'success_runtime')
        receipt = install_generated(job=root / 'success')
        assert receipt['schema'] == 'skyrim.generated_mesh_resource_install.v1'
        assert len(receipt['files']) == 23 and not receipt['accepted']
        for path, row in expected.items():
            target = mat.TARGET / 'mods/ZZ83 Verified generated item and quest assets' / path
            assert mat.sha(target) == row['source']['sha256'] and target.stat().st_nlink == 1
        connection = mat.connect()
        assert connection.execute("select count(*) from files where unit_id=? and status='materialized'", (UNIT,)).fetchone()[0] == 23
        assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
        connection.close()
        fixture(root, 'reused_unit_runtime')
        connection = mat.connect()
        connection.execute('insert into units values(?,?,?,?,?)', (UNIT, 'fixture', '[per-file mapping]', 'existing fixture row', mat.utc()))
        connection.commit()
        connection.close()
        try:
            install_generated(job=root / 'reused_unit')
        except ValueError as exc:
            assert 'Unit already planned: ' + UNIT in str(exc)
        else:
            raise AssertionError('Duplicate unit was not rejected')
        connection = mat.connect()
        assert connection.execute('select reason from units where id=?', (UNIT,)).fetchone()[0] == 'existing fixture row'
        connection.close()
        fixture(root, 'crash_runtime')
        child = '''import os,sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd().parents[1]))
import materialize as mat
from install_generated_meshes import install_generated
root = Path(sys.argv[1])
mat.TARGET = root / 'crash_runtime' / 'runtime'
mat.DB = root / 'crash_runtime' / 'journal.sqlite'
mat.RESERVE = 0
calls = [0]
def crash(source, destination, stat):
    calls[0] += 1
    if calls[0] == 2:
        os._exit(47)
    return mat.make_private(source, destination, stat)
install_generated(root / 'crash', copier=crash)
'''
        with (root / 'crash.log').open('w', encoding='utf-8') as stream:
            completed = subprocess.run([sys.executable, '-B', '-c', child, str(root)], cwd=HERE, stdout=stream, stderr=subprocess.STDOUT)
        assert completed.returncode == 47
        assert (root / 'crash/install_started.json').is_file() and not (root / 'crash/installed.json').exists()
        recovered = recover(root / 'crash')
        assert recovered['status'] == 'INTERRUPTED_RESOURCE_INSTALL_RECOVERED_NOT_ACCEPTED'
        assert not (root / 'crash/install_started.json').exists()
        for path in expected:
            assert not (mat.TARGET / 'mods/ZZ83 Verified generated item and quest assets' / path).exists()
        connection = mat.connect()
        assert not connection.execute('select 1 from files where unit_id=?', (UNIT,)).fetchone()
        assert not connection.execute('select 1 from units where id=?', (UNIT,)).fetchone()
        assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
        connection.close()
        result = {'status': 'PASS_GENERATED_RESOURCES_ROLLBACK_AND_CRASH_RECOVERY', 'fixture': str(root),
                  'resource_count': 23, 'production_files_modified': False,
                  'checks': ['exact 23 private files and journal rows', 'duplicate unit preserves existing journal row',
                             'actual second-copy process crash recovers every file and unit row']}
        print(json.dumps(result, indent=2))
    finally:
        mat.TARGET, mat.DB, mat.RESERVE = original


if __name__ == '__main__':
    main()
