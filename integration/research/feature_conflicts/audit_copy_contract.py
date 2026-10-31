"""Audit 4.1.5f copy flags and explicit parent-container closure in both drafts."""
from pathlib import Path
import collections
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True
from analyze_fields import BASE, OUT, scan


def main():
    results = []
    for filename, rowkey in (('compat_patch_plan.json', 'priority_seed_records'), ('quest_extension_plan.json', 'rows')):
        plan = json.loads((OUT / filename).read_text(encoding='utf-8'))
        rows = plan[rowkey]
        positions = {(r['origin'], int(r['object_id'], 16)): i for i, r in enumerate(rows)}
        wanted = collections.defaultdict(set)
        for r in rows: wanted[r.get('seed_path', r.get('base_path'))].add((r['origin'], int(r['object_id'], 16)))
        ancestry = []
        for path, keys in wanted.items():
            records = scan(path, wanted=keys)[0]
            for key, r in records.items():
                for typ, label in r['groups']:
                    if typ in (1, 6, 7):
                        parent = tuple(label)
                        ok = parent in positions and positions[parent] < positions[key]
                        ancestry.append({'record': f'{key[0]}|{key[1]:06X}', 'group_type': typ,
                                         'parent': f'{parent[0]}|{parent[1]:06X}', 'explicit_parent_seeded_first': ok})
        assert all(r['explicit_parent_seeded_first'] for r in ancestry)
        results.append({'plan': filename, 'seed_count': len(rows), 'parent_edges': ancestry, 'passed': True})
    copies = []
    for path in sorted(OUT.glob('Database*Draft.pas')):
        if path.name=='DatabaseComparatorSelfAuditDraft.pas':continue
        code = path.read_text(encoding='utf-8')
        flags = re.findall(r'wbCopyElementTo(?:File|Record)\([^\n]*\)', code)
        assert flags and all(re.search(r',\s*(?:False|True),\s*True\)$', s) for s in flags), (path, flags)
        copies.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'copy_calls': flags})
    report = {'passed': True, 'plans': results, 'drafts': copies,
              'source_provenance': str(OUT/'source_4_1_5f/provenance.json'),
              'primary_sources': [
                  {'path': str(OUT/'source_4_1_5f/xejviScriptAdapter.pas'), 'lines': [755, 794], 'fact': 'Script copy adapters call core wbCopyElementToFile/Record with the exact aAsNew/aDeepCopy booleans.'},
                  {'path': str(OUT/'source_4_1_5f/wbImplementation.pas'), 'lines': [161, 185], 'fact': 'Ancestor recursion uses False/False; requested source receives the caller flags through AddIfMissing.'},
                  {'path': str(OUT/'source_4_1_5f/wbImplementation.pas'), 'lines': [15887, 16015], 'fact': 'CopyMainRecord assigns payload only when aDeepCopy=True; direct main-record copying does not iterate its ChildGroup.'},
                  {'path': str(OUT/'source_4_1_5f/wbImplementation.pas'), 'lines': [8579, 8588], 'fact': 'Main-record assignment omits fields explicitly marked dfNoCopyAsOverride when copying an override.'},
                  {'path': str(OUT/'source_4_1_5f/wbDefinitionsCommon.pas'), 'lines': [803, 819], 'fact': 'DIAL INOM/INOA are internal INFO-order metadata marked dfDontAssign/dfDontSave; omission is permitted, never forced into serialized gameplay payload.'}],
              'limits': 'Source-level/API/ancestry validation only; actual xEdit execution and post-export record-set verification remain required.'}
    (OUT / 'copy_contract_audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Copy contract: PASS, all main-record/field calls deep=True; both parent closures explicit and ordered')


if __name__ == '__main__': main()
