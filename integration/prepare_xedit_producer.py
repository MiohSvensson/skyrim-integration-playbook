"""Freeze a fail-closed xEdit script job in the complete private build profile."""
import argparse
import configparser
import json
import re
from pathlib import Path
from materialize import BASE,TARGET,sha,utc
import runtime_inventory as runtime

ap=argparse.ArgumentParser()
ap.add_argument('task_name')
ap.add_argument('script')
ap.add_argument('pass_marker')
ap.add_argument('--candidate')
ap.add_argument('--profile', choices=['Unified Build', 'Unified Skyrim'], default='Unified Build')
args=ap.parse_args()
assert re.fullmatch('[A-Za-z0-9_]+',args.task_name)
source=Path(args.script).resolve(strict=True)
assert source.is_relative_to(BASE/'integration/research') and source.suffix=='.pas'
task=TARGET/'validation'/args.task_name
task.mkdir(exist_ok=False)
for n in ['logs','cache','tmp']:(task/n).mkdir()
settings=TARGET/'tools/xedit/SSEScript.ini'
settings_parser=configparser.ConfigParser()
settings_parser.read_string(settings.read_text('utf-8-sig'))
assert settings_parser.get('Options','SimpleRecords').strip()=='0', 'Use experimentally verified numeric SimpleRecords=0'
harness_dir=task/'harness'
harness_dir.mkdir()
harness_files={}
for filename in ['prepare_xedit_producer.py','xedit_producer_child.py','logged_child.py']:
    p=BASE/'integration'/filename
    (harness_dir/(filename+'.frozen.txt')).write_bytes(p.read_bytes())
    harness_files[filename]=sha(p)
script=TARGET/'tools/xedit/Edit Scripts'/(args.task_name+'.pas')
assert not script.exists()
script.write_bytes(source.read_bytes())
patch_match=re.search(r"PATCH_NAME\s*=\s*'([^']+)'",source.read_text('utf-8'))
patch_name=patch_match.group(1) if patch_match else None
if patch_name:
    assert Path(patch_name).name==patch_name and not (TARGET/'overwrite'/patch_name).exists()
profile=TARGET/'profiles'/args.profile
runtime.PROFILE=profile
before=runtime.inventory()
assert not before['missing_plugins'] and not before['missing_masters']
command=[str(TARGET/'tools/xedit/SSEEdit64.exe'),'-SSE','-nobuildrefs','-nofixup','-forcebsa','-autoload','-autoexit',
         '-script:'+str(script),'-D:'+str(TARGET/'Game/Data')+'\\','-P:'+str(profile/'plugins.txt'),
         '-I:'+str(profile/'Skyrim.ini'),'-CustomIni:'+str(profile/'SkyrimCustom.ini'),'-C:'+str(task/'cache')+'\\',
         '-T:'+str(task/'tmp')+'\\','-G:'+str(task/'tmp')+'\\','-B:'+str(task/'tmp')+'\\','-R:'+str(task/'logs/xedit.log')]
candidate=Path(args.candidate).resolve() if args.candidate else None
if candidate:
    assert candidate.is_relative_to(BASE) and not candidate.exists()
manifest={'utc':utc(),'source_script':str(source),'script':str(script),'script_sha256':sha(script),
          'normal_records_ini':str(settings),'normal_records_option':'0','harness_sha256':harness_files,
          'patch_name':patch_name,
          'profile':str(profile),'pass_marker':args.pass_marker,'candidate':str(candidate) if candidate else None,
          'context_plugins':len(before['plugins']),'game_not_selected':True}
manifest['profile_controls']={name:sha(profile/name) for name in ['modlist.txt','plugins.txt','loadorder.txt','Skyrim.ini','SkyrimCustom.ini','initweaks.ini','archives.txt','settings.ini'] if (profile/name).is_file()}
(task/'prepared.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'xedit_command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'input_inventory.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'file_map.json').write_text(json.dumps({r['name']:r['path'] for r in before['plugins']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
