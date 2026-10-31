"""Read-only TuLED source-diagnostic dispositions for the final integration."""
from pathlib import Path
from datetime import datetime, timezone
import collections
import hashlib
import json
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
BASE = Path(r'E:\stock\Skyrim collection\Database')
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE/'rootcause'))
from plugin_binary import read


def js(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def query(c, sql, args=()):
    cursor=c.execute(sql,args)
    return [dict(zip([x[0] for x in cursor.description],r)) for r in cursor]


def main():
    c=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    log=BASE/'repairs/TuLED/sweep-0e0dedd6a3a5/logs/xedit.log'
    text=log.read_text(encoding='utf-8-sig',errors='replace')
    details=[]
    for n,line in enumerate(text.splitlines(),1):
        if line.startswith('SWEEP_DETAIL\t'):
            _,plugin,record,field,message=line.split('\t',4)
            details.append({'plugin':plugin,'record':record,'field_path':field,'message':message,'log_line':n})
    complete=re.findall(r'^SWEEP_COMPLETE\t(\d+)\t(\d+)\t(\d+)',text,re.M)
    assert len(details)==819 and complete and complete[-1][-1]=='0'
    by_plugin=collections.defaultdict(list)
    for item in details:
        by_plugin[item['plugin']].append(item)
    providers=query(c,'''select s.*,m.id mod_id,m.name mod_name,m.path mod_path,
        f.relative_path,f.sha256,f.is_light from selected_plugin_resolution s
        left join mods m on m.id=s.winning_mod_id left join plugin_files f on f.id=s.winning_plugin_id
        where s.profile_id=7 order by s.list_order''')
    provider_by_key={p['plugin_key']:p for p in providers}
    reverse=collections.defaultdict(set)
    for p in providers:
        if p['winning_plugin_id'] is not None:
            masters=[r[0] for r in c.execute('select master_key from plugin_masters where plugin_id=?',(p['winning_plugin_id'],))]
        elif p['stock_path'] and Path(p['stock_path']).exists():
            # Include the original overwrite plugin, which the main plugin_files table does not own.
            masters=[m.lower() for m in read(p['stock_path'])[0]]
        else:
            masters=[]
        for master in masters:
            reverse[master].add(p['plugin_key'])

    def closure(name):
        todo=[name.lower()];seen=set()
        while todo:
            key=todo.pop()
            if key in seen:continue
            seen.add(key);todo.extend(reverse[key])
        return [provider_by_key[k]['plugin_name'] for k in sorted(seen) if k in provider_by_key]

    legal={
        'ErinRace.esm':('KEEP_SUPPORTED_EXTENSION','Installed MuErinRace/RaceMenu ear/tail/horn support intentionally uses HDPT types 35/36/37; retain the source extension values.'),
        'CS Light.esp':('KEEP_SUPPORTED_EXTENSION','Community Shaders extension LIGH flag bit 14 has verified source support; retain it and the matching renderer DLL.'),
        'TL Bulbs ISL.esp':('KEEP_SUPPORTED_EXTENSION','The same verified Community Shaders LIGH bit 14 extension; do not clear it for xEdit.'),
        'DynDOLOD.esm':('KEEP_SUPPORTED_EXTENSION','DynDOLOD underside MSTT flag bit 2 is documented by its author. Rebuild or scope output for the final world sources, preserving the intended flag.'),
    }
    policies={
        'GPPoses.esp':('USE_VERIFIED_OPTIONAL_POSE_REGISTRY','Source rings/spells were removed but legacy QUST/MGEF/FLST references remain. Use the optional direct-Poser-Hotkeys registry, preserving all 1,148 IDLE/317 ANIO records. Rebuild Synthesis without the old output and perform a new full-context check.'),
        'CollyPoser.esp':('USE_VERIFIED_OPTIONAL_POSE_REGISTRY','Use the optional direct-Poser-Hotkeys registry, preserving all 406 IDLE/5 ANIO records and 405 preset events. This does not restore the old rings/spells.'),
        'DBM_HUB_GOAAIO_Patch.esp':('DISABLE_OPTIONAL_PATCH_WITH_DEPENDENT','Wrong armor-version references and a COBJ placed in LVLI are confirmed. Disable only this display/recipe patch and LOTD_TCC_GOAAIO.esp; retain other Hall of Forgotten plugins/assets and the source armors.'),
        'NPC - Sexlab Patch.esp':('DISABLE_OPTIONAL_PATCH','The Cindiri NPC override references missing Missives.esp|000895 as a faction. Do not guess another faction/master index. Disable this optional patch; no original selected hard dependents.'),
        'DaegonReplacerSmaffs.esp':('DISABLE_OPTIONAL_COSMETIC_MOD','Two Actor Effects refer to absent records in the selected Daegon master. Disable mod 4486, including its FaceGen assets; preserve the Daegon base and language layers.'),
        'Ashe_Replacer.esp':('DISABLE_OPTIONAL_COSMETIC_MOD','One custom head-part list contains an absent own record. Disable optional mod 4262 as a whole so its FaceGen/resources also stop winning. Preserve mod 4261, the actual Ashe - Fire and Blood/SMP Hair source.'),
        'Alternate Perspective - Gate to Sovngarde Edition.esp':('DISABLE_OPTIONAL_START_ADDON','Three INFO conditions reference an absent AlternatePerspective quest alias. Disable the voiced-addon layers 6158 and 6159 together, retaining the base AlternatePerspective. Removing only the ESP leaves overriding base AP scripts from mod 6158.'),
        'Synthesis - Patch.esp':('REBUILD_AFTER_INPUT_DECISIONS','Old generated output carries eighteen GP/Colly MGEF diagnostics and OldFire source diagnostics. Do not retain it as patcher input. Regenerate the six pinned patchers after pose/source/repair decisions and validate generated headers and all references.'),
        'SPID Rihad Swordsman Set.esp':('APPLY_VERIFIED_SOURCE_RESTORATION','Restore official Xtudo clothing-compatible Rihad master file 512617 plus all 45 authored meshes, preserving verified higher-priority body/IED/Parallax winners. Whole-plugin native/full checks are already zero.'),
        'FGCEgilRapier.esp':('APPLY_VERIFIED_SOURCE_RESTORATION','Use the 25-record exact five-weapon restoration from official file 531880, preserving original existing records and Smooth Weapon keyword. Whole-plugin native/full checks are already zero.'),
        'VAE2-USSEP.esp':('APPLY_VERIFIED_EXACT_REPAIR','Use the exact EDID/type-proven five-field compaction remap candidate for the matching source SHA; already whole-plugin native/full checked.'),
        'EldenRingSkyRim_OLDFIRE.esp':('KEEP_SOURCE_AND_ADD_BOUNDED_SUPPORT_WITH_OPEN_VISUAL_DEFECTS','Installed plugin is byte-identical to official file 419988; original missing own FX/ARTO records and NULL sounds are upstream defects. The verified 17-record God of War subset restores three missing macros and 97 authored HKX files, but does not repair these fifteen original fields. Do not install the full flawed author library or map B95 to a different record type.'),
        'Inigo.esp':('KEEP_CORE_APPEARANCE_WARNING','The 23 tint warnings affect CameronUnique. Exact prebuilt FaceGeom and FaceTint exist in the selected validated Inigo.bsa. Retain the main follower; do not remove tint indices or regenerate the face blindly. RACE/tint runtime consistency remains untested.'),
        'WZOblivionArtifacts.esp':('KEEP_CONTENT_APPEARANCE_WARNING','Seven tint entries on a source Nord male preset do not match the selected race palette. Preserve the artifact content and source appearance; no semantic tint mapping is proven.'),
        'Apocalypse - Magic of Skyrim.esp':('KEEP_CORE_APPEARANCE_WARNING','Three tint indices on a summoned Dremora do not match the selected race palette. Preserve the chosen Odin/Ordinator/Apocalypse lineage; no arbitrary tint renumbering.'),
        'Female AIO Modding VN.esp':('KEEP_APPEARANCE_RESOURCE_WARNING','One NPC tint layer does not match the selected DarkElf race palette. This is not grounds to disable the central appearance resource pack.'),
        'Replacing Female Resource.esp':('KEEP_APPEARANCE_TEMPLATES_WARNING','Eight appearance-resource NPCs have NULL class fields. Their template/spawn consumers must be examined before assigning classes; keep the broad resource library rather than inventing a class.'),
        'Replacing Female Resource_2.esp':('KEEP_APPEARANCE_TEMPLATES_WARNING','Custom race templates have absent voice types and ten tint mismatches. Do not invent voices/tints or disable the broad appearance library without reviewing its consumers.'),
        'Tullius Hair 3 SMP.esp':('KEEP_HAIR_WITH_SPECIFIC_OPEN_REFERENCE','One extra HDPT reference on Athena is absent. Keep the central hairstyle library; recover the exact missing author part before changing this particular head part.'),
        '[Stella]PussycatSashaFollower.esp':('KEEP_OPTIONAL_FOLLOWER_WITH_OPEN_PRESET_REFERENCES','Six chargen preset references in a custom follower race are absent in the selected ErinRace version. Preserve follower content while recording the mismatch; do not replace core ErinRace to fit one follower. Optional removal would also require rebuilding Synthesis.'),
        'Darkend.esp':('KEEP_MAJOR_QUEST_WITH_OPEN_VISUAL_SCRIPT_REFERENCES','Twenty-six VMAD fields on merged/custom Mihail ghost visual MGEFs reference absent own AA0E/19D5B records. Preserve the quest/world; recover exact source visual records/scripts rather than replacing them with unrelated effects.'),
        'GostedDimensionalRift.esp':('KEEP_MAJOR_WORLD_WITH_OPEN_SCRIPT_REFERENCES','Consistent official stock removes the earlier missing Update bases; three VMAD references to two absent own cells remain. Do not replace them with guessed cells or remove the world.'),
        'LegacyoftheDragonborn.esm':('KEEP_MAJOR_QUEST_WITH_OPEN_ALIAS_NAV_WARNINGS','After stock consistency, two VMAD alias warnings in DBM_AMJournalQST04 and one navmesh door triangle warning remain. Actual Anno/TuLED master content is v6.7.2 and non-text-identical. Preserve the main museum; alias identity/script and geometry-aware navmesh validation are required for a semantic fix.'),
        'LOTD_HUB.esp':('KEEP_HUB_AFTER_COHERENT_STOCK','Its three missing Update base records belong to the proven stock-data revision mismatch and disappear in the consistent-stock sweep. It is not a remaining target in the 819-field snapshot.'),
        "RedBag's Falkreath.esp":('KEEP_CITY_WITH_OPEN_ARENA_QUEST_WARNINGS','An arena dialogue branch has NULL starting topic and two alias warnings. Keep the chosen city/navigation baseline; do not delete its quest/aliases to silence xEdit.'),
        'DBM_RelicNotifications.esp':('KEEP_TCC_WITH_CONFIRMED_SOURCE_SOUND_DIAGNOSTICS','Two alternate SNDR references to LOTD|9D5B81 are absent, plus one Looping schema warning. All six SNDR records are field-identical in Anno and TuLED; switching source packs does not fix it. Disabling the core also affects 42 TCC addons and generated patches, so retain museum/collector functionality while exact upstream recovery remains open.'),
        'DBM_WorldofDucky_Patch.esp':('KEEP_OPTIONAL_MARKER_SPELL_WARNING','The Dae favor spell contains a NULL effect. This may be a marker/placeholder, but intent is unproven. Preserve the display and Ducky content; do not invent an MGEF.'),
        'Full Random NPC Pack.esp':('KEEP_CONTENT_WITH_TWO_TYPED_FIELD_DEFECTS','Two NPC Gift Filter fields contain LVLI rather than FLST. Confirmed type mismatch, no intended FLST proven. Preserve the large NPC pack and flag these exact fields for author/source recovery.'),
        'mihailseawitches.esp':('KEEP_CREATURE_SOURCE_WARNINGS','Thirty-one conditions use NULL race parameters and one visual-script property is missing. Do not remove conditions or pick a race without source semantics.'),
        'Anchor spell for MCO.esp':('KEEP_COMBAT_NULL_SOUND_WARNINGS','Seventeen effects have NULL optional sound slots. Preserve attack behavior/spells; no replacement sound is proven and clearing the effects would change combat.'),
        'Sound Library.esp':('KEEP_LIBRARY_WITH_OPEN_PLACEHOLDER_SCHEMA_WARNINGS','Mixed NULL fields and projectile type warnings in a broad combat FX library require consumer/source review. Preserve library dependencies; do not treat every NULL as missing content.'),
        'TAWOBA_dawn.esp':('KEEP_ARMOR_WITH_OPEN_TEXTURE_SWAPS','Four alternate-texture entries are NULL. Similarity to Kardia does not prove identical meshes/material intent. Keep the armor until exact NIF/texture audit supports a bounded fix.'),
        'TAWOBA_Dawn_Heavy.esp':('KEEP_ARMOR_WITH_OPEN_TEXTURE_SWAPS','The same four alternate-texture diagnostics require its own NIF/material audit; do not apply the Kardia patch by name similarity.'),
        'BGS TuLED Patch.esp':('KEEP_DISABLED_CUSTOM_REFERENCES','Three LOTD safehouse REFR bases are NULL, but all have Initially Disabled flag 0x800 and a shared enable parent. Preserve the custom patch; these are not automatically active broken objects. Parent-trigger semantics remain untested.'),
        "The Adventurer's Guild.esp":('KEEP_DISABLED_SOURCE_REFERENCES','Two NULL-base references have Initially Disabled 0x800, Z=-30000 and opposite enable state relative to Player|000014. Preserve the quest/source markers rather than deleting them to silence xEdit.'),
        'LEDEffect.esp':('KEEP_EFFECT_API_PLACEHOLDERS_UNPROVEN','One empty spell effect and two NULL sound fields may be placeholders; keep source APIs and require consumer evidence before changing them.'),
        'LEDDragonSummon.esp':('KEEP_CONTENT_WITH_OPEN_MISSING_REFERENCES','An outfit references an absent armor and two spells have NULL effects. Intended source records are not recovered; preserve content while disclosing specific limitations.'),
        'Ultra Weapons.esp':('KEEP_WEAPON_WITH_OPEN_VISUAL_REFERENCE','One enchantment hit shader is absent. Recover the exact shader; do not substitute an unrelated EFSH or remove the weapon pack.'),
        'isilNarsil.esp':('KEEP_WEAPON_WITH_OPEN_SCRIPT_REFERENCE','Sting weapon VMAD property references an absent own record. Recover the expected record/script identity before changing enchantment or glow behavior.'),
    }
    # Other source-null/schema/alias cases are kept explicitly, never classified as proven safe.
    retain_unknown={
        '1YsmirArmorSE.esl':'TES4 ONAM references NPC_ while the schema expects a placed/navigation record; verify header regeneration separately, preserve armor IDs.',
        'WildwakerMagic.esl':'A PERK condition uses NULL PERK; source semantics/marker use are not proven.',
        'KittySpellPack02.esl':'Two impact-data material slots are NULL; do not invent material types.',
        'GKBWavesReborn.esp':'Six MSTT bit-2 warnings are in wave source records; DynDOLOD documentation is not proof for this different mod.',
        'Dynamic Things Alternative.esp':'Two FLOR bit-16 warnings need installed DLL/source support verification; preserve source and do not clear all unknown flags.',
        'Odin - Skyrim Magic Overhaul.esp':'One HAZD bit-25 warning needs engine/source interpretation; preserve the chosen magic framework.',
        'ValhallaCombat.esp':'Four GLOB FNAM values are zero; installed DLL may consume them independently, but the exact semantics are not proven by this audit.',
        'Daikatana.esp':'One effect sound slot is NULL; preserve source combat behavior.',
        '018AuriVIGILANTpatch.esp':'One dialogue condition has NULL quest parameter; do not guess the correct quest.',
        'AKSkyrimUnderground_AddOn.esp':'One condition has NULL voice/list parameter; preserve world content and review actual function/source intent.',
        'BPUFXelzazFollower.esp':'One SCEN quest is NULL and one VMAD property is unresolved; preserve follower and review script/scene source.',
        'DU01DagothUrFollower.esp':'One script property refers to an absent quest alias; preserve follower and do not renumber aliases.',
        'Kaidan - Immersive Features.esp':'One script property refers to an absent quest alias; preserve follower and do not renumber aliases.',
        'Soul Resurrection - Injury and Alternative Death System.esp':'One protective-cloak spell has NULL MGEF; restore source semantics before changing death-alternative behavior.',
    }
    for name,cause in retain_unknown.items():
        policies[name]=('KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED',cause)
    plugin_reports=[]
    for name,items in sorted(by_plugin.items()):
        disposition,cause=legal.get(name,policies.get(name,('KEEP_UNCLASSIFIED_DO_NOT_MODIFY','No semantic remedy has been proven; preserve source until reviewed.')))
        provider=provider_by_key.get(name.lower())
        plugin_reports.append({'plugin':name,'historical_fields':len(items),
            'historical_records':len({r['record'] for r in items}),
            'disposition':disposition,'cause_and_action':cause,'selected_provider':provider,
            'direct_original_selected_dependents':[provider_by_key[k]['plugin_name'] for k in sorted(reverse[name.lower()]) if k in provider_by_key],
            'fields':items})
    manifest=js(BASE/'repairs/candidate_manifest.json')['files']
    exact_repairs=[]
    for item in manifest:
        actual=sha(item['candidate'])
        assert actual==item['candidate_sha256']
        exact_repairs.append(item|{'candidate_rehashed_now':actual,'apply_guard':'Apply only when the selected input SHA matches source_sha256; validate again in the final integrated context.'})
    pose=[p for p in js(BASE/'repairs/pose_registry_variant.json') if p['pack']=='TuLED']
    for p in pose:
        assert sha(p['path'])==p['candidate_sha256']
    optional=[
        {'root':'DBM_HUB_GOAAIO_Patch.esp','mode':'disable_only_plugins','disable_mod_ids':[],
         'reason':'Keep Hall of Forgotten and armor content while excluding the broken optional recipe/display and its TCC mapping.'},
        {'root':'NPC - Sexlab Patch.esp','mode':'disable_only_plugins','disable_mod_ids':[5344],
         'reason':'Optional NPC faction patch references absent Missives faction; preserve source appearance/gameplay masters.'},
        {'root':'DaegonReplacerSmaffs.esp','mode':'disable_entire_cosmetic_mod','disable_mod_ids':[4486],
         'reason':'Restore Daegon base NPC and its matching FaceGen assets rather than leaving replacer assets active.'},
        {'root':'Ashe_Replacer.esp','mode':'disable_entire_cosmetic_mod','disable_mod_ids':[4262],
         'reason':'Keep Ashe - Crystal Heart (4261) main follower and source FaceGen; exclude only the extra replacer fix.'},
        {'root':'Alternate Perspective - Gate to Sovngarde Edition.esp','mode':'disable_both_addon_layers','disable_mod_ids':[6158,6159],
         'reason':'Retain base AlternatePerspective startup; remove mismatched voice-addon script overrides as well as both ESP providers.'},
    ]
    for item in optional:
        item['original_selected_hard_closure']=closure(item['root'])
        item['requires_recalculation_against_final_manifest']=True
    sound_sources=[]
    for pack in ('Anno','TuLED'):
        info=c.execute('''select m.path,f.relative_path from selected_plugin_resolution s join profiles r on r.id=s.profile_id
            join packs p on p.id=r.pack_id join mods m on m.id=s.winning_mod_id join plugin_files f on f.id=s.winning_plugin_id
            where r.is_selected=1 and p.name=? and s.plugin_key='dbm_relicnotifications.esp' ''',(pack,)).fetchone()
        path=Path(info[0])/info[1];masters,recs=read(path)
        sounds=[{'fid':f"{r['fid']:08X}",'edid':r['edid'],'fields':[(k,v.hex()) for k,v in r['fields']]} for r in recs if r['sig']=='SNDR']
        sound_sources.append({'pack':pack,'path':str(path),'sha256':sha(path),'masters':masters,'records':len(recs),'sounds':sounds})
    assert sound_sources[0]['sounds']==sound_sources[1]['sounds']
    face_keys=['meshes/actors/character/facegendata/facegeom/inigo.esp/000a7a9b.nif','textures/actors/character/facegendata/facetint/inigo.esp/000a7a9b.dds']
    face_evidence=[]
    for key in face_keys:
        face_evidence+=query(c,'''select a.path archive_path,e.path entry_path,e.sha256,s.selected_mod_enabled
            from bsa_entries e join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=e.archive_id
            where s.pack_id=3 and e.path_key=?''',(key,))
    null_reference_evidence=[]
    for name in ('BGS TuLED Patch.esp',"The Adventurer's Guild.esp"):
        provider=provider_by_key[name.lower()]
        path=Path(provider['mod_path'])/provider['relative_path']
        masters,records=read(path)
        for rec in records:
            fs=dict(rec['fields'])
            if rec['sig']=='REFR' and fs.get('NAME')==b'\0'*4:
                parent=struct.unpack('<II',fs['XESP']) if len(fs.get('XESP',b''))==8 else None
                null_reference_evidence.append({'plugin':name,'source':str(path),'source_sha256':sha(path),
                    'raw_fid':f"{rec['fid']:08X}",'flags':rec['flags'],'initially_disabled':bool(rec['flags']&0x800),
                    'enable_parent_raw_fid':f'{parent[0]:08X}' if parent else None,'enable_parent_flags':parent[1] if parent else None,
                    'position_rotation':list(struct.unpack('<6f',fs['DATA'])) if len(fs.get('DATA',b''))==24 else None,
                    'fields':[(k,v.hex()) for k,v in rec['fields']]})
    pipeline_paths={
        'tuled':BASE.parent/'TuLED/Tool/Synthesis/PipelineSettings.json',
        'burida_original':BASE.parent/'Burida/Synthesis/PipelineSettings.json',
        'validated':BASE/'repairs/Synthesis_GUI_v2/PipelineSettings.json'}
    pipes={k:js(p) for k,p in pipeline_paths.items()}
    def patchers(settings):
        return settings['Profiles'][0]['Groups'][0]['Patchers']
    pinned=[]
    for a,b in zip(patchers(pipes['tuled']),patchers(pipes['validated'])):
        assert (a['RemoteRepoPath'],a['TargetCommit'])==(b['RemoteRepoPath'],b['TargetCommit'])
        pinned.append({k:b[k] for k in ('Nickname','RemoteRepoPath','SelectedProjectSubpath','TargetCommit','MutagenVersionType','ManualMutagenVersion','SynthesisVersionType','ManualSynthesisVersion')})
    tuled_data=pipeline_paths['tuled'].parent/'Data'
    validated_data=pipeline_paths['validated'].parent/'Data'
    setting_files=[]
    for p in tuled_data.rglob('*.json'):
        other=validated_data/p.relative_to(tuled_data)
        assert other.exists() and p.read_bytes()==other.read_bytes()
        setting_files.append({'relative_path':str(p.relative_to(tuled_data)),'sha256':sha(p),'bytes':p.stat().st_size,'matches_validated_burida':True})
    synthesis={
        'source_pipelines':{k:{'path':str(p),'sha256':sha(p)} for k,p in pipeline_paths.items()},
        'source_settings':pipes,'same_six_repositories_commits_and_order':True,
        'pinned_patchers':pinned,'all_11_data_settings_byte_identical':len(setting_files)==11,'data_settings':setting_files,
        'recommended_runtime':str(BASE/'repairs/Synthesis_GUI_v2/Synthesis.exe'),
        'required_transformations':[
            'Use the verified official GUI 0.36.6 build artifacts; compile outside MO2 and execute patchers inside the final MO2 VFS.',
            'Set all six patchers to Commit and AutoUpdateToBranchTip=false; preserve the six exact TargetCommit values and manual dependency versions.',
            'Use normalized relative project paths from the validated pipeline. TuLED original AOSISCSoundPatcher project points into C:/Users/Admin/AppData/Local/Temp.',
            'Set DataPathOverride, WorkingDirectory, generated output, all caches/temp/NuGet/log paths to final Database-owned integration locations.',
            'Preserve IgnoreMissingMods=false, TargetRelease=SkyrimSE, English, Localize=false, original full-plugin style and the existing five group blacklists.',
            'Build the input list from final active plugins; omit old Synthesis generated outputs and output cutoff exclusions as in the proven pipeline; never suppress missing active masters to make the run continue.',
            'TuLED has no Unforgiving Device group. Keep that group disabled unless a complete matching Burida UD dependency stack is intentionally imported, then build/check it separately with its original pinned settings.',
            'Only six listed patchers are active. Other Data settings such as ImmersiveEquipmentMeshGen retain stale output paths but must remain inactive; change paths and audit prerequisites before enabling any extra patcher.',
            'After pose_registry input changes, verify that stale GP/Colly MGEFs are absent rather than reintroduced by old output. Recheck final generated records and Experience GeneratedExperiencePatch.ini sidecar.',
            'Do not reuse old generated FormID-targeted Dynamic String Distributor JSON. Rebuild translations using final plugin identities or isolate only this obsolete generated-output JSON.',
        ],
        'old_generated_translation':{
            'path':str(BASE.parent/'TuLED/File Mod Skyrim SE/mods/SSE-AT Output/SKSE/Plugins/DynamicStringDistributor/Synthesis - Patch.esp/Synthesis - Patch.json'),
            'sha256':'bd24d90c371b81be5705176774b17564240ac201f662ea895a7e8c8ace76d2d6','bytes':804182,
            'scope':'Contains old GP/Colly generated references; do not disable all SSE-AT Output translations.'},
        'known_output_source_diagnostics':{
            'land':'Skyrim.esm|01B539 in TestCWCampSons inherits absent LTEX|000844. Preserve source; an exact proven omission of only this generated debug-cell override would avoid copying the defect, not repair the vanilla source.',
            'oldfire':'SpecialAttackTipsmin1 still references missing own ARTO B95 and a NULL sound. The bounded macro support does not repair this visual source.'}}
    assert len(pinned)==6 and len(setting_files)==11
    actions={'recommended_base':'TuLED','scope':'Planning evidence only; parent applies only to final Database integration copies.',
        'exact_repair_candidates':exact_repairs,'optional_pose_registry_candidates':pose,
        'optional_disable_plan':optional,'disabled_plugin_union':sorted({n for a in optional for n in a['original_selected_hard_closure']}),
        'preserve_major_content':['LegacyoftheDragonborn.esm','LOTD_HUB.esp','Darkend.esp','GostedDimensionalRift.esp','Inigo.esp','WZOblivionArtifacts.esp','Full Random NPC Pack.esp','ErinRace.esm','Apocalypse - Magic of Skyrim.esp'],
        'post_apply_requirements':['Re-resolve all file providers and complete hard master closure after donor additions.','Audit relevant loose config/script soft references, including generated DSD.','Rebuild Synthesis/behavior and affected resource/LOD outputs from final inputs.','Run full xEdit against the final VFS; compare remaining diagnostics by semantic identity, not changing load-order hex prefixes.']}
    report={
        'written_utc':datetime.now(timezone.utc).isoformat(),
        'historical_snapshot':{'log':str(log),'sha256':sha(log),'sweep_complete':list(map(int,complete[-1])),
            'field_diagnostics':819,'plugins_with_diagnostics':len(by_plugin),
            'note':'Historical consistent-stock sweep, not the current final integration status. Later exact repairs/restorations/optional variants are tracked separately; field counts must not be presented as all still unresolved.'},
        'earlier_ledger':{'path':str(BASE/'repairs/diagnostic_ledger.json'),'TuLED_fields':870,'note':'Earlier pre-consistent-stock ledger; its 51 additional fields include resolved stock-version errors and exact repairs.'},
        'per_plugin':plugin_reports,'actions':actions,'synthesis_rebuild':synthesis,
        'supporting_evidence':{
            'inigo_cameron_prebuilt_facegen':face_evidence,
            'null_placed_reference_flags':null_reference_evidence,
            'tcc_sound_records_field_identical_across_sources':True,'tcc_sound_comparison':sound_sources,
            'tcc_original_selected_hard_closure':closure('DBM_RelicNotifications.esp'),
            'existing_main_native_full':str(BASE/'repairs/full_candidate_validation.json'),
            'rihad_egil':str(BASE/'repairs/upstream_full_validation.json'),
            'pose_registry_native':str(BASE/'repairs/native_validation_variants_pose_registry_only.json'),
            'pose_event_closure':str(BASE/'repairs/pose_preset_closure.json'),
            'bounded_oldfire_support':str(BASE/'repairs/oldfire_katana_support/full_validation.json'),
            'oldfire_source_and_script_semantics':str(BASE/'repairs/oldfire_dependency_graph/semantics_verified.json'),
            'known_extension_source_evidence':str(BASE/'rootcause/web_evidence.json'),
            'lotd_actual_master_equivalence':str(BASE/'integration/research/plugin_integration/lotd_selected_payload_comparison.json')},
        'add_best_if_imported':{
            'enabled_in_original_tuled':False,
            'source_sha256':'326d62050ae6ae6c04894a905a2e915f23c7b4323f30d8427fe9adf8fb84ac7d',
            'unresolved_source_merge_metadata':'Anno/Burida historical 172-field cluster includes two NULL Kardia texture swaps and stale generated membership FormLists. Preserve equipment; consumer evidence is not permission to blanket-delete lists.',
            'existing_consumer_graph':str(BASE/'repairs/Burida/consumer_graph.json'),
            'consumer_limit':'Burida full graph found no external consumers of 36 ADD BEST FLSTs. It is not a proof about all final donor scripts or dynamic lookups.',
            'kardia':'Use the Anno base-only Kardia patch only if final winning input matches ADD BEST and valid swaps still match; Burida variant references PGPatcher|0000AA and cannot be blindly transferred to TuLED.',
            'generation_order':'Feed a proven corrected Kardia source into final Parallax/Synthesis generation or rebase any override on the actual generated winning material.',
            'mybuc':'Keep TuLED original overwrite/mybuc.esp as the selected base; it has 7 LVLI and 21 masters, unlike Anno 39 LVLI/69 masters or Burida 15 LVLI/22 masters. Do not merge by filename.'},
        'no_changes':'Only source/database reads and outputs under this research folder; no original/shared DB edits, no GUI/game launch.'}
    (OUT/'base_diagnostics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'recommended_actions.json').write_text(json.dumps(actions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'synthesis_rebuild_plan.json').write_text(json.dumps(synthesis,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    md=['# TuLED 基底診斷的整合處置','','本報告只提出可執行處置，不修改來源。歷史 consistent-stock sweep 有 819 個欄位診斷，56 個插件；早期 ledger 是 870 欄位。後續已驗證修復、來源恢復和可選變體必須分開計入，這些數字不是目前成品的未決總數。','',
        '## 優先處置','','套用精確 SHA 相符的既有主修復、Rihad 衣服前置和 Egil 五武器恢復；主檔與 BSA 使用完整一致的已驗證 stock 資料。採用 GP／Colly 的直接 Poser Hotkeys 登記版可保留全部 IDLE／ANIO／現有預設事件；它不恢復已被剝除的戒指、法術和舊任務，仍須在最終配置完整複查。','',
        '限定 OldFire 支援已原生／完整 MO2 通過 17 筆、101 資源檔與三個缺少巨集，但原太刀插件十五個欄位的視覺／聲音問題仍在上游。保留其原有界線，不能把整個有缺陷的 God of War 原作者庫當作乾淨前置安裝。','',
        '## 小範圍停用計畫','','下列清單只影響可選補丁或外觀／語音附加；最終 donor 加入後須重算 master 傳播，並重新生成輸出。','']
    for item in optional:
        md.append(f"- **{item['root']}**：{item['reason']} 原選用硬依賴閉合：{', '.join(item['original_selected_hard_closure'])}；模組 ID：{item['disable_mod_ids']}。")
    md += ['', '不要整個停用 [LED]Hall of Forgotten，因為同一來源資料夾還有大量有效展示補丁。Ashe 的真正主模組是 4261；4262 只是額外 replacer fix。AP 語音附加有覆蓋基底腳本，必須連同 6158／6159 兩層關閉才是完整回復。','',
        '## 保留的核心與已知來源問題','','INIGO 的 Cameron 預製 FaceGeom／FaceTint 在選中的 Inigo.bsa 皆存在，雜湊已由完整封存驗證；23 個 tint 警告不能作為刪主隨從的理由。這只證明預製資源存在，未證明遊戲內 race／tint 行為。大型外觀庫、Darkend、Dimensional Rift、LOTD 及其城市也保留，缺失別名、視覺腳本或導航資料依原記錄追蹤，不亂補目標或改編號。','',
        'TCC 的兩個替代聲音缺件和一個 Looping 診斷在 Anno／TuLED 的六個 SNDR 內容完全一致，換來源包無效。停用 DBM_RelicNotifications 會影響 42 個 TCC 附加及生成檔，故保留收藏／展示功能，聲音來源另待精確恢復。','',
        '另直接讀取 NULL-base REFR：BGS TuLED Patch 的三筆均 Initially Disabled 0x800 且有共用 enable parent；Adventurer Guild 的兩筆同樣為 0x800、置於 Z=-30000，並與 Player 000014 的 enable state 相反。這些有具體停用／藏匿設定，應保留來源標記，不能僅因 NAME=NULL 便宣稱有五個正在載入的破損物件。BGS parent 切換後的行為仍未經遊戲測試。','',
        '## 逐插件清單','', '| 插件 | 歷史欄位 | 處置 | 原因／範圍 |', '| --- | ---: | --- | --- |']
    for item in plugin_reports:
        md.append(f"| {item['plugin']} | {item['historical_fields']} | {item['disposition']} | {item['cause_and_action'].replace('|',' / ')} |")
    md += ['', '## 合法擴展與未證實值分開','','已證明應保留的擴展：Erin HDPT 35／36／37，Community Shaders LIGH bit 14，DynDOLOD underside MSTT bit 2。GKB Waves 的同樣 bit、Dynamic Things FLOR bit 16、Odin HAZD bit 25、Valhalla GLOB FNAM=0 在本審核沒有同等證據，保留來源並標示未決，不能因數值相似一概宣告合法或清空。','',
        '## ADD BEST 與 mybuc','','原 TuLED 沒有啟用 ADD BEST。若從 Anno／Burida 導入，要按實際贏家選 Kardia 修正。Burida 變體保留 PGPatcher|0000AA，不能盲套到 TuLED；較合理是把正確源資料交給最終 Parallax／Synthesis，再核對材質贏家。舊合併 FLST 有過時成員，現有 Burida 全引用圖不等於最終整合沒有任何腳本／動態消費者，不能為形式清零整批刪除。','',
        '三包 mybuc.esp 不是同一補丁：TuLED 為 7 LVLI／21 masters，Anno 為 39／69，Burida 為 15／22。以 TuLED 覆寫目錄的版本為基底，捐入裝備不能順手覆蓋這個檔名。','',
        '## Synthesis 最終重建','','TuLED 原 Pipeline 的六個 repo、順序和 TargetCommit 與已完成驗證的 Burida 六個完全一致；Data 內 11 份 JSON 逐位元組相同。可使用既有官方 GUI 0.36.6 編譯產物及相同設定，依最終輸入重建，不需追新 branch。','',
        '保留原五項 Blacklist、IgnoreMissingMods=false、English／nonlocalized 和固定依賴版本；所有 patcher 改 Commit 並關自動更新，AOSISCSoundPatcher 改用已驗證相對 project 路徑，所有資料／工作／暫存／輸出位置轉入 Database 最終環境。TuLED 沒有 UD 群；除非完整移入且獨立驗證匹配 UD 堆疊，保持它停用。','',
        '先作 pose／來源／修復取捨，再重建。舊 Synthesis 不能作為生成輸入；否則刪除來源的舊 GP／Colly 魔法記錄可能又被帶回。SSE-AT Output 中針對舊 Synthesis 的 804,182 bytes DSD 翻譯 JSON 含舊生成編號，須重建或只隔離這一檔，保留其他翻譯。','',
        '生成後仍須檢查每個輸出與 Experience sidecar。Skyrim 測試世界 LAND|01B539 的缺 LTEX 是已證明的原版問題；只略過這一份經證明的生成 debug-cell 覆蓋，最多是避免複製問題，不是修好原版。OldFire 視覺缺件另行保持未決。','',
        '詳細候選來源 SHA、輸出 SHA、硬依賴傳播、原始逐欄位證據見 base_diagnostics.json；可讀取 recommended_actions.json 和 synthesis_rebuild_plan.json 執行主代理的整合決策。沒有啟動遊戲／GUI，也沒有修改原件或共用資料庫。']
    (OUT/'base_diagnostics.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    c.close()
    print(json.dumps({'historical_fields':819,'plugins':len(by_plugin),'dispositions':dict(collections.Counter(p['disposition'] for p in plugin_reports)),
        'optional_disable_plugins':actions['disabled_plugin_union'],'exact_repair_candidates':len(exact_repairs),'pose_candidates':len(pose),
        'same_six_patchers':True,'settings_files_identical':len(setting_files),
        'outputs':[str(OUT/n) for n in ['base_diagnostics.json','base_diagnostics.md','recommended_actions.json','synthesis_rebuild_plan.json']]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
