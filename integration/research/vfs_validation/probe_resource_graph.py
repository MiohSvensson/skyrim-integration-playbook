"""Read the actual VFS NIF/XML/auxiliary-HKX dependency graph; never run the game."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import sqlite3
import struct
import sys
import xml.etree.ElementTree as ET
from datetime import datetime,timezone

sys.dont_write_bytecode=True
from vfs_common import *
from external_nif_refs import effect_textures
from legacy_nif_contracts import LegacyNifContracts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);parser.add_argument('--expect',required=True);parser.add_argument('--output',required=True);parser.add_argument('--seed-probe')
    parser.add_argument('--physical-preflight',action='store_true',help='Inspect only the expected physical view; this cannot produce a VFS pass.')
    args=parser.parse_args();data=Path(args.data);output=safe_output(args.output)
    db=sqlite3.connect(Path(args.expect).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    expect=json.loads(db.execute("select value from metadata where key='expectations'").fetchone()[0])
    physical={r['path_key']:dict(r) for r in db.execute('select * from files')};target=Path(expect['target']);profile=Path(expect['profile'])
    result={'started_utc':datetime.now(timezone.utc).isoformat(),'data_path':str(data),'expectations':str(Path(args.expect).resolve()),
      'usvfs_x64_injected':injected(),'mode':'physical_preflight' if args.physical_preflight else 'actual_mo2_vfs',
      'status':'RUNNING','errors':[],'optional_missing_source_morphs':[],'optional_missing_hkx_extension_slots':[],
      'edges':[],'files':[],'hkx_ignored_absolute_debug_strings':[],
      'documented_legacy_nif_formats':[],
      'documented_feature_source_limitations':expect.get('documented_feature_source_limitations',[])}
    def fail(kind,**detail):result['errors'].append({'kind':kind,**detail})
    if not result['usvfs_x64_injected'] and not args.physical_preflight:
        fail('usvfs_x64_not_injected');result['status']='FAIL';write_json(output,result);return 2
    if data.resolve()!=(target/'Game/Data').resolve():fail('wrong_data_path')
    if controls(target,profile)!=expect['control_hashes']:fail('profile_changed_since_expectations')
    legacy_nif=None
    try:
        legacy_nif=LegacyNifContracts()
        if expect.get('bounded_legacy_nif_format_contract')!=legacy_nif.metadata():
            raise ValueError('Legacy NIF evidence differs from immutable expectations')
    except Exception as ex:fail('bounded_legacy_nif_contract_not_valid',error=repr(ex))
    extension=expect.get('documented_hkx_extension_slots',documented_hkx_slots())
    result['documented_hkx_extension_evidence']=extension
    if extension['sha256'] and digest(extension['evidence_path'])!=extension['sha256']:fail('documented_hkx_extension_evidence_changed')
    extension_files={r['path']:r for r in extension['files']}
    verified={}
    if args.seed_probe:
        prior=json.loads(Path(args.seed_probe).read_text(encoding='utf-8'))
        if prior.get('errors') or not prior.get('usvfs_x64_injected') or prior.get('expectations')!=str(Path(args.expect).resolve()):
            fail('seed_probe_not_valid_for_this_expectation')
        else:verified={r['path_key']:r['sha256'] for r in prior['checks']['resources']['files'] if r['matches_expected']}
    archive_names,_=active_archive_names(profile,expect['enabled_plugins'],physical)
    if archive_names!=expect['archive_names']:fail('archive_candidate_order_changed')
    archives={key(n):dict(physical[key(n)],order=i) for i,n in enumerate(archive_names)}
    catalog=ResourceCatalog(physical,archives);catalog.archive_hashes.update(expect['archive_hashes_required'])
    for ev in expect.get('bounded_feature_exception_provenance',[]):
        if digest(ev['path'])!=ev['sha256']:fail('bounded_feature_exception_evidence_changed',path=ev['path'])
    for case in result['documented_feature_source_limitations']:
        for missing in case['alternatives']:
            if catalog.resolve(missing)['kind']!='missing':fail('bounded_feature_exception_resource_is_now_present_requires_reaudit',case_id=case['case_id'],path=missing)
    sys.path.insert(0,str(BASE/'rootcause'));import nif_resource_inventory as nif_inventory
    from bsarch_readonly import extract_files
    cache_dir=safe_output(output.parent/'graph_cache/marker').parent;cache_dir.mkdir(exist_ok=True)
    blob_cache={};loc_cache={};checked_archives={};file_rows={};optional=set(expect['optional_source_morph_paths'])
    expected_seed={r['path_key']:r for r in expect['resources']}
    def locate(k):
        k=key(k)
        if k not in loc_cache:loc_cache[k]=catalog.resolve(k)
        return loc_cache[k]
    def blob(k):
        if k in blob_cache:return blob_cache[k]
        loc=locate(k)
        if loc['kind']=='missing':raise FileNotFoundError(k)
        if loc['kind']=='loose':
            source=Path(loc['physical_path']) if args.physical_preflight else data/loc['relative_path']
            b=Path(lp(source)).read_bytes();sha=hashlib.sha256(b).hexdigest()
            expected=expected_seed.get(k,{}).get('location',{}).get('sha256') or digest(loc['physical_path'])
            if sha!=expected:raise ValueError(('loose SHA differs',k,expected,sha))
        else:
            name=loc['archive']
            if name not in checked_archives:
                got=digest(loc['archive_physical'] if args.physical_preflight else data/name)
                if got!=loc['archive_sha256']:raise ValueError(('VFS archive filename winner SHA differs',name,loc['archive_sha256'],got))
                checked_archives[name]=got
            source=loc['archive_physical'] if args.physical_preflight else data/name
            b=extract_files(source,{loc['entry']:loc['sha256']})[loc['entry']];sha=hashlib.sha256(b).hexdigest()
        blob_cache[k]=b;return b
    def prove(k):
        if k in file_rows:return file_rows[k]
        loc=locate(k)
        if loc['kind']=='missing':raise FileNotFoundError(k)
        if k in verified:
            sha=verified[k];basis='SHA verified in preceding MO2 child probe'
        else:
            b=blob(k);sha=hashlib.sha256(b).hexdigest();basis='Read actual VFS loose file or actual VFS archive member and checked SHA'
        row={'path_key':k,'kind':loc['kind'],'sha256':sha,'basis':('Physical-view parser preflight only' if args.physical_preflight else basis),'provider':loc.get('provider')}
        if loc['kind']=='bsa':row.update(archive=loc['archive'],member=loc['entry'],archive_sha256=loc['archive_sha256'])
        file_rows[k]=row;return row
    queue=collections.deque((r['path_key'],'required_seed',None) for r in expect['resources']);seen=set();parsed=collections.Counter()
    while queue:
        k,parent,project_base=queue.popleft();k=key(k)
        if k in seen:continue
        seen.add(k)
        try:row=prove(k)
        except FileNotFoundError:
            if k.endswith('.tri') and k in optional:result['optional_missing_source_morphs'].append({'path_key':k,'referenced_by':parent});continue
            fail('required_graph_asset_missing',path=k,referenced_by=parent);continue
        except Exception as e:fail('graph_resource_read_or_sha_failed',path=k,error=repr(e));continue
        suffix=Path(k).suffix.casefold();refs=[]
        if suffix=='.nif':
            try:
                b=blob(k);sha=hashlib.sha256(b).hexdigest();path=cache_dir/(sha+'.nif')
                if not path.exists():path.write_bytes(b)
                inv=legacy_nif.inventory(k,b,locate(k)) if legacy_nif else None
                if inv is None:inv=nif_inventory.inventory(path)
                else:
                    result['documented_legacy_nif_formats'].append({'path_key':k,'sha256':sha,
                      'bs_version':82,'contract_sha256':inv['bounded_format_contract_sha256'],
                      'native_runtime_verified':False,'source_format_retained':True,
                      'classification':'Exact original asset; static complete typed parse only, NOT_REPAIRED'})
                row['nif_version']=[inv['user_version'],inv['bs_version']];row['nif_blocks']=len(inv['blocks']);parsed['nif']+=1
                for block in inv['blocks']:
                    if block['type']=='BSEffectShaderProperty':
                        for field,value in effect_textures(b,block):
                            child=asset_key(value,'texture',k)
                            if child:refs.append((child,'BSEffectShaderProperty:'+field,None))
                    for texture in block.get('textures',[]):
                        child=asset_key(texture,'texture',k)
                        if child:refs.append((child,'BSShaderTextureSet',None))
                    if block['type'] in ('NiStringExtraData','BSBehaviorGraphExtraData'):
                        need=8 if block['type']=='NiStringExtraData' else 9
                        if block['bytes']!=need:raise ValueError(('Unexpected typed extra-data layout',block['type'],block['bytes']))
                        ni,vi=struct.unpack_from('<II',b,block['offset']);name=inv['strings'][ni] if ni!=0xffffffff else '';value=inv['strings'][vi] if vi!=0xffffffff else ''
                        child=asset_key(value,parent=k)
                        if child:refs.append((child,block['type']+':'+name,posixpath.dirname(child) if child.endswith('.hkx') else None))
                    if block['type'] in ('NiSourceTexture','NiSourceCubeMap','NiTexturingProperty'):
                        raise ValueError('Unimplemented legacy external texture block: '+block['type'])
                if k.endswith(('_0.nif','_1.nif')):
                    paired=k[:-5]+('1.nif' if k.endswith('_0.nif') else '0.nif')
                    if locate(paired)['kind']!='missing':refs.append((paired,'existing weight endpoint',None))
            except Exception as e:fail('nif_parse_or_external_layout_failed',path=k,error=repr(e));continue
        elif suffix=='.xml':
            try:
                b=blob(k);root=ET.fromstring(b);parsed['xml']+=1
                strings=[]
                for element in root.iter():strings.extend(element.attrib.values());strings.append(element.text or '')
                for value in strings:
                    child=asset_key(value,parent=k)
                    if child:refs.append((child,'XML explicit file value',None))
            except Exception as e:fail('xml_parse_failed',path=k,error=repr(e));continue
        elif suffix=='.hkx':
            try:
                b=blob(k)
                if b[:8]!=bytes.fromhex('57e0e05710c0c010') or b[16:20]!=bytes.fromhex('08010001'):
                    raise ValueError('Not expected SSE 64-bit little-endian Havok packfile')
                parsed['hkx']+=1;root=project_base or posixpath.dirname(k);row['hkx_layout']=b[16:20].hex()
                for token in re.findall(rb'[\x20-\x7e]{5,}',b):
                    value=token.decode('ascii').strip()
                    if not value.casefold().endswith('.hkx'):continue
                    if ':' in value:result['hkx_ignored_absolute_debug_strings'].append({'path':k,'value':value});continue
                    v=value.replace('\\','/');candidates=[]
                    if key(v).startswith('meshes/'):candidates.append(key(posixpath.normpath(v)))
                    else:
                        candidates += [key(posixpath.normpath(root+'/'+v)),key(posixpath.normpath(posixpath.dirname(k)+'/'+v))]
                    candidates=list(dict.fromkeys(candidates));found=[v for v in candidates if not v.startswith('../') and locate(v)['kind']!='missing']
                    if not found:
                        approved=extension_files.get(k)
                        if approved and row['sha256']==approved['sha256'] and value in approved['optional_tokens'] and re.fullmatch(r'Animations\\SOSCustom0[0-9]\.hkx',value):
                            result['optional_missing_hkx_extension_slots'].append({'referenced_by':k,'framework_sha256':row['sha256'],
                              'declared_token':value,'attempted_paths':candidates,'reason':'Documented empty framework extension slot; no custom animation addon imported.'})
                            continue
                        raise FileNotFoundError(('HKX declared child',value,candidates))
                    if len(found)>1:
                        hashes={prove(v)['sha256'] for v in found}
                        if len(hashes)>1:raise ValueError(('Ambiguous HKX relative reference',value,found))
                    refs.append((found[0],'HKX relative project/character/animation reference',root))
            except Exception as e:fail('hkx_layout_or_declared_dependency_failed',path=k,error=repr(e));continue
        for child,field,ctx in refs:
            result['edges'].append({'from':k,'to':child,'field':field});queue.append((child,k,ctx))
        if len(seen)%500==0:print('Physical preflight graph' if args.physical_preflight else 'VFS graph',len(seen),'files; parsed',dict(parsed),'errors',len(result['errors']),flush=True)
    result['files']=list(file_rows.values());result['archives_opened_through_vfs']=checked_archives;result['parsed_counts']=dict(parsed)
    limited=bool(result['optional_missing_source_morphs'] or result['optional_missing_hkx_extension_slots'] or result['documented_feature_source_limitations'] or result['documented_legacy_nif_formats'])
    result['counts']={'visited_paths':len(seen),'verified_existing_paths':len(file_rows),'edges':len(result['edges']),
      'missing_optional_source_morphs':len(result['optional_missing_source_morphs']),'missing_optional_hkx_extension_slot_references':len(result['optional_missing_hkx_extension_slots']),
      'documented_feature_source_limitations':len(result['documented_feature_source_limitations']),
      'bounded_legacy_nif_format_files':len(result['documented_legacy_nif_formats'])}
    result['status']='FAIL' if result['errors'] else 'PASS_GRAPH_WITH_DOCUMENTED_SOURCE_LIMITATIONS' if limited else 'PASS_STATIC_RESOURCE_GRAPH'
    if args.physical_preflight:result['status']='PHYSICAL_PREFLIGHT_FAILED' if result['errors'] else 'PHYSICAL_PREFLIGHT_WITH_DOCUMENTED_SOURCE_LIMITATIONS' if limited else 'PHYSICAL_PREFLIGHT_COMPLETE'
    result['finished_utc']=datetime.now(timezone.utc).isoformat();result['limitations']=[expect['archive_order_limit'],
      'No game or animation behavior was executed. HKX validation covers format and declared filename closure, not playback.',
      'TRI presence and hashes do not by themselves prove morph vertex topology compatibility.',
      'Known missing source BODYTRI entries remain explicit limitations unless separately regenerated and verified.',
      'Exact authored feature resource gaps remain visible and unrepaired; UF6/Ben exceptions require the complete SHA-bound xEdit typed-reference context. Dynamic external lookups and gameplay are unproved.',
      'Only two exact MoonAndStar source stream82 images have bounded full-block/author-library CPU parse evidence; original format retained, native rendering and SSE conversion unproved. All four texture dependencies remain mandatory.',
      'Only exact SHA-bound SoS framework Custom00-09 clip declarations may be empty extension slots; optional custom clips are unavailable.']
    write_json(output,result);print(json.dumps({'status':result['status'],'counts':result['counts'],'parsed':dict(parsed),'errors':len(result['errors']),'output':str(output)},ensure_ascii=False),flush=True)
    return 2 if result['errors'] else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
