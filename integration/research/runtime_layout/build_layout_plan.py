"""Produce source mappings and budgets only; no actual source asset links/copies."""
import collections
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
DB = OUT.parents[2]
BULK = {'.bsa','.dds','.nif','.hkx','.tri','.fuz','.wav','.xwm','.osd','.bto','.btr','.bik','.lip','.cgid',
        '.pdb','.psd','.png','.jpg','.jpeg','.tga','.xcf','.bmp','.mp4','.mp3','.ogg','.7z','.zip','.rar',
        '.swf','.ttf','.otf'}
COPY = 'private_copy'
SHARE = 'shared_read_only_hardlink'


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def action(key, extension):
    key = key.replace('\\','/').lower()
    if key.startswith('root/'):
        return COPY
    return SHARE if extension.lower() in BULK else COPY


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    c = sqlite3.connect((DB/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    c.row_factory = sqlite3.Row
    c.execute('pragma temp_store=memory')
    c.execute('create temp table active(mod_id integer primary key,pack text,name text,ord integer,path text)')
    c.execute('''insert or ignore into active select m.id,p.name,m.name,pm.list_order,m.path from mods m
        join packs p on p.id=m.pack_id join profile_mods pm on pm.mod_id=m.id join profiles r on r.id=pm.profile_id
        where r.is_selected=1 and pm.enabled=1''')
    budgets = collections.defaultdict(lambda: collections.defaultdict(int))
    shape = collections.defaultdict(lambda: {'files':0,'bytes':0})
    for row in c.execute('select a.pack,f.path_key,f.extension,f.size_bytes from active a join files f on f.mod_id=a.mod_id'):
        mode = action(row['path_key'],row['extension'] or '')
        budgets[row['pack']][mode+'_files'] += 1
        budgets[row['pack']][mode+'_bytes'] += row['size_bytes']
        if row['path_key'].lower().startswith('calientetools/bodyslide/shapedata/') and mode == SHARE:
            shape[row['pack']]['files'] += 1
            shape[row['pack']]['bytes'] += row['size_bytes']

    pack = dict(c.execute("select * from packs where name='TuLED'").fetchone())
    root_rows = []
    providers = collections.defaultdict(list)
    for row in c.execute('''select a.mod_id,a.name,a.ord,a.path,f.relative_path,f.path_key,f.size_bytes
        from active a join files f on f.mod_id=a.mod_id
        where a.pack='TuLED' and f.path_key like 'root/%' order by a.ord desc,f.path_key'''):
        row = dict(row)
        rel = row['relative_path'].replace('\\','/').split('/',1)[1]
        row['source'] = str(Path(row['path']) / row['relative_path'])
        row['destination_relative'] = rel
        row['sha256'] = sha(row['source'])
        row['storage'] = COPY
        row['original_modlist_order'] = row.pop('ord')
        if row['name'].lower().startswith('creation kit'):
            row['disposition'] = 'tool_payload_only_exclude_from_game_root'
            row['reason'] = 'Creation Kit proxy/tbb dependencies must not override Engine Fixes runtime files.'
        elif Path(rel).suffix.lower() == '.log':
            row['disposition'] = 'historical_log_not_runtime_input'
            row['reason'] = 'Keep source evidence; new game root produces its own logs.'
        else:
            row['disposition'] = 'game_root_candidate'
            row['reason'] = 'Selected TuLED Root payload; private copy and rebase absolute paths in editable configuration.'
            providers[rel.lower()].append(row)
        root_rows.append(row)
    winners = []
    for key, rows in providers.items():
        winner = min(rows,key=lambda r:r['original_modlist_order'])
        winners.append({'destination_relative': winner['destination_relative'], 'winner': winner,
                        'other_providers': [r for r in rows if r is not winner]})

    official = OUT/'primary_sources/skse64_2_00_20/skse64_2_00_20'
    official_overrides = []
    for name in ('skse64_loader.exe','skse64_1_5_97.dll','skse64_steam_loader.dll'):
        source = official/name
        if not source.is_file():
            raise RuntimeError('Official SKSE comparison package is required for the approved root override')
        prior = next(x for x in winners if x['destination_relative'].lower() == name.lower())
        replacement = {'name':'Official SKSE 2.0.20','source':str(source),
                       'destination_relative':name,'size_bytes':source.stat().st_size,
                       'sha256':sha(source),'storage':COPY,
                       'disposition':'verified_official_runtime_override',
                       'reason':'Same supported 1.5.97 runtime; official package provenance and DLL identity verified. Original source loader remains ledger-only.'}
        prior['other_providers'].append(prior['winner'])
        prior['winner'] = replacement
        official_overrides.append(replacement)

    game_files = []
    game = Path(pack['game_path'])
    consistent = DB/'repairs/consistent_stock/Data'
    for folder, dirs, files in os.walk(game):
        dirs[:] = [d for d in dirs if not (Path(folder)/d).is_symlink()]
        for name in files:
            source = Path(folder)/name
            relative = source.relative_to(game).as_posix()
            chosen = source
            if relative.lower().startswith('data/'):
                counterpart = consistent / Path(relative).relative_to('Data')
                if counterpart.is_file(): chosen = counterpart
                kind = SHARE if chosen.suffix.lower() in BULK else COPY
            else:
                kind = COPY
            item = {'source':str(chosen),'original_source':str(source),'destination_relative':relative,
                    'bytes':chosen.stat().st_size,'storage':kind}
            if kind == COPY: item['sha256'] = sha(chosen)
            game_files.append(item)
    # Include verified consistent-stock files not physically present in old Data.
    known = {r['destination_relative'].lower() for r in game_files}
    for source in consistent.rglob('*'):
        if source.is_file():
            relative = 'Data/'+source.relative_to(consistent).as_posix()
            if relative.lower() in known: continue
            kind = SHARE if source.suffix.lower() in BULK else COPY
            item = {'source':str(source),'destination_relative':relative,'bytes':source.stat().st_size,'storage':kind}
            if kind == COPY: item['sha256'] = sha(source)
            game_files.append(item)

    measurements = json.loads((OUT/'runtime_measurements.json').read_text(encoding='utf-8'))
    tools = [
        {'name':'BodySlide', 'version':'5.7.0.0',
         'source':str(Path(pack['base_path'])/'mods/BodySlide and Outfit Studio/CalienteTools/BodySlide/BodySlide x64.exe'),
         'configuration_changes':{'GameDataPath':'{game}/Data/','GameDataPaths/SkyrimSpecialEdition':'{game}/Data/',
          'OutputDataPath':'{output}/BodySlideFresh/','OutfitStudio/DefaultSkeletonReference':'{game}/Data/meshes/actors/character/character assets female/skeleton_female.nif'},
         'explicit_output_args':['-gbuild','{reviewed_group}','-t','{output}/BodySlideFresh','-p','{chosen_base_preset}','-tri'],
         'writable':['private tool Config.xml','private BuildSelection.xml','private tool logs','{output}/BodySlideFresh'],
         'reuse_condition':'Base preset, body family, armor mesh paths and morph data retained; added outfit needs matching prebuilt NIF/TRI or a targeted reviewed group build. Never launch the source tool with its original Config.xml.'},
        {'name':'Pandora', 'version':'4.0.4.0',
         'source':str(Path(pack['base_path'])/'mods/Pandora Behaviour Engine 4.0.4/Pandora Behaviour Engine+.exe'),
         'explicit_output_args':['--tesv:{game}','-o','{output}/PandoraFresh','--auto_run','--auto_close'],
         'writable':['private Pandora_Engine/ActiveMods.json','private Engine.log','private PreviousOutput.txt','{output}/PandoraFresh'],
         'reuse_condition':'No changes to behavior patches, FNIS animation lists/custom events, paired animations or graph inputs. Pure OAR/DAR replacements alone do not automatically require new registration; verify each added mod.'},
        {'name':'PGPatcher', 'version':'0.9.9.5',
         'source':str(Path(pack['base_path'])/'mods/PGPatcher-0.9.9/PGPatcher/PGPatcher.exe'),
         'configuration_file':'private tool cfg/user.json',
         'configuration_changes':{'params.game.dir':'{game}','params.modmanager.mo2instancedir':'{instance}',
          'params.output.dir':'{output}/PGPatcherFresh','params.output.zip':False},
         'writable':['private tool cfg directory','private tool logs/cache','{output}/PGPatcherFresh'],
         'reuse_condition':'Base generated NIF/PGPatcher.esp winners and their material links retained together. Added or changed meshes/textures require targeted compatibility work or regeneration. Do not combine another pack output wholesale.'},
        {'name':'TexGen/DynDOLOD','version':'3.0.0.197',
         'source':str(Path(r'E:\stock\Skyrim collection\TuLED\Tool\DynDOLOD')),
         'configuration_changes':{'data_arg':'-D:{game}/Data','output_arg':'-o:{output}/LODFresh'},
         'writable':['private tool Edit Scripts/Export','private tool logs/settings','{output}/LODFresh'],
         'reuse_condition':'Keep base worldspace source/asset winners and existing LOD records consistent. Adding new worldspaces can use DynDOLOD update flow, with xEdit conflict review; no unconditional complete rebuild is required merely for every new mod.'},
        {'name':'xLODGen','version':'4.1.4.0',
         'source':str(Path(r'E:\stock\Skyrim collection\TuLED\Tool\xLODGen\xLODGenx64.exe')),
         'configuration_changes':{'data_arg':'-D:{game}/Data','output_arg':'-o:{output}/TerrainFresh'},
         'writable':['private tool logs/settings','{output}/TerrainFresh'],
         'reuse_condition':'Retain terrain for unchanged base worldspaces; generate only changed or additional worldspaces when necessary.'},
    ]
    result = {'utc':datetime.now(timezone.utc).isoformat(),'status':'PLAN_AND_FIXTURE_VERIFIED_NOT_MATERIALIZED',
              'base':'TuLED','storage_rule':{'shared_extensions':sorted(BULK),'all_root_payloads_private':True,
                  'everything_else_private':True,'unknown_extension_default':COPY,
                  'ShapeData':'Read-only .osd/.nif/.tri input exception regardless of path; never run Outfit Studio source editing or BodySlide to source output.'},
              'budget_by_pack':dict(budgets),'shared_shapedata':dict(shape),
              'root_priority_rule':'Original modlist is stored high-to-low; smaller list_order wins. Replay low-to-high, then reviewed explicit runtime overrides.',
              'game_files':game_files,'root_payloads':root_rows,'game_root_winners':winners,
              'recommended_root_overrides':official_overrides,
              'other_pack_injector_policy':'Burida-only dinput8.dll (Ultimate ASI Loader 8.2.0) and S33BUR5CH.asi are not part of the official SKSE 2.0.20 archive, are absent from selected TuLED Root, and must not be imported into the merged game root. Preserve audit metadata only.',
              'overwrite':{'source':str(Path(pack['base_path'])/'overwrite'),'mapping':'Data-relative top priority view; preserve every input file in a dedicated imported-overwrite mod, with private settings/scripts and shared immutable bulk assets. New overwrite starts empty.',
                  'measurement':measurements['packs']['TuLED']['overwrite']},
              'required_layout':['MO2 private application tree without RootBuilder/FOMOD Plus','Game full private root and verified complete Data','instance/mods complete selected-mod view','instance/profiles private INIs/load order/saves','instance/overwrite new empty private directory','tools private executables/configs','outputs private per-tool generation directories','cache/tmp/logs private task directories'],
              'child_environment':{'TEMP':'{cache}/tmp','TMP':'{cache}/tmp','note':'Do not globally change USERPROFILE/APPDATA or machine registry; native known-folder resolution may ignore environment rebasing. Set each tool path explicitly.'},
              'tools':tools,
              'sources':[
                  'https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions',
                  'https://github.com/Monitor221hz/Pandora-Behaviour-Engine-Plus/blob/ffef0811a1b7cff5a156201428a2ebf29f1525c3/README.md',
                  'https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/ca5c2fa30e4ee57793906637b69eba48b4966b85/src/program/BodySlideApp.cpp',
                  'https://github.com/hakasapl/PGPatcher/blob/bf2333af2077384102bd250969ede87eb4c99367/PGPatcher/src/ParallaxGenConfig.cpp',
                  'https://dyndolod.info/Updating'],
              'limitations':['Source hard links are not a sandbox; any shared input a tool may edit must first become an independent file.',
                  'Private file byte totals omit NTFS metadata, runtime-generated output and tools outside selected mods.',
                  'Existing output logical sizes guide budgets but are not proven new-output upper bounds.',
                  'All original packs unchanged, and no application/game/tool GUI launched by this task.']}
    (OUT/'root_payload_mapping.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'budgets':dict(budgets),'shared_shapedata':dict(shape),'TuLED_root_candidates':len(root_rows),'TuLED_root_winners':len(winners),'game_files':len(game_files)},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
