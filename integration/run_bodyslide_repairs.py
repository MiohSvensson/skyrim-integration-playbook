"""Execute one prepared BodySlide group into its own fresh output directory."""
import argparse
import json
import os
import subprocess
from pathlib import Path

from materialize import BASE, TARGET, sha, utc

parser = argparse.ArgumentParser()
parser.add_argument('pack', choices=['Anno', 'Burida'])
parser.add_argument('--task-suffix', default='')
args = parser.parse_args()
plan = json.loads((BASE/'integration/bodyslide_prepared.json').read_text('utf-8'))
job = next(r for r in plan['jobs'] if r['pack'] == args.pack)
tool = Path(job['tool'])
assert not args.task_suffix or args.task_suffix.replace('_','').isalnum()
task = TARGET/'validation'/('bodyslide_'+args.pack.lower()+args.task_suffix)
task.mkdir(exist_ok=False)
assert sha(tool/'Config.xml') == job['private_config_sha256']
assert sha(tool/'BodySlide x64.exe') == job['tool_sha256']
assert not any(p.is_file() for p in Path(job['output']).rglob('*')), 'Output must have no prior files'
env = os.environ.copy()
for name in ['TEMP', 'TMP', 'APPDATA', 'LOCALAPPDATA']:
    directory = task/'sandbox'/name
    directory.mkdir(parents=True, exist_ok=True)
    env[name] = str(directory)
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 4  # GUI producer remains targetable for errors, without activation.
(task/'command.json').write_text(json.dumps({'utc': utc(), 'command': job['command'], 'config_sha256': job['private_config_sha256'], 'game_not_selected': True}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
with (task/'console.log').open('w', encoding='utf-8') as console:
    process = subprocess.Popen(job['command'], cwd=tool, env=env, startupinfo=startup, stdout=console, stderr=subprocess.STDOUT)
    print(json.dumps({'pid': process.pid, 'pack': args.pack}), flush=True)
    code = process.wait()
outputs = [{'path': str(p.relative_to(job['output'])), 'bytes': p.stat().st_size, 'sha256': sha(p)}
           for p in Path(job['output']).rglob('*') if p.is_file()]
result = {'utc': utc(), 'return_code': code, 'output_files': outputs, 'status': 'GENERATED_PENDING_GEOMETRY_AND_MORPH_CHECKS'}
(task/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'return_code': code, 'files': len(outputs)}, indent=2))
raise SystemExit(code)
