import copy
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent


def summarize(j):
    ps=j['plugins'];assets=j['asset_sources'];full=sum(not r['is_light'] for r in ps)
    j['summary']={'new_plugins':len(ps),'full':full,'light':len(ps)-full,'mixed_bundle_plugins':sum(r['mixed_bundle'] for r in ps),
      'unique_asset_paths':len(assets),'inherit_base_paths':sum(r['recommended_action']=='inherit_base_then_validate' for r in assets.values()),
      'new_asset_paths':sum(r['recommended_action']=='stage_explicit_source' for r in assets.values()),
      'original_snapshot_plus_batch_slots':{'full':132+full,'light':884+len(ps)-full}}


def main():
    path=OUT/'gear_builder_manifest.json';original=json.loads(path.read_text(encoding='utf-8'))
    first=copy.deepcopy(original)
    first['plugins']=[r for r in first['plugins'] if r['name'].casefold()!='hhhair.esp']
    keys={k for r in first['plugins'] for k in r['asset_keys']}
    first['asset_sources']={k:r for k,r in first['asset_sources'].items() if k in keys}
    for r in first['asset_sources'].values():r['requested_by']=[n for n in r['requested_by'] if n.casefold()!='hhhair.esp']
    first['freeze']={'source_manifest':str(path),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
      'decision':'Exclude HHhair pending non-equivalent dedicated ponytail NIF; retain base global body/skin/vanilla equipment rendering.',
      'collision_evidence':str(OUT/'gear_collision_audit.json'),
      'new_multi_provider_assets':'Both metal_1_e and metal_3_e cubemaps are byte-identical across donor providers; no differing new multi-provider SHA.',
      'inherited_resources':'Base variant is an intentional global choice for vanilla armor, weapons, skin/body and common shader textures. No different dedicated mesh is inherited in this frozen batch.'}
    summarize(first)
    target=OUT/'gear_builder_manifest_batch1_48.json';assert not target.exists(),'Batch is frozen; inspect instead of overwriting.'
    target.write_text(json.dumps(first,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    latest=json.loads((OUT/'gear_resource_closure.json').read_text(encoding='utf-8'))
    existing={r['name'].casefold() for r in original['plugins']}
    ps=[r for r in latest['candidates'] if r['bounded_static_closure_passed'] and r['name'].casefold() not in existing and r['name'].casefold() not in ('underwear.esp','hhhair.esp')]
    second={'base':'TuLED','stage':'Batch2: BSA virtual archive shadowing resolved; stage for joint validation.','plugins':[],'asset_sources':{},
      'materialization_rules':original['materialization_rules'],
      'dependency_on_batch1':str(target),
      'source_resolution_fix':'Exclude bsa_sources.other and resolve same-name virtual BSA file before associated-plugin archive order.'}
    for row in ps:
        second['plugins'].append({k:row[k] for k in ['pack','name','is_light','source_mod_id','source_mod','source_path','plugin_path_for_validation',
          'record_count_including_header','record_signatures','masters','owned_records','override_records','mixed_bundle','vmad_records','world_records','leveled_records',
          'missing_optional_morph_tri']}|{'status':'stage_for_joint_validation','asset_keys':[a['path_key'] for a in row['assets'] if a['source']['kind']!='missing']})
        for asset in row['assets']:
            key=asset['path_key']
            if asset['source']['kind']=='missing':continue
            item=second['asset_sources'].setdefault(key,{'path_key':key,'requested_by':[],'providers':[],
              'base_presence':asset['base_presence'],'recommended_action':'inherit_base_then_validate' if asset['base_presence']['kind']!='missing' else 'stage_explicit_source'})
            item['requested_by'].append(row['name']);provider={'pack':row['pack'],'source':asset['source']}
            if 'nif_sha256' in asset:provider['nif_sha256']=asset['nif_sha256']
            if provider not in item['providers']:item['providers'].append(provider)
    summarize(second)
    (OUT/'gear_builder_manifest_batch2.json').write_text(json.dumps(second,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'batch1':first['summary'],'batch2':second['summary'],'batch2_names':[r['name'] for r in second['plugins']]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
