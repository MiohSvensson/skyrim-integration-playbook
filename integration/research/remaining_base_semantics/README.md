# 剩餘來源語義與缺件處置

已完成只讀審核，新增 **一份兩屬性 Rift 候選**及**兩個精確 SEQ sidecar**。沒有改來源、profile、共用工具或正式 runtime，沒有啟動 GUI／遊戲。其餘未證實的缺件保留為精確 known issues，沒有用空 fragment、任意音效或同名模型掩蓋。

可執行決策在 `semantic_dispositions.json`；具體 record／raw fields／腳本消費在 `base_record_semantics.json`、`feature_missing_consumers.json`。`script_evidence.json` 記錄 **311 個 SHA 驗證 PEX 的 PSC＋ASM**，零反編譯失敗；其中包含 BenDoon 全部199、Rift全部32、TCC全部73，以及相關 stock／USSEP／ScriptFixes 與 Wyrm 支線片段。

| 項目 | 結論與處置 |
| --- | --- |
| Rift YG／ZG | **候選可套，待 xEdit。** 實際 gostteleportlocked PEX 只宣告／消費 GlobalVariable XG；移除未宣告 YG、ZG 兩個 stale VMAD assignments。 |
| Rift key refToDisable | **仍未解。** `REFR|1B3A4B` 的 `defaultDisableOtherObjectWhenTaken.refToDisable → own2DE1E6` 是宣告且在玩家拾取時 Disable 使用的 ObjectReference；不能清除或猜物件。 |
| Darkend | **13 MGEF／26缺賦值仍未解。** SprigganFXSCRIPT 的兩個 Spell 屬性確在 combat／bleedout 事件 Cast 使用，不能套 MoonStar 式清理。 |
| TCC 兩 SNDR | SNAM 確實允許 NULL，但目前是**非零、無法解析的 LOTD9D5B81**，不等於已合法置空。沒有精確作者記錄，保來源，不猜新 SNDR／不擅清 alternate link。 |
| TCC Looping64 | xEdit 與 CommonLib enum 都只列0/8/16/32；一致 stock 所掃3237筆SNDR未找到64。保來源未知值，不能自選另一種模式。 |
| BenDoon horse PACK | **來源未接線殘留。** 缺片段的包保留，不停用 follower，不編造空函數。 |
| UF6 五家具 | **來源未擺放定義。** 保留世界、正常家具與原定義，將五個模型缺件列為 inactive asset exceptions；不換成別的家具，也不宣稱全資源閉合。 |
| Wyrm INFO3943AB | **活躍對話的 OnEnd fragment 未恢復。** 保 quest/dialogue，不能把 Fragment_0 當空函數。已有後續接受對話實際 SetStage10，故缺此 intro fragment 不等於已證明整條任務不能推進。 |
| Wyrm crickets | **一個活躍區域環境音樣本缺失。** 保任務包，列缺一部分 ambiance，不換任意音檔。 |
| BenDoon／ForgottenMagic SEQ | 已依本機 xEdit 4.1.5f primary 精確生成研究候選，待正式 VFS 裝入／檢查。 |

## 可採用的修復與 sidecars

`rift_stale_property_candidate/GostedDimensionalRift.esp` 的 SHA256：
`51e7371177a2c81904729fc965e5cbe6eccd4b7d986047de17a2b023a15977a3`。

只有 REFR `2ED53E` 的 VMAD property count **4→2**，刪除 `DimRiftPlayerAngleYG/ZG`。全部15930記錄、ID／flags／masters與其他 ordered decompressed subrecords 逐 byte 相同，fragment tail 相同。`rift_stale_property_evidence.json` 保存舊／新 VMAD hex、刪除 ranges 和來源／PEX SHA；最終 VFS 的 `gostteleportlocked.pex` 必須仍為 `5ed6d498...a8f38f6`，且原插件 SHA 相符才套到整合副本。預期三個歷史缺引用剩下真正的 key refToDisable 一個；未作 xEdit 或遊戲驗證。

`generate_locked_seq.py` 僅輸出本資料夾的兩個 sidecars：

- `seq_candidate/seq/BenDoonSSE.seq`：4 bytes，`6b c7 04 02`。
- `seq_candidate/seq/ForgottenMagic_Redone.seq`：8 bytes，`62 0d 00 02 63 0d 00 02`。

主要依據為 frozen **xedit-4.1.5f** `source_4_1_5f/xeMainForm.pas:4160–4237` 的 `mniNavCreateSEQFileClick`：包括新的 SGE quest，或原 Master 沒有 SGE、此 override 新設 SGE；寫出 **FixedFormID 的 little-endian Cardinal 陣列，無 header**。這裡保留兩個 masters 的 file-local self index `02`，沒有使用執行時 load-order prefix。該 tag `wbImplementation.pas:8856–8878` 的 `DoGetFixedFormID` 證實計算。工具鎖來源 SHA、精確 SGE own set 與順序；出現其他 SGE override 即停止。完整 SHA／primary source hash／計畫在 `seq_generation_plan.json`。

## 新追加內容的精確範圍

BenDoon PACK `04A1A3 SKQFollowOnHorse` 的 tail 是 **OnBegin Fragment_0＋OnChange Fragment_1**，不是零函數。整個3208筆來源記錄不存在此 FormID 的 payload byte 候選，型別明確的 PKID／ALPC 也都是零；盤點內沒有其他依賴它的 master，全部199個 PEX 也沒有任何 GetForm 名稱、PackageOverride、該包名或ID。這證實所選來源沒有一般路徑選取此包；不能擴大成任意外部動態查詢永不使用的全球保證。保原記錄，正常 follower 其他包和腳本照常保留。

UF6 FURN `000801–000805` 的五個 `0waxe/0jm` 模型在全盤點缺失，但來源全檔 raw references **0**、NAME placements **0**、整個 UF6 attached VMAD **0**，也無盤點 master-dependent。缺的是未接線的家具定義，沒有證據缺一張畫廊中實際擺放的椅子；不刪原件，保留這五個精確缺件例外。仍須最終 xEdit direct reference graph 檢查。

Wyrm INFO `3943AB` 屬 SGE `WTKillThalmor / Unwanted Guests`，條件是自身stage0、`WTWrapMeUp` stage≥30、Alberthor／Falmer 兩種 NPC。它配置真的 OnEnd `TIF__023943AB.Fragment_0`，函數內容無來源可證，沒有編造。後續 INFO `3943AF` 的實際 `WT_TIF__023943AF.pex` 呼叫 `GetOwningQuest().SetStage(10)`，其 quest stage fragment 啟用標記／目標；因此尚不能把 intro 缺片段描述成已證實的任務阻斷。

SNDR `8BFAE2 WTAMBCrickets` 由 Marsh REGN `57654E` 的RDSA第3／41筆、Forest `58CB3B` 的第5／48筆使用，flags15、chance0.25。兩個REGN分別被155／176個 source CELL XCLR 引用，且有 polygon／world 資料。缺的 `sound/fx/amb/wt_amb_crickets01.wav` 及 XWM 替代在全庫都是零候選，是真 ambiance 缺件；沒有任務 stage／對話腳本依賴。

## 未能精確恢復的 base 問題

Darkend 26個賦值分屬13個MGEF，兩個缺 Form 為 own `00AA0E/019D5B`，**預期類型是 Spell**。誤改成同 object ID 的 Skyrim Form 會得到 LAND／REFR，類型也錯。來源圖為13 MGEF→13 SPEL→4 RACE→5 NPC，並有一個非 InitiallyDisabled 的 source ACHR `604F83`。USSEP 與 stock 的 SprigganFXSCRIPT 都使用兩個 Spell 屬性 Cast，因此不是 dead property；可能影響這些生物的叫援／回血事件，不能為消除錯誤移除功能。

所有盤點 pack 都沒有三個精確缺失身份（Darkend兩個、LOTD9D5B81）。跨包相同 Darkend 記錄／Tullius Athena／Rift來源以及 TCC全部六個 SNDR 的比較在 `cross_pack_source_comparisons.json`。TCC Anno與TuLED六筆 flags和 ordered fields 完全相同；換來源包無法解決。兩個 achievement SNDR 經 SOUN 形式確被 `RN_Achivement_Script_Master.PlayFX` 的 `Playandwait` 消費，Looping64也由實際 projectile Sound使用，不能通稱未使用聲音。

Darkend [作者頁面](https://www.nexusmods.com/skyrimspecialedition/mods/10423) 明確列 Rotten Maidens 的來源；其 [原作者連結14106](https://www.nexusmods.com/skyrimspecialedition/mods/14106) 現在顯示已由作者撤下。這提供 provenance，沒有提供可恢復缺 Spell 的檔案。TCC [作者頁面](https://www.nexusmods.com/skyrimspecialedition/mods/38529) 的新版本記錄沒有證明修復本次兩個 SNAM／Looping64；不因版本號較新就整包更新或稱已修復。[CommonLibSSE-NG 的原始型別定義](https://ng.commonlib.dev/_b_g_s_standard_sound_def_8h_source.html) 也沒有給64一個可驗證的模式名稱。

## 仍啟用的外觀／顯示來源

`base_record_semantics.json` 逐筆保存9個來源：Replacing Female Resource兩個插件、Female AIO、WZArtifacts、Tullius Hair3、Sasha、Apocalypse、Full Random NPC、Inigo。目標NPC共17個，**每一個都有精確canonical origin/object ID 對應的 FaceGeom＋FaceTint inventory 候選**；這不等於最終資源贏家或遊戲內外觀已驗證。

- 八個 NULL class resource NPC 沒有 CharGenFacePreset bit；不能只憑命名說合法 preset／任意替它們填 class。保留已有 FaceGen 和資源庫。
- WZ `000NordMalePreset01` 也沒有該 bit，且有 source ACHR `002346`；不能把它當沒有使用的 preset 清掉。七個 tint 警告保留。
- Tullius Athena `HDPT|000CEA` 的 extra part `000BBC` 在 TuLED／Burida兩份相同來源中都缺失；其他現存 Athena headparts 不是它的精確身份，沒有任選 hairline 替代。
- Sasha 的六筆缺項是 custom race 的 female CharGen preset list，並非六個缺失 follower 本體。自己的 PSFollower NPC仍引用此race；不替換全局ErinRace或猜 preset ID。
- Apocalypse／Female AIO／Inigo tint palette 與 FaceGen 的實際外觀一致性仍需 final resource winners／遊戲層驗證；不盲目重生成臉。
- Full Random NPC兩個 Gift Filter 的LVLI→FLST型別失配仍無精確目標；不移除大NPC包或猜另一個list。

以上保留的 known issues 具體而可審計，不作「全0」或 runtime 完全正常的宣稱。
