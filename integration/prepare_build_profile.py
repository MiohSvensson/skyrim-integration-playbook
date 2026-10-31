"""Create a private producer profile excluding stale derived plugin closure."""
import json
import shutil
from pathlib import Path
from materialize import BASE,TARGET,key,utc
import runtime_inventory as runtime

source=runtime.PROFILE
target=TARGET/'profiles/Unified Build'
assert not target.exists(), 'Build profile already exists; inspect before refreshing'
inventory=runtime.inventory()
assert not inventory['missing_plugins'] and not inventory['missing_masters']
rows={key(r['name']):r for r in inventory['plugins']}
disabled={key(n) for n in ['Synthesis - Patch.esp','DynDOLOD.esm','DynDOLOD.esp','Occlusion.esp']}
disabled &= rows.keys()
while True:
    extra={n for n,r in rows.items() if n not in disabled and any(key(m) in disabled for m in r['masters'])}
    if not extra:break
    disabled |= extra
provider_names={rows[n]['provider'] for n in disabled}
target.mkdir()
for p in source.iterdir():
    if p.is_file():shutil.copyfile(p,target/p.name)
for name in ['plugins.txt','loadorder.txt']:
    p=target/name
    lines=p.read_text('utf-8-sig').splitlines()
    lines=[line for line in lines if key(line.lstrip('*')) not in disabled]
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
p=target/'modlist.txt'
lines=p.read_text('utf-8-sig').splitlines()
lines=['-'+line[1:] if line.startswith('+') and line[1:] in provider_names else line for line in lines]
p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
runtime.PROFILE=target
after=runtime.inventory()
assert not after['missing_plugins'] and not after['missing_masters']
report={'utc':utc(),'profile':str(target),'disabled_plugins':[rows[n]['name'] for n in sorted(disabled)],
        'disabled_mods':sorted(provider_names),'active_plugin_count':len(after['plugins']),
        'purpose':'Full active source context for compatibility/nav producers; old generated patch/LOD plugins and their dependent closure excluded.'}
(BASE/'integration/build_profile.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
