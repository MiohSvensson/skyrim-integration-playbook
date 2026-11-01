"""Freeze a fail-closed xEdit script job in the complete private build profile."""
import argparse
import configparser
import json
import re
from pathlib import Path
from materialize import BASE,TARGET,sha,utc
import runtime_inventory as runtime
from mo2_controls import normalize_profile

ap=argparse.ArgumentParser()
ap.add_argument('task_name')
ap.add_argument('script')
ap.add_argument('pass_marker')
ap.add_argument('--candidate')
ap.add_argument('--profile', choices=['Unified Build', 'Unified Skyrim', 'FC Diagnostic', 'FC Diagnostic 2', 'Synthesis Diagnostic'], default='Unified Build')
ap.add_argument('--timeout-seconds', type=int, default=3600)
ap.add_argument('--allow-mo2-disabled-mod', action='append', default=[], choices=['ZZ90 FC diagnostic', 'ZZ90 FC diagnostic 2', 'ZZ89 Synthesis candidate'])
args=ap.parse_args()
assert 30 <= args.timeout_seconds <= 86400
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
for filename in ['prepare_xedit_producer.py','xedit_producer_child.py','xedit_dialogs.py','native_xedit_context.py','logged_child.py','mo2_controls.py']:
    p=BASE/'integration'/filename
    (harness_dir/(filename+'.frozen.txt')).write_bytes(p.read_bytes())
    harness_files[filename]=sha(p)
script=TARGET/'tools/xedit/Edit Scripts'/(args.task_name+'.pas')
assert not script.exists()
source_text=source.read_text('utf-8')
progress_file=task/'native_progress.txt'
progress_match=re.search(r"(?m)^\s*PROGRESS\s*=\s*'([^']+)'\s*;",source_text)
progress_instrumented="PROGRESS_FILE = '';" in source_text or bool(progress_match)
if progress_match:
    progress_file=Path(progress_match.group(1)).resolve()
    assert progress_file.is_relative_to(BASE/'integration/research')
if "PROGRESS_FILE = '';" in source_text:
    assert source_text.count("PROGRESS_FILE = '';")==1
    source_text=source_text.replace("PROGRESS_FILE = '';", "PROGRESS_FILE = '"+str(progress_file).replace("'", "''")+"';")
    script.write_text(source_text,encoding='utf-8',newline='')
else:
    script.write_bytes(source.read_bytes())
patch_match=re.search(r"PATCH_NAME\s*=\s*'([^']+)'",source_text)
patch_name=patch_match.group(1) if patch_match else None
if patch_name:
    assert Path(patch_name).name==patch_name and not (TARGET/'overwrite'/patch_name).exists()
profile=TARGET/'profiles'/args.profile
control_normalization=normalize_profile(profile,task/'control_normalization')
assert len(set(args.allow_mo2_disabled_mod)) == len(args.allow_mo2_disabled_mod)
modlist_rows=(profile/'modlist.txt').read_text('utf-8-sig').splitlines()
for mod in args.allow_mo2_disabled_mod:
    assert (TARGET/'mods'/mod).is_dir(), 'Approved disabled mod must have a private mod directory'
    matching=[row for row in modlist_rows if row[1:].casefold()==mod.casefold()]
    assert len(matching) <= 1 and (not matching or matching[0]=='-'+mod), 'Only MO2-disabled diagnostic entries may be reconciled'
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
manifest={'utc':utc(),'source_script':str(source),'source_script_sha256':sha(source),
          'script':str(script),'script_sha256':sha(script),'progress_file':str(progress_file) if progress_instrumented else None,
          'normal_records_ini':str(settings),'normal_records_option':'0','harness_sha256':harness_files,
          'patch_name':patch_name,
          'profile':str(profile),'control_normalization':control_normalization,
          'allowed_mo2_disabled_mods':args.allow_mo2_disabled_mod,
          'expected_modlist_snapshot':str(task/'modlist.prepared.txt'),
          'pass_marker':args.pass_marker,'candidate':str(candidate) if candidate else None,
          'context_plugins':len(before['plugins']),'xedit_timeout_seconds':args.timeout_seconds,'game_not_selected':True}
manifest['profile_controls']={name:sha(profile/name) for name in ['modlist.txt','plugins.txt','loadorder.txt','Skyrim.ini','SkyrimCustom.ini','skyrimprefs.ini','initweaks.ini','archives.txt','settings.ini'] if (profile/name).is_file()}
(task/'modlist.prepared.txt').write_bytes((profile/'modlist.txt').read_bytes())
(task/'prepared.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'xedit_command.json').write_text(json.dumps(command,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'input_inventory.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(task/'file_map.json').write_text(json.dumps({r['name']:r['path'] for r in before['plugins']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
