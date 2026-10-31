"""MO2-only child; launch the reviewed read-only xEdit command and parse proof."""
import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from materialize import BASE, TARGET, utc

task = Path(sys.argv[1]).resolve(strict=True)
assert task.is_relative_to(TARGET/'validation')
kernel = ctypes.WinDLL('kernel32')
kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype = ctypes.c_void_p
assert kernel.GetModuleHandleW('usvfs_x64.dll'), 'xEdit must run in the real MO2 environment'
command = json.loads((task/'xedit_command.json').read_text(encoding='utf-8'))
assert Path(command[0]).resolve() == (TARGET/'tools/xedit/SSEEdit64.exe').resolve()
assert '-autoexit' in command and '-nofixup' in command
log = task/'logs/xedit.log'
assert not log.exists(), 'Preserve an existing run before repeating'
(task/'child_started.json').write_text(json.dumps({'utc': utc(), 'usvfs': True, 'pid': os.getpid()})+'\n', encoding='utf-8')
start = time.monotonic()
process = subprocess.Popen(command, cwd=Path(command[0]).parent)
(task/'xedit_pid.json').write_text(json.dumps({'pid': process.pid})+'\n', encoding='utf-8')
code = process.wait()
text = log.read_text(encoding='utf-8-sig', errors='replace') if log.exists() else ''
rows = re.findall(r'UNIFIED_PLUGIN\t([^\t\r\n]+)\t(\d+)\t(\d+)', text)
complete = re.findall(r'UNIFIED_COMPLETE\t(\d+)\t(\d+)', text)
expected = json.loads((task/'prepared.json').read_text(encoding='utf-8'))['targets']
results = [{'plugin': n, 'records': int(count), 'diagnostic_records': int(bad)} for n, count, bad in rows]
passed = code == 0 and bool(complete) and int(complete[-1][1]) == 0 and len(results) == len(expected)
passed = passed and {p['plugin'].casefold() for p in results} == {n.casefold() for n in expected}
passed = passed and all(p['records'] > 0 and p['diagnostic_records'] == 0 for p in results)
result = {'utc': utc(), 'status': 'PASS' if passed else 'FAIL', 'usvfs': True,
          'return_code': code, 'seconds': round(time.monotonic()-start, 1), 'plugins': results,
          'complete': complete[-1] if complete else None,
          'loaded_files': len(re.findall(r'UNIFIED_LOADED\t', text)),
          'log': str(log), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else None}
(task/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False), flush=True)
sys.exit(0 if passed else 1)
