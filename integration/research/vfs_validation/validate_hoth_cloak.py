"""Exercise Hoth resource installation and exact rollback in an isolated fixture."""
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
from install_hoth_cloak import install_hoth, MANIFEST


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
        receipt = install_hoth(job=root / 'success')
        assert receipt['schema'] == 'skyrim.hoth_cloak_install.v1'
        assert len(receipt['files']) == 4 and not receipt['accepted']
        for path, row in expected.items():
            target = mat.TARGET / 'mods/ZZ83 Verified generated item and quest assets' / path
            assert mat.sha(target) == row['source']['sha256'] and target.stat().st_nlink == 1
        with mat.connect() as connection:
            assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
            assert connection.execute("select count(*) from files where unit_id='hoth_cloak_v1' and status='materialized'").fetchone()[0] == 4
        fixture(root, 'reused_unit_runtime')
        connection = mat.connect()
        connection.execute('insert into units values(?,?,?,?,?)',
                           ('hoth_cloak_v1', 'fixture', '[per-file mapping]', 'existing fixture journal row', mat.utc()))
        connection.commit()
        connection.close()
        try:
            install_hoth(job=root / 'reused_unit')
        except ValueError as exc:
            assert 'Unit already planned: hoth_cloak_v1' in str(exc)
        else:
            raise AssertionError('Reused unit ID was not rejected')
        connection = mat.connect()
        assert connection.execute("select reason from units where id='hoth_cloak_v1'").fetchone()[0] == 'existing fixture journal row'
        assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
        connection.close()
        fixture(root, 'rollback_runtime')
        calls = [0]

        def fail_second(source, destination, stat):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError('Deliberate Hoth second-copy failure')
            return mat.make_private(source, destination, stat)

        try:
            install_hoth(job=root / 'rollback', copier=fail_second)
        except RuntimeError as exc:
            assert 'Deliberate Hoth second-copy failure' in str(exc)
        else:
            raise AssertionError('Injected failure was not raised')
        assert calls[0] == 2
        for path in expected:
            assert not (mat.TARGET / 'mods/ZZ83 Verified generated item and quest assets' / path).exists()
        with mat.connect() as connection:
            assert not connection.execute("select 1 from files where unit_id='hoth_cloak_v1'").fetchone()
            assert not connection.execute("select 1 from units where id='hoth_cloak_v1'").fetchone()
            assert connection.execute('pragma integrity_check').fetchone()[0] == 'ok'
        result = {'status': 'PASS_HOTH_PRIVATE_COPIES_AND_EXACT_ROLLBACK', 'fixture': str(root),
                  'resource_count': 4, 'production_files_modified': False,
                  'checks': ['exact private mesh and texture bytes', 'single-link files and journal rows',
                             'second-copy rollback removes all files and unit rows',
                             'duplicate unit retry preserves the existing journal row']}
        print(json.dumps(result, indent=2))
    finally:
        mat.TARGET, mat.DB, mat.RESERVE = original


if __name__ == '__main__':
    main()
