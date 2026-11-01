"""Exercise successful and interrupted two-file Igraine installations in fixtures."""
import json
from pathlib import Path
import sys
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
import install_igraine_material as tool


def main():
    original = mat.TARGET, mat.DB, mat.RESERVE
    root = HERE / 'fixtures' / uuid.uuid4().hex
    try:
        mat.TARGET = root / 'runtime'
        mat.DB = root / 'journal.sqlite'
        mat.RESERVE = 0
        mat.TARGET.mkdir(parents=True)
        (mat.TARGET / '.integration-managed.json').write_text(json.dumps({'journal': str(mat.DB)}) + '\n', encoding='utf-8')
        for profile in ['Unified Skyrim', 'Unified Build']:
            folder = mat.TARGET / 'profiles' / profile
            folder.mkdir(parents=True)
            for name in ['modlist.txt', 'plugins.txt', 'loadorder.txt']:
                (folder / name).write_bytes(b'')
        receipt = tool.install(job=root / 'success')
        assert len(receipt['files']) == 2 and not receipt['accepted']
        c = mat.connect()
        assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
        assert c.execute("select count(*) from files where unit_id=? and status='materialized'", (tool.UNIT,)).fetchone()[0] == 2
        c.close()
        mat.TARGET = root / 'rollback_runtime'
        mat.DB = root / 'rollback_journal.sqlite'
        mat.TARGET.mkdir(parents=True)
        (mat.TARGET / '.integration-managed.json').write_text(json.dumps({'journal': str(mat.DB)}) + '\n', encoding='utf-8')
        for profile in ['Unified Skyrim', 'Unified Build']:
            folder = mat.TARGET / 'profiles' / profile
            folder.mkdir(parents=True)
            for name in ['modlist.txt', 'plugins.txt', 'loadorder.txt']:
                (folder / name).write_bytes(b'')
        calls = [0]
        def fail_second(source, destination, stat):
            calls[0] += 1
            if calls[0] == 2:
                raise RuntimeError('Deliberate second-copy failure')
            return mat.make_private(source, destination, stat)
        try:
            tool.install(job=root / 'rollback', copier=fail_second)
        except RuntimeError as exc:
            assert 'Deliberate second-copy failure' in str(exc)
        else:
            raise AssertionError('Injected failure was not raised')
        assert calls[0] == 2
        for row in json.loads((root / 'rollback/install_started.json').read_text('utf-8'))['files']:
            assert not (mat.TARGET / row['destination']).exists()
        c = mat.connect()
        assert not c.execute('select 1 from files where unit_id=?', (tool.UNIT,)).fetchone()
        assert not c.execute('select 1 from units where id=?', (tool.UNIT,)).fetchone()
        assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
        c.close()
        result = {'status': 'PASS_TWO_PRIVATE_COPIES_AND_EXACT_ROLLBACK', 'fixture': str(root),
                  'production_files_modified': False, 'checks': ['private bytes and journal rows', 'second-copy rollback removes both files and unit rows']}
        path = HERE / ('validation_' + root.name + '.json')
        path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        mat.TARGET, mat.DB, mat.RESERVE = original


if __name__ == '__main__':
    main()
