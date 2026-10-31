"""Read-only comparison of original profiles for the integration base decision."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import struct

ROOT = Path(r'E:\stock\Skyrim collection')
OUT = Path(__file__).resolve().parent
DB = ROOT / 'Database/baseline/skyrim_research.sqlite'


def rows(c, sql, args=()):
    cursor = c.execute(sql, args)
    return [dict(zip([x[0] for x in cursor.description], r)) for r in cursor]


def fingerprint(path):
    p = Path(path)
    data = p.read_bytes()
    return {'path': str(p), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def main():
    c = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True)
    packs = rows(c, 'select * from packs order by id')
    all_profiles = rows(c, 'select * from profiles order by id')
    selected_profiles = {p['pack_id']: p for p in all_profiles if p['is_selected']}
    mods = rows(c, '''select m.*,pm.enabled,pm.list_order from mods m
        join profile_mods pm on pm.mod_id=m.id
        join profiles r on r.id=pm.profile_id and r.is_selected=1
        order by m.pack_id,pm.list_order''')
    plugins = rows(c, '''select r.pack_id,s.*,f.sha256,f.is_light,f.is_master,
        f.header_version,m.name mod_name,m.path mod_path,f.relative_path,
        f.id plugin_id from selected_plugin_resolution s
        join profiles r on r.id=s.profile_id and r.is_selected=1
        left join plugin_files f on f.id=s.winning_plugin_id
        left join mods m on m.id=s.winning_mod_id order by r.pack_id,s.list_order''')
    by_pack = {p['name']: {r['plugin_key']: r for r in plugins if r['pack_id']==p['id']} for p in packs}
    counts = []
    profile_evidence = []
    for pack in packs:
        profile = selected_profiles[pack['id']]
        for name in ('modlist.txt', 'plugins.txt', 'loadorder.txt', 'Skyrim.ini', 'SkyrimPrefs.ini', 'SkyrimCustom.ini', 'settings.ini', 'initweaks.ini'):
            path = Path(profile['modlist_path']).parent / name
            if path.exists():
                profile_evidence.append(fingerprint(path))
        pm = [m for m in mods if m['pack_id']==pack['id']]
        pp = list(by_pack[pack['name']].values())
        direct_mods = Path(profile['modlist_path']).read_text(encoding='utf-8-sig').splitlines()
        direct_plugins = Path(profile['plugins_path']).read_text(encoding='utf-8-sig').splitlines()
        counts.append({
            'pack': pack['name'], 'profile': profile['name'],
            'all_mod_folders': c.execute('select count(*) from mods where pack_id=?', (pack['id'],)).fetchone()[0],
            'enabled_profile_mods_database': sum(m['enabled']==1 for m in pm),
            'enabled_profile_mods_live_modlist': sum(s.startswith('+') for s in direct_mods),
            'enabled_profile_nonseparator_mods_live_modlist': sum(s.startswith('+') and not s[1:].endswith('_separator') for s in direct_mods),
            'enabled_separator_rows_live_modlist': [s[1:] for s in direct_mods if s.startswith('+') and s[1:].endswith('_separator')],
            'enabled_explicit_plugins_database': c.execute('select count(*) from profile_plugins where profile_id=? and enabled=1', (profile['id'],)).fetchone()[0],
            'enabled_explicit_plugins_live_plugins_txt': sum(s.startswith('*') for s in direct_plugins),
            'resolved_rows': len(pp),
            'mod_provider_full': sum(p['is_light']==0 for p in pp if p['plugin_id'] is not None),
            'mod_provider_light': sum(p['is_light']==1 for p in pp if p['plugin_id'] is not None),
            'non_mod_or_unresolved_rows': [p['plugin_name'] for p in pp if p['plugin_id'] is None],
            'resolved_rows_treat_unknown_as_full': sum(not p['is_light'] for p in pp),
            'count_note': 'Resolved mod-plugin counts exclude five standard masters and any implicit CCC/master closure additions. They are not the final full load-order counts.',
        })
    pairs = []
    for a,b in [('Anno','Burida'),('Anno','TuLED'),('Burida','TuLED')]:
        common = set(by_pack[a]) & set(by_pack[b])
        complete = [k for k in common if by_pack[a][k]['sha256'] and by_pack[b][k]['sha256']]
        different = [k for k in complete if by_pack[a][k]['sha256']!=by_pack[b][k]['sha256']]
        pairs.append({
            'packs': [a,b], 'common_names': len(common), 'common_mod_providers': len(complete),
            'same_plugin_sha256': len(complete)-len(different),
            'different_plugin_sha256': len(different),
            'different_plugins': [{'plugin': by_pack[a][k]['plugin_name'], a: by_pack[a][k], b: by_pack[b][k]} for k in sorted(different)],
        })
    roots_anno = ['Glenmoril.esm','Wyrmstooth.esp','ForgottenCity.esp','MoonAndStar_MAS.esp','[LongShou]WorldInPainting_ZeroHall.esp','[longshou]UF6.esp']
    roots_tuled = ['LegacyoftheDragonborn.esm','LOTD_HUB.esp','Unslaad.esm','Darkend.esp','Darkend Unofficial Quest Addon.esp']

    def quest_delta(base, donor, root_names):
        present = set(by_pack[base])
        base_id = next(p['id'] for p in packs if p['name']==base)
        present |= {r[0] for r in c.execute('select name_key from stock_plugins where pack_id=?', (base_id,))}
        # The five standard masters are intrinsic and may be absent from MO2's plugins.txt.
        present |= {'skyrim.esm','update.esm','dawnguard.esm','hearthfires.esm','dragonborn.esm'}
        required, missing, pending = {},set(),[n.lower() for n in root_names]
        while pending:
            key=pending.pop()
            if key in present or key in required:
                continue
            plugin=by_pack[donor].get(key)
            if not plugin or plugin['plugin_id'] is None:
                missing.add(key)
                continue
            required[key]=plugin
            pending += [r[0] for r in c.execute('select master_key from plugin_masters where plugin_id=?', (plugin['plugin_id'],))]
        return {'base':base,'donor':donor,'roots':root_names,
            'new_full':sum(p['is_light']==0 for p in required.values()),
            'new_light':sum(p['is_light']==1 for p in required.values()),
            'required_new_plugins':list(required.values()),'unresolved_masters':sorted(missing),
            'scope':'Hard-master closure only. Additional compatible quest patches, translations, scripts, assets, entry placement and LOD remain to be validated.'}

    quest_scenarios=[quest_delta('TuLED','Anno',roots_anno),quest_delta('Burida','Anno',roots_anno),quest_delta('Burida','TuLED',roots_tuled)]
    generated_ids=[108,112,1977,2277,3740,3990,3149,3719,3155,3514,4357,4621,4850,5388,5392,5424,5861,5881,6032,6106]
    generated=rows(c, '''select p.name pack,m.id mod_id,m.name,m.path,count(*) file_count,sum(f.size_bytes) logical_bytes
        from mods m join files f on f.mod_id=m.id join packs p on p.id=m.pack_id
        where m.id in ('''+','.join('?'*len(generated_ids))+') group by m.id order by p.id,sum(f.size_bytes) desc',generated_ids)
    exact_mod_pairs=rows(c,'''select p1.name pack_a,p2.name pack_b,count(*) exact_tree_pairs
        from mod_tree_matches z join mods a on a.id=z.mod_a join mods b on b.id=z.mod_b
        join packs p1 on p1.id=a.pack_id join packs p2 on p2.id=b.pack_id group by p1.id,p2.id''')
    union_keys=set().union(*(set(p) for p in by_pack.values()))
    union_full={k for p in by_pack.values() for k,r in p.items() if not r['is_light']}
    tuled_profile=Path(selected_profiles[3]['modlist_path']).parent
    framework={
        'engine':'1.5.97.0 + SKSE 2.0.20 for all three source packs; coherent newer official data masters/archives must use the validated Database consistent stock set.',
        'combat':'Keep TuLED Attack MCO-DXP 1.6.0.6 + SCAR/Stances + Valhalla 1.3.3 + Precision 2.0.4 + OAR 2.3.6. Do not enable Anno BFCO alongside MCO. Preserve only explicitly verified MCO variants of donor animations.',
        'body':'Keep TuLED CBBE 2.0.3/CBBE 3BA 2.48/CBPC 1.6.4 skeleton, physics configuration and built body assets as one coherent set; donor armor must match 3BA or have verified fitting output.',
        'perks_magic':'Keep Ordinator 9.31, Odin 3.1.3, Apocalypse 10.2.1 source lineage and matching compatibility patches. Do not enable Anno Vokrii and its Apocalypse patch in parallel.',
        'renderer':'Keep Community Shader-Jiaye-Exp, source meta d2026.1.21.0; exact build version is not proven by this date-like meta version. Keep matching Slama/LED shader features and PBR source set. Do not overlay Anno CommunityShaders_AIO or another core DLL merely for a later date.',
        'weather':'Keep NAT III Weather 3.1.1.0C-F and NAT.CS III 2.0.0.0. Do not add Obsidian Weathers as a second active weather overhaul.',
        'lighting':'Keep TuLED [LED]True Light + [SLAMA1210] Ambient Templates 2.3 + Window Shadows Ultimate. Burida Lux Via/Lux Orbis and their meshes/patches are not part of the chosen TuLED lighting/location baseline.',
        'start_survival':'Keep AlternatePerspective and iNeed/iNeed Extended lineage. Anno Live Another Life and SunHelm are inactive alternatives; Campfire can be an optional independent addition only with dependency/keyword/script winner checks.',
        'cities':'Keep TuLED RedBag Falkreath/Pinewatch and its existing city/terrain source baseline. Do not import Anno Northern Roads, extensive alternate cities, navmesh and all matching patches as one overwrite block.',
        'adult_framework':'Keep TuLED SexLab 1.63 and exact associated body/skeleton/PapyrusUtil/JContainers lineage. Burida-only gameplay modules must be imported with a complete typed/soft dependency group, architecture fixes and regenerated behavior; preserve tested repairs by exact input hash.',
        'generated':'Keep existing output only as an immutable input/reference where still valid. Synthesis must be rebuilt for final sources; behavior output must reflect added animation definitions. LOD/PBR/body generation is scoped by actual changed inputs. Never stack all three packs generated outputs.'}
    visual_mods=[m for m in mods if m['pack_id']==3 and m['enabled'] and re.search(r'(?i)(Community Shader-Jiaye|slama cs preset|NAT\.CS|NAT III Weather|True Light|Ambient Templates|Window Shadows|Chinese fontconfig|HuaJianCi|Chinese Translation|Chinese Localisation|Dynamic String Distributor|Display Tweaks Config)',m['name'])]
    lotd_headers=[]
    for name in ('Anno','TuLED'):
        plugin=by_pack[name]['legacyofthedragonborn.esm']
        path=Path(plugin['mod_path'])/plugin['relative_path']
        with path.open('rb') as stream:
            header=stream.read(24)
            payload=stream.read(struct.unpack_from('<I',header,4)[0])
        pos=0
        while pos<len(payload):
            tag=payload[pos:pos+4].decode('ascii');size=struct.unpack_from('<H',payload,pos+4)[0]
            value=payload[pos+6:pos+6+size];pos+=6+size
            if tag=='SNAM':
                lotd_headers.append({'pack':name,'source':str(path),'TES4_SNAM':value.rstrip(b'\0').decode('utf-8','replace')})
    report={
        'written_utc':datetime.now(timezone.utc).isoformat(),
        'decision':{'recommended_base':'TuLED','accepted_by_parent':True,'selected_profile':'TuLED',
          'reason':'Most reusable broad content (LOTD/HUB, Unslaad, Darkend) and the lowest explicit mod-provider full-plugin count while sharing most of Burida core; retain one MCO/Ordinator/3BA/OAR baseline.',
          'limits':'This is the content/framework choice, not a claim that source TuLED is clean or runtime tested.'},
        'database':str(DB),'pack_paths':packs,'profile_counts':counts,'profile_evidence':profile_evidence,
        'lotd_actual_version_evidence':{'folder_label':'TuLED source folder is labelled v6.10.0; this is not the observed plugin version.',
          'headers':lotd_headers,'actual_header_version':'v6.7.2',
          'record_comparison_evidence':str(ROOT/'Database/integration/research/plugin_integration/lotd_selected_payload_comparison.json'),
          'comparison_summary':{'records_each':122968,'changed_text_fields':17061,'non_text_or_structure_changes':0}},
        'source_selected_mods':mods,'plugin_comparisons':pairs,'exact_mod_tree_pairs':exact_mod_pairs,
        'naive_union':{'plugin_name_keys':len(union_keys),'keys_full_in_any_source_or_unknown':len(union_full),
          'note':'Includes non-mod/unresolved selected rows; not an exact engine load count. Still establishes that simply enabling every source selection is infeasible without substantive choices/rewrites.'},
        'quest_hard_dependency_scenarios':quest_scenarios,'chosen_framework':framework,
        'tuled_language_display':{
            'profile_path':str(tuled_profile),'game_language':'ENGLISH in both Skyrim.ini and SkyrimCustom.ini',
            'translation_strategy':'Preserve English string resource names with existing Chinese font/Chinese localisation/DSD layers and some source Korean mod translations. There is no basis to promise a fully Chinese UI from sLanguage alone.',
            'mo2_ui_language':'en','profile_local_settings':True,'profile_local_saves':True,
            'resolution':'2560x1440','fullscreen':False,'borderless':True,
            'display_tweaks':{'EnableVSync':False,'EnableTearing':True,'SwapEffect':'flip_discard','FramerateLimit':0,'LoadingScreenFramerateLimit':60},
            'vanilla_features_disabled':['TAA','SAO','SSR','volumetric lighting'],
            'stale_output_path':{'file':str(tuled_profile/'SkyrimCustom.ini'),'key':'Display/sScreenShotBaseName','original':r'D:\Game\Steam\steamapps\common\Skyrim Special Edition\ScreenShot','required_action':'Rewrite only integration copy to a Database output folder.'},
            'source_profile_settings_note':'settings.ini LocalSaves=true overrides the global MO2 profile_local_saves=false default; isolated final profile should retain local saves under Database.'},
        'tuled_visual_and_language_mods':visual_mods,'generated_output_inventory':generated,
        'quest_import_source_mods':[m for m in mods if m['pack_id']==1 and m['enabled'] and re.search(r'(?i)(glenmoril|wyrmstooth|forgotten.?city|moon.?and.?star|画中世界|格伦茉莉|格仑摩利)',m['name'])],
        'existing_validation':{
          'repair_candidates':rows(c,'select * from repair_candidate_validation order by pack,plugin'),
          'source_restorations':rows(c,'select * from upstream_restoration_validation order by pack,plugin'),
          'generated_patch_runs':rows(c,'select * from generated_patch_validation order by run_id')},
        'primary_online_sources':[
          {'url':'https://www.nexusmods.com/skyrimspecialedition/mods/117052','checked':'2026-10-31','finding':'BFCO author explicitly lists Skysa/ABR/MCO as incompatible; MCO animation conversion is distinct from running both behavior frameworks. Current page is newer than installed build, so retain installed evidence.'},
          {'url':'https://www.nexusmods.com/skyrimspecialedition/mods/26176','checked':'2026-10-31','finding':'Vokrii author describes an alternate perk overhaul and specific Odin compatibility patch. The local plugin collision and chosen Ordinator lineage drive the integration decision.'},
          {'url':'https://dyndolod.info/Updating','checked':'2026-10-31','finding':'Generated LOD is a load-order snapshot; regeneration is not automatically required for every unrelated added mod. Review changed records/assets and affected worldspaces.'}],
        'actions_performed':'Only read source files/databases and write this research folder. No game/MO2/GUI launches, no changes to original packs or shared databases.'}
    (OUT/'base_selection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    md=['# 整合基底決策：TuLED','','主代理已採納 TuLED 的選用配置為正式內容與框架基底。此決策不代表原包沒有既存問題，也不代表遊戲內驗證完成。','',
        '| 包 | 全部 mod 資料夾 | 選用啟用 mod | plugins.txt 啟用插件 | 已解析 mod 插件 full / light |',
        '| --- | ---: | ---: | ---: | ---: |']
    for x in counts:
        md.append(f"| {x['pack']} | {x['all_mod_folders']} | {x['enabled_profile_nonseparator_mods_live_modlist']} | {x['enabled_explicit_plugins_live_plugins_txt']} | {x['mod_provider_full']} / {x['mod_provider_light']} |")
    md += ['', '表中 full/light 只計有模組提供者的已解析插件，不含五個基本主檔及隱式 CCC／依賴閉合，不能作最終載入數。原始 modlist/plugins 已重新讀取並保存 SHA；TuLED 的 2,271 個加號列中有兩個 _separator 標題，排除後為 2,269 個真實 mod，與資料庫一致。', '',
        'TuLED 已有 LOTD／LOTD_HUB、Unslaad 3.0.4、Darkend 及任務附加、Inigo／Kaidan／Auri／Xelzaz；Burida 沒有整套 LOTD／Unslaad／Darkend。選 TuLED 可保留其現有展示與收集補丁鏈，並保留更多 full 插件空間。',
        '版本更正：TuLED 的 LOTD 資料夾標籤為 v6.10.0，但 Anno 與 TuLED 的實際 TES4 SNAM 都是 v6.7.2。plugin_integration 對兩檔 122,968 筆記錄逐欄位比較，除 17,061 處文字欄位外無結構或非文字差異。應按實際相同主檔內容配補丁，不能依資料夾名稱判版本。證據：../plugin_integration/lotd_selected_payload_comparison.json；本報告 JSON 另保存原始標頭路徑及 SNAM。',
        'Burida 與 TuLED 共有 720 個能比對提供者的同名插件，其中 685 個 SHA 完全相同，35 個不同。另有 1,850 對完整 mod 樹已證明相同；同名不等於同一版本。具體 35 項與來源路徑在 JSON。',
        '直接聯集有 2,415 個插件名稱，其中 347 個名稱至少一個來源是 full 或無法解析的非 mod row；這不是精確引擎數量，仍足以排除原樣全啟用方案。', '',
        '## 保留與改選', '']
    for k,v in framework.items():
        md.append(f'- **{k}**：{v}')
    md += ['', '## 獨有任務的 full 增量', '',
        'Anno 的 Glenmoril、Wyrmstooth、Forgotten City、Moon and Star、WorldInPainting ZeroHall，對 TuLED／Burida 的硬主檔閉合都是新增 5 full；UF6 是另 1 light 並依賴 ZeroHall。此數字只涵蓋根與硬依賴，還要逐一核對入口、資源、翻譯、相容補丁與 LOD。',
        '反過來以 Burida 為底，新增 TuLED 的 LOTD、LOTD_HUB、Unslaad、Darkend、Darkend Quest Addon 就要 5 full 及 _ResourcePack.esl 的 1 light，另有大量展示補丁及資源鏈；因此 TuLED 更符合最多可驗證內容的目標。',
        'Wyrmstooth PBR 是額外 1 full，Glenmoril Redux 音樂版也是額外 1 full，均非主模組的硬依賴。不能把所有美術與音樂附加算進「5 full」的承諾。',
        '既有 Anno 修復版 UF6 應按其原輸入 SHA 使用；導入不等於原包城市補丁也自動相容。', '',
        '## 語言、INI 與美術', '',
        f'原設定位置：`{tuled_profile}`。Skyrim.ini 和 SkyrimCustom.ini 均使用 `sLanguage=ENGLISH`，MO2 介面為 en；已有中文字型、Chinese Localisation 和 DSD，同時還有來源韓文模組譯文。保留英語 Strings 檔名及現有翻譯層，不將單改 sLanguage 當成完整漢化。',
        '原 profile settings.ini 設定 LocalSaves=true、LocalSettings=true；整合副本應把本地存檔留在 Database 的 profile。原 SkyrimCustom.ini 的截圖路徑仍為 D:\\Game\\Steam，整合副本須改為 Database。',
        'SkyrimPrefs 與啟用的 SSEDisplayTweaks 設定是 2560×1440、無邊框視窗；VSync=false、tearing=true、flip_discard、無前景 FPS 上限，載入畫面 60。原版 TAA／SAO／SSR／體積光開關關閉。這些是原設定事實，並非效能測試。',
        '美術核心：Community Shader-Jiaye-Exp（meta d2026.1.21，不能據此判為官方某穩定版），slama cs preset_20260121_Real（SettingsDefault／Theme／User + Slama pp Real JSON），NAT III Weather 3.1.1C-F + NAT.CS III 2.0，[LED]True Light + Ambient Templates 2.3 + Window Shadows Ultimate。',
        'TuLED 沒有選用 Burida 的 Lux Via／Lux Orbis；導入 Burida 內容時要排除其整套照明 meshes 和補丁覆蓋。', '',
        '## 生成產物的重用邊界', '',
        '| 來源 | mod | 原檔案邏輯大小 GiB |', '| --- | --- | ---: |']
    for x in generated:
        md.append(f"| {x['pack']} | {x['name']} | {x['logical_bytes']/1024**3:.3f} |")
    md += ['', '此表不是重建空間上限。大資源可保持來源重用；整合後的 Synthesis、動畫行為與受改動影響的身形、PBR、LOD 輸出必須逐項產生或核對。不能同時啟用三包的整套生成輸出。TuLED 原 Synthesis 未因 Burida 的重建紀錄而自動得到驗證。', '',
        '作者依據：[BFCO 相容性](https://www.nexusmods.com/skyrimspecialedition/mods/117052)、[Vokrii](https://www.nexusmods.com/skyrimspecialedition/mods/26176)、[DynDOLOD 更新說明](https://dyndolod.info/Updating)。網頁於 2026-10-31 查閱；來源安裝版本仍以本機檔案為準。', '',
        '本研究沒有啟動遊戲、MO2 或 GUI，沒有修改原包或共用資料庫。機器可讀證據與全部來源路徑見 base_selection.json。']
    (OUT/'base_selection.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    c.close()
    print(json.dumps({'decision':report['decision'],'profile_counts':counts,'quest_scenarios':[{'base':x['base'],'donor':x['donor'],'full':x['new_full'],'light':x['new_light'],'missing':x['unresolved_masters']} for x in quest_scenarios],'written':[str(OUT/'base_selection.json'),str(OUT/'base_selection.md')]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
