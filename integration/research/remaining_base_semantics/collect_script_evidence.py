"""Extract exact inventoried PEX variants and decompile in this directory only."""
from pathlib import Path
import collections
import concurrent.futures
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
from bsarch_readonly import extract_files


def main():
    db = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    requested = collections.defaultdict(dict)
    # Whole BenDoon source script set: dynamic package-lookup audit.
    for archive in (114, 189, 230):
        for key, digest in db.execute("select path_key,sha256 from bsa_entries where archive_id=? and path_key like 'scripts/%.pex'", (archive,)):
            requested[archive][key] = digest
    assert len(requested[114]) == 199
    specific = {
        189: ['gostteleportlocked.pex'],
        359: ['defaultdisableotherobjectwhentaken.pex'],
        511: ['sprigganfxscript.pex'],
        68: ['defaultdisableotherobjectwhentaken.pex', 'sprigganfxscript.pex'],
        117: ['wt_tif__023943af.pex', 'wt_tif__023943b2.pex', 'wt_qf_wtkillthalmor_023943a0.pex'],
    }
    missing = []
    for archive, names in specific.items():
        for name in names:
            key = 'scripts/' + name
            r = db.execute('select sha256 from bsa_entries where archive_id=? and path_key=?', (archive, key)).fetchone()
            if r: requested[archive][key] = r[0]
            else: missing.append({'archive': archive, 'requested': key})
    tool = BASE / 'tools/Champollion-1.3.2/Champollion.exe'
    jobs = []
    sources = []
    for archive, expected in requested.items():
        path = Path(db.execute('select path from bsa_archives where id=?', (archive,)).fetchone()[0])
        extracted = extract_files(path, expected)
        assert len(extracted) == len(expected)
        folder = OUT / 'scripts' / f'archive_{archive}'
        for name in ('pex', 'psc', 'asm', 'tmp'):
            (folder / name).mkdir(parents=True, exist_ok=True)
        for key, data in extracted.items():
            pex = folder / 'pex' / Path(key).name
            pex.write_bytes(data)
            assert hashlib.sha256(data).hexdigest() == expected[key]
            jobs.append((archive, pex, folder))
        sources.append({'archive_id': archive, 'path': str(path), 'extracted_count': len(extracted), 'entry_sha256': expected})
    def run(job):
        archive, pex, folder = job
        env = os.environ.copy(); env['TEMP'] = env['TMP'] = str(folder / 'tmp')
        args = [str(tool), str(pex), '-p', str(folder / 'psc'), '-a', str(folder / 'asm'), '--no-debug-line']
        p = subprocess.run(args, cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        source = folder / 'psc' / (pex.stem + '.psc')
        asm = folder / 'asm' / (pex.stem + '.pas')
        # Champollion assembly suffix is .pas; actual existence is checked below.
        asm_outputs = list((folder / 'asm').glob(pex.stem + '.*'))
        return {'archive_id': archive, 'pex': str(pex), 'sha256': hashlib.sha256(pex.read_bytes()).hexdigest(),
                'return_code': p.returncode, 'stdout': p.stdout.decode('utf-8', 'replace'),
                'psc': str(source), 'psc_exists': source.exists(), 'asm_outputs': [str(x) for x in asm_outputs]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(run, jobs))
    failed = [r for r in runs if r['return_code'] or not r['psc_exists'] or not r['asm_outputs'] or 'ERROR:' in r['stdout']]
    (OUT / 'scripts/decompiler.log').write_text('\n'.join(r['pex'] + '\n' + r['stdout'] for r in runs), encoding='utf-8')
    patterns = {'ben_horse_package_literal': re.compile(r'(?i)(SKQFollowOnHorse|0x0*4A1A3\b|\b303523\b)'),
                'dynamic_lookup_calls': re.compile(r'(?i)\b(?:Game\.)?GetForm(?:FromFile)?\s*\(')}
    matches = {k: [] for k in patterns}
    for r in runs:
        if r['archive_id'] != 114 or not r['psc_exists']: continue
        for n, line in enumerate(Path(r['psc']).read_text(encoding='utf-8-sig').splitlines(), 1):
            for name, pattern in patterns.items():
                if pattern.search(line): matches[name].append({'path': r['psc'], 'line': n, 'text': line.strip()})
    report = {'tool': str(tool), 'tool_sha256': hashlib.sha256(tool.read_bytes()).hexdigest(), 'sources': sources,
              'runs': runs, 'failed': failed, 'missing_requested_entries': missing, 'BenDoon_all_199_PEX_search': matches,
              'scope': 'SHA-verified inventoried extraction; exact compiled bytes decompiled to PSC/ASM. Static source consumption only; not game runtime validation.'}
    (OUT / 'script_evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Script evidence:', len(runs), 'compiled scripts, failures', len(failed), 'missing requests', missing)
    assert not failed


if __name__ == '__main__': main()
