"""MO2 child-only, read-only data-view verification. Never launches Skyrim."""
import argparse
import collections
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
from datetime import datetime,timezone

sys.dont_write_bytecode=True
from vfs_common import *


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--data',required=True);parser.add_argument('--expect',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--all-paths',action='store_true',help='Enumerate every runtime candidate and compare Win32 file identities; needed for a full pass.')
    args=parser.parse_args();data=Path(args.data);output=safe_output(args.output)
    c=sqlite3.connect(Path(args.expect).resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    expect=json.loads(c.execute("select value from metadata where key='expectations'").fetchone()[0]);target=Path(expect['target']);profile=Path(expect['profile'])
    result={'started_utc':datetime.now(timezone.utc).isoformat(),'usvfs_x64_injected':injected(),'data_path':str(data),'expectations':str(Path(args.expect).resolve()),
      'expected_counts':expect['counts'],'status':'RUNNING','errors':[],'checks':{}}
    def fail(kind,**detail):result['errors'].append({'kind':kind,**detail})
    if data.resolve()!= (target/'Game/Data').resolve():fail('wrong_data_path',expected=str(target/'Game/Data'),actual=str(data))
    if not result['usvfs_x64_injected']:
        fail('usvfs_x64_not_injected');result['status']='FAIL';write_json(output,result);print('FAIL: no usvfs_x64 injection',flush=True);return 2
    if expect['errors']:fail('physical_expectations_have_errors',details=expect['errors'])
    current=controls(target,profile)
    if current!=expect['control_hashes']:fail('profile_changed_since_expectations')
    actual_plugins=[];enabled_keys={key(n) for n in expect['enabled_plugins']}
    for row in expect['plugins']:
        try:
            got=plugin_header(data/row['name'])
            if 'owned_id_range' in row:
                ranges=owned_id_range(data/row['name'],len(got['masters']),got['is_light']);got['owned_id_range']=ranges
                if not ranges['light_owned_id_range_valid']:fail('invalid_light_owned_id_range',plugin=row['name'],range=ranges)
            actual_plugins.append({'name':row['name'],**got})
            if got['sha256']!=row['sha256']:fail('plugin_sha_mismatch',plugin=row['name'],expected=row['sha256'],actual=got['sha256'])
            if got['masters']!=row['masters']:fail('plugin_master_header_changed',plugin=row['name'])
            for master in got['masters']:
                if key(master) not in enabled_keys:fail('master_not_enabled',plugin=row['name'],master=master)
        except Exception as e:fail('plugin_read_failed',plugin=row['name'],error=repr(e))
    result['checks']['plugins']={'checked':len(actual_plugins),'files':actual_plugins}
    actual_dlls=[]
    try:
        dll_names={key(e.name) for e in os.scandir(lp(data/'SKSE/Plugins')) if e.is_file() and e.name.casefold().endswith('.dll')}
        if dll_names!={Path(r['path_key']).name for r in expect['dlls']}:fail('runtime_dll_set_mismatch',actual=sorted(dll_names),expected=sorted(Path(r['path_key']).name for r in expect['dlls']))
    except Exception as e:fail('runtime_dll_enumeration_failed',error=repr(e))
    for row in expect['dlls']:
        try:
            got=dll_info(data/row['relative_path']);actual_dlls.append({'path_key':row['path_key'],**got})
            if got['sha256']!=row['sha256']:fail('runtime_dll_sha_mismatch',path=row['path_key'])
            if got['machine']!=0x8664:fail('runtime_dll_not_x64',path=row['path_key'],machine=got['machine'])
        except Exception as e:fail('runtime_dll_read_failed',path=row['path_key'],error=repr(e))
    result['checks']['runtime_dlls']={'checked':len(actual_dlls),'files':actual_dlls}
    stock=[]
    for row in expect['stock23']:
        try:
            got=digest(data/row['relative_path']);stock.append({'relative_path':row['relative_path'],'sha256':got,'matches_expected':got==row['expected_sha256']})
            if got!=row['expected_sha256']:fail('coherent_stock_sha_mismatch',path=row['relative_path'])
        except Exception as e:fail('coherent_stock_read_failed',path=row['relative_path'],error=repr(e))
        print('VFS stock SHA',len(stock),'/',len(expect['stock23']),row['relative_path'],flush=True)
    result['checks']['coherent_stock23']={'checked':len(stock),'files':stock}
    # Every required BSA is opened through its actual VFS root filename, never its old source path.
    sys.path.insert(0,str(BASE/'rootcause'));from bsarch_readonly import extract_files
    grouped=collections.defaultdict(dict)
    for row in expect['resources']:
        loc=row['location']
        if loc['kind']=='bsa':grouped[loc['archive']][loc['entry']]=loc['sha256']
    extracted={};archive_checks=[]
    for archive,members in grouped.items():
        try:
            sha=digest(data/archive);canonical=expect['archive_hashes_required'].get(key(archive))
            if canonical and sha!=canonical:fail('required_archive_sha_mismatch',archive=archive,expected=canonical,actual=sha)
            blobs=extract_files(data/archive,members);extracted.update(blobs);archive_checks.append({'archive':archive,'sha256':sha,'verified_member_count':len(blobs)})
        except Exception as e:fail('bsa_member_read_failed',archive=archive,error=repr(e))
    resource_rows=[]
    for i,row in enumerate(expect['resources']):
        loc=row['location'];k=row['path_key']
        try:
            if loc['kind']=='loose':got=digest(data/loc['relative_path'])
            elif loc['kind']=='bsa':got=hashlib.sha256(extracted[k]).hexdigest()
            else:raise FileNotFoundError(k)
            ok=got==loc['sha256'];resource_rows.append({'path_key':k,'sha256':got,'matches_expected':ok,'tags':row['tags'],'kind':loc['kind']})
            if not ok:fail('resource_sha_mismatch',path=k,expected=loc['sha256'],actual=got)
        except Exception as e:fail('required_resource_read_failed',path=k,error=repr(e))
        if i%1000==0:print('VFS required resources',i+1,'/',len(expect['resources']),flush=True)
    result['checks']['resources']={'checked':len(resource_rows),'files':resource_rows,'bsa_archives':archive_checks}
    if args.all_paths:
        expected={r['path_key']:dict(r) for r in c.execute('select * from files')};seen=set();identity_count=0;size_count=0
        for relative,path,st in walk(data):
            k=key(relative);seen.add(k);row=expected.get(k)
            if row is None:fail('unexpected_runtime_path',path=relative);continue
            if st.st_size!=row['size_bytes']:fail('runtime_path_size_mismatch',path=relative,expected=row['size_bytes'],actual=st.st_size)
            else:size_count+=1
            try:
                actual_id=file_identity(path);physical_id=file_identity(row['physical_path'])
                if actual_id!=physical_id:fail('runtime_winning_file_identity_mismatch',path=relative,expected_provider=row['provider'],expected_file=row['physical_path'],expected_identity=physical_id,actual_identity=actual_id)
                else:identity_count+=1
            except Exception as e:fail('runtime_file_identity_failed',path=relative,error=repr(e))
            if len(seen)%25000==0:print('VFS runtime paths',len(seen),'/',len(expected),'identity matches',identity_count,flush=True)
        missing=sorted(set(expected)-seen)
        for k in missing:fail('missing_runtime_path',path=k,provider=expected[k]['provider'])
        result['checks']['all_runtime_paths']={'expected':len(expected),'enumerated':len(seen),'size_matches':size_count,'winner_identity_matches':identity_count,'missing':len(missing),'excluded_roots':sorted(EXCLUDED_ROOTS)}
    else:result['checks']['all_runtime_paths']={'status':'NOT_RUN'}
    result['checks']['resource_graph_closure']={'status':'NOT_YET_IMPLEMENTED_IN_PHASE1','scope':'Required seed existence/SHA checked; recursive NIF/XML/HKX expansion is a separate pending check.'}
    result['finished_utc']=datetime.now(timezone.utc).isoformat();result['status']='FAIL' if result['errors'] else 'PARTIAL_REQUIRED_SEEDS_PASS_GRAPH_CLOSURE_PENDING'
    result['limitations']=[expect['archive_order_limit'],'No Skyrim process was started. A VFS proof does not prove gameplay or stability.']
    write_json(output,result);print(json.dumps({'status':result['status'],'errors':len(result['errors']),'output':str(output),'counts':{k:v.get('checked') for k,v in result['checks'].items() if isinstance(v,dict)}},ensure_ascii=False),flush=True)
    return 2 if result['errors'] else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
