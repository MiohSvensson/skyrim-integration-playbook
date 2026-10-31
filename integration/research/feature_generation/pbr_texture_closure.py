"""Apply only pinned TruePBR texture-slot rules in memory and audit target paths."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
sys.dont_write_bytecode=True
from renderer_audit import OUT,DB,norm,base,ri

def flag(r,k):return bool(r.get(k,False))
def apply(slots,r,matched):
    slots=(slots+['']*8)[:8]
    if not matched:return slots
    if not flag(r,'lock_diffuse'):slots[0]=matched+'.dds'
    if not flag(r,'lock_normal'):slots[1]=matched+'_n.dds'
    if 'emissive' in r and not flag(r,'lock_emissive'):slots[2]=matched+'_g.dds' if r['emissive'] else ''
    if 'parallax' in r and not flag(r,'lock_parallax'):slots[3]=matched+'_p.dds' if r['parallax'] else ''
    if 'cubemap' in r and not flag(r,'lock_cubemap'):slots[4]=r['cubemap']
    else:slots[4]=''
    if not flag(r,'lock_rmaos'):slots[5]=matched+'_rmaos.dds'
    if not flag(r,'lock_cnr'):
        slots[6]=matched+'_cnr.dds' if flag(r,'coat_normal') else ''
        if isinstance(r.get('fuzz'),dict) and flag(r['fuzz'],'texture'):slots[6]=matched+'_f.dds'
    if not flag(r,'lock_subsurface'):slots[7]=matched+'_s.dds' if any(flag(r,k) for k in ('subsurface_foliage','subsurface','coat_diffuse')) else ''
    for i in range(7):
        if f'slot{i+1}' in r:
            value=norm(r[f'slot{i+1}']);slots[i]=value if not value or value.startswith('textures\\') else 'textures\\'+value
    return slots

def main():
    audit=json.loads((OUT/'renderer_audit.json').read_text(encoding='utf-8'));outcomes=[];paths=set();errors=[]
    for nif in audit['PBR_candidates']:
        for shape in nif['shape_matches']:
            by_config=collections.defaultdict(list)
            for m in shape['matches']:by_config[m['config']].append(m)
            for config,matches in by_config.items():
                slots=shape['textures'][:];deleted=False
                for m in sorted(matches,key=lambda r:r['entry']):
                    r=m['rule']
                    if flag(r,'delete'):deleted=True;continue
                    field='match_normal' if 'match_normal' in r else 'match_diffuse'
                    if field not in r:
                        errors.append({'mesh':nif['path_key'],'config':config,'entry':m['entry'],'reason':'Unsupported path-only rule must be handled by actual author patcher'});continue
                    tex=base(shape['textures'][1] if field=='match_normal' else shape['textures'][0])
                    if field=='match_normal':
                        for suffix in ('_msn','_n'):
                            if tex.endswith(suffix):tex=tex[:-len(suffix)];break
                    tex=tex.replace('textures\\pbr\\','textures\\',1)
                    if tex.startswith('textures\\'):tex='textures\\pbr\\'+tex[len('textures\\'):]
                    matched='\\'+base(str(r[field])).lstrip('\\');assert tex.endswith(matched),'Matched suffix drift'
                    prefix=tex[:-len(matched)];rename=r.get('rename',matched);rename='\\'+str(rename).lstrip('\\')
                    matched=norm(prefix+rename)
                    if r.get('pbr',True) is False:matched=''
                    slots=apply(slots,r,matched)
                wanted=[] if deleted else sorted({norm(x) for x in slots if x})
                paths.update(x.replace('\\','/') for x in wanted)
                outcomes.append({'mesh':nif['path_key'],'shader_block':shape['shader_block'],'config':config,'delete_shape_rule':deleted,'final_slots':slots,'needed_paths':wanted})
    ri.PROFILE=DB/'UnifiedSkyrim/profiles/Unified Build';mods=ri.active_mods();ranks={n:i for i,(n,_) in enumerate(mods)};folders=dict(mods)
    baseline={r['id']:r for r in json.loads((DB/'integration/baseline_mods.json').read_text(encoding='utf-8')) if r['directory'] in ranks}
    c=sqlite3.connect('file:'+(DB/'baseline/skyrim_research.sqlite').as_posix()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    found={};allpaths=sorted(paths)
    for start in range(0,len(allpaths),350):
        part=allpaths[start:start+350]
        for f in c.execute('select mod_id,relative_path,path_key,size_bytes from files where path_key in ('+','.join('?' for _ in part)+')',part):
            mod=baseline.get(f['mod_id'])
            if not mod:continue
            name=mod['directory'];rank=ranks[name]
            if f['path_key'] not in found or rank<found[f['path_key']]['rank']:
                found[f['path_key']]={'kind':'loose','rank':rank,'provider':name,'physical':str(folders[name]/f['relative_path']),'bytes':f['size_bytes']}
    mappings=json.loads((DB/'integration/features_preflight.json').read_text(encoding='utf-8'))['mappings']
    selected_archives={r['archive']['path'] for r in json.loads((OUT/'source_inspection.json').read_text(encoding='utf-8'))['archive_manifest']}
    for m in mappings:
        key=m['relative'].lower().replace('\\','/')
        if key not in paths:continue
        p=Path(m['destination']);p=p if p.is_absolute() else DB/'UnifiedSkyrim'/p;name=p.relative_to(DB/'UnifiedSkyrim/mods').parts[0]
        if key not in found or ranks[name]<found[key]['rank']:found[key]={'kind':'loose','rank':ranks[name],'provider':name,'physical':str(p),'bytes':p.stat().st_size}
    active_archive_ids={r[0] for r in c.execute('select archive_id from bsa_sources where mod_id in ('+','.join('?' for _ in baseline)+')',list(baseline))}
    for row in c.execute('select id,path from bsa_archives'):
        if row['path'] in selected_archives or norm(row['path']).startswith(norm(str(DB.parent/'TuLED/STOCK GAME'))):active_archive_ids.add(row['id'])
    archive_candidates=collections.defaultdict(list)
    for start in range(0,len(allpaths),350):
        part=[p for p in allpaths[start:start+350] if p not in found]
        if not part:continue
        for r in c.execute('select e.archive_id,e.path_key,e.sha256,e.size_bytes,a.path from bsa_entries e join bsa_archives a on a.id=e.archive_id where e.path_key in ('+','.join('?' for _ in part)+')',part):
            if r['archive_id'] in active_archive_ids:archive_candidates[r['path_key']].append(dict(r))
    for key,rs in archive_candidates.items():
        found[key]={'kind':'BSA_candidates_need_actual_VFS_archive_order_check','candidates':rs,'all_same_member_sha256':len({r['sha256'] for r in rs})==1}
    actual_black=OUT/'black_texture_actual.json'
    if actual_black.exists() and 'textures/black.dds' in paths:
        proof=json.loads(actual_black.read_text());provider,physical=ri.resolve(proof['logical_archive'],mods)
        assert provider==proof['provider'] and str(physical)==proof['physical_archive'],'Refresh actual BSA member proof after provider drift'
        with physical.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==proof['archive_sha256']
        found['textures/black.dds']={'kind':'BSA_ACTUAL_LOGICAL_ARCHIVE_WINNER_EXTRACTED',**proof}
    for key,r in found.items():
        if r['kind']=='loose':
            p=Path(r['physical']);r['sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
            with p.open('rb') as stream:r['header_hex']=stream.read(128).hex()
            assert bytes.fromhex(r['header_hex']).startswith(b'DDS '),'Texture target is not a DDS'
    missing=sorted(paths-found.keys());counts=collections.Counter()
    for o in outcomes:
        gaps=[p for p in o['needed_paths'] if p.replace('\\','/') not in found];o['missing_paths']=gaps
        o['status']='DELETE_SHAPE_RULE_REQUIRES_REVIEW' if o['delete_shape_rule'] else 'COMPLETE_TARGET_PATH_CLOSURE' if not gaps else 'MISSING_TARGET_PATHS_PATCHER_CHECKPATHS_WILL_REJECT'
        counts[o['status']]+=1
    report={'status':'STATIC_PBR_TARGET_CLOSURE_AUDIT','pinned_slot_source':'PGPatcher0.9.9.5 PatcherMeshShaderTruePBR.cpp729-827','statistics':dict(counts),'unique_target_paths':len(paths),
        'resolved_paths':len(found),'missing_paths':missing,'source_errors':errors,'textures':found,'outcomes':outcomes,
        'limits':['Candidate shader/config combinations are independent alternatives; actual PGPatcher chooses priority and may discover alternate plugin texture sets.','BSA candidates are restricted to active source mods/selected imported archives; actual launch must prove archive registration/order where member hashes differ.','Missing-rule targets must remain rejected with truepbr_checkpaths=true; never force nonexistent textures into NIFs.']}
    (OUT/'pbr_texture_closure.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('statistics','unique_target_paths','resolved_paths','missing_paths','source_errors')},ensure_ascii=False)[:4500])
if __name__=='__main__':main()
