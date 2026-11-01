"""MO2-only xEdit producer/typed reload verifier, with explicit completion marker."""
import configparser
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from materialize import BASE,TARGET,sha,utc
import xedit_dialogs
import native_xedit_context
import mo2_controls

task=Path(sys.argv[1]).resolve(strict=True)
assert task.is_relative_to(TARGET/'validation')
kernel=ctypes.WinDLL('kernel32')
kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype=ctypes.c_void_p
assert kernel.GetModuleHandleW('usvfs_x64.dll'), 'Actual MO2 VFS required'
prepared=json.loads((task/'prepared.json').read_text('utf-8'))
normal_settings=None
if prepared.get('normal_records_option') is not None:
    assert sha(__file__)==prepared['harness_sha256']['xedit_producer_child.py'],'Frozen harness changed before dispatch'
    assert sha(xedit_dialogs.__file__)==prepared['harness_sha256']['xedit_dialogs.py'],'Frozen dialog helper changed before dispatch'
    assert sha(native_xedit_context.__file__)==prepared['harness_sha256']['native_xedit_context.py'],'Frozen native-context helper changed before dispatch'
    assert sha(mo2_controls.__file__)==prepared['harness_sha256']['mo2_controls.py'],'Frozen control audit changed before dispatch'
    settings_path=Path(prepared['normal_records_ini'])
    assert settings_path.resolve()==TARGET/'tools/xedit/SSEScript.ini'
    ini=configparser.ConfigParser();ini.read_string(settings_path.read_text('utf-8-sig'))
    assert ini.get('Options','SimpleRecords').strip()=='0','Actual VFS tool INI no longer uses verified numeric0'
    normal_settings={'path':str(settings_path),'sha256':sha(settings_path),'SimpleRecords':'0'}
assert sha(prepared['script'])==prepared['script_sha256']
def control_audit():
    return mo2_controls.audit_profile_controls(prepared['profile'],prepared.get('profile_controls',{}),
        prepared.get('expected_modlist_snapshot',task/'modlist.prepared.txt'),prepared.get('allowed_mo2_disabled_mods',[]))
before_controls=control_audit()
(task/'profile_control_before.json').write_text(json.dumps(before_controls,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not before_controls['changed_controls'],'Profile drift before launch: '+','.join(before_controls['changed_controls'])
command=json.loads((task/'xedit_command.json').read_text('utf-8'))
assert Path(command[0]).resolve()==TARGET/'tools/xedit/SSEEdit64.exe'
assert '-nofixup' in command
log=task/'logs/xedit.log'
assert not log.exists()
(task/'child_started.json').write_text(json.dumps({'utc':utc(),'usvfs':True,'pid':os.getpid(),'normal_records_config':normal_settings})+'\n',encoding='utf-8')
started=time.monotonic()
inputs=json.loads((task/'input_inventory.json').read_text('utf-8'))
process=subprocess.Popen(command,cwd=Path(command[0]).parent)
(task/'xedit_pid.json').write_text(json.dumps({'pid':process.pid})+'\n',encoding='utf-8')
watcher=xedit_dialogs.ModuleSelectionWatcher(task,process,len(inputs['plugins']),prepared.get('progress_file'))
timed_out=False
try:
    try:
        code=process.wait(timeout=prepared.get('xedit_timeout_seconds',3600))
    except subprocess.TimeoutExpired:
        timed_out=True
        process.kill()
        code=process.wait()
finally:
    watcher.stop()
changed_inputs=[r['name'] for r in inputs['plugins'] if sha(r['path'])!=r['sha256']]
after_controls=control_audit()
changed_controls=after_controls['changed_controls']
autosave=None
patch_name=prepared.get('patch_name')
if patch_name:
    saved=TARGET/'overwrite'/patch_name
    if saved.exists():
        assert saved.is_file() and saved.resolve().is_relative_to((TARGET/'overwrite').resolve())
        assert saved.stat().st_nlink==1
        quarantine=task/'autosave'/patch_name
        quarantine.parent.mkdir(exist_ok=False)
        autosave={'source':str(saved),'quarantined':str(quarantine),'sha256':sha(saved),
                  'disposition':'Script-mode automatic save is isolated; only explicitly exported and independently verified candidate can be installed.'}
        saved.rename(quarantine)
loaded_context=native_xedit_context.evaluate(task,prepared,inputs,log)
candidate=Path(prepared['candidate']) if prepared['candidate'] else None
passed=code==0 and not timed_out and loaded_context['exact_order_match'] and loaded_context['script_done_marker_seen'] and loaded_context['marker_seen'] and not changed_inputs and not changed_controls and not (task/'module_selection_error.json').exists() and (candidate is None or candidate.is_file())
result={'utc':utc(),'status':'PASS' if passed else 'FAIL','usvfs':True,'return_code':code,
        'seconds':round(time.monotonic()-started,1),'pass_marker':prepared['pass_marker'],'timed_out':timed_out,
        'marker_seen':loaded_context['marker_seen'],'log_sha256':loaded_context['log_sha256'],
        'candidate_sha256':sha(candidate) if candidate and candidate.exists() else None,
        'native_loaded_context':loaded_context,
        'profile_control_audit':after_controls,
        'native_progress':native_xedit_context.read_log(prepared['progress_file']) if prepared.get('progress_file') else None}
result['changed_input_plugins']=changed_inputs
result['changed_profile_controls']=changed_controls
result['isolated_script_autosave']=autosave
result['module_selection_confirmation']=(task/'module_selection_confirmation.json').is_file()
(task/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False),flush=True)
raise SystemExit(0 if passed else 1)
