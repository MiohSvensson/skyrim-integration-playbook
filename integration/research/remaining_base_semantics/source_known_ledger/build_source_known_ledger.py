"""Freeze source-known diagnostics with record identities, scope and dispositions.

Historical sweeps are targeted, not proof that every record of a zero-row plugin
was checked. The classifier therefore never calls a new diagnostic 'upstream'
merely because its plugin occurred in an old run.
"""
from pathlib import Path
from datetime import datetime, timezone
import collections
import json
import re
import sqlite3
import sys

sys.dont_write_bytecode = True
from diagnostic_identity import BASE, PluginReader, canonical_id, file_sha, field_path, key_for, message_identity, record_context

OUT = Path(__file__).resolve().parent


def authoritative_map(path):
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    begin = text.rfind('SWEEP_BEGIN\t')
    text = text[begin:] if begin >= 0 else text
    result = {}
    for name, raw in re.findall(r'SWEEP_FILE\t([^\t\r\n]+)\t([0-9A-Fa-f]{8})', text):
        value = int(raw, 16)
        prefix = value & (0xFFFFF000 if value >> 24 == 0xFE else 0xFF000000)
        if name.casefold().endswith(('.esp', '.esm', '.esl')): result[prefix] = name
    return result


def main():
    old = json.loads((BASE / 'repairs/diagnostic_ledger.json').read_text(encoding='utf-8'))
    sweep_refs = json.loads((BASE / 'repairs/sweep_references.json').read_text(encoding='utf-8'))
    base = json.loads((OUT.parents[1] / 'base_diagnostics/base_diagnostics.json').read_text(encoding='utf-8'))
    per_base = {r['plugin'].casefold(): r for r in base['per_plugin']}
    latest_log = Path(base['historical_snapshot']['log'])
    latest_map = authoritative_map(latest_log)
    assert latest_map, 'Latest source sweep lacks authoritative SWEEP_FILE mapping'
    sources = {'legacy-' + pack: {int(k, 16): v for k, v in info['prefixes'].items()} for pack, info in sweep_refs.items()}
    sources['consistent-stock-TuLED'] = latest_map
    rows = [r | {'source_run': 'legacy-' + r['pack'], 'path': r['path']} for r in old]
    for plugin in base['per_plugin']:
        for r in plugin['fields']:
            rows.append({'source_run': 'consistent-stock-TuLED', 'pack': 'TuLED', 'plugin': plugin['plugin'],
                         'record': r['record'], 'path': r['field_path'], 'message': r['message'], 'line': r['log_line']})
    profiles = {}
    active = set()
    for name in ('Unified Skyrim', 'Unified Build'):
        p = BASE / 'UnifiedSkyrim/profiles' / name / 'plugins.txt'
        if p.exists():
            names = [s[1:] for s in p.read_text(encoding='utf-8-sig').splitlines() if s.startswith('*')]
            profiles[name] = {'path': str(p), 'sha256': file_sha(p), 'active_explicit': len(names), 'plugins': names}
            active |= {n.casefold() for n in names}
    active |= {'skyrim.esm', 'update.esm', 'dawnguard.esm', 'hearthfires.esm', 'dragonborn.esm'}
    index = sqlite3.connect((BASE / 'baseline/plugin_records.sqlite').as_uri() + '?mode=ro', uri=True)
    files = {}
    for pack, name, path, declared_sha, count in index.execute('select pack,name,path,sha256,record_count from plugins'):
        files.setdefault((pack, name.casefold()), []).append({'path': path, 'indexed_sha256': declared_sha, 'indexed_record_count': count})
    readers = {}
    digest_cache = {}
    def reader(path):
        if path not in readers: readers[path] = PluginReader(path)
        return readers[path]
    def digest(path):
        if path not in digest_cache: digest_cache[path] = file_sha(path)
        return digest_cache[path]
    grouped = {}
    unresolved = []
    latest_keys = set()
    count = collections.Counter()
    for row in rows:
        mapping = sources[row['source_run']]
        parsed = record_context(row['record'], mapping, row['plugin'])
        if not parsed:
            unresolved.append(row | {'reason': 'No typed record identity in historical context'}); continue
        sig, identity = parsed
        message = message_identity(row['message'], mapping)
        case_key = key_for(row['plugin'], sig, identity, row['path'], message)
        source_record = None
        witnesses = []
        for f in files.get((row['pack'], row['plugin'].casefold()), []):
            r = reader(f['path']).get(sig, identity)
            if r:
                source_record = r
                witnesses.append(f | {'actual_sha256': digest(f['path']), 'record': r})
        if not witnesses:
            unresolved.append(row | {'canonical_record': identity, 'signature': sig, 'reason': 'Authoritative historical identity absent in indexed source snapshot; do not infer by suffix/name'}); continue
        record = grouped.setdefault(case_key, {'key': case_key, 'reporting_plugin': row['plugin'], 'signature': sig, 'record': identity,
            'field_path': row['path'], 'normalized_field_path': field_path(row['path']), 'message_identity': message,
            'raw_messages': set(), 'witnesses': {}, 'runs': collections.Counter(), 'active_name_in_captured_profiles': row['plugin'].casefold() in active})
        record['raw_messages'].add(row['message'])
        record['runs'][row['source_run']] += 1
        for w in witnesses:
            key = (row['pack'], w['path'], w['actual_sha256'])
            record['witnesses'][key] = w | {'pack': row['pack'], 'historical_context': row['record']}
        if row['source_run'] == 'consistent-stock-TuLED': latest_keys.add(case_key)
        count[row['source_run']] += 1
    repairs = json.loads((BASE / 'repairs/candidate_manifest.json').read_text(encoding='utf-8'))['files']
    repair_names = {r['plugin'].casefold() for r in repairs}
    disabled = {n.casefold() for n in base['actions']['disabled_plugin_union']}
    final = []
    for k, r in grouped.items():
        plugin = r['reporting_plugin'].casefold()
        prior = per_base.get(plugin)
        disposition = prior['disposition'] if prior else 'OTHER_PACK_HISTORICAL_SOURCE_DIAGNOSTIC'
        expected = 'REVIEW_AS_SOURCE_KNOWN_ONLY_AFTER_RECORD_FINGERPRINT_MATCH'
        reason = prior['cause_and_action'] if prior else 'No current semantic decision for this source diagnostic; preserve exact identity and review context.'
        if plugin in disabled: expected = 'MUST_NOT_BE_LOADED_DISABLED_SOURCE'
        elif plugin in ('synthesis - patch.esp', 'dyndolod.esm', 'dyndolod.esp', 'occlusion.esp'):
            expected = 'OLD_GENERATED_DIAGNOSTIC_MUST_NOT_BE_REINTRODUCED'
        elif plugin in ('gpposes.esp', 'collyposer.esp'):
            expected = 'MUST_BE_ABSENT_AFTER_POSE_REGISTRY_VARIANT'
        elif plugin in repair_names or disposition.startswith('APPLY_VERIFIED'):
            expected = 'MUST_BE_ABSENT_AFTER_VERIFIED_REPAIR_OR_RESTORATION'
        elif plugin == 'gosteddimensionalrift.esp' and r['record'].endswith('|2ED53E') and any(s in r['message_identity'].upper() for s in ('2F2640', '2F2641')):
            expected = 'MUST_BE_ABSENT_IF_RIFT_STALE_PROPERTY_CANDIDATE_IS_APPLIED'
        elif 'legacy-TuLED' in r['runs'] and k not in latest_keys:
            expected = 'OLDER_SOURCE_RUN_ONLY_NOT_PRESENT_IN_LATEST_TULED_BASELINE_REVIEW_IF_REAPPEARS'
        r = r | {'raw_messages': sorted(r['raw_messages']), 'witnesses': list(r['witnesses'].values()), 'runs': dict(r['runs']),
                 'max_historical_multiplicity': max(r['runs'].values()), 'latest_TuLED_baseline_present': k in latest_keys,
                 'semantic_disposition': disposition, 'expected_state': expected, 'reason': reason}
        final.append(r)
    passes = []
    for name in ('native_validation.json', 'full_candidate_validation.json', 'native_validation_variants_pose_registry_only.json'):
        path = BASE / 'repairs' / name
        for r in json.loads(path.read_text(encoding='utf-8')):
            if r.get('diagnostic_records') == 0:
                passes.append(r | {'provenance': str(path), 'scope_note': 'Only stated whole-plugin/targeted count and exact input hash; not global runtime compatibility.'})
    current_pass = BASE / 'UnifiedSkyrim/validation/equipment_repaired/result.json'
    if current_pass.exists():
        result = json.loads(current_pass.read_text(encoding='utf-8'))
        inputs = json.loads((current_pass.parent / 'input_inventory.json').read_text(encoding='utf-8'))
        hashed = {r['name'].casefold(): r for r in inputs['plugins']}
        if result['status'] == 'PASS' and file_sha(result['log']) == result['log_sha256']:
            for r in result['plugins']:
                if r['diagnostic_records'] != 0: continue
                inp = hashed[r['plugin'].casefold()]
                actual_count = len(reader(inp['path']).index())
                passes.append(r | {'pack': 'Unified-equipment-repaired', 'sha256': inp['sha256'], 'source_path': inp['path'],
                    'provenance': str(current_pass), 'log': result['log'], 'log_sha256': result['log_sha256'],
                    'whole_plugin_record_count_matches': actual_count == r['records'],
                    'scope_note': 'Actual final-VFS 52-target native pass before feature additions. New errors in the same byte input still require context/regression analysis.'})
    result = {'schema': 1, 'written_utc': datetime.now(timezone.utc).isoformat(), 'captured_profiles': profiles,
              'source_row_counts_included': dict(count), 'cases': sorted(final, key=lambda r: r['key']),
              'unresolved_historical_identities': unresolved, 'prior_zero_evidence': passes,
              'provenance': {'old_ledger': str(BASE/'repairs/diagnostic_ledger.json'), 'old_ledger_sha256': file_sha(BASE/'repairs/diagnostic_ledger.json'),
                             'latest_TuLED_log': str(latest_log), 'latest_TuLED_log_sha256': file_sha(latest_log)},
              'contract': [
                  'Historical SWEEP checked targeted masks, not all records in all plugins. Zero historical rows never implies the plugin was fully clean.',
                  'A source-known key requires reporting plugin, canonical origin+object ID, signature, exact field path and canonicalized diagnostic message.',
                  'Same key alone is insufficient: classifier also compares a namespace-aware exact record fingerprint including ordered raw subrecords, flags, masters, self filename, VCS1/2 and form version.',
                  'Unexpected diagnostics after repairs, excluded pose/generated/disabled inputs are regressions or context problems even when an old source identity matches.',
                  'Supported extensions, unresolved source defects and context-sensitive navigation/alias warnings remain distinct semantic categories. No blanket upstream label.',
                  'Unmapped identities or missing authoritative SWEEP_FILE mappings require review; never infer owners from current load-order suffixes.'
              ]}
    (OUT / 'source_known_ledger.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Ledger:', len(final), 'exact cases;', len(unresolved), 'unresolved historical identities;', sum(r['active_name_in_captured_profiles'] for r in final), 'active-name cases')


if __name__ == '__main__': main()
