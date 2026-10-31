# TuLED 基底診斷的整合處置

本報告只提出可執行處置，不修改來源。歷史 consistent-stock sweep 有 819 個欄位診斷，56 個插件；早期 ledger 是 870 欄位。後續已驗證修復、來源恢復和可選變體必須分開計入，這些數字不是目前成品的未決總數。

## 優先處置

套用精確 SHA 相符的既有主修復、Rihad 衣服前置和 Egil 五武器恢復；主檔與 BSA 使用完整一致的已驗證 stock 資料。採用 GP／Colly 的直接 Poser Hotkeys 登記版可保留全部 IDLE／ANIO／現有預設事件；它不恢復已被剝除的戒指、法術和舊任務，仍須在最終配置完整複查。

限定 OldFire 支援已原生／完整 MO2 通過 17 筆、101 資源檔與三個缺少巨集，但原太刀插件十五個欄位的視覺／聲音問題仍在上游。保留其原有界線，不能把整個有缺陷的 God of War 原作者庫當作乾淨前置安裝。

## 小範圍停用計畫

下列清單只影響可選補丁或外觀／語音附加；最終 donor 加入後須重算 master 傳播，並重新生成輸出。

- **DBM_HUB_GOAAIO_Patch.esp**：Keep Hall of Forgotten and armor content while excluding the broken optional recipe/display and its TCC mapping. 原選用硬依賴閉合：DBM_HUB_GOAAIO_Patch.esp, LOTD_TCC_GOAAIO.esp；模組 ID：[]。
- **NPC - Sexlab Patch.esp**：Optional NPC faction patch references absent Missives faction; preserve source appearance/gameplay masters. 原選用硬依賴閉合：NPC - Sexlab Patch.esp；模組 ID：[5344]。
- **DaegonReplacerSmaffs.esp**：Restore Daegon base NPC and its matching FaceGen assets rather than leaving replacer assets active. 原選用硬依賴閉合：DaegonReplacerSmaffs.esp；模組 ID：[4486]。
- **Ashe_Replacer.esp**：Keep Ashe - Crystal Heart (4261) main follower and source FaceGen; exclude only the extra replacer fix. 原選用硬依賴閉合：Ashe_Replacer.esp；模組 ID：[4262]。
- **Alternate Perspective - Gate to Sovngarde Edition.esp**：Retain base AlternatePerspective startup; remove mismatched voice-addon script overrides as well as both ESP providers. 原選用硬依賴閉合：Alternate Perspective - Gate to Sovngarde Edition.esp；模組 ID：[6158, 6159]。

不要整個停用 [LED]Hall of Forgotten，因為同一來源資料夾還有大量有效展示補丁。Ashe 的真正主模組是 4261；4262 只是額外 replacer fix。AP 語音附加有覆蓋基底腳本，必須連同 6158／6159 兩層關閉才是完整回復。

## 保留的核心與已知來源問題

INIGO 的 Cameron 預製 FaceGeom／FaceTint 在選中的 Inigo.bsa 皆存在，雜湊已由完整封存驗證；23 個 tint 警告不能作為刪主隨從的理由。這只證明預製資源存在，未證明遊戲內 race／tint 行為。大型外觀庫、Darkend、Dimensional Rift、LOTD 及其城市也保留，缺失別名、視覺腳本或導航資料依原記錄追蹤，不亂補目標或改編號。

TCC 的兩個替代聲音缺件和一個 Looping 診斷在 Anno／TuLED 的六個 SNDR 內容完全一致，換來源包無效。停用 DBM_RelicNotifications 會影響 42 個 TCC 附加及生成檔，故保留收藏／展示功能，聲音來源另待精確恢復。

另直接讀取 NULL-base REFR：BGS TuLED Patch 的三筆均 Initially Disabled 0x800 且有共用 enable parent；Adventurer Guild 的兩筆同樣為 0x800、置於 Z=-30000，並與 Player 000014 的 enable state 相反。這些有具體停用／藏匿設定，應保留來源標記，不能僅因 NAME=NULL 便宣稱有五個正在載入的破損物件。BGS parent 切換後的行為仍未經遊戲測試。

## 逐插件清單

| 插件 | 歷史欄位 | 處置 | 原因／範圍 |
| --- | ---: | --- | --- |
| 018AuriVIGILANTpatch.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One dialogue condition has NULL quest parameter; do not guess the correct quest. |
| 1YsmirArmorSE.esl | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | TES4 ONAM references NPC_ while the schema expects a placed/navigation record; verify header regeneration separately, preserve armor IDs. |
| AKSkyrimUnderground_AddOn.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One condition has NULL voice/list parameter; preserve world content and review actual function/source intent. |
| Alternate Perspective - Gate to Sovngarde Edition.esp | 3 | DISABLE_OPTIONAL_START_ADDON | Three INFO conditions reference an absent AlternatePerspective quest alias. Disable the voiced-addon layers 6158 and 6159 together, retaining the base AlternatePerspective. Removing only the ESP leaves overriding base AP scripts from mod 6158. |
| Anchor spell for MCO.esp | 17 | KEEP_COMBAT_NULL_SOUND_WARNINGS | Seventeen effects have NULL optional sound slots. Preserve attack behavior/spells; no replacement sound is proven and clearing the effects would change combat. |
| Apocalypse - Magic of Skyrim.esp | 3 | KEEP_CORE_APPEARANCE_WARNING | Three tint indices on a summoned Dremora do not match the selected race palette. Preserve the chosen Odin/Ordinator/Apocalypse lineage; no arbitrary tint renumbering. |
| Ashe_Replacer.esp | 1 | DISABLE_OPTIONAL_COSMETIC_MOD | One custom head-part list contains an absent own record. Disable optional mod 4262 as a whole so its FaceGen/resources also stop winning. Preserve mod 4261, the actual Ashe - Fire and Blood/SMP Hair source. |
| BGS TuLED Patch.esp | 3 | KEEP_DISABLED_CUSTOM_REFERENCES | Three LOTD safehouse REFR bases are NULL, but all have Initially Disabled flag 0x800 and a shared enable parent. Preserve the custom patch; these are not automatically active broken objects. Parent-trigger semantics remain untested. |
| BPUFXelzazFollower.esp | 2 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One SCEN quest is NULL and one VMAD property is unresolved; preserve follower and review script/scene source. |
| CS Light.esp | 21 | KEEP_SUPPORTED_EXTENSION | Community Shaders extension LIGH flag bit 14 has verified source support; retain it and the matching renderer DLL. |
| CollyPoser.esp | 35 | USE_VERIFIED_OPTIONAL_POSE_REGISTRY | Use the optional direct-Poser-Hotkeys registry, preserving all 406 IDLE/5 ANIO records and 405 preset events. This does not restore the old rings/spells. |
| DBM_HUB_GOAAIO_Patch.esp | 22 | DISABLE_OPTIONAL_PATCH_WITH_DEPENDENT | Wrong armor-version references and a COBJ placed in LVLI are confirmed. Disable only this display/recipe patch and LOTD_TCC_GOAAIO.esp; retain other Hall of Forgotten plugins/assets and the source armors. |
| DBM_RelicNotifications.esp | 3 | KEEP_TCC_WITH_CONFIRMED_SOURCE_SOUND_DIAGNOSTICS | Two alternate SNDR references to LOTD / 9D5B81 are absent, plus one Looping schema warning. All six SNDR records are field-identical in Anno and TuLED; switching source packs does not fix it. Disabling the core also affects 42 TCC addons and generated patches, so retain museum/collector functionality while exact upstream recovery remains open. |
| DBM_WorldofDucky_Patch.esp | 1 | KEEP_OPTIONAL_MARKER_SPELL_WARNING | The Dae favor spell contains a NULL effect. This may be a marker/placeholder, but intent is unproven. Preserve the display and Ducky content; do not invent an MGEF. |
| DU01DagothUrFollower.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One script property refers to an absent quest alias; preserve follower and do not renumber aliases. |
| DaegonReplacerSmaffs.esp | 2 | DISABLE_OPTIONAL_COSMETIC_MOD | Two Actor Effects refer to absent records in the selected Daegon master. Disable mod 4486, including its FaceGen assets; preserve the Daegon base and language layers. |
| Daikatana.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One effect sound slot is NULL; preserve source combat behavior. |
| Darkend.esp | 26 | KEEP_MAJOR_QUEST_WITH_OPEN_VISUAL_SCRIPT_REFERENCES | Twenty-six VMAD fields on merged/custom Mihail ghost visual MGEFs reference absent own AA0E/19D5B records. Preserve the quest/world; recover exact source visual records/scripts rather than replacing them with unrelated effects. |
| DynDOLOD.esm | 27 | KEEP_SUPPORTED_EXTENSION | DynDOLOD underside MSTT flag bit 2 is documented by its author. Rebuild or scope output for the final world sources, preserving the intended flag. |
| Dynamic Things Alternative.esp | 2 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | Two FLOR bit-16 warnings need installed DLL/source support verification; preserve source and do not clear all unknown flags. |
| EldenRingSkyRim_OLDFIRE.esp | 15 | KEEP_SOURCE_AND_ADD_BOUNDED_SUPPORT_WITH_OPEN_VISUAL_DEFECTS | Installed plugin is byte-identical to official file 419988; original missing own FX/ARTO records and NULL sounds are upstream defects. The verified 17-record God of War subset restores three missing macros and 97 authored HKX files, but does not repair these fifteen original fields. Do not install the full flawed author library or map B95 to a different record type. |
| ErinRace.esm | 43 | KEEP_SUPPORTED_EXTENSION | Installed MuErinRace/RaceMenu ear/tail/horn support intentionally uses HDPT types 35/36/37; retain the source extension values. |
| FGCEgilRapier.esp | 14 | APPLY_VERIFIED_SOURCE_RESTORATION | Use the 25-record exact five-weapon restoration from official file 531880, preserving original existing records and Smooth Weapon keyword. Whole-plugin native/full checks are already zero. |
| Female AIO Modding VN.esp | 1 | KEEP_APPEARANCE_RESOURCE_WARNING | One NPC tint layer does not match the selected DarkElf race palette. This is not grounds to disable the central appearance resource pack. |
| Full Random NPC Pack.esp | 2 | KEEP_CONTENT_WITH_TWO_TYPED_FIELD_DEFECTS | Two NPC Gift Filter fields contain LVLI rather than FLST. Confirmed type mismatch, no intended FLST proven. Preserve the large NPC pack and flag these exact fields for author/source recovery. |
| GKBWavesReborn.esp | 6 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | Six MSTT bit-2 warnings are in wave source records; DynDOLOD documentation is not proof for this different mod. |
| GPPoses.esp | 330 | USE_VERIFIED_OPTIONAL_POSE_REGISTRY | Source rings/spells were removed but legacy QUST/MGEF/FLST references remain. Use the optional direct-Poser-Hotkeys registry, preserving all 1,148 IDLE/317 ANIO records. Rebuild Synthesis without the old output and perform a new full-context check. |
| GostedDimensionalRift.esp | 3 | KEEP_MAJOR_WORLD_WITH_OPEN_SCRIPT_REFERENCES | Consistent official stock removes the earlier missing Update bases; three VMAD references to two absent own cells remain. Do not replace them with guessed cells or remove the world. |
| Inigo.esp | 23 | KEEP_CORE_APPEARANCE_WARNING | The 23 tint warnings affect CameronUnique. Exact prebuilt FaceGeom and FaceTint exist in the selected validated Inigo.bsa. Retain the main follower; do not remove tint indices or regenerate the face blindly. RACE/tint runtime consistency remains untested. |
| Kaidan - Immersive Features.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One script property refers to an absent quest alias; preserve follower and do not renumber aliases. |
| KittySpellPack02.esl | 2 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | Two impact-data material slots are NULL; do not invent material types. |
| LEDDragonSummon.esp | 3 | KEEP_CONTENT_WITH_OPEN_MISSING_REFERENCES | An outfit references an absent armor and two spells have NULL effects. Intended source records are not recovered; preserve content while disclosing specific limitations. |
| LEDEffect.esp | 3 | KEEP_EFFECT_API_PLACEHOLDERS_UNPROVEN | One empty spell effect and two NULL sound fields may be placeholders; keep source APIs and require consumer evidence before changing them. |
| LegacyoftheDragonborn.esm | 3 | KEEP_MAJOR_QUEST_WITH_OPEN_ALIAS_NAV_WARNINGS | After stock consistency, two VMAD alias warnings in DBM_AMJournalQST04 and one navmesh door triangle warning remain. Actual Anno/TuLED master content is v6.7.2 and non-text-identical. Preserve the main museum; alias identity/script and geometry-aware navmesh validation are required for a semantic fix. |
| NPC - Sexlab Patch.esp | 1 | DISABLE_OPTIONAL_PATCH | The Cindiri NPC override references missing Missives.esp / 000895 as a faction. Do not guess another faction/master index. Disable this optional patch; no original selected hard dependents. |
| Odin - Skyrim Magic Overhaul.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One HAZD bit-25 warning needs engine/source interpretation; preserve the chosen magic framework. |
| RedBag's Falkreath.esp | 3 | KEEP_CITY_WITH_OPEN_ARENA_QUEST_WARNINGS | An arena dialogue branch has NULL starting topic and two alias warnings. Keep the chosen city/navigation baseline; do not delete its quest/aliases to silence xEdit. |
| Replacing Female Resource.esp | 8 | KEEP_APPEARANCE_TEMPLATES_WARNING | Eight appearance-resource NPCs have NULL class fields. Their template/spawn consumers must be examined before assigning classes; keep the broad resource library rather than inventing a class. |
| Replacing Female Resource_2.esp | 14 | KEEP_APPEARANCE_TEMPLATES_WARNING | Custom race templates have absent voice types and ten tint mismatches. Do not invent voices/tints or disable the broad appearance library without reviewing its consumers. |
| SPID Rihad Swordsman Set.esp | 15 | APPLY_VERIFIED_SOURCE_RESTORATION | Restore official Xtudo clothing-compatible Rihad master file 512617 plus all 45 authored meshes, preserving verified higher-priority body/IED/Parallax winners. Whole-plugin native/full checks are already zero. |
| Soul Resurrection - Injury and Alternative Death System.esp | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | One protective-cloak spell has NULL MGEF; restore source semantics before changing death-alternative behavior. |
| Sound Library.esp | 8 | KEEP_LIBRARY_WITH_OPEN_PLACEHOLDER_SCHEMA_WARNINGS | Mixed NULL fields and projectile type warnings in a broad combat FX library require consumer/source review. Preserve library dependencies; do not treat every NULL as missing content. |
| Synthesis - Patch.esp | 21 | REBUILD_AFTER_INPUT_DECISIONS | Old generated output carries eighteen GP/Colly MGEF diagnostics and OldFire source diagnostics. Do not retain it as patcher input. Regenerate the six pinned patchers after pose/source/repair decisions and validate generated headers and all references. |
| TAWOBA_Dawn_Heavy.esp | 4 | KEEP_ARMOR_WITH_OPEN_TEXTURE_SWAPS | The same four alternate-texture diagnostics require its own NIF/material audit; do not apply the Kardia patch by name similarity. |
| TAWOBA_dawn.esp | 4 | KEEP_ARMOR_WITH_OPEN_TEXTURE_SWAPS | Four alternate-texture entries are NULL. Similarity to Kardia does not prove identical meshes/material intent. Keep the armor until exact NIF/texture audit supports a bounded fix. |
| TL Bulbs ISL.esp | 57 | KEEP_SUPPORTED_EXTENSION | The same verified Community Shaders LIGH bit 14 extension; do not clear it for xEdit. |
| The Adventurer's Guild.esp | 2 | KEEP_DISABLED_SOURCE_REFERENCES | Two NULL-base references have Initially Disabled 0x800, Z=-30000 and opposite enable state relative to Player / 000014. Preserve the quest/source markers rather than deleting them to silence xEdit. |
| Tullius Hair 3 SMP.esp | 1 | KEEP_HAIR_WITH_SPECIFIC_OPEN_REFERENCE | One extra HDPT reference on Athena is absent. Keep the central hairstyle library; recover the exact missing author part before changing this particular head part. |
| Ultra Weapons.esp | 1 | KEEP_WEAPON_WITH_OPEN_VISUAL_REFERENCE | One enchantment hit shader is absent. Recover the exact shader; do not substitute an unrelated EFSH or remove the weapon pack. |
| VAE2-USSEP.esp | 5 | APPLY_VERIFIED_EXACT_REPAIR | Use the exact EDID/type-proven five-field compaction remap candidate for the matching source SHA; already whole-plugin native/full checked. |
| ValhallaCombat.esp | 4 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | Four GLOB FNAM values are zero; installed DLL may consume them independently, but the exact semantics are not proven by this audit. |
| WZOblivionArtifacts.esp | 7 | KEEP_CONTENT_APPEARANCE_WARNING | Seven tint entries on a source Nord male preset do not match the selected race palette. Preserve the artifact content and source appearance; no semantic tint mapping is proven. |
| WildwakerMagic.esl | 1 | KEEP_SOURCE_DIAGNOSTIC_UNRESOLVED | A PERK condition uses NULL PERK; source semantics/marker use are not proven. |
| [Stella]PussycatSashaFollower.esp | 6 | KEEP_OPTIONAL_FOLLOWER_WITH_OPEN_PRESET_REFERENCES | Six chargen preset references in a custom follower race are absent in the selected ErinRace version. Preserve follower content while recording the mismatch; do not replace core ErinRace to fit one follower. Optional removal would also require rebuilding Synthesis. |
| isilNarsil.esp | 1 | KEEP_WEAPON_WITH_OPEN_SCRIPT_REFERENCE | Sting weapon VMAD property references an absent own record. Recover the expected record/script identity before changing enchantment or glow behavior. |
| mihailseawitches.esp | 32 | KEEP_CREATURE_SOURCE_WARNINGS | Thirty-one conditions use NULL race parameters and one visual-script property is missing. Do not remove conditions or pick a race without source semantics. |

## 合法擴展與未證實值分開

已證明應保留的擴展：Erin HDPT 35／36／37，Community Shaders LIGH bit 14，DynDOLOD underside MSTT bit 2。GKB Waves 的同樣 bit、Dynamic Things FLOR bit 16、Odin HAZD bit 25、Valhalla GLOB FNAM=0 在本審核沒有同等證據，保留來源並標示未決，不能因數值相似一概宣告合法或清空。

## ADD BEST 與 mybuc

原 TuLED 沒有啟用 ADD BEST。若從 Anno／Burida 導入，要按實際贏家選 Kardia 修正。Burida 變體保留 PGPatcher|0000AA，不能盲套到 TuLED；較合理是把正確源資料交給最終 Parallax／Synthesis，再核對材質贏家。舊合併 FLST 有過時成員，現有 Burida 全引用圖不等於最終整合沒有任何腳本／動態消費者，不能為形式清零整批刪除。

三包 mybuc.esp 不是同一補丁：TuLED 為 7 LVLI／21 masters，Anno 為 39／69，Burida 為 15／22。以 TuLED 覆寫目錄的版本為基底，捐入裝備不能順手覆蓋這個檔名。

## Synthesis 最終重建

TuLED 原 Pipeline 的六個 repo、順序和 TargetCommit 與已完成驗證的 Burida 六個完全一致；Data 內 11 份 JSON 逐位元組相同。可使用既有官方 GUI 0.36.6 編譯產物及相同設定，依最終輸入重建，不需追新 branch。

保留原五項 Blacklist、IgnoreMissingMods=false、English／nonlocalized 和固定依賴版本；所有 patcher 改 Commit 並關自動更新，AOSISCSoundPatcher 改用已驗證相對 project 路徑，所有資料／工作／暫存／輸出位置轉入 Database 最終環境。TuLED 沒有 UD 群；除非完整移入且獨立驗證匹配 UD 堆疊，保持它停用。

先作 pose／來源／修復取捨，再重建。舊 Synthesis 不能作為生成輸入；否則刪除來源的舊 GP／Colly 魔法記錄可能又被帶回。SSE-AT Output 中針對舊 Synthesis 的 804,182 bytes DSD 翻譯 JSON 含舊生成編號，須重建或只隔離這一檔，保留其他翻譯。

生成後仍須檢查每個輸出與 Experience sidecar。Skyrim 測試世界 LAND|01B539 的缺 LTEX 是已證明的原版問題；只略過這一份經證明的生成 debug-cell 覆蓋，最多是避免複製問題，不是修好原版。OldFire 視覺缺件另行保持未決。

詳細候選來源 SHA、輸出 SHA、硬依賴傳播、原始逐欄位證據見 base_diagnostics.json；可讀取 recommended_actions.json 和 synthesis_rebuild_plan.json 執行主代理的整合決策。沒有啟動遊戲／GUI，也沒有修改原件或共用資料庫。
