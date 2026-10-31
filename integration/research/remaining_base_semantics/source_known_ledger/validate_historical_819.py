"""Reconcile all 819 preserved TuLED fields; this cannot certify final scope."""
import json
import sqlite3
import sys

sys.dont_write_bytecode = True
from classify_full_check import OUT, execute, parse_run
from diagnostic_identity import BASE


def main():
    ledger = json.loads((OUT / 'source_known_ledger.json').read_text(encoding='utf-8'))
    log = BASE / 'repairs/TuLED/sweep-0e0dedd6a3a5/logs/xedit.log'
    run = parse_run(log.read_text(encoding='utf-8-sig', errors='replace'), historical=True)
    db = sqlite3.connect((BASE / 'baseline/plugin_records.sqlite').as_uri() + '?mode=ro', uri=True)
    physical = {name.casefold(): path for name, path in db.execute("select name,path from plugins where pack='TuLED'")}
    for case in ledger['cases']:
        for w in case['witnesses']:
            if w['pack'] == 'TuLED': physical[case['reporting_plugin'].casefold()] = w['path']
    for name in ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm'):
        p = BASE / 'repairs/consistent_stock/Data' / name
        if p.exists(): physical[name.casefold()] = str(p)
    output = OUT / 'parser_validation/historical_819_file_map.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(physical, ensure_ascii=False, indent=2), encoding='utf-8')
    report = OUT / 'parser_validation/historical_819_classification.json'
    result = execute(log, None, output, report, historical=True)
    assert len(result['diagnostics']) == 819
    assert all(r.get('source_case') for r in result['diagnostics']), 'A preserved diagnostic did not match its exact ledger identity'
    assert all(r['source_case']['exact_record_payload_match'] for r in result['diagnostics']), 'Historical source payload no longer matches'
    assert result['completion_blocked_by_unknown_regression_or_invalid_check']
    print('All 819 historical diagnostics exact identity/payload match; final-completion certification disabled')
    print(result['class_counts'])


if __name__ == '__main__': main()
