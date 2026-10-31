"""Emit an inert plan, never run a generator or alter the final profile."""
import hashlib
import json
import shutil
from pathlib import Path

OUT = Path(__file__).resolve().parent
DB = OUT.parents[3]
ROOT = DB.parent
GIB = 1024**3


def total(summary):
    return sum(item['logical_bytes'] for kinds in summary.values() for item in kinds.values())


def main():
    inventory = json.loads((OUT / 'scope_inventory.json').read_text(encoding='utf-8'))
    own_worlds = []
    for feature in inventory['features']:
        summary = {}
        for provider in feature['provider_assets']:
            for location in ('loose', 'BSA'):
                for world, assets in provider[location].items():
                    summary.setdefault(world, {}).update(assets)
        for world in feature['worlds']:
            if not world['own']:
                continue
            assets = summary.get(world['editor_id'].lower(), {})
            own_worlds.append({**world, 'plugin': feature['plugin'], 'author_assets': assets,
                'LODSettings_present': 'lodsettings' in assets,
                'grass_cache_found': 'grass_cache' in inventory['planned_materialized_lod_assets_all_providers'].get(world['editor_id'].lower(), {}),
                'plan': 'Bounded world batch: current object/tree/dynamic generation; author terrain mesh conditional reuse; current terrain texture regeneration as needed.'
                    if 'lodsettings' in assets else 'No automatic LOD generation: author has no LODSettings; retain intended small/no-landscape setup unless a separate evidence-backed need is established.'})
    profile = DB / 'UnifiedSkyrim/profiles/Unified Skyrim'
    free = shutil.disk_usage(DB).free
    stages = [
        {'name': 'private_tools_and_metadata', 'cap_bytes': GIB, 'preserve_original': True},
        {'name': 'new_TexGen_output', 'cap_bytes': 3*GIB, 'preserve_original': True},
        {'name': 'new_terrain_output', 'cap_bytes': 8*GIB, 'preserve_original': True},
        {'name': 'Tamriel_object_tree_dynamic_update', 'cap_bytes': 18*GIB, 'preserve_original': True},
        {'name': 'new_world_object_tree_dynamic_updates', 'cap_bytes': 10*GIB, 'preserve_original': True},
        {'name': 'temporary_exports_cache_and_plugin_journal', 'cap_bytes': 5*GIB, 'preserve_original': True},
        {'name': 'optional_offline_current_grass_cache_overlay', 'cap_bytes': 6*GIB, 'preserve_original': True},
    ]
    plan = {'status': 'INERT_PLAN_NO_TOOL_LAUNCHED_NO_OUTPUT_CREATED',
      'scope_inventory_sha256': hashlib.sha256((OUT/'scope_inventory.json').read_bytes()).hexdigest(),
      'profile_snapshot': {name: hashlib.sha256((profile/name).read_bytes()).hexdigest() for name in ('plugins.txt','modlist.txt','loadorder.txt')},
      'new_worlds': own_worlds,
      'existing_world_update_candidates': [
        {'world':'Tamriel','object_tree_dynamic':'Required by added/altered exterior objects, final winning references and source models; preserve city/world framework inputs, regenerate output.',
         'terrain':'Glen/FC have no LAND changes. MoonAndStar carries 35 Tamriel LAND changes: recompute final winning height/texture/water input, regenerate affected terrain or deliberately forward chosen baseline before reuse.',
         'grass':'Existing TuLED cache retained as historical source. New collision placements/35 LAND cells prevent claiming globally current cache. Pinned FasterNGIO1.6 CPU CLI is a no-game generation candidate; full final-VFS probe/validation still required.'},
        {'world':'WindhelmWorld','condition':'MoonAndStar_MAS.esp enabled','source_changes':'1 CELL, 1 REFR; child world uses parent LOD. Include in final child/parent copy and parent Tamriel object audit.'}],
      'no_new_external_worlds':['ForgottenCity.esp','[LongShou]WorldInPainting_ZeroHall.esp','MoonAndStar_MAS.esp'],
      'conditional_author_terrain_mesh_reuse': ['Same world editor ID and LODSettings bounds/levels',
        'Final winning LAND height/normal topology unchanged at all contributing cells',
        'Final CELL/WRLD water levels and no-landscape/water flags unchanged',
        'No selected world/terrain overhaul changes this world geometry; otherwise xLODGen terrain first'],
      'conditional_author_terrain_texture_reuse':['Final LAND layers/vertex colors/normals unchanged',
        'Final LTEX/TXST records and referenced full diffuse/normal files equal author-generation inputs',
        'Otherwise regenerate textures using current final visual framework; existing author textures are only an authored fallback, not proven exact current match'],
      'reuse_unaffected_TuLED_output':['Keep source files/hardlinks unchanged; new generated paths overlay only in dedicated output mods',
        'Unselected world assets and generated records must remain semantically identical before/after each batch',
        'Maintain same generation settings/rules/resources for retained worlds; mesh/texture changes affecting those worlds trigger additional updates'],
      'generation_order':['Freeze final active sources, load order and compatibility choices; resolve complete game/INI/VFS inputs',
        'Private tool copy and rebased configs, fresh exports/cache and explicit output/temp paths',
        'xLODGen terrain if required, install resulting private output first',
        'TexGen current inputs, install resulting private output',
        'Update existing private DynDOLOD plugins, highest priority among matching ESM/ESP types; selected affected-world batches with object/tree/dynamic',
        'Current no-game grass route: validate FasterNGIO1.6 CPU CLI on final VFS and fresh output, then selected worlds with explicit write-empty-cells; until validated, new worlds use DoGrass=0',
        'Generate Occlusion after every selected batch has been installed, one final selected-world pass; separate plugin last',
        'Audit CELL/WRLD gameplay fields against pre-generation final winners, allowing only intended generated fields',
        'Full xEdit fresh load/Check, masters/budget and asset-reference validation; keep game unlaunched'],
      'current_tool_versions':{'DynDOLODx64.exe':'3.0.0.197','TexGenx64.exe':'3.0.0.197','xLODGenx64.exe':'4.1.4.0'},
      'private_tool_target': str(DB/'tools/Unified_DynDOLOD_3.0.0.197'),
      'tool_copy_policy': {'copy':['EXE/DLL/helper binaries','Edit Scripts/DynDOLOD immutable render/rules/config resources','desired custom presets after path rebase'],
         'exclude_old_generated':['Edit Scripts/Export','Edit Scripts/DynDOLOD/Cache','Logs','Summary','old *_Output folders'],
         'reason':'Source presets/exports embed C:\\Modding 2 paths; normal fresh export generation is required for changed plugins.'},
      'documented_argv_template': ['-sse','-d:'+str(DB/'UnifiedSkyrim/Game/Data')+'\\',
        '-p:'+str(DB/'workspace/lod_generation/runtime/plugins.txt'),
        '-m:'+str(DB/'workspace/lod_generation/runtime/ini')+'\\',
        '-t:'+str(DB/'workspace/lod_generation/temp')+'\\',
        '-o:'+str(DB/'workspace/lod_generation/STAGE_OUTPUT')+'\\'],
      'argv_notes':['Primary-author documentation supports only the listed path switches here; no invented worldspace CLI selectors.',
        'Run through isolated MO2 VFS and verify loaded plugin/BSA/game/INI/output paths in the actual log.',
        'Runtime plugins/INI snapshots must represent the game-used final settings, not an arbitrary stale MO2 profile; record matching source hashes.',
        'Select worlds in supported tool UI/private preset, validate eligibility and world list; do not launch GUI from this research agent.'],
      'existing_output_units': inventory['existing_generated_output_units'],
      'author_LOD_assets_logical_bytes': {feature['plugin']: sum(total(provider['loose'])+total(provider['BSA']) for provider in feature['provider_assets']) for feature in inventory['features']},
      'budget': {'free_bytes_at_plan':free,'reserve_bytes':32*GIB,'usable_above_reserve':free-32*GIB,'operational_caps_not_prediction': stages,
        'caps_total_bytes':sum(stage['cap_bytes'] for stage in stages),
        'margin_above_reserve_after_all_caps_bytes':free-32*GIB-sum(stage['cap_bytes'] for stage in stages),
        'notes':['Caps are operational stop limits, not a promised output bound. Real size depends on assets/rules/grass density and errors.',
          'Sequential selected-world generation prevents parallel peak growth. Recheck free space before each batch and monitor long-running writers.',
          'Do not zip output during generation: avoids simultaneous archive plus loose-output peak.',
          'Install output by same-volume move into a dedicated new mod after validation; never copy over source hardlinks.',
          'Keep every prior original/evidence file. Failed new output must never be enabled.']},
      'offline_grass_candidate':'offline_grass_plan.json; official 1.6 source/archive pinned, --help tested, no generation run by this research agent',
      'important_limits':['Current inventory is read-only source scope, not the final effective winner proof. Re-audit after parent materializes every quest/patch.',
        'Old TuLED grass cache cannot be claimed fully current after changed terrain/objects. Offline FasterNGIO candidate must pass final VFS, setting, diagnostics and output checks before enabling new cache/grass LOD.',
        'Source/author LOD presence is not proof that its textures/trees match the combined load order.',
        'This task did not execute xLODGen, TexGen, DynDOLOD, MO2, xEdit GUI or the game.']}
    (OUT/'generation_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Eligible authored new worlds:',sum(row['LODSettings_present'] for row in own_worlds),'of',len(own_worlds),'; budget caps',sum(stage['cap_bytes'] for stage in stages)//GIB,'GiB')


if __name__=='__main__':
    main()
