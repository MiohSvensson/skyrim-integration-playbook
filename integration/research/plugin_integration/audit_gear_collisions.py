"""Hash all multi-provider assets and inherited model paths of the frozen batch."""
import collections
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent


def digest(provider):
    source=provider.get('source',provider)
    if provider.get('nif_sha256'):return provider['nif_sha256']
    if source.get('sha256'):return source['sha256']
    if source['kind'] in ('loose','stock_loose'):
        path=str(Path(source['path']).absolute())
        if not path.startswith('\\\\?\\'):path='\\\\?\\'+path
        h=hashlib.sha256()
        with open(path,'rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    return None


def main():
    j=json.loads((OUT/'gear_builder_manifest.json').read_text(encoding='utf-8'))
    latest=json.loads((OUT/'gear_resource_closure.json').read_text(encoding='utf-8'))
    base_latest={a['path_key']:a['base_presence'] for r in latest['candidates'] for a in r['assets']}
    multi=[];inherited_models=[];inherited_other=[]
    for key,row in j['asset_sources'].items():
        if len(row['providers'])>1:
            ps=[{'pack':p['pack'],'path':p['source'].get('path'),'sha256':digest(p)} for p in row['providers']]
            multi.append({'path_key':key,'action':row['recommended_action'],'requested_by':row['requested_by'],'providers':ps,
              'same_sha256':len({p['sha256'] for p in ps})==1})
        if row['recommended_action']=='inherit_base_then_validate':
            bp=base_latest.get(key,row['base_presence']);base_sha=digest(bp)
            ps=[{'pack':p['pack'],'path':p['source'].get('path'),'sha256':digest(p)} for p in row['providers']]
            entry={'path_key':key,'requested_by':row['requested_by'],'base_source':bp,'base_sha256':base_sha,'donors':ps,
              'all_donors_identical_to_base':base_sha is not None and all(p['sha256']==base_sha for p in ps)}
            is_global=key.startswith(('textures/actors/','textures/cubemaps/','textures/effects/','textures/blood/',
              'meshes/actors/character/character assets/','meshes/armor/studded/','meshes/armor/ebony/',
              'meshes/armor/imperial/','meshes/armor/bandit/','meshes/armor/hide/','meshes/armor/daedric/',
              'meshes/armor/amuletsandrings/','meshes/clothes/yarlclothes','meshes/clothes/beggarclothes/',
              'meshes/weapons/daedric/'))
            entry['known_global_path']=is_global
            (inherited_models if key.endswith('.nif') else inherited_other).append(entry)
    output={'frozen_manifest':str(OUT/'gear_builder_manifest.json'),'multi_provider_assets':multi,'inherited_models':inherited_models,
      'inherited_other_assets':inherited_other,'summary':{'multi_provider':len(multi),
        'new_multi_different_sha':[r['path_key'] for r in multi if r['action']=='stage_explicit_source' and not r['same_sha256']],
        'inherited_models':len(inherited_models),'inherited_dedicated_models_not_identical':[r['path_key'] for r in inherited_models if not r['known_global_path'] and not r['all_donors_identical_to_base']],
        'inherited_global_models_not_identical':sum(r['known_global_path'] and not r['all_donors_identical_to_base'] for r in inherited_models)}}
    (OUT/'gear_collision_audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output['summary'],ensure_ascii=False,indent=2))
    for r in inherited_models:
        if not r['known_global_path']:print('dedicated/hair',r['path_key'],r['all_donors_identical_to_base'],r['requested_by'])


if __name__=='__main__':main()
