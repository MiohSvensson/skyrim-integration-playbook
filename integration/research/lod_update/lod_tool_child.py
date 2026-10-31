"""Parent-controlled MO2 GUI-tool child. Does not select/launch any game."""
import argparse
import ctypes
import json
import os
import subprocess
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
from runtime_common import OUT,TARGET,owned,sha
sys.path.insert(0,str(OUT.parent/'vfs_validation'))
from vfs_common import file_identity


def verify_tool_batch(batch,directory):
    tool_name='xLODGen' if batch['stage']=='terrain' else 'DynDOLOD'
    root=(directory/'tool'/tool_name).resolve()
    assert batch['tool_name']==tool_name and Path(batch['tool_root']).resolve()==root
    owned(root);assert root.is_dir()
    expected={}
    for row in batch['tool_files']:
        relative=Path(row['relative']);assert not relative.is_absolute() and '..' not in relative.parts
        path=(root/relative).resolve(strict=True);assert path.is_relative_to(root) and Path(row['path']).resolve()==path
        owned(path);assert path.is_file() and path.stat().st_nlink==1
        assert path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'Frozen batch tool drift: '+str(path)
        assert path not in expected,'Duplicate tool manifest path'
        expected[path]=row
    entries=list(root.rglob('*'))
    for path in entries:owned(path)
    actual={path.resolve() for path in entries if path.is_file()}
    assert actual==set(expected),'Unpinned or missing file in isolated tool directory'
    for change in batch.get('private_preset_changes',[]):
        path=Path(change['path']).resolve();assert path in expected and sha(path)==change['sha256_after']
    executable={'texgen':'TexGenx64.exe','terrain':'xLODGenx64.exe','dyndolod':'DynDOLODx64.exe','occlusion':'DynDOLODx64.exe'}[batch['stage']]
    program=(root/executable).resolve();assert program in expected and Path(batch['argv'][0]).resolve()==program
    assert sha(program)==batch['exe_sha256'] and program.stat().st_nlink==1
    return program


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);args=parser.parse_args()
    path=Path(args.manifest).resolve(strict=True);assert path.name=='batch_manifest.json' and path.is_relative_to(OUT/'batches')
    batch=json.loads(path.read_text(encoding='utf-8'));directory=path.parent
    assert not (directory/'process_result.json').exists(),'Preserve previous launch; prepare a new batch name'
    kernel=ctypes.WinDLL('kernel32');kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];kernel.GetModuleHandleW.restype=ctypes.c_void_p
    assert kernel.GetModuleHandleW('usvfs_x64.dll'),'MO2 VFS required'
    profile=Path(batch['profile_path'])
    for relative,digest in batch['profile_sha256'].items():assert sha(profile/relative)==digest,'Profile drift: reprepare batch'
    for row in batch['plugins']:
        virtual=TARGET/'Game/Data'/row['name']
        assert file_identity(virtual)==file_identity(row['path']),'VFS provider mismatch: '+row['name']
        assert sha(virtual)==row['sha256'],'VFS plugin content mismatch: '+row['name']
        assert Path(row['path']).stat().st_nlink==1,'Loaded plugin must be a private input before any generator can run: '+row['name']
    command=batch['argv'];program=verify_tool_batch(batch,directory)
    for argument in command[1:]:
        if argument[:3].lower() in ('-o:','-c:','-t:','-b:','-r:'):owned(argument[3:])
    environment=os.environ.copy()
    for variable in ('TEMP','TMP','APPDATA','LOCALAPPDATA'):
        target=owned(directory/'environment'/variable);target.mkdir(parents=True,exist_ok=True);environment[variable]=str(target)
    (directory/'child_started.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'usvfs':True,'program':str(program),'argv':command},indent=2)+'\n')
    # These are the requested generation GUIs; root controls their supported UI.
    # No game/SKSE/launcher executable is allowed by the explicit whitelist.
    process=subprocess.Popen(command,cwd=program.parent,env=environment)
    (directory/'pid.json').write_text(json.dumps({'pid':process.pid})+'\n')
    code=process.wait()
    changed=[]
    for row in batch['plugins']:
        after=sha(row['path'])
        if after!=row['sha256']:changed.append({'name':row['name'],'path':row['path'],'sha256_before':row['sha256'],'sha256_after':after})
    result={'utc':datetime.now(timezone.utc).isoformat(),'returncode':code,'status':'PROCESS_EXITED_REQUIRES_GENERATION_LOG_AND_OUTPUT_AUDIT',
            'output':batch['output'],'game_started':False,'input_provider_changes':changed}
    if changed:result['status']='INPUT_PROVIDER_CHANGED_NEEDS_REVIEW_NO_AUTOMATIC_INSTALL'
    (directory/'process_result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True);return code


if __name__=='__main__':sys.exit(main())
