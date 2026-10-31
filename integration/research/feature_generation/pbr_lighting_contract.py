"""Pinned ordered TruePBR rule contracts and native trace witnesses, read-only."""
import argparse
import collections
import ctypes
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
from pg_nif_reader import NifFile,nifly
from pg_nif_validate import sha,owned
LIGHT_FIELDS=('smooth_angle','vertex_colors','vertex_color_lum_mult','vertex_color_sat_mult')
ASCII_LOWER=str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')

def lower(s):return str(s).translate(ASCII_LOWER)
def key(s):return lower(s).replace('\\','/')
def canonical_hash(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf8')).hexdigest()
def texbase(value,normal=False):
    # Windows filesystem::parent_path()/stem() then operator/ uses preferred
    # separator for the last join. Contract inputs are ASCII; rules are all
    # backslash paths, checked below. No guessed texture prefix is inserted.
    value=lower(value);pos=max(value.rfind('\\'),value.rfind('/'));parent=value[:pos] if pos>=0 else '';name=value[pos+1:]
    dot=name.rfind('.')
    if dot>0:name=name[:dot]
    value=parent+'\\'+name if parent else ('\\'+name if pos==0 else name)
    if normal:
        for suffix in ('_msn','_n'):
            if value.endswith(suffix):value=value[:-len(suffix)];break
    if value.startswith('textures\\pbr\\'):value='textures\\'+value[13:]
    return value

def rules_from_files(configs):
    rules=[];files=[]
    ordered=sorted(configs,key=lambda c:tuple(key(c['relative']).split('/')))
    for order,c in enumerate(ordered):
        rel=key(c['relative']);assert rel.isascii(),'NonASCII rule ordering requires independent native witness'
        p=Path(c['path']);raw=p.read_bytes();obj=json.loads(raw);digest=hashlib.sha256(raw).hexdigest()
        files.append({'relative':rel,'path':str(p),'sha256':digest,'provider':c['provider'],'file_order':order})
        if isinstance(obj,dict):
            if not ('default' in obj and 'entries' in obj):continue
            defaults=obj['default'];entries=obj['entries']
        else:defaults={};entries=obj
        assert isinstance(entries,list)
        for i,e in enumerate(entries):
            r={**defaults,**e}
            if 'texture' in r:r['match_diffuse']=r['texture']
            for f in ('match_normal','match_diffuse','rename'):
                if f in r:
                    assert isinstance(r[f],str) and '/' not in r[f],'Unmodeled rule path spelling'
                    if not r[f].startswith('\\'):r[f]='\\'+r[f]
            r['json']=rel.replace('/','\\')
            rules.append({'sequence':len(rules),'config':rel,'config_path':str(p),'config_sha256':digest,'provider':c['provider'],'entry_index':i,
              'native_rule':r,'native_rule_sha256':canonical_hash(r),'lighting_operation':{f:r[f] for f in LIGHT_FIELDS if f in r}})
    return files,rules

def matching_rules(rules,slots,mesh):
    assert len(slots)==9
    diffuse=texbase(slots[0]);normal=texbase(slots[1],True);mesh=lower(mesh).replace('/','\\');matches=[]
    for r in rules:
        v=r['native_rule']
        if 'nif_filter' in v and lower(v['nif_filter']) not in mesh:continue
        match=False
        if 'match_normal' in v:match=bool(normal) and normal.endswith(texbase(v['match_normal']))
        else:
            if 'match_diffuse' in v:match=bool(diffuse) and diffuse.endswith(texbase(v['match_diffuse']))
            if 'path_contains' in v and lower(v['path_contains']) in diffuse:match=True
        if match:matches.append(r)
    return matches

def groups_for(rules,slots,mesh):
    result=collections.defaultdict(list)
    for r in matching_rules(rules,slots,mesh):result[r['config']].append(r)
    return [{'config':k,'ordered_rule_sequences':[r['sequence'] for r in v],
       'ordered_rule_sha256':[r['native_rule_sha256'] for r in v],
       'ordered_lighting_operations':[r['lighting_operation'] for r in v],
       'contains_geometry_delete':any(r['native_rule'].get('delete',False) for r in v)} for k,v in result.items()]

def apply_group_slots(slots,group,rules):
    """Exact author matchedPath + applyOnePatchSlots, all nine slots retained."""
    from pbr_texture_closure import apply
    original=slots[:];result=slots[:]
    for seq in group['ordered_rule_sequences']:
        r=rules[seq]['native_rule'];field='match_normal' if 'match_normal' in r else 'match_diffuse'
        assert field in r,'Path-only matchedPath needs explicit author evidence'
        tex=texbase(original[1],True) if field=='match_normal' else texbase(original[0])
        if tex.startswith('textures\\'):tex='textures\\pbr\\'+tex[len('textures\\'):]
        matched=texbase(r[field]);assert len(tex)>=len(matched)
        matched=lower(tex[:-len(matched)]+r.get('rename',matched)) if matched else tex
        if not r.get('pbr',True):matched=''
        # The older audit helper has eight-slot storage and seven explicit-slot
        # overrides. Repair only the exact slot8 loop difference here.
        tail=result[8];result=apply(result[:8],r,matched)+[tail]
        if matched and 'slot8' in r:
            value=lower(r['slot8']);result[7]=value if not value or value.startswith('textures\\') else 'textures\\'+value
    return [lower(s) for s in result]

def source_matrix(run,proof):
    m=json.loads((run/'manifest.json').read_text(encoding='utf8'));sources=json.loads(proof.read_text(encoding='utf8'))
    configs=json.loads((OUT/'active_PBR_rules.json').read_text(encoding='utf8'));files,rules=rules_from_files(configs)
    expected={str(Path(r['path'])):r['sha256'] for r in m['rule_files']};assert expected=={str(Path(r['path'])):r['sha256'] for r in files},'Rule files drift from prepared run'
    static=json.loads((OUT/'source_inspection.json').read_text(encoding='utf8'));byhash={}
    for r in static['nifs']:byhash[(r['path_key'],r['sha256'])]=r
    dest=run/'lighting_contract';assert not dest.exists();dest.mkdir();meshes={};stats=collections.Counter()
    outcomes=json.loads((OUT/'pbr_texture_closure.json').read_text(encoding='utf8'))['outcomes'];outcomes={(r['mesh'],r['shader_block'],str(Path(r['config']))):r for r in outcomes}
    for i,(mesh,row) in enumerate(sorted(sources['entries'].items())):
        p=Path(row['snapshot']);assert sha(p)==row['sha256'];meta=byhash[(mesh,row['sha256'])]
        shaders={s['block']:s for s in meta['shaders']};geo=json.loads(Path(row['typed_snapshot']).read_text(encoding='utf8'));assert len(geo['shapes'])>0 or not meta['shaders']
        n=NifFile(str(p));shape_rows=[]
        try:
            assert len(n.shapes)==len(geo['shapes'])
            for shape,g in zip(n.shapes,geo['shapes']):
                assert shape.name==g['name'] and shape.blockname==g['block_type']
                sid=shape.properties.shaderPropertyID;shader=shaders.get(sid);slots=(shader['textures']+['']*9)[:9] if shader else ['']*9
                slots=[lower(s) for s in slots];assert all(',' not in s for s in slots),'Native trace CSV needs typed recovery for comma texture path'
                can_pbr=shader is not None and not (int(shader['flags1'],16)&(1<<21))
                groups=groups_for(rules,slots,mesh) if can_pbr else []
                for group in groups:
                    selected=[rules[j] for j in group['ordered_rule_sequences']];cfg=selected[0]['config_path'];closure=outcomes.get((mesh,sid,str(Path(cfg))))
                    group['static_default_target_status']=closure['status'] if closure else 'NO_PREVIOUS_DEFAULT_TARGET_OUTCOME_REQUIRES_NATIVE_OR_POST_RESOURCE_CHECK'
                    group['static_default_missing_paths']=closure['missing_paths'] if closure else None
                shape_rows.append({'source_block_id':shape.id,'source_shader_block_id':sid,'name':shape.name,'canonical_child_path':g['key'],'old_texture_slots':slots,'can_apply_TruePBR':can_pbr,'candidate_groups':groups,
                  'no_selected_recipe_policy':'All lighting attributes exact unless an actual native trace witness selects a validated ordered group.'})
                stats['shapes']+=1;stats['candidate_groups']+=len(groups);stats['shapes_with_recipe_candidates']+=bool(groups)
        finally:n.close()
        meshes[mesh]={'source_sha256':row['sha256'],'source_provider':row['provider'],'shapes':shape_rows}
        if i%200==0:print(json.dumps({'contract_sources':i+1,'total':len(sources['entries'])}),flush=True)
    report={'status':'PINNED_CANDIDATE_ORDERED_RULE_CONTRACT_NATIVE_SELECTION_REQUIRED','run_manifest_sha256':sha(run/'manifest.json'),'source_proof':str(proof),'source_proof_sha256':sha(proof),'files':files,'rules':rules,'meshes':meshes,'statistics':dict(stats),
      'native_sequence_basis':'PG BethesdaDirectory lowercase std::map path component order; loadStatics entries array order, per-config matched sequence map ascending. Native trace must exactly confirm every loaded sequence and rule JSON.',
      'selection':'JSON files are alternative candidates, never merged across files. Exact winning config comes from actual native trace, including alternate TXST texture slots. Default candidates alone never authorize a variant.',
      'boundaries':['Vertex positions/triangles/UVs/nodes/skin/weights/partitions remain exact. Only selected explicit lighting recipes authorize normal/tangent/color changes.',
       'All emitted textures and TXST canonical links require final resource closure. Any geometry delete is forbidden in this incoming-only pass.',
       'No game/GUI/PG/native helper execution performed by contract builder.']}
    (dest/'contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(stats))

def trace_witness(run,contract):
    m=json.loads(contract.read_text(encoding='utf8'));rules=m['rules'];loaded={};current={};logs=list((run/'tool/log').glob('PGPatcher*.log'));assert logs
    def slots_from(text):
        parts=text.rstrip('\r\n').split(',') if text else [];assert len(parts)<=9
        return ['']*(9-len(parts))+[lower(s) for s in parts]
    def order(p):
        v=re.search(r'\.(\d+)\.log$',p.name);return -(int(v.group(1)) if v else 0)
    for log in sorted(logs,key=order):
        with log.open(encoding='utf-8-sig',errors='strict') as f:
            for line_no,line in enumerate(f,1):
                match=re.search(r'TruePBR Config (\d+) Loaded: (\{.*\})',line)
                if match:
                    seq=int(match.group(1));obj=json.loads(match.group(2));assert seq<len(rules) and seq not in loaded
                    assert obj==rules[seq]['native_rule'],'Native load order/default preprocessing changed';loaded[seq]={'log':str(log),'line':line_no,'sha256':canonical_hash(obj)}
                context=re.search(r'\[(meshes[\\/].+?\.nif)\] \[([^\]]+)\] \[(\d+)/(.*)/(-?\d+)\]',line,re.I)
                if not context:continue
                mesh=key(context.group(1));use=context.group(2);bid=int(context.group(3));name=context.group(4);idx=int(context.group(5));ctx=(mesh,use,bid,name,idx)
                assert mesh in m['meshes'];shape=next(s for s in m['meshes'][mesh]['shapes'] if s['source_block_id']==bid);assert shape['name']==name
                event=current.setdefault(ctx,{'mesh':mesh,'use':use,'source_block_id':bid,'name':name,'old_index3D':idx,'source_child_path':shape['canonical_child_path'],
                  'selected_group':None,'has_alternate_texture':False,'complete':False,'log':str(log),'first_line':line_no})
                if 'Alternate texture exist for this shape' in line:event['has_alternate_texture']=True
                if 'Texture Slots: ' in line:
                    assert 'old_texture_slots' not in event,'Repeated source/context shape processing'
                    event['old_texture_slots']=slots_from(line.split('Texture Slots: ',1)[1])
                if 'Winning Match: ' in line:
                    shader,provider,config=[x.strip() for x in line.split('Winning Match: ',1)[1].rstrip('\r\n').split(' / ',2)];assert 'old_texture_slots' in event
                    selected=[]
                    if shader.lower()=='pbr':
                        config=key(config);selected=[g for g in groups_for(rules,event['old_texture_slots'],mesh) if g['config']==config]
                        assert len(selected)==1 and not selected[0]['contains_geometry_delete'],'Unproven or geometry-deleting native selected rule group'
                    else:assert shader.lower() in ('default','unknown'),'Unexpected enabled renderer family '+shader
                    event.update(native_winning_shader=shader,native_winning_provider=provider,config=config,selected_group=selected[0] if selected else None,winning_line=line_no)
                if 'Texture Slots Modified: ' in line:
                    event['modified_texture_slots']=slots_from(line.split('Texture Slots Modified: ',1)[1]);expected=apply_group_slots(event['old_texture_slots'],event['selected_group'],rules) if event['selected_group'] else event['old_texture_slots']
                    assert expected==event['modified_texture_slots'],'Native modified slots do not equal witnessed author rule group'
                    event.update(complete=True,completion_line=line_no)
                if 'Skipping: Shape is not patchable' in line:event.update(complete=True,skipped_unpatchable=True,completion_line=line_no)
    events=list(current.values());assert set(loaded)==set(range(len(rules))) and events,'Missing complete native loaded-rule sequence or shape witnesses'
    assert all(e['complete'] for e in events),'Incomplete native shape trace; no partial provenance accepted'
    dest=run/'lighting_contract/native_trace_witness.json';assert not dest.exists()
    result={'status':'NATIVE_ORDERED_RULE_AND_VARIANT_WITNESSES_PINNED','contract_sha256':sha(contract),'logs':[{'path':str(p),'sha256':sha(p)} for p in logs],'loaded':loaded,'events':events,
      'usage':'Pair actual output shape by canonical child path. Select only a witnessed config/old-texture use whose ordered color/normal attributes and actual output material/TXST match. No blind union of all candidates.'}
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'loaded_rules':len(loaded),'events':len(events)}))

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['build','trace']);p.add_argument('--run',required=True);p.add_argument('--source-proof');p.add_argument('--contract');a=p.parse_args();run=owned(a.run)
    if a.mode=='build':source_matrix(run,Path(a.source_proof).resolve())
    else:trace_witness(run,Path(a.contract).resolve())
if __name__=='__main__':main()
