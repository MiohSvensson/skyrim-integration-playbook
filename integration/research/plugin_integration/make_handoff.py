"""Create concrete source-only manifests for the root integrator."""
import collections
import json
from pathlib import Path
import sqlite3

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]


def main():
    c=sqlite3.connect((ROOT/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    evidence=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))
    gear=json.loads((OUT/'gear_resource_closure.json').read_text(encoding='utf-8'))
    mods={r['id']:dict(r) for r in c.execute('select * from mods')}
    chosen=[r for r in gear['candidates'] if r['bounded_static_closure_passed'] and r['name'].casefold()!='underwear.esp']
    assets={};plugins=[]
    for row in chosen:
        key=row['name'].casefold();original=evidence['source_plugins'][row['pack']][key]
        plugins.append({k:row[k] for k in ['pack','name','is_light','source_mod_id','source_mod','source_path','plugin_path_for_validation',
          'record_count_including_header','record_signatures','masters','owned_records','override_records','mixed_bundle','vmad_records','world_records','leveled_records',
          'missing_optional_morph_tri']}|{'status':'stage_for_joint_validation','source_sha256':original['sha256'],
          'source_root_plugin_count':len(row['root_plugins_in_source_mod']),
          'asset_keys':[a['path_key'] for a in row['assets'] if a['source']['kind']!='missing'],
          'validated_replacement':original.get('validated_replacement'),
          'candidate_semantics':'Pure new item/support records; no VMAD, leveled or world record modification. Source archive ordering is inferred, not live-tested.'})
        for asset in row['assets']:
            key=asset['path_key']
            if asset['source']['kind']=='missing':continue
            entry=assets.setdefault(key,{'path_key':key,'requested_by':[],'providers':[],
              'base_presence':asset['base_presence'],'recommended_action':'inherit_base_then_validate' if asset['base_presence']['kind']!='missing' else 'stage_explicit_source'})
            entry['requested_by'].append(row['name'])
            provider={'pack':row['pack'],'source':asset['source']}
            if 'nif_sha256' in asset:provider['nif_sha256']=asset['nif_sha256']
            if provider not in entry['providers']:entry['providers'].append(provider)
    full=sum(not r['is_light'] for r in plugins);light=len(plugins)-full
    result={'base':'TuLED','stage':'Source selection for joint validation, not automatically proven gameplay compatible.',
      'plugins':plugins,'asset_sources':assets,
      'summary':{'new_plugins':len(plugins),'full':full,'light':light,'mixed_bundle_plugins':sum(r['mixed_bundle'] for r in plugins),
        'unique_asset_paths':len(assets),'inherit_base_paths':sum(r['recommended_action']=='inherit_base_then_validate' for r in assets.values()),
        'new_asset_paths':sum(r['recommended_action']=='stage_explicit_source' for r in assets.values()),
        'original_snapshot_plus_gear_slots':{'full':132+full,'light':884+light}},
      'materialization_rules':[
        'Select only listed plugins and explicit resource paths. Never import the whole clothes pack or Caenarvon mixed mod at high priority.',
        'Never import scripts, DLLs, OAR/DAR configurations, actor behavior or generated framework output from these mixed item sources.',
        'Referenced physics XML is a resource exception: only the exact listed XML may be staged; do not copy unrelated SKSE directories.',
        'If a resource already exists in the base, keep the complete base provider and validate the final model/texture graph. A differing dedicated model needs explicit resolution.',
        'BSA members can be extracted with bsarch_readonly using the recorded member SHA. Do not load a broad mixed archive solely for a single item member.',
        'Missing BODYTRI entries are documented optional morph limitations from the source. No guessed TRI or filename substitution is authorized.',
        'Use the known validated replacement for BDOR Ars Magna rather than its original LE CRDT bytes.',
      ],
      'excluded':[{k:r[k] for k in ['pack','name','source_mod_id','source_mod','missing_required_assets','missing_optional_morph_tri','ambiguous_archive_assets','inspection_errors','vmad_records']}|
        {'reason':'Source DLL feature not imported' if r['name'].casefold()=='underwear.esp' else 'Required static closure not complete; retain as optional investigation candidate'}
        for r in gear['candidates'] if not r['bounded_static_closure_passed'] or r['name'].casefold()=='underwear.esp']}
    (OUT/'gear_builder_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    def mod(mid):
        row=mods[mid].copy();row['inventory']=[dict(r) for r in c.execute('select extension,count(*) file_count,sum(size_bytes) logical_bytes from files where mod_id=? group by extension',(mid,))]
        return row
    def plug(name,pack='Anno'):
        row=evidence['source_plugins'][pack][name.casefold()]
        return {k:row[k] for k in ['name','pack','source_mod_id','source_mod','source_path','snapshot_path','sha256','masters','record_count','is_light','native_reported_errors','diagnostic_families']}|{'validated_replacement':row.get('validated_replacement')}
    features=[
      {'feature':'Wyrmstooth','status':'stage_for_joint_validation','mods':[mod(1641)],'plugins':[plug('Wyrmstooth.esp')],
       'optional_selected_patches':[plug('DBM_Wyrmstooth_Patch.esp'),plug('LOTD_TCC_Wyrmstooth.esp')],
       'must_preserve':['Wyrmstooth.esp','Wyrmstooth.bsa','Wyrmstooth - Textures.bsa','Video/WT_Title.bik'],
       'exclude':['Wyrmstooth PBR.esp and PBR assets (source NULL TXST and different renderer)','Wyrmstooth TKAA Patch.esp unless matching TKAA is deliberately selected'],
       'base_conflicts':'Only new worldspace plus Red Wave CELL/NAVI, some vanilla dialogue INFO; final field conflict review still required.',
       'official_source':'https://www.nexusmods.com/skyrimspecialedition/mods/45565',
       'author_requirements':'SKSE/SkyUI only for MCM; core quest has no extra DLC requirement. Actual file checks retain its two declared masters.'},
      {'feature':'The Forgotten City','status':'stage_for_joint_validation','mods':[mod(137),mod(1510)],
       'plugins':[plug('ForgottenCity.esp'),plug('Forgotten City Music Fix.esp')],
       'optional_selected_patches':[plug('DBM_ForgottenCity_Patch.esp')],
       'must_preserve':['ForgottenCity.esp and both original BSA archives','Music Fix standalone PEX/PSC resources'],
       'exclude':['NPC appearance/TKAA patches','Northern Roads patches without the selected Northern Roads framework'],
       'base_conflicts':'Skyrim|108AB4 NAVM genuinely differs from USSEP. Record overlap alone is not a patch; geometry and edge-link intentions need a deliberate winner or compatible authored patch. INFO|071440 and REFR|071A05 also intersect USSEP.',
       'official_source':'https://www.nexusmods.com/skyrimspecialedition/mods/1179',
       'author_requirements':'Author lists no extra install dependencies and names M.H.A.R.P.I.N. as an incompatibility.'},
      {'feature':'World In Painting / Zero Hall / UF6','status':'stage_for_joint_validation','mods':[mod(291),mod(290)],
       'plugins':[plug('[LongShou]WorldInPainting_ZeroHall.esp'),plug('[longshou]UF6.esp')],
       'must_preserve':['All virtual meshes/textures in both mods','Use validated fixed UF6 plugin, not an optional nested compact/brightness variant'],
       'base_conflicts':'ZeroHall has only CELL/LCTN/NAVI shared containers. UF6 includes one Dragonborn DOOR override and a ZeroHall CELL; keep its exact base/reference interpretation.',
       'exclude':['Nested sun-angle and ESP/ESL selector alternatives; they are author installation choices, not additional active plugins']},
      {'feature':'Glenmoril','status':'conditional_navmesh_resolution','mods':[mod(1163),mod(59)],
       'plugins':[plug('Glenmoril.esm')],
       'conditional_patches':[plug("RedBag's Falkreath - Glenmoril patch.esp")],
       'must_preserve':['Original GLENMORIL resource BSA, loose voices, music, models and included new-world LOD from mod1163','English translation plugin from mod59 after original resources'],
       'base_conflicts':'Skyrim|0EC466/0EC469 Ancient Land geometry requires compatible authored patch; Skyrim|016F5D can be bounded doorlink merge with AKSkyrimUnderground (exact shared topology proven). RedBag Falkreath base SHA matches Anno.',
       'exclude':['Northern Roads patches without Northern Roads','Lux patches because TuLED has no active Lux plugin','Unreviewed NPC replacers/children tweaks'],
       'official_source':'https://www.nexusmods.com/skyrimspecialedition/mods/32998',
       'author_requirements':'Fuz Ro D-oh, PapyrusUtil >=3.3, SkyUI and SKSE must be present in the final base.'},
      {'feature':'Moon and Star','status':'disabled_known_source_missing_records','mods':[mod(88)],'plugins':[plug('MoonAndStar_MAS.esp')],
       'reason':'Four missing own VMAD targets 02|02CD4A and 02|039A41/039A42/039A43 are absent in both local 4910-record versions (mods88/1140). No guessed deletion or remapping.',
       'official_source':'https://www.nexusmods.com/skyrimspecialedition/mods/4301'},
      {'feature':'Forgotten Magic Redone','status':'conditional_script_and_final_conflict_check','mods':[mod(751)],'plugins':[plug('ForgottenMagic_Redone.esp')],
       'must_preserve':['84 original PEX and supporting NIF/textures/sounds; its own new perk/quest implementation'],
       'base_conflicts':'Only four external origin overrides are three CELL containers and WRLD; no global perk overhaul replacement. Soft-dependency/script consumers and final container fields still need review.',
       'exclude':['Optional different-language plugin mod752 unless selecting that translation deliberately'],
       'official_source':'https://www.nexusmods.com/skyrimspecialedition/mods/12711'},
    ]
    followers=[]
    for name,mid in [('SofiaFollower.esp',127),('HothFollower.esp',64),('BenDoonSSE.esp',14)]:
        followers.append({'feature':name,'status':'conditional_actor_dialogue_field_review','mods':[mod(mid)],'plugins':[plug(name)],
          'reason':'Native source check passed, but vanilla dialogue/actor/cell overrides intersect USSEP and other base content; not automatically authorized by an empty master list.',
          'exclude':['Optional NPC appearance replacers from other frameworks; keep original complete follower resources']})
    handoff={'base':'TuLED','features':features,'followers':followers,
      'global_evidence':{'lotd_comparison':str(OUT/'lotd_selected_payload_comparison.json'),
        'lotd_result':'122968 records same IDs/structure/flags; all 17061 ordered field differences are defined text translations, zero non-text changes. Actual headers say6.7.2 despite nominal folder names.',
        'navmesh_comparison':str(OUT/'navmesh_comparison.json'),'gear_manifest':str(OUT/'gear_builder_manifest.json')},
      'rules':['Whole resource roots are selected only for the standalone quest/follower sources listed. Mixed patch collections contribute only chosen plugins and explicitly referenced resources.',
        'Do not import city/forest/weather/perk/animation framework replacements in order to satisfy a patch. Omit incompatible optional patches.',
        'No gameplay stability claim; source, master, model and record closure must be checked in the final view.']}
    (OUT/'feature_builder_manifest.json').write_text(json.dumps(handoff,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'gear':result['summary'],'features':[(r['feature'],r['status']) for r in features]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
