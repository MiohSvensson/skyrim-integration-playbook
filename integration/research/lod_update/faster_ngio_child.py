"""Only run this child inside MO2; CPU CLI smoke, no game or GUI launch."""
import argparse
import csv
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,TARGET,owned,sha
sys.path.insert(0,str(OLD))
from verify_cgid import parse,NAME
sys.path.insert(0,str(OUT.parent/'vfs_validation'))
from vfs_common import file_identity


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--run-name');args=parser.parse_args()
    source=Path(args.manifest).resolve(strict=True);assert source==OUT/'smoke_manifest.json'
    manifest=json.loads(source.read_text(encoding='utf-8'))
    name=args.run_name or 'smoke_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    assert re.fullmatch('[A-Za-z0-9_-]+',name)
    run=owned(OUT/'runs'/name);assert not run.exists(),'Preserve prior runs; use a new run name';run.mkdir(parents=True)
    (run/'manifest_used.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    result={'utc':datetime.now(timezone.utc).isoformat(),'status':'RUNNING','manifest_sha256':sha(source),'run':str(run),'phases':[]}
    try:
        kernel=ctypes.WinDLL('kernel32');kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
        assert kernel.GetModuleHandleW('usvfs_x64.dll'),'MO2 VFS required; do not run directly'
        result['usvfs']=True
        profile=Path(manifest['profile_path']);assert profile==TARGET/'profiles'/manifest['profile']
        for relative,digest in manifest['profile_sha256'].items():assert sha(profile/relative)==digest,'Profile drift: rerun prepare_smoke.py'
        assert sha(TARGET/'Game/Skyrim.ccc')==manifest['Skyrim_ccc_sha256']
        vfs_rows=[]
        for row in manifest['plugins']:
            path=TARGET/'Game/Data'/row['name']
            try:
                # Python 3.13 nt._path_isfile may call an unhooked by-name API.
                # CreateFileW/FileID and long-path open are the proven VFS route.
                virtual_id=file_identity(path);physical_id=file_identity(row['path'])
                assert virtual_id==physical_id,f"FileID mismatch virtual={virtual_id} physical={physical_id}"
                digest=sha(path);assert digest==row['sha256'],f"SHA mismatch actual={digest} expected={row['sha256']}"
            except Exception as error:
                raise RuntimeError(f"VFS open/FileID/SHA precheck: plugin={row['name']} virtual={path} expected_provider={row['path']} error={error!r}") from error
            vfs_rows.append({'plugin':row['name'],'virtual_file_id':virtual_id,'physical_file_id':physical_id,'sha256':digest})
        (run/'vfs_preflight.json').write_text(json.dumps({'status':'ALL_VFS_PLUGIN_FILEID_AND_SHA_PASS','plugins':vfs_rows,
            'vfs_common_sha256':sha(OUT.parent/'vfs_validation/vfs_common.py')},indent=2)+'\n',encoding='utf-8')
        for relative,row in manifest['auxiliary'].items():assert sha(TARGET/'Game/Data'/relative)==row['sha256'],f'VFS config mismatch {relative}'
        exe=Path(manifest['generator']['path']);assert exe.resolve()==OUT/'tools/FasterNGIO_1.6/FasterNGIO.exe'
        assert sha(exe)==manifest['generator']['sha256']
        assert shutil.disk_usage(OUT).free>33*1024**3,'Keep 32GiB reserve plus 1GiB smoke headroom'
        environment=os.environ.copy()
        for variable in ('TEMP','TMP','TMPDIR'):
            directory=owned(run/'tmp');directory.mkdir(exist_ok=True);environment[variable]=str(directory)
        common=['--data',str(TARGET/'Game/Data'),'--plugins',str(profile/'plugins.txt'),
                '--game-ini-dir',str(profile),'--ngio-config',str(TARGET/'Game/Data/SKSE/Plugins/GrassControl.ini'),
                '--placement','vanilla','--reject','cpu','--write-empty-cells','--threads','4','--writers','1']
        def execute(command,phase):
            for i,argument in enumerate(command):
                if argument in ('--out','--inspect-grass'):owned(command[i+1])
            assert '--reject' in command and command[command.index('--reject')+1]=='cpu'
            assert '--gui' not in command and '--overwrite' not in command and Path(command[0])==exe
            (run/(phase+'_command.json')).write_text(json.dumps(command,indent=2)+'\n')
            started=time.monotonic()
            with (run/(phase+'.log')).open('wb') as output:
                process=subprocess.Popen(command,cwd=exe.parent,env=environment,stdout=output,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
                (run/(phase+'_pid.json')).write_text(json.dumps({'pid':process.pid})+'\n')
                code=process.wait()
            text=(run/(phase+'.log')).read_text(encoding='utf-8-sig',errors='replace')
            row={'name':phase,'returncode':code,'seconds':round(time.monotonic()-started,2),'log_sha256':sha(run/(phase+'.log'))}
            result['phases'].append(row)
            assert code==0,f'{phase} tool returned {code}; inspect retained log'
            assert re.search(r'load order: '+str(len(manifest['plugins']))+r' plugin\(s\)',text),'Generator plugin count mismatch'
            assert not re.search(r'\[error\]|\[critical\]',text,re.I),f'{phase} contains errors'
            return row,text
        for case in manifest['cases']:
            role=case['role'];folder=owned(run/role);folder.mkdir();grass=owned(folder/'Grass');grass.mkdir()
            local=['--world','0x'+case['world_full_runtime_FormID'],'--cell',str(case['XY'][0]),str(case['XY'][1]),'--out',str(grass)]
            report=owned(folder/'placement.csv')
            row,text=execute([str(exe),*common,*local,'--inspect-grass',str(report)],role+'_inspect')
            values=list(csv.DictReader(report.open(encoding='utf-8-sig',newline='')))
            values=[value for value in values if [int(value['x']),int(value['y'])]==case['XY']]
            assert len(values)==1 and values[0]['status']=='land','No unique expected LAND row'
            placed=int(values[0]['blades']);expected=case['inspect_expected']
            assert placed>=expected['blades_min'] and (expected['blades_max'] is None or placed<=expected['blades_max']),f'{role}: current placement contradicts pinned control; investigate, do not relabel'
            assert values[0]['cell'].upper()==case['cell_full_runtime_FormID'],'Current cell identity differs from manifest'
            row['placement']=values[0]
            row,text=execute([str(exe),*common,*local],role+'_generate')
            files=list(grass.glob('*.cgid'));assert len(files)==1,f'{role}: exactly one cache expected'
            match=NAME.match(files[0].name);assert match and match.group(1).lower()=='tamriel'
            assert [int(match.group(2)),int(match.group(3))]==case['XY']
            parsed=parse(files[0]);expected=case['cache_expected']
            assert parsed['blades']>=expected['blades_min'] and (expected['blades_max'] is None or parsed['blades']<=expected['blades_max'])
            if expected['empty_exact_bytes'] is not None:assert files[0].read_bytes().hex()==expected['empty_exact_bytes']
            row['cache']={'path':str(files[0]),**parsed}
        for relative,digest in manifest['profile_sha256'].items():assert sha(profile/relative)==digest,'Profile changed while smoke ran'
        for row in manifest['plugins']:assert sha(TARGET/'Game/Data'/row['name'])==row['sha256'],'Plugin content changed while smoke ran: '+row['name']
        assert not list(run.rglob('*.fail'))
        result['status']='CPU_MO2_TWO_CELL_SMOKE_PASS_GAME_NOT_STARTED'
    except Exception as error:
        result['status']='PRECHECK_FAIL_GENERATOR_NOT_STARTED' if not result['phases'] else 'SMOKE_FAIL_NO_OUTPUT_ACTIVATED';result['error']=repr(error)
    (run/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'run':str(run),'error':result.get('error')},ensure_ascii=False),flush=True)
    return 0 if result['status']=='CPU_MO2_TWO_CELL_SMOKE_PASS_GAME_NOT_STARTED' else 1


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');sys.exit(main())
