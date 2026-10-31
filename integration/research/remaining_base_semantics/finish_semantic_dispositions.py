"""Freeze actionable conclusions and exact cross-pack witnesses, no mutation."""
from pathlib import Path
import hashlib
import json
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(OUT.parent / 'feature_conflicts'))
from analyze_fields import scan, canonical, formvalue


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    records = json.loads((OUT / 'base_record_semantics.json').read_text(encoding='utf-8'))
    features = json.loads((OUT / 'feature_missing_consumers.json').read_text(encoding='utf-8'))
    scripts = json.loads((OUT / 'script_evidence.json').read_text(encoding='utf-8'))
    db = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    ids = sqlite3.connect((BASE / 'baseline/record_identifiers.sqlite').as_uri() + '?mode=ro', uri=True)
    comparisons = {}
    for name, key, wanted in (
        ('Darkend.esp', 'mihailfxrottenmaidenmournxjk', {('darkend.esp', i) for i in (0x5FFD1C, 0x5FFD21, 0xAA0E, 0x19D5B)}),
        ('GostedDimensionalRift.esp', 'pdimriftolddungeon', {('gosteddimensionalrift.esp', i) for i in (0x1B3A4B, 0x2ED53E, 0x2DE1E6, 0x2F2640, 0x2F2641)}),
        ('Tullius Hair 3 SMP.esp', '0000313_wo4_athena', {('tullius hair 3 smp.esp', i) for i in (0xCEA, 0xBBC)})
    ):
        paths = [Path(p) for p, in ids.execute('''select distinct s.path from identified_records r join plugin_snapshots s on s.canonical_sha256=r.sha256 where s.name=? and r.edid_key=?''', (name, key))]
        witnesses = []
        for path in paths:
            rs = scan(path, wanted=wanted)[0]
            witnesses.append({'path': str(path), 'sha256': digest(path),
                              'records': [{'record': f'{k[0]}|{k[1]:06X}', 'signature': r['signature'],
                                           'canonical': canonical(r)} for k, r in sorted(rs.items())]})
        comparisons[name] = witnesses
    tcc = []
    for pack in ('Anno', 'TuLED'):
        path = BASE / 'xedit_runs' / pack / 'Data/DBM_RelicNotifications.esp'
        # All six SNDR records in each selected file, not only the three warnings.
        rs = scan(path)[0]
        sounds = {k: r for k, r in rs.items() if r['signature'] == 'SNDR'}
        tcc.append({'pack': pack, 'path': str(path), 'sha256': digest(path),
                    'SNDR': [{'record': f'{k[0]}|{k[1]:06X}', 'flags': r['flags'], 'fields': [(t, v.hex()) for t, v in r['fields']]} for k, r in sorted(sounds.items())]})
    assert len(tcc[0]['SNDR']) == len(tcc[1]['SNDR']) == 6 and tcc[0]['SNDR'] == tcc[1]['SNDR']
    comparisons['DBM_RelicNotifications.esp'] = tcc
    audio = {'path': 'sound/fx/amb/wt_amb_crickets01.wav', 'bsa_candidates': [], 'loose_candidates': []}
    audio['bsa_candidates'] = db.execute("select archive_id,path_key,sha256 from bsa_entries where path_key in ('sound/fx/amb/wt_amb_crickets01.wav','sound/fx/amb/wt_amb_crickets01.xwm')").fetchall()
    audio['loose_candidates'] = db.execute("select mod_id,relative_path from files where path_key in ('sound/fx/amb/wt_amb_crickets01.wav','sound/fx/amb/wt_amb_crickets01.xwm')").fetchall()
    assert not audio['bsa_candidates'] and not audio['loose_candidates']
    comparisons['Wyrmstooth_crickets_inventory'] = audio
    (OUT / 'cross_pack_source_comparisons.json').write_text(json.dumps(comparisons, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    dispositions = [
        {'case': 'Rift stale YG/ZG assignments', 'status': 'BOUNDED_CANDIDATE_READY_XEDIT_PENDING',
         'action': 'Apply only hash-matched rift_stale_property_candidate to integration copy, after final winning PEX hash check; then native/full validate.',
         'candidate_evidence': str(OUT / 'rift_stale_property_evidence.json'), 'removed_missing_diagnostics': 2,
         'kept': 'Consumed XG and all other plugin contents; original key refToDisable remains unresolved.'},
        {'case': 'Rift key refToDisable', 'status': 'REAL_DECLARED_CONSUMER_REMAINING', 'record': 'gosteddimensionalrift.esp|1B3A4B',
         'property': 'defaultDisableOtherObjectWhenTaken.refToDisable', 'missing': 'gosteddimensionalrift.esp|2DE1E6',
         'action': 'Keep world and key; do not clear the declared/Disable-consumed property or guess another object. No exact replacement in indexed packs.'},
        {'case': 'Darkend ghost spell properties', 'status': 'REAL_DECLARED_CONSUMERS_REMAINING', 'records': 13, 'missing_assignments': 26,
         'missing': ['darkend.esp|00AA0E', 'darkend.esp|019D5B'], 'expected_type_from_actual_PEX': 'Spell',
         'action': 'Keep Darkend. Do not remove or remap these assignments. Both properties are Cast-consumed by stock and USSEP SprigganFXSCRIPT. Exact original author spell recovery remains open.',
         'scope': '13 MGEF -> 13 SPEL -> 4 RACE -> 5 NPC -> 1 non-disabled source ACHR. These are not merely unattached VMAD properties.',
         'author_source': 'Darkend official credits link Rotten Maidens Nexus14106, which now reports removed by author. Current local Darkend providers share the defect.'},
        {'case': 'TCC alternate SNDR', 'status': 'OPTIONAL_FIELD_BUT_NONZERO_UNRESOLVED_TARGET',
         'records': ['dbm_relicnotifications.esp|9C686C', 'dbm_relicnotifications.esp|D1946E'], 'missing': 'legacyofthedragonborn.esm|9D5B81',
         'action': 'Keep TCC achievements. SNAM schema allows NULL, but no exact author replacement or engine proof justifies clearing the current nonzero missing alternative link. Do not fabricate SNDR.',
         'consumption': 'Own SOUN forms are actual RN_Achivement_Script_Master PlayFX/Playandwait consumers; all six SNDR payloads match Anno/TuLED, so pack swapping does not repair it.'},
        {'case': 'TCC Looping64', 'status': 'UNDOCUMENTED_SOURCE_VALUE_REMAINING', 'record': 'dbm_relicnotifications.esp|9B2418',
         'action': 'Keep exact source64; do not guess 0/8/16/32. Both xEdit and CommonLib enum omit64. This SNDR is a projectile Sound consumer, not proven dormant.'},
        {'case': 'BenDoon horse fragment', 'status': 'SOURCE_DISCONNECTED_PACKAGE_KEEP_WITH_INACTIVE_ASSET_EXCEPTION', 'record': 'bendoonsse.esp|04A1A3',
         'action': 'Keep follower and original unused package. Do not create empty fragments or remove mounted-follower behavior elsewhere.',
         'evidence': 'OnBegin Fragment_0 and OnChange Fragment_1 are configured, so not zero-function tails. Yet all source records have zero raw references; typed PKID/ALPC zero; no indexed master dependents; all199 inventoried PEX decompiled successfully and contain no GetForm variant, package override, target name or ID.',
         'limits': 'No ordinary selected source route selects this package. External dynamically constructed lookup/console use is outside this static conclusion; not a global guarantee.'},
        {'case': 'UF6 five furniture models', 'status': 'SOURCE_UNPLACED_DEFINITIONS_KEEP_WITH_INACTIVE_ASSET_EXCEPTIONS',
         'records': [f'[longshou]uf6.esp|{i:06X}' for i in range(0x801, 0x806)],
         'action': 'Keep private worlds, placed furniture and all original definitions. Catalogue five unresolved models as unused source leftovers; do not substitute unrelated furniture or declare complete asset closure.',
         'evidence': 'Zero source NAME placements, zero entire-source raw references, no attached VMAD anywhere in UF6, no indexed master dependents. Final direct reference graph still to be checked by xEdit.'},
        {'case': 'Wyrmstooth missing INFO fragment', 'status': 'LIVE_DIALOGUE_CONFIGURED_FRAGMENT_UNRECOVERED', 'record': 'wyrmstooth.esp|3943AB',
         'missing': 'scripts/tif__023943ab.pex', 'action': 'Keep dialogue/quest and report one unrecovered OnEnd function. Do not silently remove VMAD or invent an empty function.',
         'scope': 'This is Unwanted Guests SGE quest3943A0 intro after WrapMeUp3920D5 stage>=30; actor OR condition Alberthor/Falmer. The existing subsequent accept INFO3943AF PEX explicitly SetStage10, so this missing introductory function alone is not proof the quest cannot progress.',
         'evidence': 'Full dialogue/quest/conditions/fragment tail in feature_missing_consumers.json; actual accept/quest PEX in script_evidence.json.'},
        {'case': 'Wyrmstooth crickets sample', 'status': 'LIVE_AMBIENT_AUDIO_SAMPLE_MISSING', 'record': 'wyrmstooth.esp|8BFAE2',
         'missing': audio['path'], 'action': 'Retain Wyrmstooth; disclose one missing ambient sample without substituting arbitrary audio.',
         'scope': 'Marsh RDSA entry3 of41 / Forest entry5 of48, flags15, chance0.25; referenced by155/176 source CELL XCLR lists. Not a quest-script blocker; one part of regional ambience is incomplete.'},
        {'case': 'BenDoon/ForgottenMagic SEQ', 'status': 'HASH_LOCKED_BINARY_CANDIDATES_READY', 'action': 'Use seq_candidate/seq sidecars with exact unchanged owning plugin names and source SHAs; final VFS check required.', 'evidence': str(OUT / 'seq_generation_plan.json')}
    ]
    appearance = []
    for item in records['appearance']:
        appearance.append({'plugin': item['plugin'], 'source_sha256': item['sha256'], 'record_count': len(item['records']),
                           'action': 'Preserve active content/appearance resources; no arbitrary class/voice/tint/headpart substitutions.',
                           'known_detail': 'Exact targeted ACBS/race/template flags, source consumers, hard dependents and all facegen candidates in base_record_semantics.json.',
                           'facegen_pairs_present_for_NPCs': all(bool(p['archived'] or p['loose']) for r in item['records'] if r['signature'] == 'NPC_' for p in r['exact_facegen_inventory']),
                           'limits': 'Inventory presence is not final winner or game appearance validation. Names containing Preset do not prove dormant: WZ NPC00233B has a real source ACHR placement and no CharGenFacePreset flag.'})
    result = {'scope': 'Read-only analysis; only the two-property Rift candidate and exact SEQ sidecars are authored. No runtime/profile/source changes or GUI/game execution.',
              'dispositions': dispositions, 'appearance': appearance, 'evidence': [str(OUT / n) for n in ('base_record_semantics.json', 'cross_pack_source_comparisons.json', 'feature_missing_consumers.json', 'script_evidence.json')],
              'xedit_pending': True, 'runtime_tested': False}
    (OUT / 'semantic_dispositions.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Frozen semantic dispositions:', len(dispositions), 'cases,', len(appearance), 'appearance sources')


if __name__ == '__main__': main()
