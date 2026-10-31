"""Bounded item plugin audit and explicit model/texture/physics resource graph.

Reads original sources. Extracted NIF samples stay in this research directory.
No whole mixed mod, configuration, script, DLL or behavior tree is imported.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'rootcause'))
import plugin_binary
import nif_inventory

DATA=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))
STRICT={'ARMA','ARMO','WEAP','TXST','COBJ','KYWD','MATT','OTFT','ENCH','MGEF','SPEL','BOOK','FLST','EXPL','PROJ','STAT','ARTO','EFSH','SOUN','SNDR','SNCT','SOPM','IPDS'}
MODEL_TAGS={'MODL','MOD2','MOD3','MOD4','MOD5','DMDL'}
EXTENSIONS={'.nif','.dds','.tri','.xml','.hkx','.wav','.xwm','.fuz'}


def winpath(path):
    s=str(Path(path).absolute())
    return s if s.startswith('\\\\?\\') else '\\\\?\\'+s


def normal(value,kind=None,parent=None):
    value=value.strip('\x00 \r\n\t').replace('\\','/').strip('/')
    if not value:return None
    if ':' in value:
        m=re.search(r'(meshes|textures|skse|sound|music)/',value,re.I)
        if not m:return None
        value=value[m.start():]
    if value.casefold().startswith('data/'):value=value[5:]
    ext=Path(value).suffix.casefold()
    if ext not in EXTENSIONS:return None
    if kind=='model' and not value.casefold().startswith('meshes/'):value='meshes/'+value
    elif kind=='texture' and not value.casefold().startswith('textures/'):value='textures/'+value
    elif ext in ('.nif','.tri','.hkx') and not value.casefold().startswith('meshes/'):
        value='meshes/'+value
    elif ext=='.dds' and not value.casefold().startswith('textures/'):
        value='textures/'+value
    elif ext=='.xml' and not value.casefold().startswith(('skse/','meshes/')):
        value=(str(Path(parent).parent).replace('\\','/')+'/' if parent else '')+value
    if '..' in Path(value).parts:return None
    return value.casefold()


def main():
    c=sqlite3.connect((ROOT/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    mods={r['id']:dict(r) for r in c.execute('select * from mods')}
    packids={r['name']:r['id'] for r in c.execute('select id,name from packs')}
    games={r['name']:r['game_path'] for r in c.execute('select name,game_path from packs')}
    priorities=collections.defaultdict(dict)
    for r in c.execute('''select p.name,pm.mod_id,pm.list_order from profile_mods pm join profiles r on r.id=pm.profile_id
      join packs p on p.id=r.pack_id where r.is_selected=1 and pm.enabled=1 and pm.mod_id is not null'''):
        priorities[r['name']][r['mod_id']]=r['list_order']
    plugin_order={p:{key:i for i,key in enumerate(rows)} for p,rows in DATA['source_plugins'].items()}
    resolved_cache={};extracted_cache={};sample=OUT/'nif_samples';sample.mkdir(exist_ok=True)

    def resolve(pack,key):
        cachekey=(pack,key)
        if cachekey in resolved_cache:return resolved_cache[cachekey]
        options=[]
        for r in c.execute('select mod_id,relative_path,size_bytes from files indexed by ix_file_path where path_key=? and virtual_candidate=1',(key,)):
            if r['mod_id'] in priorities[pack]:options.append(dict(r))
        if options:
            r=min(options,key=lambda x:priorities[pack][x['mod_id']]);m=mods[r['mod_id']]
            out={'kind':'loose','path':str(Path(m['path'])/r['relative_path']),'mod_id':m['id'],'mod_name':m['name'],
              'size_bytes':r['size_bytes'],'original_priority':priorities[pack][m['id']]}
            resolved_cache[cachekey]=out;return out
        loose=Path(games[pack])/'Data'/key.replace('/', '\\')
        if loose.is_file():
            out={'kind':'stock_loose','path':str(loose),'size_bytes':loose.stat().st_size}
            resolved_cache[cachekey]=out;return out
        archives=[]
        for r in c.execute('''select a.id,a.path,a.sha256 as archive_sha256,e.sha256,e.size_bytes,s.mod_id,s.source_kind,s.relative_path
          from bsa_entries e indexed by ix_bsa_entries_path join bsa_archives a on a.id=e.archive_id
          join bsa_sources s on s.archive_id=a.id where e.path_key=? and s.pack_id=? and e.status='ok' ''',(key,packids[pack])):
            r=dict(r);mid=r['mod_id'];name=Path(r['relative_path']).name.casefold()
            if r['source_kind'] not in ('mod','stock Data'):continue
            if mid is not None and mid not in priorities[pack]:continue
            plugin_stem=Path(name).stem.split(' - ')[0]
            associated=[p for p in plugin_order[pack] if Path(p).stem==plugin_stem]
            if mid is not None and not associated:continue
            actual_archive=resolve(pack,name)
            if actual_archive.get('path','').casefold()!=r['path'].casefold():continue
            r['associated_plugins']=associated;r['activation_evidence']='active associated plugin name' if associated else 'stock archive candidate'
            archives.append(r)
        if archives:
            hashes={r['sha256'] for r in archives}
            if len(hashes)==1:
                r=archives[0]
                out={'kind':'bsa_same_content_candidates','path':r['path'],'archive_id':r['id'],'sha256':r['sha256'],'size_bytes':r['size_bytes'],
                     'alternatives':archives,'entry':key,'mod_id':r['mod_id']}
            else:
                rank=lambda a:max((plugin_order[pack][p]+1 for p in a['associated_plugins']),default=0)
                top=max(rank(a) for a in archives);top_candidates=[a for a in archives if rank(a)==top]
                if len({a['sha256'] for a in top_candidates})==1:
                    r=top_candidates[0]
                    out={'kind':'bsa_associated_loadorder_candidate','path':r['path'],'archive_id':r['id'],'sha256':r['sha256'],
                      'size_bytes':r['size_bytes'],'alternatives':archives,'entry':key,'mod_id':r['mod_id'],
                      'limitation':'Associated-plugin order inferred from selected snapshot; live VFS/engine archive ordering still to verify.'}
                else:out={'kind':'ambiguous_bsa','candidates':archives,'entry':key}
        else:out={'kind':'missing','entry':key}
        resolved_cache[cachekey]=out;return out

    def physical(asset,key):
        if asset['kind'] in ('loose','stock_loose'):return Path(asset['path'])
        if asset['kind'] in ('bsa_same_content_candidates','bsa_associated_loadorder_candidate'):
            stamp=(asset['archive_id'],key)
            if stamp in extracted_cache:return extracted_cache[stamp]
            import bsarch_readonly
            blob=bsarch_readonly.extract_files(Path(asset['path']),{key:asset['sha256']})[key]
            p=sample/(asset['sha256']+Path(key).suffix);p.write_bytes(blob);extracted_cache[stamp]=p;return p
        return None

    rows=[r for r in DATA['base_additions']['TuLED']['candidates'] if r['status']=='eligible_bounded_new_items' and
      set(r['record_signatures'])<=STRICT and ('ARMO' in r['record_signatures'] or 'WEAP' in r['record_signatures'])]
    results=[]
    for index,row in enumerate(rows):
        source=row.get('validated_replacement',{}).get('candidate') or row['snapshot_path']
        masters,records=plugin_binary.read(source)
        root_plugins=c.execute('select name,relative_path from plugin_files where mod_id=? and instr(relative_path,char(92))=0 and instr(relative_path,\'/\')=0',(row['source_mod_id'],)).fetchall()
        source_runtime_files=[dict(r) for r in c.execute("select relative_path,extension,size_bytes from files where mod_id=? and extension in ('.dll','.exe','.pex')",(row['source_mod_id'],))]
        vmad=[];direct=[];types=collections.Counter(r['sig'] for r in records if r['sig']!='TES4')
        for record in records:
            for tag,value in record['fields']:
                if tag=='VMAD':vmad.append({'signature':record['sig'],'form_id':f"{record['fid']:08X}",'edid':record['edid'],'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()})
                if tag in MODEL_TAGS:
                    key=normal(value.rstrip(b'\0').decode('utf-8','replace'),'model')
                elif record['sig']=='TXST' and re.fullmatch('TX0[0-7]',tag):
                    key=normal(value.rstrip(b'\0').decode('utf-8','replace'),'texture')
                elif tag in ('ICON','MICO'):
                    key=normal(value.rstrip(b'\0').decode('utf-8','replace'),'texture')
                else:continue
                if key:direct.append({'key':key,'signature':record['sig'],'form_id':f"{record['fid']:08X}",'edid':record['edid'],'field':tag})
        seen={};queue=collections.deque((d['key'],'plugin') for d in direct);inspection_errors=[];edges=[]
        while queue:
            key,parent=queue.popleft()
            if key in seen:continue
            asset=resolve(row['pack'],key);base=resolve('TuLED',key)
            entry={'path_key':key,'source':asset,'base_presence':base,'referenced_by':parent};seen[key]=entry
            if asset['kind'] in ('missing','ambiguous_bsa'):continue
            ext=Path(key).suffix
            if ext=='.nif':
                try:
                    path=physical(asset,key);inv=nif_inventory.inventory(winpath(path));entry['nif_sha256']=inv['sha256'];entry['nif_version']=[inv['user_version'],inv['bs_version']]
                    refs=[]
                    for block in inv['blocks']:
                        for texture in block.get('textures',[]):
                            k=normal(texture,'texture',key)
                            if k:refs.append((k,'BSShaderTextureSet'))
                    # Node/shape names can look like filenames. Only typed extra-data values are paths.
                    nif_bytes=Path(winpath(path)).read_bytes();extra=[]
                    for block in inv['blocks']:
                        if block['type']!='NiStringExtraData':continue
                        assert block['bytes']==8,block
                        ni,vi=__import__('struct').unpack_from('<II',nif_bytes,block['offset'])
                        name=inv['strings'][ni] if ni!=0xffffffff else ''
                        value=inv['strings'][vi] if vi!=0xffffffff else ''
                        extra.append({'name':name,'value':value})
                        k=normal(value,parent=key)
                        if k:refs.append((k,'NiStringExtraData:'+name))
                    entry['nif_string_extra_data']=extra
                    behavior_graphs=[]
                    for block in inv['blocks']:
                        if block['type']!='BSBehaviorGraphExtraData':continue
                        assert block['bytes']==9,block
                        ni,vi=__import__('struct').unpack_from('<II',nif_bytes,block['offset'])
                        name=inv['strings'][ni] if ni!=0xffffffff else ''
                        value=inv['strings'][vi] if vi!=0xffffffff else ''
                        behavior_graphs.append({'name':name,'behavior_graph_file':value})
                        k=normal(value,parent=key)
                        if k:refs.append((k,'BSBehaviorGraphExtraData:Behavior Graph File'))
                    entry['nif_behavior_graph_extra_data']=behavior_graphs
                    # Weighted armor models conventionally load both endpoints.
                    if key.endswith(('_0.nif','_1.nif')):
                        other=key[:-5]+('1.nif' if key.endswith('_0.nif') else '0.nif')
                        if resolve(row['pack'],other)['kind']!='missing':refs.append((other,'weight endpoint pair'))
                    for child,field in refs:
                        edges.append({'from':key,'to':child,'field':field});queue.append((child,key))
                except Exception as e:inspection_errors.append({'path_key':key,'error':repr(e)})
            elif ext=='.xml':
                try:
                    path=physical(asset,key);data=Path(winpath(path)).read_bytes();ET.fromstring(data)
                    for token in re.findall(rb'[\x20-\x7e]{4,}',data):
                        text=token.decode('ascii');
                        for value in re.findall(r'[\"\']([^\"\']+\.(?:xml|nif|tri|dds))[\"\']',text,re.I):
                            child=normal(value,parent=key)
                            if child:edges.append({'from':key,'to':child,'field':'XML quoted asset'});queue.append((child,key))
                except Exception as e:inspection_errors.append({'path_key':key,'error':repr(e)})
        missing=[k for k,v in seen.items() if v['source']['kind']=='missing'];optional_morph=[k for k in missing if k.endswith('.tri')]
        required_missing=[k for k in missing if k not in optional_morph];ambiguous=[k for k,v in seen.items() if v['source']['kind']=='ambiguous_bsa']
        results.append({k:row[k] for k in ['pack','name','source_mod_id','source_mod','source_path','is_light','masters','owned_records','override_records']}|
          {'plugin_path_for_validation':source,'record_signatures':dict(types),'record_count_including_header':len(records),'vmad_records':vmad,
           'leveled_records':sum(types[t] for t in ['LVLI','LVLN','LVSP']),'world_records':sum(types[t] for t in ['WRLD','CELL','NAVM','NAVI','LAND','REFR','ACHR']),
           'mixed_bundle':len(root_plugins)>1,'root_plugins_in_source_mod':[r['name'] for r in root_plugins],
           'direct_asset_references':direct,'assets':list(seen.values()),'asset_edges':edges,'missing_assets':missing,
           'missing_required_assets':required_missing,'missing_optional_morph_tri':optional_morph,'source_runtime_files_not_imported':source_runtime_files,
           'ambiguous_archive_assets':ambiguous,'inspection_errors':inspection_errors,
           'bounded_static_closure_passed':bool(direct) and not(vmad or required_missing or ambiguous or inspection_errors),
           'limitations':'Typed plugin model/TXST paths, SSE NIF NiStringExtraData/BSShaderTextureSet, XML references and existing weight endpoint pairs only. Missing BODYTRI morph files are separate optional limitations; no scripts/behavior/config side-effects are imported and no runtime proof.'})
        if index%15==0:print('audited',index+1,'of',len(rows),flush=True)
    output={'base':'TuLED','scope':'Explicit gear-only resource planning, original sources unchanged. BSA source inference is not a live VFS result.',
      'candidates':results,'counts':{'plugins':len(results),'static_closure_passed':sum(r['bounded_static_closure_passed'] for r in results),
        'mixed_bundle_plugins':sum(r['mixed_bundle'] for r in results),'unique_assets':len({a['path_key'] for r in results for a in r['assets']})}}
    (OUT/'gear_resource_closure.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(output['counts'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
