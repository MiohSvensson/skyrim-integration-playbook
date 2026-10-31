"""Exercise acceptance/rejection against real input bytes and labelled fixtures.

Fixtures are not xEdit runs. They test that inventory tampering, incomplete
coverage, unmatched errors and names-only maps cannot yield completion.
"""
from pathlib import Path
import json
import sys

sys.dont_write_bytecode = True
from classify_full_check import OUT, execute, parse_run
from diagnostic_identity import BASE, PluginReader, file_sha


def main():
    root = OUT / 'parser_validation'
    root.mkdir(exist_ok=True)
    inventory = json.loads((BASE / 'UnifiedSkyrim/validation/equipment_repaired/input_inventory.json').read_text(encoding='utf-8'))
    row = next(r for r in inventory['plugins'] if r['name'] == '(lilyrim)fangfeizhuzhi.esp')
    reader = PluginReader(row['path']); records = reader.index(); n = len(records)
    (root / 'input_inventory.json').write_text(json.dumps({'fixture': True, 'plugins': [row]}, indent=2), encoding='utf-8')
    clean = '\n'.join(['SYNTHETIC PARSER FIXTURE - NOT AN XEDIT RUN',
        'UNIFIED_BEGIN\t2\t1', f'UNIFIED_FILE\t{row["name"]}\t00000800\t{n}', 'UNIFIED_SCOPE\t1',
        f'UNIFIED_PLUGIN\t{row["name"]}\t{n}\t0\t0\t{n}', f'UNIFIED_COMPLETE\t{n}\t0\t0\t1',
        f'FULL_AUDIT_COMPLETED\t2\t{n}\t0\t0', ''])
    results = []

    def check(name, log_text, blocked, inv=None):
        log = root / (name + '.log'); log.write_text(log_text, encoding='utf-8')
        result = execute(log, inv or root / 'input_inventory.json', None, root / (name + '.json'))
        assert result['completion_blocked_by_unknown_regression_or_invalid_check'] == blocked, result['status']
        results.append({'case': name, 'status': result['status'], 'correctly_blocked': blocked,
                        'scope_problems': result['scope_or_integrity_problems'], 'class_counts': result['class_counts']})
    check('complete_no_error_fixture', clean, False)
    check('missing_final_marker', clean.replace(f'FULL_AUDIT_COMPLETED\t2\t{n}\t0\t0', ''), True)
    check('missing_record_coverage', clean.replace(f'UNIFIED_PLUGIN\t{row["name"]}\t{n}\t', f'UNIFIED_PLUGIN\t{row["name"]}\t{n-1}\t'), True)
    bad_inventory = root / 'changed_sha_inventory.json'
    bad_inventory.write_text(json.dumps({'fixture': True, 'plugins': [row | {'sha256': '0' * 64}]}), encoding='utf-8')
    check('changed_inventory_hash', clean, True, bad_inventory)
    sig, identity = next(k for k in records if k[0] != 'TES4' and k[1].split('|')[0] == row['name'].casefold())
    own = identity.split('|')[1]; context = 'Fixture [' + sig + ':00' + own + ']'
    detail = '\t'.join(['UNIFIED_DETAIL', row['name'], context, 'EDID', 'Deliberate unmatched fixture diagnostic', row['name'], own, sig, 'Fixture\\EDID'])
    unknown = clean.replace('UNIFIED_SCOPE\t1', 'UNIFIED_SCOPE\t1\n' + detail)
    unknown = unknown.replace(f'\t{n}\t0\t0\t{n}', f'\t{n}\t1\t1\t{n}').replace(f'UNIFIED_COMPLETE\t{n}\t0\t0\t1', f'UNIFIED_COMPLETE\t{n}\t0\t1\t1').replace(f'FULL_AUDIT_COMPLETED\t2\t{n}\t0\t0', f'FULL_AUDIT_COMPLETED\t2\t{n}\t1\t0')
    check('new_unmatched_diagnostic', unknown, True)
    try:
        parse_run(clean.replace('UNIFIED_FILE', 'UNIFIED_LOADED'))
    except ValueError as ex:
        results.append({'case': 'names_only_prefix_map', 'rejected': True, 'reason': str(ex)})
    else: raise AssertionError('Names-only map was accepted')
    result = {'passed': True, 'fixture_only_not_xedit_execution': True, 'source_plugin': row['path'],
              'source_plugin_sha256': file_sha(row['path']), 'actual_physical_record_count': n, 'cases': results}
    (OUT / 'parser_validation_result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Parser acceptance/rejection validation:', len(results), 'cases PASS; no xEdit execution claimed')


if __name__ == '__main__': main()
