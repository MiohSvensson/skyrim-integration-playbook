"""Classify the exact final all-active Check log, inventory and known identities.

Default final mode requires v2 script markers, exact input inventory hashes,
authoritative engine prefixes and whole-plugin coverage. Historical SWEEP logs
require --historical-targeted and cannot certify completion. No unknown diagnostic
is automatically labelled upstream.
"""
from pathlib import Path
import argparse
import collections
import json
import re
import sys

sys.dont_write_bytecode = True
from diagnostic_identity import PluginReader, field_path, file_sha, key_for, message_identity, record_context

OUT = Path(__file__).resolve().parent


def parse_run(log_text, historical=False):
    starts = list(re.finditer(r'(?:SWEEP|UNIFIED)_BEGIN\t', log_text))
    if not starts:
        raise ValueError('No Check begin marker; arbitrary or failed builder logs are not Check results')
    text = log_text[starts[-1].start():]
    rows = []; exceptions = []; mapping = {}; names = {}; native_counts = {}; plugins = []
    problems = []
    for lineno, line in enumerate(text.splitlines(), 1):
        match = re.search(r'(?:SWEEP|UNIFIED)_(?:FILE|DETAIL|PLUGIN|EXCEPTION)\t', line)
        if not match: continue
        parts = line[match.start():].split('\t')
        marker = parts[0].split('_', 1)[1]
        if marker == 'FILE':
            if len(parts) < 3 or not re.fullmatch('[0-9A-Fa-f]{8}', parts[2]):
                problems.append('Malformed authoritative file-prefix line ' + str(lineno)); continue
            name, raw = parts[1], parts[2]
            if not name.casefold().endswith(('.esp', '.esm', '.esl')): continue
            value = int(raw, 16)
            prefix = value & (0xFFFFF000 if value >> 24 == 0xFE else 0xFF000000)
            if prefix in mapping or name.casefold() in names:
                problems.append('Duplicate engine file name/prefix: ' + name)
            mapping[prefix] = name; names[name.casefold()] = name
            if len(parts) >= 4:
                try: native_counts[name.casefold()] = int(parts[3])
                except ValueError: problems.append('Noninteger native record count for ' + name)
        elif marker == 'DETAIL':
            if len(parts) not in (5, 9):
                problems.append('Malformed detail line ' + str(lineno)); continue
            row = {'plugin': parts[1], 'record_context': parts[2], 'field_path': parts[3], 'message': parts[4], 'line_in_selected_run': lineno}
            if len(parts) == 9:
                row |= {'explicit_owner': parts[5], 'explicit_object_id': parts[6], 'explicit_signature': parts[7], 'full_typed_path': parts[8]}
            elif not historical: problems.append('Final run detail lacks v2 explicit identity/FullPath at line ' + str(lineno))
            rows.append(row)
        elif marker == 'EXCEPTION':
            exceptions.append({'parts': parts[1:], 'line_in_selected_run': lineno})
        elif marker == 'PLUGIN':
            try:
                r = {'plugin': parts[1], 'checked_records': int(parts[2]), 'bad_records': int(parts[3])}
                if len(parts) >= 6: r |= {'reported_diagnostic_fields': int(parts[4]), 'native_record_count': int(parts[5])}
                elif not historical: problems.append('Final plugin summary lacks v2 field/native counts: ' + parts[1])
                plugins.append(r)
            except (ValueError, IndexError): problems.append('Malformed plugin summary at line ' + str(lineno))
    if not mapping: raise ValueError('No authoritative UNIFIED_FILE/SWEEP_FILE engine-prefix map. UNIFIED_LOADED names are insufficient.')
    complete_match = re.search(r'(?:SWEEP|UNIFIED)_COMPLETE\t([^\r\n]+)', text)
    marker_match = re.search(r'FULL_AUDIT_COMPLETED\t([^\r\n]+)', text)
    complete = None; marker = None
    try:
        if complete_match: complete = [int(s) for s in complete_match[1].split('\t')]
        if marker_match: marker = [int(s) for s in marker_match[1].split('\t')]
    except ValueError: problems.append('Noninteger completion marker')
    if not complete: problems.append('No complete marker')
    if not historical:
        if not re.match(r'UNIFIED_BEGIN\t2\t\d+', text): problems.append('Final mode requires v2 UNIFIED_BEGIN schema')
        if not complete or len(complete) != 4: problems.append('Final complete marker requires total/exceptions/diagnostics/files')
        if not marker or len(marker) != 4 or marker[0] != 2: problems.append('Missing/malformed FULL_AUDIT_COMPLETED v2 marker')
        if complete and marker and len(complete) == 4 and len(marker) == 4:
            if marker[1:] != [complete[0], complete[2], complete[1]]: problems.append('Completion markers disagree')
        if complete and len(complete) == 4:
            if complete[0] != sum(r['checked_records'] for r in plugins): problems.append('Total count differs from plugin summaries')
            if complete[1] != len(exceptions): problems.append('Exception count differs from exception lines')
            if complete[2] != len(rows): problems.append('Diagnostic count differs from detail lines')
            if complete[3] != len(mapping) or complete[3] != len(plugins): problems.append('File count differs from prefix/summary maps')
        if len(native_counts) != len(mapping): problems.append('Missing initialization native counts')
    return {'mapping': mapping, 'names': names, 'native_counts': native_counts, 'rows': rows,
            'plugins': plugins, 'exceptions': exceptions, 'complete': complete, 'marker': marker, 'problems': problems}


def load_inputs(inventory_path, file_map_path, historical):
    inventory = json.loads(inventory_path.read_text(encoding='utf-8-sig')) if inventory_path else None
    paths = {}; declared = {}; problems = []
    if inventory:
        for r in inventory['plugins']:
            name = r['name'].casefold()
            if name in paths: problems.append('Duplicate inventory plugin: ' + r['name'])
            paths[name] = Path(r['path']); declared[name] = r['sha256'].casefold()
    elif not historical: raise ValueError('Final mode requires --input-inventory with exact paths and SHA256')
    if file_map_path:
        physical = json.loads(file_map_path.read_text(encoding='utf-8-sig'))
        for n, p in physical.items():
            name = n.casefold()
            if inventory and (name not in paths or paths[name].resolve() != Path(p).resolve()):
                problems.append('File map disagrees with inventory: ' + n)
            elif not inventory: paths[name] = Path(p)
    if not paths: raise ValueError('No resolved physical plugin inputs')
    return inventory, paths, declared, problems


def classify(run, ledger, physical, hashes, readers):
    cases = {r['key']: r for r in ledger['cases']}
    by_record = collections.defaultdict(list); by_field = collections.defaultdict(list)
    for r in ledger['cases']:
        by_record[(r['signature'], r['record'])].append(r)
        by_field[(r['signature'], r['record'], r['normalized_field_path'], r['message_identity'])].append(r)
    prior_zeros = collections.defaultdict(list)
    for r in ledger['prior_zero_evidence']:
        h = r.get('sha256') or r.get('candidate_sha256') or r.get('validated_candidate_sha256')
        if h: prior_zeros[(r['plugin'].casefold(), h)].append(r)
    rift = OUT.parent / 'rift_stale_property_evidence.json'
    rift_hash = json.loads(rift.read_text(encoding='utf-8'))['candidate_sha256'] if rift.exists() else None
    rows = []; occurrences = collections.Counter(); counts = collections.Counter()
    for row in run['rows']:
        plugin = row['plugin'].casefold()
        context = record_context(row['record_context'], run['mapping'], row['plugin'])
        if 'explicit_owner' in row:
            explicit = None
            if re.fullmatch('[0-9A-Fa-f]{6}', row['explicit_object_id']) and re.fullmatch('[A-Z0-9_]{4}', row['explicit_signature']):
                explicit = (row['explicit_signature'], row['explicit_owner'].casefold() + '|' + row['explicit_object_id'].upper())
            if not explicit or row['explicit_owner'].casefold() not in run['names'] or (context and context != explicit):
                run['problems'].append('Invalid/disagreeing explicit identity at diagnostic line ' + str(row['line_in_selected_run'])); context = None
            else: context = explicit
        if not context or context[1].startswith('UNMAPPED:'):
            rows.append(row | {'classification': 'UNMAPPED_RECORD_IDENTITY_REQUIRES_REVIEW'}); counts[rows[-1]['classification']] += 1; continue
        sig, identity = context
        message = message_identity(row['message'], run['mapping'])
        key = key_for(plugin, sig, identity, row['field_path'], message)
        case = cases.get(key); current = readers.get(plugin)
        try: record = current.get(sig, identity) if current else None
        except Exception as ex:
            run['problems'].append('Cannot fingerprint diagnostic record ' + identity + ': ' + repr(ex)); record = None
        record_sha = record['record_payload_sha256'] if record else None
        occurrences[key] += 1
        classification = 'NEW_DIAGNOSTIC_UNMATCHED_REQUIRES_REVIEW'; case_info = None
        possible_forwards = by_field.get((sig, identity, field_path(row['field_path']), message), [])
        if case:
            policy = case['expected_state']
            same = any(w['record']['record_payload_sha256'] == record_sha for w in case['witnesses']) if record_sha else False
            case_info = {'key': case['key'], 'expected_state': policy, 'semantic_disposition': case['semantic_disposition'],
                         'reason': case['reason'], 'exact_record_payload_match': same,
                         'source_witnesses': [{'pack': w['pack'], 'path': w['path'], 'sha256': w['actual_sha256']} for w in case['witnesses']]}
            if policy == 'MUST_NOT_BE_LOADED_DISABLED_SOURCE': classification = 'REGRESSION_DISABLED_SOURCE_WAS_CHECKED'
            elif policy.startswith('OLD_GENERATED'): classification = 'REGRESSION_OLD_GENERATED_DIAGNOSTIC_REINTRODUCED'
            elif policy.startswith('MUST_BE_ABSENT_IF_RIFT'):
                classification = 'REGRESSION_RIFT_CANDIDATE_NOT_EFFECTIVE' if hashes.get(plugin) == rift_hash else 'REGRESSION_KNOWN_STALE_PROPERTY_REPAIR_NOT_APPLIED'
            elif policy.startswith('MUST_BE_ABSENT'): classification = 'REGRESSION_VERIFIED_REPAIR_OR_VARIANT_NOT_EFFECTIVE'
            elif policy.startswith('OLDER_SOURCE_RUN_ONLY'): classification = 'OLDER_SOURCE_DIAGNOSTIC_REAPPEARED_REQUIRES_CONTEXT_REVIEW'
            elif not same: classification = 'SOURCE_IDENTITY_MATCH_BUT_PAYLOAD_OR_NAMESPACE_CHANGED_REQUIRES_REVIEW'
            elif occurrences[key] > case['max_historical_multiplicity']: classification = 'EXCESS_DIAGNOSTIC_MULTIPLICITY_REQUIRES_REVIEW'
            elif 'navmesh' in row['message'].casefold(): classification = 'KNOWN_SOURCE_RECORD_NAVIGATION_DIAGNOSTIC_GEOMETRY_CONTEXT_STILL_REQUIRED'
            elif 'alias' in row['message'].casefold(): classification = 'KNOWN_SOURCE_RECORD_ALIAS_DIAGNOSTIC_SCRIPT_CONTEXT_STILL_REQUIRED'
            elif case['semantic_disposition'] == 'KEEP_SUPPORTED_EXTENSION': classification = 'KNOWN_SOURCE_SUPPORTED_EXTENSION_RECORD_VERIFIED'
            else: classification = 'KNOWN_SOURCE_RECORD_AND_DIAGNOSTIC_VERIFIED_SEMANTIC_STATUS_RETAINED'
        elif possible_forwards:
            classification = 'POSSIBLE_FORWARDED_KNOWN_FIELD_DIAGNOSTIC_REQUIRES_TYPED_PROVENANCE'
        elif prior_zeros.get((plugin, hashes.get(plugin))):
            classification = 'NEW_DIAGNOSTIC_ON_EXACT_PREVIOUSLY_ZERO_INPUT_REQUIRES_CONTEXT_REVIEW'
        elif by_record.get((sig, identity)):
            classification = 'NEW_FIELD_OR_MESSAGE_ON_KNOWN_RECORD_REQUIRES_REVIEW'
        if record is None: run['problems'].append('Diagnostic record absent from hashed reporting file: ' + plugin + ' / ' + sig + ' / ' + identity)
        rows.append(row | {'signature': sig, 'canonical_record': identity, 'message_identity': message,
                           'classification': classification, 'source_case': case_info,
                           'current_provider': str(physical[plugin]) if plugin in physical else None,
                           'current_plugin_sha256': hashes.get(plugin), 'current_record_payload_sha256': record_sha,
                           'possible_known_record_cases': len(by_record.get((sig, identity), [])),
                           'possible_forwarded_cases': [{'source_reporting_plugin': c['reporting_plugin'], 'source_case_key': c['key'],
                               'expected_state': c['expected_state'], 'semantic_disposition': c['semantic_disposition'],
                               'proof_required': 'Read-only typed canonical leaf comparison or frozen builder/reload record-field provenance, including remapped LinksTo targets. Same key under a different reporting plugin is not proof.'}
                               for c in possible_forwards if c['reporting_plugin'].casefold() != plugin]})
        counts[classification] += 1
    return rows, counts


def execute(log, inventory_path, file_map_path, report, historical=False):
    if not report.resolve().is_relative_to(OUT.resolve()): raise ValueError('Report must remain in source_known_ledger')
    ledger_path = OUT / 'source_known_ledger.json'
    ledger = json.loads(ledger_path.read_text(encoding='utf-8'))
    run = parse_run(log.read_text(encoding='utf-8-sig', errors='replace'), historical)
    inventory, physical, declared, problems = load_inputs(inventory_path, file_map_path, historical)
    run['problems'] += problems
    loaded = set(run['names']); all_inputs = set(physical)
    if not historical and loaded != all_inputs:
        run['problems'].append('Runtime prefix map and inventory differ: unloaded inputs=' + repr(sorted(all_inputs-loaded)) + '; noninventory loaded=' + repr(sorted(loaded-all_inputs)))
    readers = {}; hashes = {}; input_checks = []
    for name in sorted(loaded):
        path = physical.get(name); entry = {'plugin': run['names'][name], 'path': str(path) if path else None}
        try:
            if path is None: raise ValueError('No physical input provider')
            hashes[name] = file_sha(path); readers[name] = PluginReader(path)
            entry |= {'sha256': hashes[name], 'declared_sha256': declared.get(name), 'physical_record_count_including_header': len(readers[name].index())}
            if path.name.casefold() != name: raise ValueError('Provider basename differs from plugin identity')
            if name in declared and hashes[name] != declared[name]: raise ValueError('Input hash changed after inventory capture')
        except Exception as ex:
            entry['error'] = repr(ex); run['problems'].append('Input validation failed for ' + name + ': ' + repr(ex))
        input_checks.append(entry)
    rows, counts = classify(run, ledger, physical, hashes, readers)
    details = collections.Counter(r['plugin'].casefold() for r in run['rows'])
    bad_ids = collections.defaultdict(set)
    for r in rows:
        if r.get('canonical_record'): bad_ids[r['plugin'].casefold()].add((r['signature'], r['canonical_record']))
    summaries = {}; checked = []
    for r in run['plugins']:
        name = r['plugin'].casefold()
        if name in summaries: run['problems'].append('Duplicate plugin summary: ' + r['plugin'])
        summaries[name] = r
        current = len(readers[name].index()) if name in readers else None
        same = current == r['checked_records']
        item = r | {'physical_record_count_including_header': current, 'whole_plugin_count_matches': same,
                    'actual_detail_lines': details[name], 'plugin_sha256': hashes.get(name)}
        if not historical:
            if not same: run['problems'].append('Whole-plugin physical record coverage mismatch: ' + r['plugin'])
            if run['native_counts'].get(name) != r['checked_records'] or r.get('native_record_count') != r['checked_records']:
                run['problems'].append('Initialize/final native/checked counts disagree: ' + r['plugin'])
            if r.get('reported_diagnostic_fields') != details[name]: run['problems'].append('Detail count differs from summary: ' + r['plugin'])
            if not run['exceptions'] and r['bad_records'] != len(bad_ids[name]): run['problems'].append('Bad-record identity count differs: ' + r['plugin'])
        checked.append(item)
    if not historical and set(summaries) != loaded: run['problems'].append('Not every loaded plugin has exactly one summary')
    disabled = {r['reporting_plugin'].casefold() for r in ledger['cases'] if r['expected_state'] == 'MUST_NOT_BE_LOADED_DISABLED_SOURCE'}
    disabled_loaded = sorted(disabled & loaded)
    if disabled_loaded and not historical: run['problems'].append('Excluded optional plugin is loaded even without diagnostics: ' + repr(disabled_loaded))
    blocking_rows = [r for r in rows if not r['classification'].startswith('KNOWN_SOURCE_')]
    known_semantics = [r for r in rows if r['classification'].startswith('KNOWN_SOURCE_') and r['classification'] != 'KNOWN_SOURCE_SUPPORTED_EXTENSION_RECORD_VERIFIED']
    if historical: status = 'HISTORICAL_TARGETED_CLASSIFICATION_ONLY_NOT_FINAL_COMPLETION'
    elif run['problems'] or run['exceptions'] or (run['complete'] and run['complete'][1]): status = 'INCOMPLETE_EXCEPTION_OR_INVALID_INPUT_SCOPE_BLOCKS_COMPLETION'
    elif blocking_rows: status = 'NEW_CHANGED_OR_REGRESSION_DIAGNOSTICS_BLOCK_COMPLETION'
    elif known_semantics: status = 'COMPLETE_CHECK_KNOWN_SOURCE_DIAGNOSTICS_REQUIRE_SEMANTIC_DISPOSITION'
    elif rows: status = 'COMPLETE_CHECK_KNOWN_SUPPORTED_EXTENSIONS_ONLY'
    else: status = 'COMPLETE_CHECK_ZERO_DIAGNOSTICS'
    blocked = historical or bool(run['problems'] or run['exceptions'] or blocking_rows)
    result = {'schema': 2, 'status': status, 'completion_blocked_by_unknown_regression_or_invalid_check': blocked,
              'known_source_semantic_disposition_required': len(known_semantics), 'new_changed_or_regression_diagnostics': len(blocking_rows),
              'log': str(log), 'log_sha256': file_sha(log), 'input_inventory': str(inventory_path) if inventory_path else None,
              'input_inventory_sha256': file_sha(inventory_path) if inventory_path else None,
              'file_map': str(file_map_path) if file_map_path else None, 'file_map_sha256': file_sha(file_map_path) if file_map_path else None,
              'source_ledger_sha256': file_sha(ledger_path), 'engine_mapping_count': len(loaded),
              'complete_marker': run['complete'], 'full_audit_completed_marker': run['marker'],
              'input_checks': input_checks, 'scope_or_integrity_problems': sorted(set(run['problems'])), 'exceptions': run['exceptions'],
              'class_counts': dict(counts), 'plugins_checked': checked, 'diagnostics': rows,
              'contract': [
                  'FULL_AUDIT_COMPLETED only proves Finalize ran. Counts, SHA hashes, exceptions, authoritative prefixes and physical coverage must also validate.',
                  'New, unmatched, changed-payload/namespace, repaired/disabled regressions and excess multiplicity block completion.',
                  'Source-known requires exact reporting plugin, canonical record, signature, field path, canonical message and namespace-aware raw payload fingerprint.',
                  'Known unresolved, navigation, alias and supported-extension categories retain distinct semantic decisions. Same-source never proves runtime correctness.',
                  'This is not a game runtime test or a blanket native-zero assertion.'
              ]}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', type=Path, required=True)
    ap.add_argument('--input-inventory', type=Path)
    ap.add_argument('--file-map', type=Path)
    ap.add_argument('--historical-targeted', action='store_true')
    ap.add_argument('--report', type=Path, default=OUT / 'full_check_classification.json')
    args = ap.parse_args()
    result = execute(args.log, args.input_inventory, args.file_map, args.report, args.historical_targeted)
    print(result['status'], 'diagnostics', len(result['diagnostics']), 'plugins', len(result['plugins_checked']),
          'scope problems', len(result['scope_or_integrity_problems']), 'classes', result['class_counts'])
    raise SystemExit(2 if result['completion_blocked_by_unknown_regression_or_invalid_check'] and not args.historical_targeted else 0)


if __name__ == '__main__': main()
