"""MO2 Python bootstrap retaining stdout, stderr and even pre-main exceptions."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import runpy
import sys
import traceback
from contextlib import redirect_stdout, redirect_stderr
from materialize import BASE,TARGET,sha,utc

p=argparse.ArgumentParser()
p.add_argument('task_name')
p.add_argument('script')
p.add_argument('arguments',nargs=argparse.REMAINDER)
a=p.parse_args()
assert a.task_name.replace('_','').replace('-','').isalnum()
source=Path(a.script).resolve(strict=True)
assert source.is_relative_to(BASE/'integration') and source.suffix=='.py'
task=TARGET/'validation'/a.task_name
task.mkdir(parents=True,exist_ok=True)
log=task/'python_child.log'
assert not log.exists(), 'Every bootstrap invocation has a fresh task name'
kernel=ctypes.WinDLL('kernel32')
kernel.GetModuleHandleW.argtypes=[ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype=ctypes.c_void_p
started={'utc':utc(),'pid':os.getpid(),'usvfs':bool(kernel.GetModuleHandleW('usvfs_x64.dll')),
         'script':str(source),'script_sha256':sha(source),'arguments':a.arguments}
(task/'bootstrap_started.json').write_text(json.dumps(started,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert started['usvfs'], 'Actual MO2 environment required'
sys.path.insert(0,str(source.parent))
sys.argv=[str(source),*a.arguments]
code=0
with log.open('w',encoding='utf-8',buffering=1) as stream,redirect_stdout(stream),redirect_stderr(stream):
    print(json.dumps(started,ensure_ascii=False),flush=True)
    try:
        runpy.run_path(str(source),run_name='__main__')
    except SystemExit as ex:
        code=ex.code if isinstance(ex.code,int) else (0 if ex.code is None else 1)
        if code:traceback.print_exc()
    except BaseException:
        code=1
        traceback.print_exc()
(task/'bootstrap_exit.json').write_text(json.dumps({'utc':utc(),'return_code':code,'log_sha256':sha(log)})+'\n',encoding='utf-8')
raise SystemExit(code)
