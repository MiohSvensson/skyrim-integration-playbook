"""Pin xEdit 4.1.5f and its normal-record settings to a private tool location."""
import hashlib
import json
import shutil
from pathlib import Path

from materialize import BASE, TARGET, utc

source = BASE/'tools/xedit'
target = TARGET/'tools/xedit'
target.mkdir(parents=True, exist_ok=True)
if not (target/'SSEEdit64.exe').exists():
    shutil.copyfile(source/'SSEEdit64.exe', target/'SSEEdit64.exe')
assert hashlib.sha256((target/'SSEEdit64.exe').read_bytes()).digest() == hashlib.sha256((source/'SSEEdit64.exe').read_bytes()).digest()
scripts = target/'Edit Scripts'
if not scripts.exists():
    shutil.copytree(source/'Edit Scripts', scripts)
settings = '[Options]\nSimpleRecords=0\n'
for name in ['SSEEdit.ini', 'SSEScript.ini', 'SSECheckForErrors.ini']:
    (target/name).write_text(settings, encoding='utf-8')
profile = TARGET/'profiles/Unified Skyrim'
(profile/'plugins.sseviewsettings').write_text(settings, encoding='utf-8')
ini = TARGET/'MO2/ModOrganizer.ini'
lines = ini.read_text(encoding='utf-8-sig').splitlines()
for i, line in enumerate(lines):
    if line.startswith('2\\binary='):
        lines[i] = '2\\binary='+(target/'SSEEdit64.exe').as_posix()
    elif line.startswith('2\\workingDirectory='):
        lines[i] = '2\\workingDirectory='+target.as_posix()
ini.write_text('\n'.join(lines)+'\n', encoding='utf-8')
manifest = {'utc': utc(), 'executable': str(target/'SSEEdit64.exe'),
            'sha256': hashlib.sha256((target/'SSEEdit64.exe').read_bytes()).hexdigest(),
            'normal_records': True, 'source_copy': str(source), 'game_not_started': True}
(BASE/'integration/private_xedit.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
print(json.dumps(manifest, indent=2))
