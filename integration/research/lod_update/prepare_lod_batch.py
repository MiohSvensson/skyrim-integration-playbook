"""Prepare exact private-tool CLI and settings for one parent-controlled batch.

This never launches a program and never changes a profile or original tools.
World selection is prepared in the private preset and must be confirmed in the
supported tool UI. There is no invented unattended world-selection switch.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,TARGET,Mini,final_inputs,runtime_id,owned,sha


def replace_keys(text,section,values):
    lines=text.splitlines();result=[];inside=False;done=set();found=False
    def missing():
        for key,value in values.items():
            if key.lower() not in done:result.append(key+'='+str(value));done.add(key.lower())
    for line in lines:
        match=re.fullmatch(r'\s*\[([^]]+)\]\s*',line)
        if match:
            if inside:missing()
            inside=match.group(1).lower()==section.lower();found=found or inside
        if inside and '=' in line and not line.lstrip().startswith((';','#')):
            key=line.split('=',1)[0].strip()
            desired=next((name for name in values if name.lower()==key.lower()),None)
            if desired is not None:line=key+'='+str(values[desired]);done.add(desired.lower())
        result.append(line)
    if inside:missing()
    if not found:result.append('['+section+']');missing()
    return '\n'.join(result)+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',required=True,choices=['texgen','terrain','dyndolod','occlusion'])
    parser.add_argument('--profile',choices=['Unified Build','Unified Skyrim'],default='Unified Build')
    parser.add_argument('--name',required=True);parser.add_argument('--world',action='append',default=[])
    parser.add_argument('--grass',choices=['off','retained','current'],default='off');parser.add_argument('--grass-evidence')
    args=parser.parse_args();assert re.fullmatch('[A-Za-z0-9_-]+',args.name)
    profile,mods,plugins=final_inputs(args.profile)
    snapshot={name:sha(profile/name) for name in ('plugins.txt','modlist.txt','loadorder.txt','Skyrim.ini','SkyrimPrefs.ini','SkyrimCustom.ini') if (profile/name).exists()}
    directory=owned(OUT/'batches'/args.name);assert not directory.exists(),'Preserve prior batch; choose a new name';directory.mkdir(parents=True)
    world_map={};world_by_identity={}
    def collect(record,raw,reader):
        if record['flags']&0x1000:return
        if record['flags']&0x20:world_by_identity.pop(record['id'],None);return
        if record['flags']&0x4000:return
        data=dict(raw);editor=data.get('EDID',b'').rstrip(b'\0').decode('utf-8','replace')
        if editor:world_by_identity[record['id']]={'editor_id':editor,'origin_id':record['id'],'full_runtime_FormID':f'{runtime_id(record["id"],plugins):08X}',
              'source_plugin':record['plugin'],'DATA':int.from_bytes(data.get('DATA',b'\0'),'little')}
    for row in plugins:Mini(row).read('worlds',collect)
    for world in world_by_identity.values():
        key=world['editor_id'].lower()
        assert key not in world_map,'Duplicate final world EditorID requires review: '+world['editor_id']
        world_map[key]=world
    selected=[]
    for name in args.world:
        assert name.lower() in world_map,f'Unknown world EditorID: {name}'
        selected.append(world_map[name.lower()])
    if args.stage!='texgen':assert selected,'Explicit supported-tool world selection required'
    keys={row['name_key'] for row in plugins}
    if args.stage in ('dyndolod','occlusion'):
        assert {'dyndolod.esm','dyndolod.esp'}<=keys,'Incremental update requires existing private DynDOLOD plugins active; current build profile intentionally omits them'
        full=[row for row in plugins if row['is_master']]
        normal=[row for row in plugins if not row['is_master']]
        assert full[-1]['name_key']=='dyndolod.esm','DynDOLOD.esm must be last among master-type plugins, actual last='+full[-1]['name']
        assert normal[-1]['name_key'] in ('dyndolod.esp','occlusion.esp'),'DynDOLOD.esp must have highest possible regular-plugin priority, actual last='+normal[-1]['name']
        if 'occlusion.esp' in keys:assert normal[-1]['name_key']=='occlusion.esp' and normal[-2]['name_key']=='dyndolod.esp','Occlusion immediately after DynDOLOD.esp'
    if args.stage=='texgen':
        assert not any('texgen output' in name.lower() for name,_ in mods),'Deactivate older installed TexGen output first; preparer never changes profile'
    if args.grass=='current':
        assert args.grass_evidence,'Current grass needs an audited whole-batch evidence report, not just two-cell smoke'
        evidence=json.loads(Path(args.grass_evidence).read_text(encoding='utf-8'))
        assert evidence['status']=='CURRENT_GRASS_BATCH_VERIFIED' and evidence['files_validated']>0
        assert {world['editor_id'].lower() for world in selected}<={name.lower() for name in evidence['worlds']}
        assert evidence['profile_plugins_sha256']==sha(profile/'plugins.txt')
    if args.grass=='retained':
        assert all(world['origin_id'].startswith('skyrim.esm|') for world in selected),'Retained old cache cannot cover new worlds'
    runtime=owned(directory/'runtime');runtime.mkdir();ini=owned(runtime/'ini');ini.mkdir()
    for name in ('Skyrim.ini','SkyrimPrefs.ini','SkyrimCustom.ini'):
        source=profile/name
        if source.exists():shutil.copyfile(source,ini/name)
    shutil.copyfile(profile/'plugins.txt',runtime/'plugins.txt')
    output=owned(directory/'output');output.mkdir()
    for name in ('temp','cache','backups','logs'):owned(directory/name).mkdir()
    tool_name='xLODGen' if args.stage=='terrain' else 'DynDOLOD'
    shared_tool=(OUT/'tools'/tool_name).resolve();tool_root=owned(directory/'tool'/tool_name)
    staged=json.loads((OUT/'tool_staging_manifest.json').read_text(encoding='utf-8'))
    staged_rows=staged['tools'][tool_name]['files']
    required=sum(row['bytes'] for row in staged_rows)
    assert shutil.disk_usage(OUT).free>=32*1024**3+required+128*1024**2,'Insufficient space for isolated tool copy and reserve'
    tool_files=[]
    for row in staged_rows:
        source=Path(row['target']).resolve(strict=True)
        assert source.is_relative_to(shared_tool) and source.is_file() and source.stat().st_nlink==1
        assert not source.stat().st_file_attributes&0x400 and source.stat().st_size==row['bytes']
        assert sha(source)==row['target_sha256'],'Staged tool drift: '+str(source)
        relative=Path(row['relative']);assert not relative.is_absolute() and '..' not in relative.parts
        destination=owned(tool_root/relative);destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        assert destination.stat().st_nlink==1 and sha(destination)==row['target_sha256']
        tool_files.append({'relative':relative.as_posix(),'path':str(destination),'sha256':sha(destination),'bytes':destination.stat().st_size})
    program={'texgen':tool_root/'TexGenx64.exe','terrain':tool_root/'xLODGenx64.exe',
             'dyndolod':tool_root/'DynDOLODx64.exe','occlusion':tool_root/'DynDOLODx64.exe'}[args.stage]
    assert program.is_file() and program.stat().st_nlink==1
    argv=[str(program),'-sse','-d:'+str(TARGET/'Game/Data')+'\\','-p:'+str(runtime/'plugins.txt'),
          '-m:'+str(ini)+'\\','-i:'+str(ini/'Skyrim.ini'),'-o:'+str(output)+'\\','-t:'+str(directory/'temp')+'\\',
          '-c:'+str(directory/'cache')+'\\','-b:'+str(directory/'backups')+'\\','-r:'+str(directory/'logs/tool.log')]
    preset_changes=[]
    if args.stage in ('dyndolod','occlusion'):
        preset=tool_root/'Edit Scripts/DynDOLOD/Presets/DynDOLOD_SSE_Default.ini'
        before=preset.read_bytes();text=before.decode('utf-8-sig')
        (directory/'private_preset_before.ini').write_bytes(before)
        values={world['editor_id']:0 for world in world_map.values()}
        # Also clear old world keys which may no longer be in the final world map.
        prior=json.loads((OLD/'scope_inventory.json').read_text(encoding='utf-8'))['planned_materialized_lod_assets_all_providers']
        values.update({name:0 for name in prior})
        values.update({world['editor_id']:1 for world in selected})
        occlusion=args.stage=='occlusion'
        values.update({'OutputPath':str(output)+'\\','DoObjectLOD':int(not occlusion),'DoTreeLOD':int(not occlusion),
          'DoDynamicLOD':int(not occlusion),'DoOcclusion':int(occlusion),'OcclusionPlugin':1,
          'DoTerrainUnderside':int(not occlusion),'DoGrass':int(not occlusion and args.grass!='off'),
          'DoSeasons':0,'GrassLODMode':1,'GrassLODDensity':15})
        text=replace_keys(text,'DynDOLOD',values)
        preset.write_text(text,encoding='utf-8')
        pinned=next(row for row in tool_files if row['path']==str(preset))
        pinned.update(sha256=sha(preset),bytes=preset.stat().st_size)
        preset_changes.append({'path':str(preset),'sha256_before':sha(directory/'private_preset_before.ini'),
          'sha256_after':sha(preset),'before_saved':str(directory/'private_preset_before.ini')})
    assert snapshot=={name:sha(profile/name) for name in snapshot},'Profile changed while preparing batch; use a new refreshed batch'
    result={'status':'PREPARED_NOT_LAUNCHED_GUI_WORLD_OPTIONS_REQUIRE_CONFIRMATION','utc':datetime.now(timezone.utc).isoformat(),
      'name':args.name,'stage':args.stage,'profile':args.profile,'profile_path':str(profile),'profile_sha256':snapshot,
      'plugins':plugins,'selected_worlds':selected,'world_mapping':world_map,'argv':argv,'exe_sha256':sha(program),
      'tool_name':tool_name,'tool_root':str(tool_root),'tool_files':tool_files,
      'runtime_snapshot':{'plugins_sha256':sha(runtime/'plugins.txt'),'ini':{path.name:sha(path) for path in ini.iterdir()}},
      'private_preset_changes':preset_changes,'output':str(output),'grass_mode':args.grass,
      'required_UI_check':['All expected plugin/BSA loaded, Data/INI/output/cache/temp paths correct',
        'Only selected world EditorIDs checked; CLI does not select worlds automatically',
        'TexGen: current retained framework options; output outside MO2/game; no Zip',
        'Terrain: only terrain meshes/textures needed; do not also generate conflicting object/tree output',
        'DynDOLOD: update existing plugins; selected worlds; no seasons unless final framework explicitly changes',
        'Occlusion final: only Occlusion Data + Plugin, other generation options off; after all terrain/object outputs installed'],
      'completion_gate':['Process exit alone is not generation success','Tool log reports every selected world succeeded and no unreviewed errors',
        'Generated plugins fresh xEdit Check, masters/slots and final CELL/WRLD gameplay forwarding audit',
        'Unselected-world assets/records/swap data preserved; current output installed before next incremental batch'],
      'official_evidence':{'paths':'https://dyndolod.info/Help/Command-Line-Argument',
        'cache_backup_log':'https://tes5edit.github.io/docs/2-overview.html#CommandLineSwitches',
        'incremental':'https://dyndolod.info/Updating','world_selection':'https://dyndolod.info/Help/Advanced-Mode',
        'occlusion':'https://dyndolod.info/Help/Occlusion-Data'},
      'root_invocation':['python','Database/integration/run_mo2_child.py','--profile',args.profile,'lod_'+args.name,str(OUT/'lod_tool_child.py'),'--manifest',str(directory/'batch_manifest.json')]}
    (directory/'batch_manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'manifest':str(directory/'batch_manifest.json'),'worlds':[row['editor_id'] for row in selected],'argv':argv},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
