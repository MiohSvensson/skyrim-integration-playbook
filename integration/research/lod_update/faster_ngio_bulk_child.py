"""Actual MO2 CPU CLI only. New outputs, exact coverage, resource gaps stop generation."""
import argparse
import csv
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime,timezone
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,TARGET,owned,sha
sys.path.insert(0,str(OLD))
from verify_cgid import parse,NAME
sys.path.insert(0,str(OUT.parent/'vfs_validation'))
from vfs_common import file_identity

def source_limit(gap,world,entries):
    matches=[entry for entry in entries if entry['runtime_id']==gap['grass'] and entry['model']==gap['model']]
    if len(matches)!=1:return None
    entry=matches[0]
    for occ in entry['allowed_occurrences']:
        if occ['world']==world and occ['texture_runtime_id']==gap['texture'] and all(gap[k]==occ[k] for k in ('density','min_slope','max_slope','water_state','water_distance')):
            return entry
    return None

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--run-name',required=True)
    parser.add_argument('--inspect-only',action='store_true');parser.add_argument('--only-world',action='append');args=parser.parse_args()
    source=Path(args.manifest).resolve(strict=True);assert source==OUT/'bulk_manifest.json'
    manifest=json.loads(source.read_text(encoding='utf-8'));assert re.fullmatch('[A-Za-z0-9_-]+',args.run_name)
    run=owned(OUT/'bulk_runs'/args.run_name);assert not run.exists();run.mkdir(parents=True)
    (run/'manifest_used.json').write_bytes(source.read_bytes())
    result={'utc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','manifest_sha256':sha(source),'phases':[],'worlds':[],'resource_gaps':[],'known_source_limits_not_repaired':[],'unexpected_resource_gaps':[]}
    try:
        kernel=ctypes.WinDLL('kernel32');kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
        assert kernel.GetModuleHandleW('usvfs_x64.dll'),'Actual MO2 VFS required';result['usvfs']=True
        profile=Path(manifest['profile_path']);assert profile==TARGET/'profiles'/manifest['profile']
        for relative,digest in manifest['profile_sha256'].items():assert sha(profile/relative)==digest,'Profile drift: prepare again'
        assert sha(TARGET/'Game/Skyrim.ccc')==manifest['Skyrim_ccc_sha256']
        vfs=[]
        for row in manifest['plugins']:
            path=TARGET/'Game/Data'/row['name']
            try:
                actual=file_identity(path);physical=file_identity(row['path']);assert actual==physical
                assert sha(path)==row['sha256']
            except Exception as error:raise RuntimeError(f"VFS CreateFileW/FileID/SHA failed plugin={row['name']} virtual={path} physical={row['path']} error={error!r}") from error
            vfs.append({'plugin':row['name'],'FileID':actual,'sha256':row['sha256']})
        (run/'vfs_preflight.json').write_text(json.dumps(vfs,indent=2)+'\n')
        for relative,row in manifest['auxiliary'].items():assert sha(TARGET/'Game/Data'/relative)==row['sha256']
        if manifest.get('known_missing_grass_sha256'):
            assert sha(OUT/'known_missing_grass.json')==manifest['known_missing_grass_sha256'],'Missing-source evidence drift'
        exe=Path(manifest['generator']['path']);assert exe.resolve()==OUT/'tools/FasterNGIO_1.6/FasterNGIO.exe' and sha(exe)==manifest['generator']['sha256']
        reserve=manifest['reserve_GiB']*1024**3;assert shutil.disk_usage(OUT).free>reserve+manifest['output_budget_GiB']*1024**3,'Insufficient output budget above reserve'
        environment=os.environ.copy();temp=owned(run/'tmp');temp.mkdir()
        for variable in ('TEMP','TMP','TMPDIR'):environment[variable]=str(temp)
        common=['--data',str(TARGET/'Game/Data'),'--plugins',str(profile/'plugins.txt'),'--game-ini-dir',str(profile),
            '--ngio-config',str(TARGET/'Game/Data/SKSE/Plugins/GrassControl.ini'),'--placement','vanilla','--reject','cpu','--write-empty-cells',
            '--threads',str(manifest['threads']),'--writers',str(manifest['writers'])]
        batches=manifest['batches']
        if args.only_world:
            requested=set(args.only_world);assert requested<={b['editor_id'] for b in batches};batches=[b for b in batches if b['editor_id'] in requested]
        assert batches and all(b['editor_id']!='WhiterunWorld' and not b['no_grass'] for b in batches)
        def execute(command,label):
            assert Path(command[0])==exe and '--gui' not in command and '--overwrite' not in command
            assert command[command.index('--reject')+1]=='cpu' and command[command.index('--world')+1]!='all'
            for i,arg in enumerate(command):
                if arg in ('--out','--inspect-grass'):owned(command[i+1])
            assert shutil.disk_usage(OUT).free>reserve+128*1024**2
            (run/(label+'_command.json')).write_text(json.dumps(command,indent=2)+'\n');start=time.monotonic()
            with (run/(label+'.log')).open('wb') as output:
                process=subprocess.Popen(command,cwd=exe.parent,env=environment,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                (run/(label+'_pid.json')).write_text(json.dumps({'pid':process.pid})+'\n')
                while process.poll() is None:
                    if shutil.disk_usage(OUT).free<reserve+64*1024**2:
                        process.terminate();process.wait();raise RuntimeError('Stopped generator before reserve exhaustion; partial outputs not activated')
                    time.sleep(2)
                code=process.returncode
            text=(run/(label+'.log')).read_text(encoding='utf-8-sig',errors='replace')
            phase={'name':label,'returncode':code,'seconds':round(time.monotonic()-start,2),'log_sha256':sha(run/(label+'.log')),
                'warnings':[line for line in text.splitlines() if '[warning]' in line or '[warn]' in line]}
            result['phases'].append(phase)
            assert code==0 and not re.search(r'\[error\]|\[critical\]',text,re.I),label+' generator error; inspect log'
            assert re.search(r'load order: '+str(len(manifest['plugins']))+r' plugin\(s\)',text),'Unexpected generator load order'
            return phase,text
        for batch in batches:
            name=batch['editor_id'];assert re.fullmatch('[A-Za-z0-9_]+',name)
            folder=owned(run/name);folder.mkdir();grass=owned(folder/'Grass');grass.mkdir();csv_path=owned(folder/'placement.csv')
            local=['--world','0x'+batch['world_runtime_id'],'--out',str(grass)]
            xy_rows=[v['XY'] for v in batch['expected_cells']]
            cx=(min(x[0] for x in xy_rows)+max(x[0] for x in xy_rows))//2
            cy=(min(x[1] for x in xy_rows)+max(x[1] for x in xy_rows))//2
            radius=max(max(abs(x[0]-cx),abs(x[1]-cy)) for x in xy_rows)
            assert all(abs(x[0]-cx)<=radius and abs(x[1]-cy)<=radius for x in xy_rows)
            # 1.6 inspector requires a --cell or --radius window; generation below
            # remains complete-world. The square includes every pinned LAND XY.
            phase,text=execute([str(exe),*common,*local,'--radius',str(cx),str(cy),str(radius),'--inspect-grass',str(csv_path)],name+'_inspect')
            values=list(csv.DictReader(csv_path.open(encoding='utf-8-sig',newline='')));values=[v for v in values if v['status']=='land']
            expected={tuple(v['XY']):v for v in batch['expected_cells']};actual={(int(v['x']),int(v['y'])):v for v in values}
            assert len(actual)==len(values) and actual.keys()==expected.keys(),f'{name} independent effective LAND XY coverage mismatch'
            for xy,v in actual.items():
                assert v['cell'].upper()==expected[xy]['cell_runtime_id'] and v['land'].upper()==expected[xy]['land_runtime_id'],f'{name} CELL/LAND identity mismatch at {xy}'
            textures=list(csv.DictReader(Path(str(csv_path)+'.textures.csv').open(encoding='utf-8-sig',newline='')))
            gaps=[v for v in textures if v['grass'] and v['loadable']!='1'];result['resource_gaps'].extend({'world':name,**g} for g in gaps)
            unexpected=[]
            for gap in gaps:
                entry=source_limit(gap,name,manifest.get('allowed_unloadable_grass',[]))
                if entry is not None:
                    result['known_source_limits_not_repaired'].append({'world':name,**gap,'canonical_GRAS':entry['canonical'],'GRAS_payload_sha256':entry['final_GRAS_payload_sha256'],'model_sha256':None,'status':'PREEXISTING_AUTHOR_MODEL_ABSENT_NOT_REPAIRED'})
                else:unexpected.append(gap);result['unexpected_resource_gaps'].append({'world':name,**gap})
            summary={'world':name,'expected_cells':len(expected),'inspect_cells':len(actual),'inspect_candidate_blades':sum(int(v['blades']) for v in values),
                'inspect_window':{'center':[cx,cy],'radius':radius,'all_expected_cells_inside':True},
                'resource_gaps':gaps,'status':'INSPECT_ONLY' if args.inspect_only else 'INSPECTED'};result['worlds'].append(summary)
            if args.inspect_only:continue
            assert not unexpected,f'{name}: NEW/CHANGED relevant missing grass model(s); generator not started for this world'
            phase,text=execute([str(exe),*common,*local],name+'_generate')
            cache_rows=[]
            for path in sorted(grass.glob('*.cgid')):
                m=NAME.match(path.name);assert m and m.group(1).lower()==name.lower() and not m.group(4),'Unexpected world/season output; review settings'
                xy=(int(m.group(2)),int(m.group(3)));assert xy in expected
                parsed=parse(path);assert parsed['blades']<=int(actual[xy]['blades']),'Rejection unexpectedly added blades'
                cache_rows.append({'path':str(path),'XY':list(xy),**parsed})
            assert len(cache_rows)==len(expected) and {tuple(r['XY']) for r in cache_rows}==expected.keys(),'Generation omitted cells; stale cache would show through'
            blades=sum(r['blades'] for r in cache_rows);assert blades>=batch['minimum_written_blades'],'World unexpectedly has no generated grass'
            (folder/'cache_verification.json').write_text(json.dumps(cache_rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            summary.update(status='CPU_CACHE_STRUCTURAL_AND_COVERAGE_PASS_NOT_ACTIVATED',cache_files=len(cache_rows),written_blades=blades,empty_files=sum(r['blades']==0 for r in cache_rows),
                collision_missing_counts=[int(x) for x in re.findall(r'collision:.*?, (\d+) missing',text)])
        for relative,digest in manifest['profile_sha256'].items():assert sha(profile/relative)==digest,'Profile changed during generation'
        for row in manifest['plugins']:assert sha(TARGET/'Game/Data'/row['name'])==row['sha256'],'Input plugin changed during generation'
        assert not list(run.rglob('*.fail'))
        if args.inspect_only:result['status']='BULK_INSPECT_RESOURCE_GAPS_REVIEW' if result['resource_gaps'] else 'BULK_INSPECT_COVERAGE_AND_MODELS_PASS_NOT_GENERATED'
        else:result['status']='BULK_CPU_CACHES_CREATED_KNOWN_SOURCE_LIMITS_NOT_REPAIRED_REVIEW_BEFORE_ACTIVATION' if result['known_source_limits_not_repaired'] else 'BULK_CPU_CACHES_CREATED_REVIEW_WARNINGS_AND_COLLISION_BEFORE_ACTIVATION'
    except Exception as error:
        result['status']='PRECHECK_FAIL_GENERATOR_NOT_STARTED' if not result['phases'] else 'BULK_STOP_REVIEW_PARTIAL_OUTPUT_NOT_ACTIVATED';result['error']=repr(error)
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'run':str(run),'worlds':len(result['worlds']),'resource_gaps':len(result['resource_gaps']),'error':result.get('error')},ensure_ascii=False),flush=True)
    return 1 if 'FAIL' in result['status'] or 'STOP' in result['status'] else 0
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');sys.exit(main())
