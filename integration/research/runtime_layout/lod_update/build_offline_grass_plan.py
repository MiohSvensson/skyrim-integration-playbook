"""Write an inert source-audited offline grass plan; never generate caches."""
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
DB=OUT.parents[3]


def main():
    inventory=json.loads((OUT/'scope_inventory.json').read_text(encoding='utf-8'))
    package=OUT/'FasterNGIO_1.6'
    manifest=json.loads((package/'manifest.json').read_text())
    worlds=[{'plugin':feature['plugin'],'origin_id':world['id'],'editor_id':world['editor_id'],
             'LAND_records':world['record_counts']['LAND'],'full_runtime_FormID':'Resolve with final xEdit/MO2 load order; do not hardcode source-local master index.'}
      for feature in inventory['features'] for world in feature['worlds']
      if world['own'] and not world['no_grass'] and world['record_counts'].get('LAND',0)>0]
    # UF6 has no LAND and is intentionally absent, even though its NoGrass bit is clear.
    plan={'status':'SOURCE_AUDITED_CLI_HELP_PASS_FINAL_VFS_GENERATION_NOT_RUN',
      'author':'https://github.com/panthuncia/FasterNGIO','version':'1.6','commit':manifest['source_commit'],
      'binary_archive_sha256':manifest['expected_and_observed_binary_archive_sha256'],
      'exe':str(package/'binary/FasterNGIO.exe'),'exe_sha256':'e955a84cc48b1d1448adf92c796da896190e40c6ea1ac46d1b83282d3970331c',
      'help_probe':str(package/'help_probe.json'),'new_grass_worlds':worlds,
      'existing_worlds_needing_review':['Tamriel: changed object collision and 35 authored MoonAndStar LAND records, subject to final winners',
        'WindhelmWorld: parent/child and ForceGrass settings audit; do not assume new source ref requires blanket grass changes'],
      'common_argv':['--data',str(DB/'UnifiedSkyrim/Game/Data'),
        '--plugins',str(DB/'UnifiedSkyrim/profiles/Unified Skyrim/plugins.txt'),
        '--game-ini-dir',str(DB/'UnifiedSkyrim/profiles/Unified Skyrim'),
        '--ngio-config',str(DB/'UnifiedSkyrim/Game/Data/SKSE/Plugins/GrassControl.ini'),
        '--out',str(DB/'workspace/lod_generation/GRASS_FRESH_BATCH/Grass'),
        '--world','FINAL_RUNTIME_FORM_ID_LIST','--placement','vanilla','--reject','cpu',
        '--write-empty-cells','--threads','4','--writers','1'],
      'diagnostic_first':{'world':'0x3C','cell':[-10,-23],
         'args_append':['--cell','-10','-23','--inspect-grass',str(DB/'workspace/lod_generation/grass_probe/placement.csv')],
         'explanation':'Example is a stable Tamriel coordinate around the reviewed Glen door area. Inspect placement first, then a tiny CPU generation probe; verify populated/empty outcome against current LAND/grass lists. It is not proof of all worlds.'},
      'must_do':['Run hidden CLI through the final isolated MO2 VFS; never run with no args or --gui',
        'Use CPU backend: GPU shadercache uses SHGetKnownFolderPath(FOLDERID_LocalAppData); setting LOCALAPPDATA alone does not redirect it',
        'Use a new, empty dedicated output folder outside Game/Data and MO2 mod trees; never pass the old Grass Cache provider as --out',
        'Explicit write-empty-cells is required for an overlay, otherwise omitted empty files expose stale lower-priority old cache',
        'Use explicit final runtime world IDs: --world all honors the old Only-pregenerate list, which omits the added worlds',
        'Record final plugin list/order, all input INI hashes, NGIO configs, generator commit and source resource winners',
        'Retain per-world logs; investigate missing models, archive failures, unsupported geometry, no LAND, no grass types and dropped cells',
        'Parse all generated CGID with verify_cgid.py; verify expected world/cell coverage, source model availability and relevant placement CSV counts',
        'Activate cache overlay only after validation; rebuild selected-world grass LOD using the same current cache and matched billboards',
        'Do not launch the game. No claim of in-game placement/rendering verification is possible in this task'],
      'known_source_limits':['1.6 filters WRLD NoGrass flags but does not read GrassCacheHelperNG.ini ForceGrassWorlds; TuLED forces WhiterunWorld grass at runtime. Keep its old cache and do not blindly regenerate or clear that world.',
        'Default placement=smooth changes placements; use vanilla to follow the retained framework intent.',
        'The source reader and offline collision model are static; runtime script/BOS-driven swaps or later quest states require separate consideration. No runtime equivalence is claimed.',
        'No game/GUI was started; only --help has been executed by this research agent. Source/API review is not an end-to-end generation pass.'],
      'source_line_evidence':[
        {'path':'apps/FasterNGIO/Main.cpp','lines':[26,40],'fact':'Nonempty CLI args avoid launcher; help returns before generation'},
        {'path':'src/Platform/FileSystem.cpp','lines':[20,23,78,110],'fact':'Windows settings/cache resolve a Known Folder, not environment variable alone'},
        {'path':'apps/FasterNGIO/WorldSetup.cpp','lines':[195,210],'fact':'GPU constructor supplies per-user shader cache; CPU avoids this constructor'},
        {'path':'apps/FasterNGIO/Generate.cpp','lines':[398,457],'fact':'NoGrass filtering, all-world only/skip lists and explicit selection branch'},
        {'path':'apps/FasterNGIO/Generate.cpp','lines':[178,237,565,576],'fact':'Removals/empty replacements operate on outputDirectory; use fresh output'},
        {'path':'src/Grass/NgioCacheWriter.cpp','lines':[30,58],'fact':'Exact little-endian CGID serialization'},
        {'path':'src/Grass/CellCache.cpp','lines':[35,84],'fact':'Nine descriptor words and bladeCount*16*uint16 payload'}],
      'independent_cache_check':str(OUT/'verify_cgid.py'),
      'existing_source_format_samples':{'Tamriel':'3 single-segment caches parsed fully, 44,305 blades; existing_Tamriel_cache_schema_samples.json',
        'Alftand':'3 caches have exactly four identical serialized segments; recorded separately without altering/trimming originals; not treated as a strict new-output pass'}}
    (OUT/'offline_grass_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Pinned offline generation candidate:',len(worlds),'new non-NoGrass worlds with LAND; no generation started')


if __name__=='__main__':main()
