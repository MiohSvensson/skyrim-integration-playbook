"""Bounded physical resource manifest for the three selected LOTD/TCC patches."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent;BASE=OWN.parents[2]
sys.path.insert(0,str(BASE/'integration/research/vfs_validation'))
from vfs_common import *
OWN=Path(__file__).resolve().parent
from quest_resource_seeds import records,vmad_scripts,text
from external_nif_refs import effect_textures
sys.path.insert(0,str(BASE/'rootcause'))
from bsarch_readonly import extract_files
from nif_resource_inventory import inventory


def main():
    db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    mods={r['id']:dict(r) for r in db.execute('select * from mods')}
    priority={r['mod_id']:r['list_order'] for r in db.execute('''select pm.mod_id,pm.list_order from profile_mods pm join profiles p on p.id=pm.profile_id where p.pack_id=1 and p.is_selected=1 and pm.enabled=1 and pm.mod_id is not null''')}
    source_meta=json.loads((BASE/'integration/research/plugin_integration/plugin_candidates.json').read_text(encoding='utf-8'))
    order={key(n):i for i,n in enumerate(source_meta['source_plugins']['Anno'])}
    stock=Path(db.execute('select game_path from packs where id=1').fetchone()[0])/'Data'
    snap=sqlite3.connect((BASE/'integration/research/vfs_validation/phase2_expectations.sqlite').as_uri()+'?mode=ro',uri=True);snap.row_factory=sqlite3.Row
    e=json.loads(snap.execute("select value from metadata where key='expectations'").fetchone()[0]);physical={r['path_key']:dict(r) for r in snap.execute('select * from files')}
    archives={key(n):dict(physical[key(n)],order=i) for i,n in enumerate(e['archive_names'])};base=ResourceCatalog(physical,archives);base.archive_hashes.update(e['archive_hashes_required'])
    cache={};blobs={};errors=[];variants=[];edges=[];used={};direct=collections.defaultdict(list)
    manifest=json.loads((BASE/'integration/research/plugin_integration/feature_builder_manifest.json').read_text(encoding='utf-8'))
    plugins=[p for f in manifest['features'] for p in f.get('optional_selected_patches',[])]
    feature_mods={m['id'] for f in manifest['features'] for m in f.get('mods',[])}
    def source(k):
        if k in cache:return cache[k]
        loose=[dict(r) for r in db.execute('select mod_id,relative_path,size_bytes from files where path_key=? and virtual_candidate=1',(k,)) if r['mod_id'] in priority]
        preferred=feature_mods|{p['source_mod_id'] for p in plugins}
        author_loose=[r for r in loose if r['mod_id'] in preferred]
        # With a new quest, prefer the complete author's resource layer over
        # unrelated old generated source-pack output. The selected base still wins.
        author_bsa=[]
        if not author_loose and '/' in k:
            for ar in db.execute('''select a.id,a.path,a.sha256 archive_sha,e.sha256,e.size_bytes,s.mod_id from bsa_entries e join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=a.id where e.path_key=? and s.pack_id=1 and s.source_kind='mod' and e.status='ok' ''',(k,)):
                if ar['mod_id'] in preferred:
                    name=key(Path(ar['path']).name);stem=Path(name).stem.removesuffix(' - textures');rank=max((order[n] for n in order if Path(n).stem==stem),default=-1)
                    if rank>=0:author_bsa.append((rank,dict(ar)))
        if author_loose:
            r=min(author_loose,key=lambda x:priority.get(x['mod_id'],10**8));p=Path(mods[r['mod_id']]['path'])/r['relative_path']
            found={'kind':'loose','physical_path':str(p),'relative_path':r['relative_path'],'mod_id':r['mod_id'],'sha256':digest(p),'bytes':r['size_bytes']}
        elif author_bsa:
            _,r=max(author_bsa,key=lambda x:x[0]);found={'kind':'bsa','archive_physical':r['path'],'archive_id':r['id'],'archive_sha256':r['archive_sha'],'entry':k,'sha256':r['sha256'],'bytes':r['size_bytes'],'mod_id':r['mod_id']}
        elif loose:
            r=min(loose,key=lambda x:priority[x['mod_id']]);p=Path(mods[r['mod_id']]['path'])/r['relative_path']
            found={'kind':'loose','physical_path':str(p),'relative_path':r['relative_path'],'mod_id':r['mod_id'],'sha256':digest(p),'bytes':r['size_bytes']}
        elif (stock/k).is_file():found={'kind':'stock_loose','physical_path':str(stock/k),'sha256':digest(stock/k),'bytes':(stock/k).stat().st_size}
        else:
            matches=[]
            for r in db.execute('''select a.id,a.path,a.sha256 archive_sha,e.sha256,e.size_bytes,s.mod_id,s.source_kind from bsa_entries e join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=a.id where e.path_key=? and s.pack_id=1 and s.source_kind in ('mod','stock Data') and e.status='ok' ''',(k,)):
                mid=r['mod_id'];name=key(Path(r['path']).name)
                if mid is not None and mid not in priority:continue
                stem=Path(name).stem.removesuffix(' - textures');associated=[n for n in order if Path(n).stem==stem]
                if mid is not None and not associated:continue
                logical=source(name)
                if logical.get('physical_path','').casefold()!=r['path'].casefold():continue
                rank=max((order[n] for n in associated),default=-1);matches.append((rank,dict(r)))
            if matches:
                _,r=max(matches,key=lambda x:x[0]);found={'kind':'bsa','archive_physical':r['path'],'archive_id':r['id'],'archive_sha256':r['archive_sha'],'entry':k,'sha256':r['sha256'],'bytes':r['size_bytes'],'mod_id':r['mod_id']}
            else:found={'kind':'missing'}
        cache[k]=found;return found
    def read_blob(k,loc):
        if k in blobs:return blobs[k]
        if loc['kind'] in ('loose','stock_loose'):b=Path(lp(loc['physical_path'])).read_bytes()
        else:b=extract_files(loc['archive_physical'],{loc['entry']:loc['sha256']})[loc['entry']]
        blobs[k]=b;return b
    plugin_rows=[]
    for p in plugins:
        h=plugin_header(p['source_path']);sge=[]
        for r in records(p['source_path'],masters=h['masters'],name=p['name']):
            for tag,b in r['fields']:
                v=text(b);k=None
                if tag in ('MODL','MOD2','MOD3','MOD4','MOD5') and v:k=asset_key(v)
                elif r['sig']=='TXST' and tag.startswith('TX0') and v:k=asset_key(v,'texture')
                if k:direct[k].append({'plugin':p['name'],'record':r['identity'],'field':tag})
                if tag=='VMAD':
                    for script,where in vmad_scripts(b,r['sig']):direct[key('scripts/'+script.removesuffix('.psc')+'.pex')].append({'plugin':p['name'],'record':r['identity'],'field':where})
            if r['sig']=='QUST' and r['fid']>>24>=len(h['masters']):
                d=next((v for t,v in r['fields'] if t=='DNAM'),b'')
                if len(d)>=2 and struct.unpack_from('<H',d)[0]&1:sge.append(r['identity'])
        if sge:direct[key('seq/'+Path(p['name']).stem+'.seq')].append({'plugin':p['name'],'field':'Own SGE quest sequence','records':sge})
        plugin_rows.append({'name':p['name'],'source_path':p['source_path'],'source_mod_id':p['source_mod_id'],**h,'own_sge_quests':sge})
    queue=collections.deque(direct);seen=set();sample=OWN/'nif_cache';sample.mkdir(exist_ok=True)
    while queue:
        k=queue.popleft()
        if k in seen:continue
        seen.add(k);baseline=base.resolve(k);src=source(k)
        if baseline['kind']!='missing':
            if baseline['kind']=='loose':baseline['sha256']=digest(baseline['physical_path'])
            disposition='inherit_base';loc=baseline
            if src.get('sha256') and src['sha256']!=baseline['sha256']:variants.append({'path_key':k,'source_sha256':src['sha256'],'base_sha256':baseline['sha256'],'decision':'Keep selected TuLED base resource winner; variant is explicit.'})
        elif src['kind']!='missing':
            loc=src;disposition='inherit_standalone_feature_or_stage_if_absent' if src.get('mod_id') in feature_mods else 'stage_exact_source_resource'
        else:errors.append({'kind':'patch_resource_missing','path_key':k});continue
        used[k]={'path_key':k,'decision':disposition,'selected_source':loc,'source_anno_candidate':src,'requested_by':direct.get(k,[])}
        if k.endswith('.nif'):
            try:
                b=read_blob(k,loc);sha=hashlib.sha256(b).hexdigest();path=sample/(sha+'.nif');path.write_bytes(b);inv=inventory(path);refs=[]
                for block in inv['blocks']:
                    for value in block.get('textures',[]):
                        child=asset_key(value,'texture',k)
                        if child:refs.append((child,'BSShaderTextureSet'))
                    if block['type']=='BSEffectShaderProperty':
                        for field,value in effect_textures(b,block):
                            child=asset_key(value,'texture',k)
                            if child:refs.append((child,'BSEffectShaderProperty:'+field))
                    if block['type'] in ('NiStringExtraData','BSBehaviorGraphExtraData'):
                        ni,vi=struct.unpack_from('<II',b,block['offset']);value=inv['strings'][vi] if vi!=0xffffffff else ''
                        child=asset_key(value,parent=k)
                        if child:refs.append((child,block['type']))
                for child,field in refs:edges.append({'from':k,'to':child,'field':field});queue.append(child)
            except Exception as ex:errors.append({'kind':'patch_nif_graph_parse_failed','path_key':k,'error':repr(ex)})
    asset_errors=[r for r in errors if not (r['kind']=='patch_resource_missing' and r['path_key'].startswith('seq/'))]
    status='FAIL' if asset_errors else 'RESOURCE_ASSETS_CLOSED_SEQUENCE_FILES_REQUIRED' if errors else 'BOUNDED_PATCH_RESOURCE_MANIFEST_READY'
    result={'status':status,'plugins':plugin_rows,'resource_count':len(used),'direct_seed_count':len(direct),
      'counts':dict(collections.Counter(r['decision'] for r in used.values())),'resources':list(used.values()),'edges':edges,'base_source_variants':variants,'errors':errors,
      'scope':'Only typed record model/TXST/VMAD executable PEX/SEQ dependencies and recursive NIF texture/extra-data paths. No whole mixed patch collection is imported.',
      'limitations':['This is a physical source manifest, not a final VFS or Papyrus execution pass.','Inherited selected base versions intentionally win; any different source SHA is reported explicitly.','Final feature VFS must use exact active plugin master/context and runtime assets.']}
    result['sequence_files_to_generate']=[{'plugin':p['name'],'path_key':'seq/'+Path(p['name']).stem.lower()+'.seq',
      'raw_own_sge_formids':[f'{len(p["masters"]):02X}'+v.split('|')[1].upper() for v in p['own_sge_quests']]} for p in plugin_rows if p['own_sge_quests']]
    contract=OWN/'script_audit/rn_patch_property_contract.json'
    if contract.is_file():
        result['base_script_variant_evidence']=json.loads(contract.read_text(encoding='utf-8'))
        result['base_script_variant_evidence']['evidence_sha256']=digest(contract)
    (OWN/'patch_resource_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':result['status'],'direct_seeds':len(direct),'resources':len(used),'counts':result['counts'],'variants':len(variants),'errors':errors},ensure_ascii=False),flush=True)
    return 2 if asset_errors else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
