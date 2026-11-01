"""Exercise MO2 comment canonicalization and its isolated journal rollback."""
import hashlib
import json
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import materialize as mat
import mo2_controls as m


def fixture(root, original, fail=False):
    target = root / 'runtime'
    profile = target / 'profiles' / 'Unified Build'
    profile.mkdir(parents=True)
    control = profile / 'modlist.txt'
    control.write_bytes(original)
    mat.TARGET, mat.DB, mat.RESERVE = target, root / 'journal.sqlite', 0
    source = root / 'original.txt'
    source.write_bytes(original)
    c = mat.connect()
    mat.add_file_mapping(c, 'original_control', [{'source': str(source), 'destination': 'profiles/Unified Build/modlist.txt', 'storage': 'private'}], 'Control normalization fixture')
    c.execute("update files set status='materialized',sha256=?", (mat.sha(source),))
    c.commit()
    old_rows = [dict(r) for r in c.execute('select * from files order by id')]
    old_units = [dict(r) for r in c.execute('select * from units order by id')]
    c.close()
    original_copy = mat.make_private
    if fail:
        raised = [False]
        def interrupted(src, dst, st):
            result = original_copy(src, dst, st)
            if not raised[0]:
                raised[0] = True
                raise RuntimeError('Deliberate post-copy fixture failure')
            return result
        mat.make_private = interrupted
    try:
        try:
            result = m.normalize_profile(profile, root / 'receipt')
        except RuntimeError:
            assert fail
        else:
            assert not fail and result['changed']
    finally:
        mat.make_private = original_copy
    c = mat.connect()
    assert c.execute('pragma integrity_check').fetchone()[0] == 'ok'
    rows = [dict(r) for r in c.execute('select * from files order by id')]
    units = [dict(r) for r in c.execute('select * from units order by id')]
    c.close()
    if fail:
        assert rows == old_rows and units == old_units and control.read_bytes() == original
        return 'ROLLBACK_EXACT_BYTES_AND_ROWS'
    expected = m.canonical_modlist(original)
    assert control.read_bytes() == expected and rows[0]['sha256'] == mat.sha(control)
    assert not m.normalize_profile(profile)['changed']
    return 'NORMALIZED_IDEMPOTENT_JOURNAL_MATCH'


def main():
    original = (mat.TARGET, mat.DB, mat.RESERVE)
    source = Path('integration/research/verified_patch_install/runs/feature_v13_v14/controls/Unified Skyrim/modlist.txt').read_bytes()
    actual = Path('UnifiedSkyrim/profiles/Unified Skyrim/modlist.txt').read_bytes()
    assert m.canonical_modlist(source) == actual
    assert b''.join(line for line in source.splitlines(keepends=True) if line.rstrip(b'\r\n') != m.COMMENT) == b''.join(line for line in actual.splitlines(keepends=True) if line.rstrip(b'\r\n') != m.COMMENT)
    assert m.canonical_modlist(b'\xef\xbb\xbf+A\r\n' + m.COMMENT + b'\r\n+B\r\n') == b'\xef\xbb\xbf' + m.COMMENT + b'\r\n+A\r\n+B\r\n'
    assert m.canonical_modlist(b'+A\n' + m.COMMENT) == m.COMMENT + b'\n+A\n'
    try:
        m.canonical_modlist(m.COMMENT + b'\n' + m.COMMENT + b'\n')
    except ValueError:
        pass
    else:
        raise AssertionError('Duplicate generated comment not rejected')
    root = Path(__file__).resolve().parent / 'fixtures' / uuid.uuid4().hex
    root.mkdir(parents=True)
    expected = m.canonical_modlist(source)
    additions = ['ZZ90 FC diagnostic 2', 'ZZ90 FC diagnostic']
    eol = b'\r\n' if expected.startswith(m.COMMENT + b'\r\n') else b'\n'
    prefix = expected.splitlines(keepends=True)[0]
    permitted = prefix + b''.join(b'-' + name.encode() + eol for name in additions) + expected[len(prefix):]
    assert m.reconcile_modlist(expected, permitted, additions)['status'] == 'APPROVED_MO2_DISABLED_ADDITIONS_ONLY'
    for unauthorized in [permitted.replace(b'-ZZ90 FC diagnostic 2', b'+ZZ90 FC diagnostic 2'),
                         permitted.replace(b'FC diagnostic 2', b'FC diagnostic 3'),
                         expected.replace(b'+ZZ87', b'-ZZ87'),
                         m.COMMENT + eol + b'-ZZ90 FC diagnostic\r\n' + expected[len(m.COMMENT)+2:]]:
        try:
            m.reconcile_modlist(expected, unauthorized, additions)
        except ValueError:
            pass
        else:
            raise AssertionError('Unauthorized modlist change was accepted')
    try:
        results = [fixture(root / 'normal', source), fixture(root / 'rollback', source, fail=True)]
        audit_root = root / 'audit'
        profile = audit_root / 'runtime/profiles/Unified Build'
        profile.mkdir(parents=True)
        (profile / 'modlist.txt').write_bytes(permitted)
        (profile / 'plugins.txt').write_bytes(b'Skyrim.esm\r\n')
        snapshot = audit_root / 'modlist.prepared.txt'
        snapshot.write_bytes(expected)
        mat.TARGET = audit_root / 'runtime'
        pins = {'modlist.txt': mat.sha(snapshot), 'plugins.txt': mat.sha(profile / 'plugins.txt')}
        audit = m.audit_profile_controls(profile, pins, snapshot, additions)
        assert not audit['changed_controls'] and audit['reconciled_controls']['modlist.txt']['added_disabled_mods'] == additions
        (profile / 'plugins.txt').write_bytes(b'Unexpected.esp\r\n')
        assert m.audit_profile_controls(profile, pins, snapshot, additions)['changed_controls'] == ['plugins.txt']
        results.append('EXPLICIT_DISABLED_ADDITIONS_AND_UNAUTHORIZED_DRIFT_GUARDS')
    finally:
        mat.TARGET, mat.DB, mat.RESERVE = original
    receipt = {'status': 'PASS_MO2_COMMENT_AND_JOURNAL_ROLLBACK', 'checks': results,
               'actual_launch_sha256': mat.sha(Path('UnifiedSkyrim/profiles/Unified Skyrim/modlist.txt')),
               'canonical_source_sha256': hashlib.sha256(source).hexdigest(),
               'real_profiles_modified_by_fixture': False}
    (root / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
