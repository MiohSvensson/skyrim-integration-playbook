"""Static incoming-NIF / final-loose-provider / pinned TruePBR-rule audit."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(DB/'integration'));import runtime_inventory as ri

def norm(s):return s.lower().replace('/','\\')
def base(s):return norm(s).rsplit('.',1)[0] if '.' in s.rsplit('\\',1)[-1] else norm(s)
def main():
    d=json.loads((OUT/'source_inspection.json').read_text(encoding='utf-8'));configs=json.loads((OUT/'active_PBR_rules.json').read_text(encoding='utf-8'))
    ri.PROFILE=DB/'UnifiedSkyrim/profiles/Unified Build';mods=ri.active_mods();ranks={n:i for i,(n,_) in enumerate(mods)};folders=dict(mods)
    baseline={r['id']:r for r in json.loads((DB/'integration/baseline_mods.json').read_text(encoding='utf-8')) if r['directory'] in ranks}
    wanted={r['path_key'] for r in d['nifs']};loose={};c=sqlite3.connect('file:'+(DB/'baseline/skyrim_research.sqlite').as_posix()+'?mode=ro',uri=True)
    keys=sorted(wanted)
    for begin in range(0,len(keys),400):
        part=keys[begin:begin+400]
        for mid,rel,key in c.execute('select mod_id,relative_path,path_key from files where path_key in ('+','.join('?' for _ in part)+')',part):
            row=baseline.get(mid)
            if row:
                name=row['directory'];candidate=(ranks[name],name,str(folders[name]/rel))
                if key not in loose or candidate[0]<loose[key][0]:loose[key]=candidate
    plan=json.loads((DB/'integration/features_preflight.json').read_text(encoding='utf-8'))
    for m in plan['mappings']:
        key=m['relative'].lower().replace('\\','/')
        if key not in wanted:continue
        path=Path(m['destination'])
        if not path.is_absolute():path=DB/'UnifiedSkyrim'/path
        name=path.relative_to(DB/'UnifiedSkyrim/mods').parts[0]
        candidate=(ranks[name],name,str(path))
        if key not in loose or candidate[0]<loose[key][0]:loose[key]=candidate
    rules=[]
    for config in configs:
        obj=config['json'];defaults=obj.get('default',{}) if isinstance(obj,dict) else {};entries=obj.get('entries',[]) if isinstance(obj,dict) else obj
        if not isinstance(entries,list):continue
        for i,e in enumerate(entries):
            r={**defaults,**e}
            if 'texture' in r:r['match_diffuse']=r['texture']
            rules.append({'source':config['path'],'provider':config['provider'],'entry':i,'rule':r})
    candidates=[];unchanged=[];shadows=[];stats=collections.Counter()
    for nif in d['nifs']:
        key=nif['path_key'];blocked=False
        if key in loose:
            rank,name,path=loose[key];digest=hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if digest!=nif['sha256']:
                blocked=True;shadows.append({'incoming':{k:nif[k] for k in ('path_key','sha256','kind','feature')},'final_loose_provider':name,'final_loose_path':path,'final_loose_sha256':digest,
                    'old_PG_diff':nif.get('old_PG_diff'),'same_as_old_PG_original':nif.get('matches_old_PG_original'),'action':'Preserve final TuLED loose winner; do not process hidden incoming copy or replace base mesh without geometry review.'})
        if blocked:stats['source_NIFs_shadowed_by_different_final_loose_mesh']+=1;continue
        shape_matches=[]
        for shader in nif['shaders']:
            # The pinned patcher refuses FACEGEN_RGB_TINT.
            if int(shader['flags1'],16)&(1<<21):continue
            tex=shader['textures'];diff=base(tex[0]) if tex else '';normal=base(tex[1]) if len(tex)>1 else ''
            for suffix in ('_msn','_n'):
                if normal.endswith(suffix):normal=normal[:-len(suffix)];break
            diff=diff.replace('textures\\pbr\\','textures\\',1);normal=normal.replace('textures\\pbr\\','textures\\',1)
            matches=[]
            for item in rules:
                r=item['rule']
                if 'nif_filter' in r and norm(r['nif_filter']) not in norm(key):continue
                matched=[]
                checks=[('match_normal',normal)] if 'match_normal' in r else [('match_diffuse',diff)]
                for field,value in checks:
                    if field in r and value.endswith('\\'+base(str(r[field])).lstrip('\\')):matched.append(field)
                if 'match_normal' not in r and 'path_contains' in r and norm(str(r['path_contains'])) in diff:matched.append('path_contains')
                if matched:matches.append({'config':item['source'],'entry':item['entry'],'matched_fields':matched,'rule':r})
            if matches:shape_matches.append({'shader_block':shader['block'],'shader_type':shader['shader_type'],'textures':tex,'matches':matches})
        statics={k:nif[k] for k in ('path_key','sha256','bytes','kind','feature','bs_version')}
        if shape_matches:
            candidates.append({**statics,'shape_matches':shape_matches,'status':'TRUEPBR_RULE_MATCH_REQUIRES_PATCHER_TEXTURE_EXISTENCE_AND_RESULT_CHECK'});stats['effective_source_NIFs_with_TruePBR_rule_match']+=1
        else:
            unchanged.append({**statics,'status':'NO_EXPLICIT_TRUEPBR_RULE_MATCH_STANDARD_SHADERS_RENDERABLE_CM_HEIGHT_DISCOVERY_STILL_CONDITIONAL'});stats['effective_source_NIFs_without_explicit_TruePBR_rule_match']+=1
    report={'status':'STATIC_BOUNDED_RENDERER_AUDIT_NOT_GENERATED','profile_plugins_sha256':hashlib.sha256((ri.PROFILE/'plugins.txt').read_bytes()).hexdigest(),
        'source_inspection_sha256':hashlib.sha256((OUT/'source_inspection.json').read_bytes()).hexdigest(),'active_TruePBR_config_files':len(configs),'active_TruePBR_entries':len(rules),
        'statistics':dict(stats),'source_shader_summary':{'type_counts':dict(collections.Counter(s['shader_type'] for r in d['nifs'] for s in r['shaders'])),
            'explicit_parallax_flag_shapes':sum(s['parallax_flag'] for r in d['nifs'] for s in r['shaders']),
            'incoming_PBR_or_RMAOS_texture_paths':sum(any('_rmaos' in t.lower() or 'textures\\pbr\\' in t.lower() for t in s['textures']) for r in d['nifs'] for s in r['shaders'])},
        'PBR_candidates':candidates,'standard_shader_inputs':unchanged,'shadowed_source_meshes':shadows,
        'format_errors':d['errors'],'limitations':['This matches pinned author rules, not actual patcher output. Rule precedence/deletion/texture existence and alternate plugin texture sets require actual private processing and verification.',
            'No NIF is declared fully unnecessary solely from its filename. Non-rule CM/height discovery may qualify additional non-skinned shapes.',
            'No original/hardlink target was written. Source configs with old absolute paths must never be executed as-is.']}
    (OUT/'renderer_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    allow=sorted({r['path_key'].replace('/','\\') for r in candidates+unchanged if not r['path_key'].startswith(('meshes/lod/','meshes/terrain/'))})
    (OUT/'incoming_effective_mesh_allowlist.json').write_text(json.dumps(allow,indent=2)+'\n')
    print(json.dumps({'statistics':report['statistics'],'configs':len(configs),'rules':len(rules),'allowlist':len(allow)},indent=2))
if __name__=='__main__':main()
