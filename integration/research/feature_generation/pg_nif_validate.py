"""Freeze effective PG inputs before generation, compare all actual outputs after."""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(DB/'integration'));import runtime_inventory as ri
sys.path.insert(0,str(OUT.parent/'vfs_validation'));from vfs_common import ResourceCatalog,active_archive_names,key,lp
sys.path.insert(0,str(DB/'rootcause'));from bsarch_readonly import extract_files
from pg_nif_reader import snapshot,compare,raw_table

def sha(p):
    with open(lp(p),'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def owned(p):
    p=Path(p).resolve();assert p.is_relative_to(OUT/'pg_runs');return p
def complete_typed_node_coverage(s):
    # PyNifly nodes is name-keyed. Duplicate names must not silently hide an
    # AVObject. Every known node/shape class must match the independent raw
    # table count, not merely the number returned by that dictionary.
    known={'NiNode','BSFadeNode','BSLeafAnimNode','BSMultiBoundNode','NiBillboardNode','NiTriShape','BSTriShape','BSSubIndexTriShape','BSMeshLODTriShape','BSDynamicTriShape','NiTriStrips'}
    actual=collections.Counter(v['block_type'] for v in s['nodes'].values())
    raw=s['raw']['block_types']
    for t in known|set(actual):
        assert actual.get(t,0)==raw.get(t,0),f'Incomplete author typed node coverage {t}: raw={raw.get(t,0)} typed={actual.get(t,0)}; duplicate names/unsupported mapping require separate review'
    assert len(s['nodes'])==s['native_NiNode_count']+s['native_NiShape_count'],'Incomplete native handle inventory'
def physical_view(mods,wanted):
    rows={}
    for provider,folder in mods+[('Game/Data',DB/'UnifiedSkyrim/Game/Data')]:
        if not folder.is_dir():continue
        for f in folder.iterdir():
            if f.is_file():rows.setdefault(key(f.name),{'relative_path':f.name,'physical_path':str(f),'provider':provider,'size_bytes':f.stat().st_size})
        mesh=folder/'meshes'
        if not os.path.isdir(lp(mesh)):continue
        for parent,dirs,files in os.walk(lp(mesh),followlinks=False):
            dirs[:]=[x for x in dirs if not x.lower().endswith('.mohidden')]
            for name in files:
                rel='meshes/'+Path(parent).relative_to(Path(lp(mesh))).as_posix().strip('.')+'/'+name;rel=rel.replace('//','/');k=key(rel)
                if k in wanted:rows.setdefault(k,{'relative_path':rel,'physical_path':str(Path(parent)/name),'provider':provider,'size_bytes':os.path.getsize(Path(parent)/name)})
    return rows

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','verify']);p.add_argument('--run',required=True)
    p.add_argument('--research-allow-source-trailers',action='store_true');p.add_argument('--research-inspect-nonfinite',action='store_true');p.add_argument('--resume-research',action='store_true');a=p.parse_args();run=owned(a.run);m=json.loads((run/'manifest.json').read_text(encoding='utf8'))
    if a.research_allow_source_trailers or a.research_inspect_nonfinite or a.resume_research:assert run.name.startswith('nif_cpu_preflight_') and a.mode=='freeze','Research-only options cannot enable a formal PG run'
    for name,digest in m['profile_sha256'].items():assert sha(Path(m['profile_path'])/name)==digest,'Profile drift; prepare fresh run'
    frozen=run/'nif_inputs';manifest=frozen/'manifest.json';wanted={key(s) for s in m['expected_mesh_allowlist']} - {key(m['blocked_single_mesh'])}
    if a.mode=='freeze':
        assert (not frozen.exists() or (a.resume_research and (frozen/'FAILED.json').exists() and not manifest.exists())) and not any(Path(m['output']).iterdir()),'Fresh private source snapshot must precede tool execution'
        assert shutil.disk_usage(run).free>34*1024**3,'Preserve32GiBreserve+2GiBsnapshotbudget'
        excluded={key(r['path_key']):r for r in m.get('source_exclusions',[])};assert not wanted&excluded.keys()
        ri.PROFILE=Path(m['profile_path']);mods=ri.active_mods();physical=physical_view(mods,wanted|excluded.keys())
        anames,_=active_archive_names(ri.PROFILE,[x['name'] for x in m['plugins']],physical);cat=ResourceCatalog(physical,{key(n):dict(physical[key(n)],order=i) for i,n in enumerate(anames)})
        frozen.mkdir(exist_ok=a.resume_research);(frozen/'bytes').mkdir(exist_ok=a.resume_research)
        typed_dir=frozen/(('typed_source_research_' if a.research_allow_source_trailers else 'typed_')+sha(OUT/'pg_nif_reader.py')[:12]);typed_dir.mkdir(exist_ok=a.resume_research);entries={};source_trailers=[];numeric_defects=[];audit_gaps=[];excluded_providers=[];lighting_cache={};excluded_archive_checks={}
        if not a.research_inspect_nonfinite:
            from pg_nif_lighting_validate import schema_snapshot,serializer_proof
            serializer_evidence=serializer_proof()
        else:serializer_evidence=None
        def freeze_one(k,info):
            loc=cat.resolve(k);info['provider']=loc;assert loc['kind']!='missing','Missing actual input '+k
            if loc['kind']=='loose':data=Path(loc['physical_path']).read_bytes();digest=hashlib.sha256(data).hexdigest();loc['sha256']=digest
            else:data=extract_files(loc['archive_physical'],{k:loc['sha256']})[k];digest=loc['sha256']
            dest=frozen/'bytes'/(digest+'.nif')
            if not dest.exists():dest.write_bytes(data)
            assert dest.stat().st_nlink==1 and sha(dest)==digest
            info.update(sha256=digest,bytes=len(data),snapshot=str(dest))
            table=raw_table(data,a.research_allow_source_trailers);typed_path=typed_dir/(digest+'.json')
            if not typed_path.exists():
                typed=snapshot(dest,a.research_allow_source_trailers,a.research_inspect_nonfinite);complete_typed_node_coverage(typed)
                typed_path.write_text(json.dumps(typed,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            else:typed=json.loads(typed_path.read_text(encoding='utf8'));complete_typed_node_coverage(typed)
            for warning in typed['source_warnings']:
                if 'numeric_defects' in warning:numeric_defects.append({'path_key':k,'source_sha256':digest,**warning})
            if table['trailer_bytes']:
                core=frozen/'bytes'/(table['declared_core_sha256']+'.core.nif')
                if not core.exists():core.write_bytes(data[:table['declared_core_bytes']])
                assert sha(core)==table['declared_core_sha256'] and core.stat().st_nlink==1
                clean=snapshot(core,False,a.research_inspect_nonfinite);complete_typed_node_coverage(clean);proof=compare(typed,clean)
                assert not proof['failures'] and not proof['material_changes'],'Author reader consumed trailer semantics; cannot bound source suffix'
                source_trailers.append({'path_key':k,'source_sha256':digest,'core_bytes':table['declared_core_bytes'],'core_sha256':table['declared_core_sha256'],
                  'trailer_bytes':table['trailer_bytes'],'trailer_sha256':table['trailer_sha256'],'full_vs_core_author_typed_equal':True,'private_core':str(core),'adopted_for_formal_run':False})
            if not a.research_inspect_nonfinite:
                if digest not in lighting_cache:
                    lighting=schema_snapshot(dest);assert lighting['sha256']==digest
                    assert {';'.join(s['paths']) for s in lighting['shapes']}=={s['key'] for s in typed['shapes']}
                    lighting_cache[digest]={'sha256':hashlib.sha256(json.dumps(lighting,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),'shapes':lighting['shape_count'],'stream':lighting['stream']}
                info['strict_lighting_source']=lighting_cache[digest]
            return {**info,'typed_snapshot':str(typed_path),'typed_snapshot_sha256':sha(typed_path)}
        try:
            for k,row in sorted(excluded.items()):
                loc=cat.resolve(k);assert loc['kind']!='missing','Excluded source disappeared; refresh exclusion proof '+k
                digest=sha(loc['physical_path']) if loc['kind']=='loose' else loc['sha256'];assert digest==row['source_sha256'],'Excluded source provider changed; do not silently skip repaired/different author mesh '+k
                if loc['kind']!='loose':
                    ar=loc['archive_physical']
                    if ar not in excluded_archive_checks:excluded_archive_checks[ar]=sha(ar)
                    assert excluded_archive_checks[ar]==loc['archive_sha256']
                excluded_providers.append({'path_key':k,'source_sha256':digest,'actual_provider':loc,'PG_processing_excluded':True,'runtime_source_kept':True,'source_repaired':False})
            for i,k in enumerate(sorted(wanted)):
                info={}
                try:entries[k]=freeze_one(k,info)
                except Exception as error:
                    if not a.research_inspect_nonfinite:raise
                    gap={'path_key':k,**info,'error':repr(error),'status':'RESEARCH_SOURCE_AUDIT_GAP_NOT_FORMALLY_ACCEPTED'}
                    audit_gaps.append(gap);entries[k]=gap;print(json.dumps({'source_audit_gap':k,'error':repr(error)},ensure_ascii=True),flush=True)
                if i%100==0:print(json.dumps({'frozen':i+1,'total':len(wanted)}),flush=True)
                assert shutil.disk_usage(run).free>32*1024**3+128*1024**2,'Snapshot stopped before reserve'
            final_controls={name:sha(Path(m['profile_path'])/name) for name in m['profile_sha256']};drift=final_controls!=m['profile_sha256']
            if not a.research_inspect_nonfinite:assert not drift,'Profile drift during formal source freeze'
            report={'status':'RESEARCH_FROZEN_INPUTS_WITH_SOURCE_FORMAT_DEFECTS_NOT_FORMAL' if source_trailers or numeric_defects or audit_gaps or drift else 'FROZEN_ACTUAL_EFFECTIVE_NIF_INPUT_BYTES','run_manifest_sha256':sha(run/'manifest.json'),'entries':entries,'source_trailer_cases':source_trailers,'source_numeric_defects':numeric_defects,'source_audit_gaps':audit_gaps,'profile_drift_during_research':drift,'final_profile_controls':final_controls,
              'reader_dll_sha256':sha(OUT/'primary_sources/PyNifly/addon/io_scene_nifly/NiflyDLL.dll'),'reader_script_sha256':sha(OUT/'pg_nif_reader.py'),
              'strict_lighting_validator_sha256':sha(OUT/'pg_nif_lighting_validate.py') if not a.research_inspect_nonfinite else None,'strict_schema_sha256':sha(OUT/'lighting_schema/lighting_schema.py') if not a.research_inspect_nonfinite else None,'serializer_derivation_evidence':serializer_evidence,
              'source_exclusion_providers':excluded_providers,'source_files_written':False,'cache_policy':'All private input bytes, typed snapshots and reports remain under this Database run.'}
            manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            if not a.research_inspect_nonfinite:
                from pbr_lighting_contract import source_matrix
                source_matrix(run,manifest)
        except Exception as e:
            failed=frozen/'FAILED.json'
            if failed.exists():failed=frozen/('FAILED_'+str(len(list(frozen.glob('FAILED*')))+1)+'.json')
            failed.write_text(json.dumps({'error':repr(e),'current_path':k,'completed':len(entries),'partial_not_accepted':True,'source_trailers_so_far':source_trailers,'numeric_defects_so_far':numeric_defects})+'\n');raise
    else:
        f=json.loads(manifest.read_text(encoding='utf8'));assert f['run_manifest_sha256']==sha(run/'manifest.json')
        assert f['status']=='FROZEN_ACTUAL_EFFECTIVE_NIF_INPUT_BYTES','Research source-format defect catalog is not a formal accepted input freeze'
        assert f['reader_dll_sha256']==sha(OUT/'primary_sources/PyNifly/addon/io_scene_nifly/NiflyDLL.dll') and f['reader_script_sha256']==sha(OUT/'pg_nif_reader.py')
        result=json.loads((run/'result.json').read_text(encoding='utf8'));assert result['status']=='PRIVATE_PG_OUTPUT_CREATED_NOT_DEPLOYED_PENDING_TYPED_RECORD_AND_NIF_REVIEW'
        from pg_nif_lighting_validate import schema_snapshot,serializer_proof,validate
        from pbr_lighting_contract import trace_witness
        assert f['strict_lighting_validator_sha256']==sha(OUT/'pg_nif_lighting_validate.py') and f['strict_schema_sha256']==sha(OUT/'lighting_schema/lighting_schema.py')
        assert f['serializer_derivation_evidence']==serializer_proof()
        contract_path=run/'lighting_contract/contract.json';contract=json.loads(contract_path.read_text(encoding='utf8'));assert contract['source_proof_sha256']==sha(manifest)
        witness_path=run/'lighting_contract/native_trace_witness.json'
        if not witness_path.exists():trace_witness(run,contract_path)
        witness=json.loads(witness_path.read_text(encoding='utf8'));assert witness['contract_sha256']==sha(contract_path) and all(sha(r['path'])==r['sha256'] for r in witness['logs'])
        inventory=json.loads((run/'output_inventory.json').read_text(encoding='utf8'));review=run/'nif_review';assert not review.exists();review.mkdir();cache={};reports=[];archive_checks={}
        for row in inventory:
            if not row['relative'].lower().endswith('.nif'):continue
            path=owned(row['path']);assert sha(path)==row['sha256'] and path.stat().st_nlink==1
            k=key(row['relative']);source_key=re.sub(r'^meshes/_pgpatcher_dups/[1-9][0-9]*/','meshes/',k);src=f['entries'][source_key];before=Path(src['snapshot']);assert sha(before)==src['sha256']
            loc=src['provider']
            if loc['kind']=='loose':assert sha(loc['physical_path'])==src['sha256'],'Runtime source changed during PG'
            else:
                ar=loc['archive_physical']
                if ar not in archive_checks:archive_checks[ar]=sha(ar)
                assert archive_checks[ar]==loc['archive_sha256'],'Runtime source BSA changed'
            if src['sha256'] not in cache:cache[src['sha256']]=snapshot(before)
            original=cache[src['sha256']];candidate=snapshot(path)
            complete_typed_node_coverage(original);complete_typed_node_coverage(candidate)
            lighting_before=schema_snapshot(before);lighting_after=schema_snapshot(path)
            lighting_proof=validate(original,candidate,lighting_before,lighting_after,witness,source_key,k==source_key,contract['rules'],allow_serializer_rebuild=True)
            comparison=lighting_proof['accepted_native_passes'][0]['comparison']
            item={'output':row,'source_key':source_key,'source':src,'comparison':comparison,'lighting':lighting_proof,'source_warnings':original['source_warnings'],'output_reader_log':candidate['reader_log']}
            reports.append(item);detail=review/(row['sha256']+'.json');detail.write_text(json.dumps({'before':original,'after':candidate,'comparison':comparison,'lighting':lighting_proof},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            print(json.dumps({'checked':len(reports),'path':k,'status':comparison['status']}),flush=True)
        assert reports,'No actual output NIFs'
        failures=[r for r in reports if r['comparison']['failures']]
        summary={'status':'ALL_OUTPUT_NIF_GEOMETRY_PRESERVED_PENDING_RENDERER_CLOSURE' if not failures else 'STOP_UNPROVEN_NIF_CHANGES','files':len(reports),'failed':len(failures),'reports':reports,'actual_generation_result_sha256':sha(run/'result.json'),'input_manifest_sha256':sha(manifest),
          'next_required':'Typed ESP verifier plus every emitted texture path/TXST canonical reference closure. No automatic deployment.','native_rendering_verified':False}
        (review/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return 1 if failures else 0
    return 0
if __name__=='__main__':sys.exit(main())
