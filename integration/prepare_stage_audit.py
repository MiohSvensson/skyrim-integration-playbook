"""Prepare one full-load xEdit audit of every new item and reviewed repair."""
import hashlib
import json
import sys
import re
from pathlib import Path

from materialize import BASE, TARGET, key, utc
from runtime_inventory import PROFILE, inventory

task_name = sys.argv[1] if len(sys.argv) > 1 else 'equipment_stage'
assert re.fullmatch(r'[A-Za-z0-9_]+', task_name)
task = TARGET/'validation'/task_name
assert not (task/'result.json').exists(), 'Preserve completed runs; choose a new task name'
for name in ['logs', 'cache', 'tmp']:
    (task/name).mkdir(parents=True, exist_ok=True)
targets = set()
gear = json.loads((BASE/'integration/imported_equipment.json').read_text(encoding='utf-8'))
targets.update(row['name'] for row in gear['plugins'])
repairs = json.loads((BASE/'integration/applied_baseline_repairs.json').read_text(encoding='utf-8'))
targets.update(row['plugin'] for row in repairs['repairs'])
targets.update(['God of War.esp', 'HentairimMaleVoice.esp'])
targets = sorted(targets, key=str.casefold)
target_file = task/'targets.txt'
target_file.write_text('\n'.join(targets)+'\n', encoding='utf-8-sig')
pas = r'''unit UnifiedStageAudit;
var targets:TStringList;counts,bad:array[0..8191] of integer;total,exceptions:integer;
function Clean(s:string):string;
begin Result:=StringReplace(s,#9,' ',[rfReplaceAll]);Result:=StringReplace(Result,#13,' ',[rfReplaceAll]);Result:=StringReplace(Result,#10,' ',[rfReplaceAll]);end;
function CheckTree(e:IInterface;fn,rec:string):integer;
var i:integer;s:string;
begin
 Result:=0;s:=Check(e);
 if s<>'' then begin Result:=1;AddMessage('UNIFIED_DETAIL'+#9+fn+#9+rec+#9+Clean(Path(e))+#9+Clean(s));end;
 for i:=0 to ElementCount(e)-1 do Result:=Result+CheckTree(ElementByIndex(e,i),fn,rec);
end;
function Initialize:integer;
var i:integer;f:IInterface;
begin
 targets:=TStringList.Create;targets.LoadFromFile('TARGETFILE');targets.CaseSensitive:=False;targets.Sorted:=True;
 for i:=0 to 8191 do begin counts[i]:=0;bad[i]:=0;end;
 total:=0;exceptions:=0;AddMessage('UNIFIED_BEGIN'+#9+IntToStr(FileCount));
 for i:=0 to FileCount-1 do begin f:=FileByIndex(i);AddMessage('UNIFIED_LOADED'+#9+GetFileName(f));end;
 Result:=0;
end;
function Process(e:IInterface):integer;
var fn:string;idx,n:integer;
begin
 Result:=0;total:=total+1;fn:=GetFileName(GetFile(e));idx:=targets.IndexOf(fn);if idx<0 then Exit;
 counts[idx]:=counts[idx]+1;
 try n:=CheckTree(e,fn,Clean(Name(e)));if n>0 then bad[idx]:=bad[idx]+1;
 except exceptions:=exceptions+1;AddMessage('UNIFIED_EXCEPTION'+#9+fn+#9+Clean(Name(e)));end;
end;
function Finalize:integer;
var i:integer;
begin
 for i:=0 to targets.Count-1 do AddMessage('UNIFIED_PLUGIN'+#9+targets[i]+#9+IntToStr(counts[i])+#9+IntToStr(bad[i]));
 AddMessage('UNIFIED_COMPLETE'+#9+IntToStr(total)+#9+IntToStr(exceptions));targets.Free;Result:=0;
end;
end.
'''.replace('TARGETFILE', str(target_file))
pas = pas.replace('unit UnifiedStageAudit;', 'unit UnifiedStageAudit_'+task_name+';')
script = TARGET/'tools/xedit/Edit Scripts'/('UnifiedStageAudit_'+task_name+'.pas')
script.write_text(pas, encoding='utf-8')
exe = TARGET/'tools/xedit/SSEEdit64.exe'
arguments = [str(exe), '-SSE', '-nobuildrefs', '-nofixup', '-forcebsa', '-autoload', '-autoexit',
             f'-script:{script}', f'-D:{TARGET/"Game/Data"}\\', f'-P:{PROFILE/"plugins.txt"}',
             f'-I:{PROFILE/"Skyrim.ini"}', f'-CustomIni:{PROFILE/"SkyrimCustom.ini"}',
             f'-C:{task/"cache"}\\', f'-T:{task/"tmp"}\\', f'-G:{task/"tmp"}\\',
             f'-B:{task/"tmp"}\\', f'-R:{task/"logs/xedit.log"}']
before = inventory()
assert not before['missing_plugins'] and not before['missing_masters'] and not before['non_x64_runtime_dlls']
(task/'input_inventory.json').write_text(json.dumps(before, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(task/'xedit_command.json').write_text(json.dumps(arguments, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
(task/'prepared.json').write_text(json.dumps({'utc': utc(), 'targets': targets,
    'script_sha256': hashlib.sha256(script.read_bytes()).hexdigest(), 'full_active_context': len(before['plugins'])}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'targets': len(targets), 'active_plugins': len(before['plugins']), 'task': str(task)}, indent=2))
