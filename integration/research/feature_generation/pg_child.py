"""MO2-only private PG runner/preflight. Never installs generated files."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'lod_update'));from runtime_common import TARGET,sha
sys.path.insert(0,str(OUT.parent/'vfs_validation'));from vfs_common import file_identity
sys.path.insert(0,str(OUT.parent/'navmesh_patch'));from verify_candidate import Plugin

def known_folder(identity):
    guid=(ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(identity).bytes_le);value=ctypes.c_void_p()
    shell=ctypes.WinDLL('shell32');shell.SHGetKnownFolderPath.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)];shell.SHGetKnownFolderPath.restype=ctypes.c_long
    assert shell.SHGetKnownFolderPath(ctypes.byref(guid),0,None,ctypes.byref(value))==0
    try:return Path(ctypes.wstring_at(value))
    finally:
        ole=ctypes.WinDLL('ole32');ole.CoTaskMemFree.argtypes=[ctypes.c_void_p];ole.CoTaskMemFree(value)

def owned(path):
    p=Path(path).absolute();assert p.resolve().is_relative_to(OUT.resolve()) and p!=OUT
    for parent in [p,*p.parents]:
        if parent==OUT.parent:break
        if parent.exists():assert not parent.stat().st_file_attributes&0x400,'Reparse output forbidden'
    return p

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',required=True);p.add_argument('--run-tool',action='store_true');a=p.parse_args();source=owned(a.manifest);assert source.name=='manifest.json'
    m=json.loads(source.read_text(encoding='utf-8'));run=owned(m['run']);assert source.parent==run;result_path=run/('result.json' if a.run_tool else 'preflight_result.json');assert not result_path.exists(),'Preserve previous result'
    result={'status':'PREFLIGHT_RUNNING','manifest_sha256':sha(source),'generator_started':False}
    try:
        kernel=ctypes.WinDLL('kernel32');kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
        assert kernel.GetModuleHandleW('usvfs_x64.dll'),'Actual MO2 child required';result['usvfs']=True
        profile=Path(m['profile_path']);assert profile==TARGET/'profiles'/m['profile']
        for rel,digest in m['profile_sha256'].items():assert sha(profile/rel)==digest,'Refresh preparation after final profile drift'
        for f in m['tool_files']:assert sha(f['path'])==f['sha256'] and Path(f['path']).stat().st_nlink==1
        cfg=owned(m['user_config']);assert sha(cfg)==m['user_config_sha256'] and cfg.stat().st_nlink==1
        expected=json.loads(cfg.read_text(encoding='utf-8'))['params'];assert expected['shaderpatcher']['truepbr_checkpaths'] and expected['shaderpatcher']['truepbr']
        assert not expected['shaderpatcher']['complexmaterial'] and not expected['shaderpatcher']['parallax'] and not expected['shadertransforms']['parallaxtocm'] and not expected['postpatcher']['fixsss']
        assert expected['processing']['enabletracelogging'],'Native rule/shape provenance trace is mandatory for lighting validation'
        vfs=[]
        for row in m['plugins']:
            virtual=TARGET/'Game/Data'/row['name']
            try:
                fid=file_identity(virtual);assert fid==file_identity(row['path']) and sha(virtual)==row['sha256']
            except Exception as e:raise RuntimeError(f"VFS plugin CreateFileW/FileID/SHA plugin={row['name']} provider={row['path']} error={e!r}") from e
            vfs.append({'plugin':row['name'],'FileID':fid,'sha256':row['sha256']})
        # PG reads the real KnownFolder paths. Prove MO2 redirects these reads to
        # this profile; changing APPDATA environment is not accepted as proof.
        local=known_folder('F1B32785-6FBA-4FCF-9D55-7B8E7F157091');documents=known_folder('FDD39AD0-238F-46AF-ADB4-6C85480369C7');special=[]
        for virtual,physical in [(local/'Skyrim Special Edition/plugins.txt',profile/'plugins.txt'),
                (documents/'My Games/Skyrim Special Edition/Skyrim.ini',profile/'Skyrim.ini'),
                (documents/'My Games/Skyrim Special Edition/SkyrimPrefs.ini',profile/'SkyrimPrefs.ini')]:
            try:assert file_identity(virtual)==file_identity(physical) and sha(virtual)==sha(physical)
            except Exception as e:raise RuntimeError(f'PG KnownFolder VFS read does not match frozen profile: virtual={virtual} expected={physical} error={e!r}') from e
            special.append({'virtual_knownfolder_read':str(virtual),'expected_profile':str(physical),'sha256':sha(physical)})
        for row in m['rule_files']:assert sha(row['path'])==row['sha256'],'PBR rule drift'
        output=owned(m['output']);assert not any(output.iterdir()),'Fresh output mandatory; never seed old PGPatcher.esp'
        (run/'vfs_preflight.json').write_text(json.dumps({'plugins':vfs,'knownfolder_reads':special},indent=2)+'\n')
        result.update(status='PRIVATE_PG_MO2_PREFLIGHT_PASS_NOT_STARTED',KnownFolder_reads=special,required_before_launch=m['required_before_launch'],os_driver_cache_boundary=m['cache_policy']['os_driver_cache_boundary'])
        if a.run_tool:
            assert m['cache_policy'].get('os_driver_cache_boundary_acknowledged') is True and not m['cache_policy'].get('database_only_formal_run_blocked'),'OS-managed driver cache boundary has not been recorded/acknowledged'
            freeze=run/'nif_inputs/manifest.json';frozen=json.loads(freeze.read_text(encoding='utf8'));assert frozen['status']=='FROZEN_ACTUAL_EFFECTIVE_NIF_INPUT_BYTES' and frozen['run_manifest_sha256']==sha(source),'Formal clean source freeze required before generation'
            contract=json.loads((run/'lighting_contract/contract.json').read_text(encoding='utf8'));assert contract['run_manifest_sha256']==sha(source) and contract['source_proof_sha256']==sha(freeze),'Pinned lighting matrix must match this exact fresh run'
            assert not m['required_before_launch'],'Prepare a fresh run after disabling old LOD outputs and completing final record patches: '+str(m['required_before_launch'])
            reserve=m['reserve_GiB']*1024**3;assert shutil.disk_usage(OUT).free>reserve+m['output_budget_GiB']*1024**3
            exe=owned(m['tool']);assert exe.name=='PGPatcher.exe';command=[str(exe),'--autostart']
            env=os.environ.copy()
            for variable,folder in [('TEMP','tmp'),('TMP','tmp'),('TMPDIR','tmp'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata'),('NUGET_PACKAGES','nuget'),('DOTNET_CLI_HOME','dotnet_home')]:
                directory=owned(run/'sandbox'/folder);directory.mkdir(parents=True,exist_ok=True);env[variable]=str(directory)
            symbols=owned(run/'sandbox/symbols');symbols.mkdir(parents=True,exist_ok=True);env['_NT_SYMBOL_PATH']=str(symbols)
            env['DOTNET_ROOT']=m['net8_root'];env['DOTNET_ROOT_X64']=m['net8_root'];env['DOTNET_CLI_TELEMETRY_OPTOUT']='1';env['DOTNET_SKIP_FIRST_TIME_EXPERIENCE']='1'
            (run/'command.json').write_text(json.dumps(command,indent=2)+'\n');started=time.monotonic()
            with (run/'stdout.log').open('wb') as log:
                process=subprocess.Popen(command,cwd=exe.parent,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);result.update(generator_started=True,pid=process.pid)
                (run/'pid.json').write_text(json.dumps({'pid':process.pid})+'\n')
                while process.poll() is None:
                    if shutil.disk_usage(OUT).free<reserve+128*1024**2:process.terminate();process.wait();raise RuntimeError('PG stopped before reserve exhaustion; partial output not activated')
                    time.sleep(2)
                code=process.returncode
            result.update(returncode=code,seconds=round(time.monotonic()-started,2));assert code==0,'Tool returned error; normal OS security refusal is fatal, never bypass it'
            log=exe.parent/'log/PGPatcher.log';assert log.exists();logs=sorted(log.parent.glob('PGPatcher*.log'));assert logs
            result['tool_logs']=[{'path':str(f),'sha256':sha(f),'bytes':f.stat().st_size} for f in logs];result['tool_log_sha256']=sha(log)
            loaded_rule_trace=False;winning_match_trace=False
            for f in logs:
                with f.open(encoding='utf-8-sig',errors='replace') as stream:
                    for line in stream:
                        assert not re.search(r'\[critical\]|\[error\]',line,re.I),'Tool log has errors in '+str(f)
                        loaded_rule_trace |= 'TruePBR Config ' in line and ' Loaded: ' in line
                        winning_match_trace |= 'Winning Match: ' in line
            assert loaded_rule_trace and winning_match_trace,'Native rule/shape trace missing or rotated away; no lighting provenance proof'
            allowed={x.lower().replace('\\','/') for x in m['expected_mesh_allowlist']};blocked=m['blocked_single_mesh'].lower().replace('\\','/');inventory=[]
            for file in sorted(output.rglob('*')):
                if not file.is_file():continue
                owned(file);assert file.stat().st_nlink==1;rel=file.relative_to(output).as_posix().lower()
                if file.suffix.lower()=='.nif':
                    original=re.sub(r'^meshes/_pgpatcher_dups/[1-9][0-9]*/','meshes/',rel);assert original in allowed and original!=blocked,'Unexpected NIF outside incoming allowlist'
                elif file.suffix.lower()=='.dds':
                    assert rel=='textures/cubemaps/dynamic1pxcubemap_black.dds' and sha(file)==sha(exe.parent/'assets/dynamic1pxcubemap_black.dds'),'Texture generation was disabled; unexpected generated DDS'
                elif file.suffix.lower() in ('.esp','.esm','.esl'):
                    assert file.name.lower()=='dbpatcher.esp' or re.fullmatch(r'db_[1-9][0-9]*\.esp',file.name.lower()),'Unexpected/clashing plugin filename'
                    plugin=Plugin(file)
                    records=[r for r in plugin.records if r['signature']!='TES4']
                    if file.name.lower()=='dbpatcher.esp':assert all(r['signature']=='TXST' and r['id'].startswith('dbpatcher.esp|') for r in records),'New owner may contain only own TXST'
                    else:assert all(not r['id'].startswith(plugin.name+'|') and r['signature'] not in ('NAVM','NAVI','WRLD','CELL','QUST','NPC_','PACK') for r in records),'Graphics split must contain only existing modeled-record overrides'
                    expected_names={r['name_key'] for r in m['plugins']}|{p.name.lower() for p in output.glob('*.esp')}
                    assert all(x in expected_names for x in plugin.masters),'Output has unresolved master name'
                inventory.append({'relative':rel,'path':str(file),'bytes':file.stat().st_size,'sha256':sha(file)})
            assert any(r['relative'].endswith('.nif') for r in inventory),'No NIF output; exit0 alone does not prove generation'
            (run/'output_inventory.json').write_text(json.dumps(inventory,indent=2)+'\n')
            for rel,digest in m['profile_sha256'].items():assert sha(profile/rel)==digest,'Profile changed during generation'
            for row in m['plugins']:assert sha(TARGET/'Game/Data'/row['name'])==row['sha256'],'Source plugin changed'
            for row in m['rule_files']:assert sha(row['path'])==row['sha256'],'Source PBR rule changed'
            result['status']='PRIVATE_PG_OUTPUT_CREATED_NOT_DEPLOYED_PENDING_TYPED_RECORD_AND_NIF_REVIEW';result['output_files']=len(inventory)
    except Exception as error:result.update(status='PRIVATE_PG_STOP_NO_DEPLOYMENT',error=repr(error))
    result_path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=True),flush=True)
    return 1 if result['status']=='PRIVATE_PG_STOP_NO_DEPLOYMENT' else 0
if __name__=='__main__':sys.exit(main())
