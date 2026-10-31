# TuLED 與九個追加插件的欄位相容計畫

已按 canonical origin＋object ID 檢查 **213 筆 override**，保留原始 subrecord、來源／原版／TuLED 贏家三向差異與 SHA。推薦保留九個插件的內容，以兩份小型 metadata 補丁和獨立導航補丁處理交點。這裡完成的是來源、欄位和有界合併規格；本代理沒有啟動遊戲、MO2 或 xEdit，也沒有產生或宣稱驗證成品 ESP。

基準為 `Database/repairs/consistent_stock/Data` 的五個 ESM，原 TuLED 六個已建議停用插件與舊 Synthesis／DynDOLOD／Occlusion 不參與贏家判定。原 profile 的讀取前後 hash 一致，留在 `raw_field_comparison.json`。TuLED 四個精確修復，以及現有九份 Rihad／Egil／pose／OldFire 變體，均沒有覆蓋這些 feature 目標；具體路徑、SHA、交集在 `compat_patch_plan.json`。

| 插件 | 自有記錄 | Override | 槽位 | 採用處置 |
| --- | ---: | ---: | --- | --- |
| Wyrmstooth | 103212 | 11 | full、ESM flag | 採用；4 INFO 轉入新增條件，保留基底容器與文字 |
| ForgottenCity | 11076 | 32 | full | 採用；metadata 與有界 USSEP 導航補丁分開驗證 |
| Forgotten City Music Fix | 3 | 2 | light | 與 ForgottenCity 一起採用；共享容器保基底 |
| WorldInPainting ZeroHall | 40 | 4 | full | 採用；3 共享容器／location 保基底 |
| 修正版 UF6 | 372 | 3 | light | 採用已驗證修正版；在 ZeroHall 之後 |
| ForgottenMagic Redone | 1040 | 4 | full | 採用；僅轉送四個基底容器 |
| Sofia | 1672 | 69 | full | 採用；49 VMAD hooks＋horse PACK 隔離＋Persistent 位 |
| Hoth | 302 | 41 | full | 採用；voice FLST union＋Moorside Inn XCAS |
| BenDoon | 3161 | 47 | full | 採用；Persistent／必要 XLRL，保基底修復 |

九個來源合計增加 7 full＋2 light；此處兩份 metadata 補丁均為 ESL flag，再增加 2 light。導航、生成輸出和其他任務根另計，不以此數字代替最終槽位實測。

## 可直接交給主代理的草稿

1. `DatabaseFeatureCompatibilityDraft.pas`：152 個共享基底 record，加 Sofia quest override 與唯一新 PACK，預期 **154 payload records／1 own PACK**。49 Sofia VMAD、4 Wyrm Conditions、5 BenDoon XLRL、1 Hoth XCAS、18 Persistent 位及 voice union。對應 `compat_patch_plan.json`。
2. `DatabaseQuestFeatureCompatibilityDraft.pas`：**27 overrides／0 own**；16 筆保留基底，加 11 筆沒有 TuLED 欄位競爭的作者入口／自訂 race 支援；FC INFO 以基底 VMAD＋作者 Conditions 合併。對應 `quest_extension_plan.json`。
3. 各有 `DatabaseVerify...Draft.pas`，只讀重載驗證版本。先跑 metadata，再由 `research/forgotten_city_navigation` 的草稿建立 FC 導航補丁，讓導航轉送最終 CELL `007644`。

兩組來源預檢分別 **36 SHA/CRC guards＋152 基底／14 guards＋27 seeds 通過**。四份 PAS 的註冊 API 可用性稽核通過；這不是 Pascal 編譯通過。腳本要求 fresh xEdit 4.1.5f normal definitions，舊生成輸出尚未載入。來源磁碟 CRC 不涵蓋既存未儲存的記憶體編輯，因此必須新程序執行。

腳本僅變更新建記憶體插件；先核 VFS CRC、每筆真正基底贏家，再作 typed copy。所有複製欄位以 xEdit required masters／型別化 AddCopy 處理，來源 FormID 逐 leaf 用 resolved load-order identity 重設並核對 `LinksTo`。只有全部斷言通過才 export，不修改原件；失敗時不儲存未完成補丁。新 PACK 的 object ID 必須在 `800–FFF`。

精確 **xEdit 4.1.5f** 定義中，WRLD RNAM／OFST 標記 no-copy-as-override，允許省略；若存在仍精確核對。**MHDT 沒有該旗標，必須保留並 strict 核對**，不可沿用最新 main 的不同 schema。DIAL INOM／INOA 是 editor-only INFO order，帶 dfDontSave／dfDontAssign，僅允許省略、存在時仍核對。DIAL TIFC 和室內 XCLW 的原 cpIgnore 規則另列。來源凍結在 `source_4_1_5f/provenance.json`：Common 803–819（INOM／INOA）；TES5 5189–5219（MHDT）、13145–13160（RNAM）、13241–13243（OFST）。未知欄位仍 fail closed。

實際 producer 的初期失敗顯示，serialized Data Size 會改變、Record Header 不保證位於 index 0、VCS byte-array 不可用一般 Variant 等號比較、typed Copy 會重設 VCS2。草稿現在只略過 derived Data Size，FormID 用 canonical identity，其餘 Signature／Flags／FormVersion／VCS1／VCS2 仍精確驗證；新記錄及最終種子在排序／突變後恢復來源 metadata，再核對。

共用 leaf verifier 已改為處理真正的 native Variant 型別：任何一端有 `LinksTo` 必須雙端解析且 canonical 相同；接著只有雙端 `VarType=8209`（Array Byte）才由精確 4.1.5f 已註冊的 `TBytesStream`／`TBinaryReader` 取完整 native 向量，驗 Size、逐 byte 和完整 Position。這同時覆蓋 CTDA None 與 PACK PLDT union，沒有欄位名白名單，也不靠可能格式化的 edit 字串判定 bytes。其他 native array 型別及不符合預期的 ByteArray 會 STOP。證據在 `native_byte_vector_evidence.json`；實際編譯／執行仍由主流程另驗。

CTDA 的 `ptVariableName` 有另一項精確 schema 語義：stored U32 並非變數名，getter 從相鄰 CIS1／CIS2 讀完整字串、setter 固定回零。原 USSEP `0B1231` 的 stored U32 本就為 `b009c6a4`，合法 typed copy 將它歸零。只有 exact function＋parameter 型別守衛者採 CIS 比對；獨立 binary verifier 另強制 candidate 的該 U32 為零，核 CIS 精確 bytes 與對應的 CTDA 綁定。其他 UInt32 仍 strict。`semantic_exception_contract.json`、`semantic_native_value_audit.json` 和八項 `cis_semantic_validation.json` 記錄完整範圍與反例驗證。來源已檢查的 typed floats 沒有 NaN／Inf／subnormal；negative zero 和 MaxSingle 原 bits 不正規化，binary 比對繼續嚴格。

`verify_compatibility.py`、`verify_quest_extension.py` 可先無參數預檢；`--file-map` 接受 `{plugin_filename: absolute_physical_winner_path}`，`--candidate` 檢查新候選。輸出受限本資料夾。它們是有限 binary canonical decoder；仍要由新 xEdit 程序執行 typed verifier，完成最終 profile 的 native／master／全域檢查。

目前 feature 成品必須使用 `verify_compatibility_v14.py`，不是保留作 v13 凍結證據的 `verify_compatibility.py`。v13  verifier 會把 Sofia QUST VMAD tail 的兩個合法 master-index remap 當成差異；v14 只 canonicalize 這兩個 typed FormID，其他 tail bytes 仍逐位嚴格檢查。已安裝候選 SHA `25f5a1a4…4557` 的 v14 resolved-map 複核與 fresh typed reload 均通過；quest 成品繼續使用 `verify_quest_extension.py`。

## 主要交點的具體判定

**Wyrmstooth：**四筆 DIAL 僅文字編碼／TIFC；四筆 INFO `068454/0684F4/068526/06884E` 新增的是 function 579 `GetEquippedShout`，把自有 SHOU `30C92F` 加入 Aura Whisper OR 分支，並非覆寫戰鬥或技能框架。基底沒有 CTDA 競爭；`068526` 的正文標點保 USSEP。CELL `0A1793` 保 Water for ENB 的 XWEM／基底名稱。NAVM `0DEB13` 有真實作者改動，但 TuLED 贏家仍是原版；全局 NAVI 必須另作最終彙總，不能當 ITM 刪掉。

**ForgottenMagic：**沒有覆蓋 Ordinator／Odin 的 PERK、AVIF。四個交點都是 WRLD/CELL：Tamriel `00003C`、persistent CELL `000D74`、Whiterun stables `009A07`、Bannered Mare `01605E`。來源相對原版只有 cache／XCLC unused bytes／區域排序／在地化等價；保 KuroneSoulTomb 的五個 XCLR 區域、Nix container 和 TL Bulbs 標題。僅轉送容器，絕不清掉其 child groups。

**Sofia：**49 個既有 INFO 新增 fragment VMAD；基底的 USSEP／HearthFires 條件、正文和 PNAM 保留，沒有 VMAD 對 VMAD 或 CTDA 對 CTDA 的未解競爭。來源改動的 PNAM 都指向其他既有 Skyrim INFO，不是自有新回應；採用基底連結次序。ACHR `0B8E97` 僅加 Persistent `0x400`，保留 USSEP 移位、ragdoll 和其他旗標修復。

來源把全局 `Skyrim|09845C PlayerHorseStayPut` 改成 `SofiaHorseStayPut` 並移除兩個條件，會影響普通玩家坐騎。實際型別化使用者為 `Sofia|00AA58 JJSofiaScripts` 的 **Alias 1 SofiaHorse / ALPC**。草稿遍歷整個來源插件全部 typed payload leaves，必須恰好這一個使用者，才克隆作者 PACK、只改該 ALPC，並完整恢復原版全局 PACK。整個 quest 其餘 leaves 與來源逐一相同。

Sofia BSA 的 **323/323 PEX** 均依 inventory SHA 驗證、逐檔反編譯出 PSC＋ASM，零失敗。全部沒有 `GetForm/GetFormFromFile` 呼叫，也沒有 `0x9845C`／`623708` 或兩個 horse PACK 名稱。這是完整所選 BSA 腳本的靜態證據，不能泛稱任意外部腳本不會計算動態 ID。證據為 `sofia_scripts/audit.json`、decompiler log 和 `follower_source_consumers.json`。

**Hoth：**`DefaultNPCVoiceTypes FLST|03B4A5` 以 TuLED ErinRace 贏家為底，保 `ErinRace|001040`，追加一次 `Hoth|00333C`；不覆蓋成任一單方列表。Moorside Inn `CELL|0138CE` 只搬作者 XCAS，保 WSU 其他欄位。INFO `0653F1` 的作者新增 CTDA 已與 USSEP 相同，保 USSEP VMAD；`0DE50E` 的 Previous INFO 保 USSEP。其餘 DIAL 多為等價翻譯／TIFC。

**BenDoon：**來源實質旗標改動是 Persistent `0x400`，不是 Deleted。保留 USSEP／Kaidan 的位置、額外 links 與現有旗標，加作者 Persistent；僅在基底尚無相同來源新增 XLRL 時轉入。`REFR|0868CB` 的 VMAD 是 v4/object-format1 到 v5/object-format2 編碼／property 順序差異，解析後相同。LCTN `020082` 的來源移除八個原版 special-reference cache entries，轉送原版完整 LCTN。來源 ITM `REFR|0B8307/0B830F` 不得蓋掉 BPUFXelzaz 的 persistent 修復。

**ZeroHall／UF6：**Dragonsreach `CELL|0165A3`、Kynareth Temple `0165A7` 和 `LCTN|01F87D` 的交點保基底；作者 Chinese FULL 不蓋基底命名、水環境。Location 的 ACSR/LCSR 換位解析後是相同三筆 special refs。UF6 對 `ZeroHall|000D68` 是 feature 自有 namespace 的作者接續，不是 TuLED 交點。UF6 的 `Dragonborn|03A741` Deleted 記錄對應新舊 stock 都沒有 EDID/model 的空 DOOR stub；沒有證據它是可用的 Dragonborn 大門，因此保作者狀態，不憑空製造 undelete 修補。

**ForgottenCity：**十個 WRLD/CELL metadata 容器保 TuLED，包括 Natural Waterfalls／Landscape Fixes 的 XCWT；一筆 DIAL 保 Kaidan；`INFO|071440` 合併作者 Conditions 和 USSEP VMAD。`REFR|071A05` 作者相對原版只是微小 float jitter，來源 XLRL／XSCL 已與 USSEP 相同，完整保 USSEP；另三筆作者入口／disabled reference 修改保留。四個 ARMA 加自有 race `084640`，三筆 headpart FLST 同樣擴展該 race，Astrid HDPT 有作者 DATA 支援；沒有 TuLED 記錄對手，保作者整筆，沒有帶入原 NPC replacer。

唯一真正的競爭 NAVM 為 `108AB4`。runtime_layout 已逐三角形與互惠驗證：保 USSEP 271 vertices／324 triangles／grid，只關閉 triangle 50 的一條 portal、刪精確 Edge Links row 6，重編更大的 external indices。作者鄰 mesh 刪面 317/469；其餘 16/17 portals 保原 ordered 三頂點與雙向鏈接。NAVI 保完整 USSEP primary NVMI，另六筆 shared NVMI 保作者版，其他最終表不變。完整證據／草稿／限制在 `research/forgotten_city_navigation/README.md`；尚須主代理實際生成與重載。

**MusicFix：**實際 PEX 已獨立反編譯，所有十個 GetFormFromFile literal 目標均存在於精確所選 FC：一個 QUST、九個 MUSC。它透過 `GetModByName/GetFormFromFile("ForgottenCity.esp")` 軟依賴主插件，雖無 MAST，仍必須成對保留原名。三個自有記錄及 trigger script 保留；兩個 stock 容器已由第二補丁保基底。證據 `music_fix/audit.json`。

## 導航、stock 和驗證邊界

`own_navigation_scope.json` 確認 Sofia 一筆 NAVM 在自有室內 CELL；BenDoon 兩筆皆自有室內；ZeroHall 一筆自有畫廊室內；UF6 一筆自有 WRLD `(0,0)`；Hoth 無 NAVM。這些沒有向 TuLED 既有 CELL 增加自有 NAVM，但仍須最終 NAVI／資源／LOD 與全 profile 驗證。

`coherent_stock_target_delta.json` 比較所有目標的新舊 stock：Skyrim.esm 零差異；四個 Cleaned Vanilla master 合計九個 file/record 差異，主要是 WRLD RNAM 和 NAVI 表，另 Dragonborn 對 INFO `0D8DD4` 的 VMAD 原始編碼不同但解碼等價。舊 NAVI 不能蓋回完整一致 stock。

仍未涵蓋的層級包括遊戲內入口可達性、任務順序、實際 follower 行為、碰撞／視覺、生成的行為／LOD 和 asset soft dependency 的全域勝出情況。這些由最終整合工作繼續處理；本結果沒有把 native 0 當成內容相容或 runtime 通過。
