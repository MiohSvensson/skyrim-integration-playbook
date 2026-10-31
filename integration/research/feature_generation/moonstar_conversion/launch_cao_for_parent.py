"""Parent-only explicit author GUI launch; this research agent does not execute it."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'manifest.json').read_text(encoding='utf-8'))
k=ctypes.WinDLL('kernel32');k.GetModuleHandleW.argtypes=[ctypes.c_wchar_p];k.GetModuleHandleW.restype=ctypes.c_void_p
assert not k.GetModuleHandleW('usvfs_x64.dll'),'CAO must run standalone, outside MO2 VFS'
for r in m['input_files']:
    p=Path(r['candidate']);assert p.resolve().is_relative_to((ROOT/'candidate').resolve()) and p.stat().st_nlink==1
    assert hashlib.sha256(p.read_bytes()).hexdigest()==r['source_sha256'],'Candidate already processed: inspect previous results before any rerun'
env=os.environ.copy()
for variable,folder in [('TEMP','tmp'),('TMP','tmp'),('TMPDIR','tmp'),('APPDATA','appdata'),('LOCALAPPDATA','localappdata')]:
    d=ROOT/'sandbox'/folder;d.mkdir(parents=True,exist_ok=True);env[variable]=str(d)
exe=ROOT/'tool/Cathedral_Assets_Optimizer.exe';expected=next(r['sha256'] for r in m['tool_files'] if Path(r['private_path']).name==exe.name)
assert hashlib.sha256(exe.read_bytes()).hexdigest()==expected
process=subprocess.Popen([str(exe)],cwd=exe.parent,env=env,creationflags=subprocess.CREATE_NO_WINDOW)
(ROOT/'launch.json').write_text(json.dumps({'pid':process.pid,'executable':str(exe),'cwd':str(exe.parent),'input_directory_to_choose':str(ROOT/'candidate'),'source_sha256':expected,'gui_settings':m['GUI_exact_settings']},indent=2)+'\n')
print(json.dumps({'pid':process.pid,'input_directory':str(ROOT/'candidate')}))
