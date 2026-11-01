"""Adversarial pure checks and private fixture journal/rollback exercises.

The journal fixtures redirect materialize.TARGET/DB to this research folder.
Crash children exit deliberately only against these isolated fixtures. No real
integration runtime, profile, or shared journal is written.
"""
import contextlib
import io
import json
import os
import struct
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

sys.dont_write_bytecode = True
import install_verified_patch as m


def main():
    result = []
    folder = m.HERE / 'fixtures' / uuid.uuid4().hex
    folder.mkdir(parents=True)

    def check(name, function):
        function()
        result.append({'case': name, 'passed': True})

    def rejects(function):
        try:
            function()
        except (ValueError, AssertionError, FileNotFoundError):
            return
        raise AssertionError('Expected rejection')

    def text_case():
        original = b'\xef\xbb\xbf# kept CRLF\r\n*A.esm\r\nDisabled.esp\n*X.esp\r\n# trailing note\r\n*Syn.esp'
        new = m.edit_plugin_order(original, 'New.esp', {'syn.esp'}, True)
        assert new == b'\xef\xbb\xbf# kept CRLF\r\n*A.esm\r\nDisabled.esp\n*X.esp\r\n# trailing note\r\n*New.esp\r\n*Syn.esp\r\n'
        assert original == original[:]
        mod = b'# comment\r\n*DLC: Dawnguard\r\n*Unmanaged: FNIS\r\n+old\r\n-optional\n'
        changed = m.edit_modlist(mod)
        assert changed.startswith(b'# comment\r\n+' + m.LAYER.encode() + b'\r\n')
        assert changed.endswith(mod.split(b'\r\n', 1)[1])
        assert m.edit_modlist(changed) == changed
        old = b'# c\n-keep\n-' + m.LAYER.encode() + b'\n'
        assert m.edit_modlist(old).count(m.LAYER.encode()) == 1
        disabled = m.edit_plugin_order(b'# c\nPatch.esp\n*A.esp\n', 'Patch.esp', set(), True)
        assert disabled == b'# c\n*A.esp\n*Patch.esp\n'

    check('byte-preserved BOM/comments/stars/mixed-newlines/builtin-modlist/activation', text_case)
    check('duplicate activation rejected', lambda: rejects(lambda: m.Lines(b'*A.esp\nA.ESP\n').names()))
    check('duplicate mod rows rejected', lambda: rejects(lambda: m.Lines(b'+A\n-A\n').names(True)))
    def stable_compatibility_order():
        known = list(m.COMPATIBILITY_PRIORITY)
        source = b'# preserved\r\n*A.esm\r\nDisabled.esp\n*Synthesis - Patch.esp\r\n'
        active = set()
        # Install quest before feature, Glen before FC, Underground last.
        for n in [known[1], known[0], known[4], known[2], known[3]]:
            source = m.edit_plugin_order(source, n, {'synthesis - patch.esp'}, True, active)
            active.add(n)
        entries = [k for k, _, prefix in m.Lines(source).names() if prefix == '*']
        assert entries == ['a.esm', *[name for name in known if name in active], 'synthesis - patch.esp']
        assert b'# preserved\r\n' in source and b'Disabled.esp\n' in source
    check('stable feature quest FC Underground Glen priority independent of install sequence', stable_compatibility_order)
    h = {'a.esm': {'masters': [], 'is_light': False}, 'b.esp': {'masters': ['A.esm'], 'is_light': True}}
    check('master topology valid', lambda: m.topo(['A.esm', 'B.esp'], h))
    check('master inversion rejected', lambda: rejects(lambda: m.topo(['B.esp', 'A.esm'], h)))
    check('missing master rejected', lambda: rejects(lambda: m.topo(['B.esp'], h)))
    check('full slot overflow rejected', lambda: rejects(lambda: m.topo([f'{i}.esp' for i in range(255)], {f'{i}.esp': {'masters': [], 'is_light': False} for i in range(255)})))
    check('light slot overflow rejected', lambda: rejects(lambda: m.topo([f'{i}.esp' for i in range(4097)], {f'{i}.esp': {'masters': [], 'is_light': True} for i in range(4097)})))

    source = folder / 'source.bin'
    source.write_bytes(b'original guarded source')
    candidate = folder / 'Test.esp'
    candidate.write_bytes(b'candidate bytes')
    digest = m.mat.sha(candidate)
    report = {'candidate': str(candidate), 'candidate_sha256': digest, 'passed': True,
              'candidate_checks': [{'matching': True, 'different_fields': []}], 'errors': [],
              'file_checks': [{'matches': True, 'path': str(source), 'sha256': m.mat.sha(source)}]}
    check('explicit SHA-bound binary pass', lambda: m.binary_gate(report, candidate, digest))
    for name, changes in [('false-pass', {'passed': False}), ('truthy-string-pass', {'passed': 'true'}),
                          ('missing-candidate-sha', {'candidate_sha256': None}), ('wrong-candidate-sha', {'candidate_sha256': '0' * 64}),
                          ('source-only-preflight', {'candidate': None, 'candidate_checks': []}),
                          ('failed-leaf', {'candidate_checks': [{'matching': False, 'different_fields': ['VMAD']}]}),
                          ('errors-even-with-pass', {'errors': ['bad']})]:
        check('reject ' + name, lambda changes=changes: rejects(lambda: m.binary_gate(report | changes, candidate, digest)))
    source.write_bytes(b'changed guarded source')
    check('changed independent-verifier source rejected', lambda: rejects(lambda: m.binary_gate(report, candidate, digest)))
    source.write_bytes(b'original guarded source')
    nav = {'status': 'BINARY_PASS_TYPED_RELOAD_REQUIRED', 'candidate': {'path': str(candidate), 'sha256': digest, 'records': [{'sig': 'NAVM'}]}}
    check('explicit navigation binary pass', lambda: m.binary_gate(nav, candidate, digest))
    check('navigation source preflight rejected', lambda: rejects(lambda: m.binary_gate(nav | {'status': 'SOURCE_PREFLIGHT_PASS'}, candidate, digest)))

    def write_esp(object_id):
        fields = m.plugin_binary.encode_subs([('HEDR', struct.pack('<fII', 1.7, 1, 0x801)), ('MAST', b'Skyrim.esm\0'), ('DATA', b'\0' * 8)])
        tes4 = b'TES4' + struct.pack('<IIIIHH', len(fields), 0x200, 0, 0, 44, 0) + fields
        data = m.plugin_binary.encode_subs([('EDID', b'TestPack\0')])
        pack = b'PACK' + struct.pack('<IIIIHH', len(data), 0, (1 << 24) | object_id, 0, 44, 0) + data
        candidate.write_bytes(tes4 + pack)
    write_esp(0x800)
    check('candidate own ID ESL-safe', lambda: m.candidate_header(candidate))
    write_esp(0x1000)
    check('candidate own ID ESL overflow rejected', lambda: rejects(lambda: m.candidate_header(candidate)))
    write_esp(0x800)
    v9 = m.mat.TARGET / 'validation/feature_compat_v9'
    if v9.exists():
        check('actual failed v9 producer rejected', lambda: rejects(lambda: m.producer_gate(v9)))

    physical_plans = []
    fake_header = {'masters': ['Skyrim.esm'], 'flags': 512, 'version': 1.7,
                   'sha256': 'f' * 64, 'is_light': True, 'is_master': False}
    for name in m.PROFILES:
        plan, controls = m.profile_plan(name, Path('ReadOnlyInstallerFixture.esp'), fake_header, None)
        physical_plans.append({k: plan[k] for k in ('profile', 'slots', 'relocated_derived_suffix')})
        assert all(isinstance(b, bytes) for b in controls.values())
    result.append({'case': 'both actual profiles read-only planning/topology/consistent activation-loadorder', 'passed': True})

    saved = (m.mat.TARGET, m.mat.DB, m.mat.RESERVE, m.check_plan, m.mat.make_private)
    def journal_fixture(mode):
        root = folder / mode
        runtime = root / 'runtime'
        runtime.mkdir(parents=True)
        m.mat.TARGET, m.mat.DB, m.mat.RESERVE = runtime, root / 'journal.sqlite', 0
        m.check_plan = lambda p, verify_current=True: None
        job = root / 'job'
        job.mkdir()
        replacement = mode == 'crash_replacement'
        paths = [f'mods/{m.LAYER}/Test.esp'] + [f'profiles/{p}/{n}' for p in m.PROFILES for n in m.CONTROLS[:3]]
        mappings, prior, old_mappings = [], {}, []
        for i, destination in enumerate(paths):
            src = job / f'new_{i}.bin'
            src.write_bytes(f'new {i}'.encode())
            mappings.append({'source': str(src), 'destination': destination, 'storage': 'private', 'bytes': src.stat().st_size})
            dst = runtime / destination
            if i or replacement:
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(f'old {i}'.encode())
                oldsrc = job / f'old_{i}.bin'
                oldsrc.write_bytes(dst.read_bytes())
                old_mappings.append({'source': str(oldsrc), 'destination': destination, 'storage': 'private'})
                prior[destination] = dst.read_bytes()
        c = m.mat.connect()
        m.mat.add_file_mapping(c, 'fixture_old', old_mappings, 'Private research fixture')
        for item in old_mappings:
            c.execute("update files set status='materialized',sha256=? where dest_key=?",
                      (m.mat.sha(item['source']), m.mat.key(item['destination'])))
        c.commit()
        old_rows = [dict(r) for r in c.execute('select * from files order by id')]
        old_units = [dict(r) for r in c.execute('select * from units order by id')]
        c.close()
        plan = {'candidate_name': 'Test.esp', 'candidate_sha256': m.mat.sha(mappings[0]['source']),
                'replace_sha256': m.sha_bytes(prior[paths[0]]) if replacement else None,
                'mappings': mappings, 'profiles': [], 'source_pins': [], 'staged_pins': []}
        prepared = job / 'prepared.json'
        m.save_new(prepared, plan)
        calls = [0]
        crashed = None
        if mode.startswith('crash_'):
            child = '''import os,sys
from types import SimpleNamespace
from pathlib import Path
import install_verified_patch as m
prepared,target,db,mode=sys.argv[1:]
m.mat.TARGET=Path(target);m.mat.DB=Path(db);m.mat.RESERVE=0
m.check_plan=lambda p,verify_current=True:None
original=m.mat.make_private
calls=[0]
def crash(src,dst,st):
    calls[0]+=1
    if mode in ('crash_before_copy','crash_replacement') and calls[0]==2:os._exit(42)
    result=original(src,dst,st)
    if mode=='crash_after_copy' and calls[0]==7:os._exit(43)
    return result
m.mat.make_private=crash
m.install_unlocked(SimpleNamespace(prepared=prepared))
'''
            with (root / 'crash_stdout.log').open('w', encoding='utf-8') as stream:
                crashed = subprocess.run([sys.executable, '-B', '-c', child, str(prepared), str(runtime), str(m.mat.DB), mode],
                                         cwd=m.HERE, stdout=stream, stderr=subprocess.STDOUT)
            assert crashed.returncode == (43 if mode == 'crash_after_copy' else 42)
            assert (job / 'install_started.json').is_file() and not (job / 'installed.json').exists()
            started = m.load(job / 'install_started.json')
            live = dict(started, install_pid=os.getpid())
            (job / 'install_started.json').write_text(json.dumps(live), encoding='utf-8')
            rejects(lambda: m.recover_unlocked(SimpleNamespace(prepared=str(prepared))))
            (job / 'install_started.json').write_text(json.dumps(started), encoding='utf-8')
            drifted = runtime / paths[0]
            correct = drifted.read_bytes()
            drifted.write_bytes(b'external drift')
            rejects(lambda: m.recover_unlocked(SimpleNamespace(prepared=str(prepared))))
            drifted.write_bytes(correct)
            lock = m.HERE / 'install.lock'
            assert not lock.exists() or m.load(lock).get('operation_finished') is True or not m.pid_running(m.load(lock)['pid']), 'An unrelated installer must not be active during fixture recovery'
            lock.write_text(json.dumps({'pid': started['install_pid'], 'prepared': str(prepared)}) + '\n', encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                m.locked_operation(SimpleNamespace(prepared=str(prepared)), m.recover_unlocked, recovery=True)
            assert m.load(lock)['operation_finished'] is True
        else:
            def atomic(src, dst, st):
                calls[0] += 1
                if mode == 'rollback' and calls[0] == 2:
                    raise RuntimeError('Injected failure after the first atomic copy')
                return saved[4](src, dst, st)
            m.mat.make_private = atomic
            with contextlib.redirect_stdout(io.StringIO()):
                try:
                    m.install_unlocked(SimpleNamespace(prepared=str(prepared)))
                except RuntimeError:
                    assert mode == 'rollback'
        c = m.mat.connect()
        rows = [dict(r) for r in c.execute('select * from files order by id')]
        units = [dict(r) for r in c.execute('select * from units order by id')]
        integrity = c.execute('pragma integrity_check').fetchone()[0]
        c.close()
        assert integrity == 'ok'
        if mode != 'success':
            assert rows == old_rows and units == old_units
            for destination, blob in prior.items():
                assert (runtime / destination).read_bytes() == blob
            if mode.startswith('crash_'):
                assert not (runtime / paths[0]).exists() or replacement
                assert m.load(job / 'recovered.json')['status'] == 'INTERRUPTED_INSTALL_RECOVERED_NOT_ACCEPTED'
                assert not (job / 'install_started.json').exists() and (job / 'recovered_attempt.json').is_file()
            else:
                assert m.load(job / 'install_failure.json')['status'] == 'INSTALL_FAILED_ROLLED_BACK'
        else:
            assert len(rows) == 7 and len(units) == len(old_units) + 1
            assert all(r['status'] == 'materialized' and r['storage'] == 'private' for r in rows)
            assert m.load(job / 'installed.json')['accepted'] is False
            for mapping in mappings:
                dst = runtime / mapping['destination']
                assert m.mat.sha(dst) == m.mat.sha(mapping['source']) and dst.stat().st_nlink == 1
        return {'fixture': str(root), 'atomic_calls': calls[0], 'journal_rows': len(rows),
                'crash_exit_code': crashed.returncode if crashed else None}
    try:
        success = journal_fixture('success')
        result.append({'case': 'seven private atomic copies and journal replacements succeed but acceptance remains false', 'passed': True, **success})
        rollback = journal_fixture('rollback')
        result.append({'case': 'injected second-copy failure restores exact prior bytes and journal rows', 'passed': True, **rollback})
        for mode in ['crash_before_copy', 'crash_after_copy', 'crash_replacement']:
            recovered = journal_fixture(mode)
            result.append({'case': 'actual child-process crash recovers bytes and complete journal: ' + mode, 'passed': True, **recovered})
    finally:
        m.mat.TARGET, m.mat.DB, m.mat.RESERVE, m.check_plan, m.mat.make_private = saved
    output = {'utc': m.mat.utc(), 'status': 'PASS_RESEARCH_FIXTURES_AND_READONLY_PROFILE_PREFLIGHT',
              'installer_sha256': m.mat.sha(m.__file__), 'cases': result, 'actual_profile_previews': physical_plans,
              'limits': 'No real runtime/profile/journal mutation. Fixture I/O exercises explicitly bypass producer guards; those gates are separately checked. No actual candidate installed or accepted.'}
    path = folder / 'validation.json'
    m.save_new(path, output)
    m.save_new(m.HERE / ('validation_' + folder.name + '.json'), output)
    print(json.dumps({'status': output['status'], 'checks': len(result), 'report': str(path)}, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
