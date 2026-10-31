"""Build an auditable, bounded feature plan and xEdit draft. No plugin mutation."""
from pathlib import Path
import collections
from datetime import datetime, timezone
import hashlib
import json
import sys
import zlib

sys.dont_write_bytecode = True
from analyze_fields import BASE, OUT, scan, canonical
from comparator_scope import current_scope, statements as comparator_statements
from placement_contract import build as build_placement_contract, pascal_dispatch

PRIORITY = {'Wyrmstooth.esp', 'ForgottenMagic_Redone.esp', 'SofiaFollower.esp', 'HothFollower.esp', 'BenDoonSSE.esp'}
PATCH = 'Database Feature Compatibility.esp'
GUARD_CACHE = {}


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sha(obj):
    return hashlib.sha256(encoded(obj)).hexdigest()


def file_guard(path):
    path = Path(path)
    key = str(path).casefold()
    if key in GUARD_CACHE:
        return GUARD_CACHE[key]
    data = path.read_bytes()
    result = {'filename': path.name, 'path': str(path), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest(), 'crc32': f'{zlib.crc32(data):08X}'}
    GUARD_CACHE[key] = result
    return result


def trim_diff(diff):
    result = []
    for item in diff:
        r = {'field': item['field']}
        for side in ('a', 'b'):
            value = item.get(side)
            raw = encoded(value)
            r[side + '_sha256'] = hashlib.sha256(raw).hexdigest()
            r[side + '_json_bytes'] = len(raw)
            if len(raw) < 4500:
                r[side] = value
        result.append(r)
    return result


def quote(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    audit = json.loads((OUT / 'raw_field_comparison.json').read_text(encoding='utf-8'))
    manifest = json.loads((BASE / 'integration/research/plugin_integration/feature_builder_manifest.json').read_text(encoding='utf-8'))
    repairs = json.loads((BASE / 'integration/research/base_diagnostics/recommended_actions.json').read_text(encoding='utf-8'))
    excluded = sorted({p['name'] for group in ('features', 'followers') for f in manifest[group] for p in f['plugins']}
                      | set(audit['excluded_rebuilt_generated_plugins']) | {PATCH,
                          'Database Quest Feature Compatibility.esp','Database Forgotten City USSEP Navigation.esp',
                          'Database Glenmoril Navigation Compatibility.esp'}, key=str.casefold)
    priority = [f for f in audit['features'] if f['plugin'] in PRIORITY]
    seeds = {}
    operations = []
    records = []
    files = {}
    source_records = {}
    for feature in audit['features']:
        keys = {(r['origin'], int(r['object_id'], 16)) for r in feature['override_records']}
        parsed, _, _ = scan(feature['path'], wanted=keys)
        source_records[feature['plugin']] = parsed
        for r in feature['override_records']:
            identity = r['origin'] + '|' + r['object_id']
            src_fields = [x['field'] for x in r['canonical_source_from_vanilla']]
            base_fields = [x['field'] for x in r['canonical_base_from_vanilla']]
            rec = {'feature': feature['feature'], 'plugin': feature['plugin'], 'record': identity,
                   'signature': r['signature'], 'base_winner': r['base_record']['plugin'] if r['base_record'] else None,
                   'source_changed_fields': src_fields, 'base_changed_fields': base_fields,
                   'intersecting_different_fields': r['canonical_conflicting_fields'],
                   'source_from_origin': trim_diff(r['canonical_source_from_vanilla']),
                   'base_from_origin': trim_diff(r['canonical_base_from_vanilla']),
                   'source_raw_payload_sha256': sha({'flags': parsed[(r['origin'], int(r['object_id'], 16))]['flags'],
                       'fields': [(t, v.hex()) for t, v in parsed[(r['origin'], int(r['object_id'], 16))]['fields']]}),
                   'source_semantic_sha256': sha(canonical(parsed[(r['origin'], int(r['object_id'], 16))])) if r['signature'] != 'NAVI' else None}
            if r['signature'] == 'NAVI':
                rec.update(action='final_navigation_aggregation', classification='complex generated navigation index; not ITM-classified', draft_v1=False)
            elif r['signature'] == 'NAVM':
                rec.update(action='retain_authored_geometry_pending_navigation_finalization',
                           classification='substantive topology' if src_fields else 'unclassified topology', draft_v1=False)
                if identity == 'skyrim.esm|108AB4':
                    rec['action'] = 'runtime_layout_verified_bounded_edge_removal_plan_pending_xEdit_execution'
                    rec['evidence'] = str(BASE / 'integration/research/forgotten_city_navigation')
            elif feature['plugin'] in PRIORITY:
                rec.update(action='forward_base_container_or_metadata', draft_v1=True,
                           classification='semantic ITM / localization / cache' if not src_fields else 'bounded authored field additions')
                assert r['base_record'], identity
                key = (r['origin'], int(r['object_id'], 16))
                seed = {'origin': r['origin'], 'object_id': r['object_id'], 'signature': r['signature'],
                        'base_file': r['base_record']['plugin'], 'base_path': r['base_record']['path'],
                        'allowed_fields': set(), 'persistent': False, 'donors': set()}
                old = seeds.setdefault(key, seed)
                assert old['base_file'] == seed['base_file'], (old, seed)
                old['donors'].add(feature['plugin'])
                if feature['plugin'] == 'SofiaFollower.esp' and r['signature'] == 'INFO' and 'VMAD' in src_fields:
                    old['allowed_fields'].add('VMAD')
                    operations.append({'operation': 'typed_field_forward', 'record': identity, 'source': feature['plugin'], 'field': 'VMAD'})
                    rec['action'] = 'base_INFO_plus_Sofia_VMAD_keep_base_CTDA_text_and_PNAM'
                if feature['plugin'] == 'Wyrmstooth.esp' and r['signature'] == 'INFO':
                    assert 'CTDA' in src_fields and 'CTDA' not in base_fields
                    old['allowed_fields'].add('Conditions')
                    operations.append({'operation': 'typed_field_forward', 'record': identity, 'source': feature['plugin'], 'field': 'Conditions'})
                    rec['action'] = 'base_INFO_plus_Wyrm_GetEquippedShout_OR_branch_keep_base_wording_PNAM'
                if feature['plugin'] in ('SofiaFollower.esp', 'BenDoonSSE.esp') and '$FLAGS' in src_fields:
                    assert r['flag_bit_analysis']['source_changed_mask'] == 0x400, rec
                    old['persistent'] = True
                    old['allowed_fields'].add('$FLAGS')
                    rec['action'] = 'preserve_base_record_plus_source_Persistent_bit'
                if feature['plugin'] == 'BenDoonSSE.esp' and 'XLRL' in src_fields and 'XLRL' not in base_fields:
                    old['allowed_fields'].add('XLRL')
                    operations.append({'operation': 'typed_field_forward', 'record': identity, 'source': feature['plugin'], 'field': 'XLRL'})
                    rec['action'] += '_and_source_location_cache'
                if feature['plugin'] == 'HothFollower.esp' and r['signature'] == 'CELL' and 'XCAS' in src_fields:
                    assert 'XCAS' not in base_fields
                    old['allowed_fields'].add('XCAS')
                    operations.append({'operation': 'typed_field_forward', 'record': identity, 'source': feature['plugin'], 'field': 'XCAS'})
                    rec['action'] = 'base_MoorsideInn_metadata_plus_Hoth_XCAS'
                if feature['plugin'] == 'HothFollower.esp' and identity == 'skyrim.esm|03B4A5':
                    old['allowed_fields'].update(('FormIDs', 'LNAM'))  # exact FLST RArray signature in pinned 4.1.5f
                    rec['action'] = 'base_voice_FLST_union_Hoth_00333C_keep_Erin_001040'
                if feature['plugin'] == 'SofiaFollower.esp' and identity == 'skyrim.esm|09845C':
                    rec['action'] = 'restore_base_global_PACK_and_clone_source_PACK_retarget_only_SofiaHorse_Alias1_ALPC'
            else:
                rec.update(draft_v1=False)
                if feature['plugin'] == '[LongShou]WorldInPainting_ZeroHall.esp':
                    rec.update(action='forward_base_shared_container_preserve_own_children', classification='translated FULL; normalized special-ref cache matches origin')
                elif feature['plugin'] == '[longshou]UF6.esp' and r['origin'].startswith('[longshou]'):
                    rec.update(action='retain_repaired_feature_own_namespace_override', classification='feature-to-feature override; not TuLED intersection')
                elif feature['plugin'] == '[longshou]UF6.esp' and r['signature'] == 'DOOR':
                    rec.update(action='do_not_blindly_undelete_review_empty_stock_stub_users', classification='source deleted flag on empty stock DOOR stub; no proof of an active Dragonborn door')
                elif feature['plugin'] == 'Forgotten City Music Fix.esp':
                    rec.update(action='forward_base_shared_container_keep_own_3_records_and_assets_with_ForgottenCity', classification='shared container metadata')
                else:
                    action = 'forward_base_shared_container_preserve_own_children' if r['signature'] in ('CELL', 'WRLD') else 'retain_authored_source_fields_when_base_origin_unchanged'
                    if r['signature'] == 'INFO': action = 'base_INFO_plus_source_Conditions_keep_base_VMAD'
                    if identity == 'skyrim.esm|071A05': action = 'forward_complete_USSEP_record_source_DATA_only_tiny_float_jitter_XLRL_XSCL_already_match_base'
                    rec.update(action=action, classification='authored custom-race / entrance / condition support' if src_fields else 'semantic ITM / localization / cache')
            records.append(rec)
    for f in priority:
        g = file_guard(f['path']); files[g['filename'].casefold()] = g
    for name in ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm'):
        g = file_guard(BASE / 'repairs/consistent_stock/Data' / name); files[g['filename'].casefold()] = g
    for s in seeds.values():
        g = file_guard(s['base_path']); files[g['filename'].casefold()] = g
    # Source-only quest and PACK are not stock override entries in the comparison.
    quest_key = ('sofiafollower.esp', 0xAA58)
    qrs, _, _ = scan(next(f['path'] for f in priority if f['plugin'] == 'SofiaFollower.esp'), wanted={quest_key})
    assert quest_key in qrs
    quest_hash = sha({'flags': qrs[quest_key]['flags'], 'fields': [(t, v.hex()) for t, v in qrs[quest_key]['fields']]})
    repair_hits = []
    keys = set(seeds)
    for r in repairs['exact_repair_candidates']:
        if r['pack'] == 'TuLED':
            hits, _, _ = scan(r['candidate'], wanted=keys)
            repair_hits.append({'plugin': r['plugin'], 'candidate': r['candidate'], 'sha256': r['candidate_sha256'], 'priority_target_intersections': sorted(f'{a}|{b:06X}' for a, b in hits)})
            assert not hits
    variant_hits = []
    all_keys = {(r['origin'], int(r['object_id'], 16)) for f in audit['features'] for r in f['override_records']}
    for path in sorted((BASE / 'repairs/TuLED/variants').rglob('*.esp')):
        hits, _, _ = scan(path, wanted=all_keys)
        variant_hits.append(file_guard(path) | {'all_feature_target_intersections': sorted(f'{a}|{b:06X}' for a, b in hits)})
        assert not hits
    base_keys = collections.defaultdict(set)
    for k, s in seeds.items():
        base_keys[s['base_path']].add(k)
    parsed_base = {path: scan(path, wanted=ks)[0] for path, ks in base_keys.items()}
    seeds_json = []
    # File.AddCopy creates ancestors with [] flags and may otherwise take an
    # authored/highest visible ancestor. Seed final WRLD/CELL/DIAL bodies first.
    rank = {'WRLD': 0, 'CELL': 1, 'DIAL': 2}
    for k, s in sorted(seeds.items(), key=lambda item: (rank.get(item[1]['signature'], 3), item[0])):
        rr = parsed_base[s['base_path']]
        assert k in rr
        seeds_json.append(s | {'allowed_fields': sorted(s['allowed_fields']), 'donors': sorted(s['donors']),
            'base_raw_payload_sha256': sha({'flags': rr[k]['flags'], 'fields': [(t, v.hex()) for t, v in rr[k]['fields']]}),
            'base_semantic_sha256': sha(canonical(rr[k]))})
    plan = {'schema': 1, 'written_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'field-audited; xEdit draft not executed or runtime tested by this agent',
            'baseline': str(BASE / 'repairs/consistent_stock/Data'),
            'audit_profile_hashes': audit['profile_hashes_after'],
            'patch': PATCH, 'draft': str(OUT / 'DatabaseFeatureCompatibilityDraft.pas'),
            'priority_features': [f['plugin'] for f in priority],
            'all_feature_inputs': [file_guard(f['path']) | {'own_records': sum(f['own_counts'].values()), 'override_records': len(f['override_records'])} for f in audit['features']],
            'priority_seed_records': seeds_json, 'typed_field_operations': operations,
            'input_file_guards': sorted(files.values(), key=lambda r: r['filename'].casefold()),
            'excluded_from_base_winner_search': excluded,
            'must_not_be_loaded': audit['disabled_original_plugins'] + audit['excluded_rebuilt_generated_plugins'],
            'source_quest': {'record': 'sofiafollower.esp|00AA58', 'edid': 'JJSofiaScripts', 'raw_payload_sha256': quest_hash,
                             'alias_id': 1, 'alias_name': 'SofiaHorse', 'field': 'ALPC', 'old_target': 'skyrim.esm|09845C', 'expected_redirect_count': 1},
            'new_own_record': {'signature': 'PACK', 'from': 'SofiaFollower.esp override of Skyrim.esm|09845C', 'count': 1, 'object_id_min': 0x800, 'object_id_max': 0xFFF},
            'hoth_voice_union': {'record': 'skyrim.esm|03B4A5', 'base_must_contain': 'erinrace.esm|001040', 'append_once': 'hothfollower.esp|00333C'},
            'sofia_script_audit': str(OUT / 'sofia_scripts/audit.json'),
            'sofia_script_findings': '323/323 SHA-verified PEX decompiled to PSC and ASM; no GetForm/GetFormFromFile calls, 0x9845C/623708 or horse PACK names found. Literal/static evidence, not a proof about arbitrary computed external lookups.',
            'four_TuLED_repair_target_audit': repair_hits,
            'additional_TuLED_variant_target_audit': variant_hits,
            'stock_target_delta_evidence': str(OUT / 'coherent_stock_target_delta.json'),
            'music_fix_compiled_script_evidence': str(OUT / 'music_fix/audit.json'),
            'own_navigation_scope_evidence': str(OUT / 'own_navigation_scope.json'),
            'forgotten_city_navigation': {'status': 'bounded three-way geometry/reciprocal/NVMI plan verified by runtime_layout; drafts not yet xEdit executed',
               'comparison': str(BASE / 'integration/research/forgotten_city_navigation/comparison.json'),
               'report': str(BASE / 'integration/research/forgotten_city_navigation/README.md'),
               'primary': 'skyrim.esm|108AB4', 'keep': 'all USSEP 271 vertices / 324 triangles / grid',
               'edit': 'close triangle 50 side 2 portal; remove USSEP Edge Links row 6; remap larger external edge array indices only',
               'reciprocal_proof': 'Only 1 of 17 old-USSEP portals lacks its author-neighbor counterpart; other 16 preserve ordered triangle coordinates and reciprocal links. Author deleted old neighbor faces 317/469.',
               'NAVI': 'Keep complete USSEP primary NVMI incl island + 7 neighbors; keep exact author six other shared NVMI; preserve all other final entries/NVPP/NVSI. Seven keys have zero NVPP references in all three inputs.'},
            'records': records,
            'execution_contract': [
                'All source WRLD/CELL/DIAL ancestors are included in the exact record set and seeded first. Exact 4.1.5f script adapters call core wbCopyElementToFile/Record with aAsNew/aDeepCopy booleans; main-record payload assignment requires deep=True, while ancestors are built with False/False. ChildGroups are not implicitly copied by the main-record path.',
                'Fresh final-profile xEdit 4.1.5f session, normal typed definitions, never launch game. Existing unsaved in-memory edits are outside CRC coverage.',
                'SHA preflight for the resolved physical file map, then xEdit validates VFS CRC, expected base owner, all typed input/outputs and source-only quest consumer before export.',
                'Build a new ESL-flagged compatibility plugin only; do not modify input plugins. Any exception exports nothing. Close without saving incomplete/unrelated plugins.',
                'All field copies use xEdit typed AddCopy and required masters; every source FormID leaf is explicitly set by resolved load-order identity and LinksTo compared afterwards.',
                'Shared INFO PNAM uses existing TuLED/official linked order; source alterations are only other vanilla INFO IDs and cpBenign, not own-feature insertion targets. Sofia VMAD hooks and Wyrm Conditions are preserved.',
                'No NAVM/NAVI are copied by this patch. Final navigation aggregation and runtime_layout results are separately required.',
                'Reload exported candidate, run full master/native reference checks and offline canonical verifier; original candidate validation is not game/runtime validation.'
            ]}
    comparator=current_scope(priority=plan)
    quest_plan=json.loads((OUT/'quest_extension_plan.json').read_text(encoding='utf-8'))
    placement=build_placement_contract(plan,quest_plan)
    plan['physical_placement_contract']=str(OUT/'physical_placement_contract.json')
    (OUT/'physical_placement_contract.json').write_text(json.dumps(placement,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    plan['input_file_guards']=comparator['input_file_guards']
    plan['comparator_self_audit']={'scope':str(OUT/'comparator_self_audit_scope.json'),'exact_scope_rows':len(comparator['exact_records']),
        'visible_parent_rows':len(comparator['visible_source_parents']),'rule':'Audit every source leaf e-vs-e and collect all unsupported kinds before AddNewFileName. Any failure blocks patch creation.'}
    (OUT/'comparator_self_audit_scope.json').write_text(json.dumps(comparator,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT / 'compat_patch_plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Generated statements are intentionally simple so the JvInterpreter does not parse external JSON.
    generated = []
    for g in plan['input_file_guards']:
        generated.append(f"  GuardFile({quote(g['filename'])}, {quote(g['crc32'])});")
    generated.extend('  Need(not Assigned(FileByName(' + quote(n) + ')), ' + quote('Excluded plugin is loaded: ' + n) + ');' for n in plan['must_not_be_loaded'])
    guards = '\n'.join(generated)
    seeds_pas = '\n'.join(f"  Seed({quote(s['origin'])}, ${s['object_id']}, {quote(s['signature'])}, {quote(s['base_file'])});" for s in seeds_json)
    apply_pas = '\n'.join(f"  ForwardField({quote(op['source'])}, {quote(op['record'].split('|')[0])}, ${op['record'].split('|')[1]}, {quote(op['field'])});" for op in operations)
    persistent_pas = '\n'.join(f"  SetPersistentBit({quote(s['origin'])}, ${s['object_id']});" for s in seeds_json if s['persistent'])
    verify_pas = '\n'.join(f"  PostMerged({quote(s['origin'])}, ${s['object_id']}, {quote(s['base_file'])}, {quote('|' + '|'.join(s['allowed_fields']) + '|')}, {str(s['persistent'])});" for s in seeds_json)
    verify_field_pas = '\n'.join(f"  PostForwarded({quote(op['source'])}, {quote(op['record'].split('|')[0])}, ${op['record'].split('|')[1]}, {quote(op['field'])});" for op in operations)
    restore_metadata_pas = '\n'.join(f"    RestoreSeedMetadata({quote(s['origin'])}, ${s['object_id']}, {quote(s['base_file'])});" for s in seeds_json)
    template = (OUT / 'compatibility_template.pas').read_text(encoding='utf-8')
    replace = {'@@PATCH@@': PATCH, '@@OUTPUT@@': str(OUT / 'candidate' / PATCH), '@@GUARDS@@': guards,
               '@@COMPARATOR_SCOPE@@':comparator_statements(comparator,quote),
               '@@REF_PLACEMENT_DISPATCH@@':pascal_dispatch(placement,quote),
               '@@SEEDS@@': seeds_pas, '@@APPLY@@': apply_pas, '@@PERSISTENT@@': persistent_pas,
               '@@VERIFY@@': verify_pas, '@@VERIFY_FIELDS@@': verify_field_pas,
               '@@RESTORE_METADATA@@': restore_metadata_pas,
               '@@EXCLUDED@@': '\n'.join('    SameText(n, ' + quote(n) + ') or' for n in excluded) + '\n    False',
               '@@RECORD_COUNT@@': str(len(seeds_json) + 2)}
    for k, v in replace.items(): template = template.replace(k, v)
    assert '@@' not in template
    (OUT / 'DatabaseFeatureCompatibilityDraft.pas').write_text(template, encoding='utf-8')
    (OUT / 'DatabaseVerifyFeatureCompatibilityDraft.pas').write_text(template.replace('VERIFY_ONLY = False;', 'VERIFY_ONLY = True;', 1), encoding='utf-8')
    print('Plan records', len(records), 'priority base overrides', len(seeds_json), 'field forwards', len(operations), 'input guards', len(plan['input_file_guards']))


if __name__ == '__main__':
    main()
