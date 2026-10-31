# Forgotten City／USSEP 導航三向結果

**此處已有可定界的組合方案和 typed 草稿，尚未產生或驗證成品 ESP。** 沒有啟動 xEdit／MO2／遊戲，沒有改原件或共用 Edit Scripts。`source_preflight.json` 的 `SOURCE_PREFLIGHT_PASS` 只表示三個來源與已審查檔案 SHA 相符。

## 核心結論

`Skyrim.esm|108AB4` 雖然在 USSEP 有真實幾何修改，Forgotten City 的功能差異沒有落在那片修改區域。作者真正的改動僅為關閉 triangle 50 的一條跨 Cell portal；可以保留 USSEP 的全部頂點、三角形和 grid，再精確轉送這條斷邊。

| 來源 | 頂點 | 三角形 | Edge Links |
| --- | ---: | ---: | ---: |
| 一致原版 | 269 | 321 | 29 |
| Forgotten City | 269 | 321 | 28 |
| TuLED USSEP | 271 | 324 | 30 |

Forgotten City 與原版的頂點／grid 位元組完全相同。28 個 raw triangle tuple 差異中，27 個只因 Edge Links 陣列重新排列；將外鏈 index 還原為真正目的地後，只有 **triangle 50、Edge 2-0** 不同：

- 原版外鏈：`Skyrim.esm|107528` triangle 469。
- 作者：該邊改成 border `-1`，Flags `2052 → 2048`，其他資料相同。
- USSEP 的同一 triangle 仍是 vertices `[48,12,47]`、內鄰接 `51/49`、cover flags `0`；同一外鏈的陣列 index 從原版 16 變成 6。

候選保留 USSEP，將其 triangle 50 tuple 從 `[48,12,47,51,49,6,2052,0]` 改成 `[48,12,47,51,49,-1,2048,0]`，刪除精確的 Edge Links[6]，並將其餘所有 **external** index >6 減一。內部三角形 index 完全不變，沒有留下孤立 link 或任意重排。

## USSEP 幾何差異的具體範圍

USSEP 修改既有 vertices **115–118**，另新增 **269–270**；triangle 50 使用的 48／12／47 不在其中。舊 triangle 幾何面 125–130 被替換，增加的幾何面位於 125–130 和 321–323。321 個原面中，315 個仍有精確的座標三頂點對應；作者要修改的 triangle 50 在 USSEP 唯一對應 triangle 50。

| Vertex | 原版 XYZ | USSEP XYZ |
| --- | --- | --- |
| 115 | (-158571.640625, -20419.419921875, 839.5513916015625) | (-158571.609375, -20418.291015625, 839.5513916015625) |
| 116 | (-158373.4375, -20473.037109375, 811.3741455078125) | (-158375.703125, -20480, 823.4896850585938) |
| 117 | (-158153.3125, -20480, 810.25390625) | (-158148.046875, -20479.97265625, 810.25390625) |
| 118 | (-158090.703125, -20480, 821.9931640625) | (-158092.21875, -20480, 821.9931640625) |

新增 269 為 `(-158368.1875,-20436.025390625,805.401611328125)`；270 為 `(-158269.296875,-20479.986328125,804.16455078125)`。這些都是從來源讀出的座標，草稿不設定任何座標。

## 互惠連接已只讀證實

對面的 `Skyrim.esm|107528` 在作者版保留 365 個相同頂點，三角形 `487 → 485`；精確刪去原幾何面 **317 和 469**。原 triangle 469 的面已不存在，不能照舊把 portal 指向作者現在的「469」：那個 index 已被其他面填入。

USSEP 108AB4 有 17 條 portal 通往該對面；只有 triangle 50 的那條失去對面。另 **16 條**都在作者對面保留同 index、相同有序座標三頂點及反向連接；作者對面反向 **16 條**也全部對上 USSEP。刪去唯一失效 portal 後，組合恰好是 **16／16 條互惠連接**。

另外已掃作者全部 **46 個 NAVM** 對這兩個目標的外鏈。沒有作者自有 NAVM 對這兩個目標增加未審查的連接。完整三向、幾何唯一對應、全部 callers 和互惠資料在 `comparison.json`。

## CELL、門與 NAVI

108AB4 的 container 是 CELL `007644`（Tamriel X=-39、Y=-5），目前基底 CELL 欄位贏家為 I5K Treasure Hunt；對面 107528 是 CELL `007645`（X=-40、Y=-5），基底欄位贏家為 Landscape Fixes For Grass Mods。這與入口相關 REFR `0719C6` 所在的 `007665` 是不同 Cell。草稿只複製**最終已套用欄位相容補丁後**的 007644 作 container，保留其水、環境等全部欄位。

七個共享 NAVM 的 Door Triangles 都是空的；本案是戶外 portal 斷邊，沒有門 FormID／CRC 需要推算。

NAVI 的 108AB4 NVMI 是 island：USSEP 含 **7 個鄰居**，保留其新增 `USSEP|074C54`／`074C55` 與相配的簡化 island 幾何；作者版本只有 6 個鄰居且 island 資料不同。候選採 **USSEP 整筆 NVMI**，不將作者舊幾何／座標混入。關閉一條 portal 後仍有 16 條連往 107528，所以該鄰居依然存在，USSEP 的七鄰居集合保持不變。

其餘六個作者共享 NAVM 沒有競爭的 USSEP NAVM／NVMI；精確轉送作者各自的 NVMI，與作者保留的 NAVM／107528 的真實刪面配對。**其他所有最終 NAVI 條目、NVPP、NVSI 都不變。** 七個目標在三來源的 NVPP／roadmarkers 都沒有引用；若實際最終視圖不同，草稿會停止，不能自行重算。

## 草稿與驗證流程

- `DatabaseForgottenCityNavigationDraft.pas`：正常 4.1.5f defs 下建立新 ESL-flag ESP。只允許既有 Skyrim NAVM 108AB4、CELL 007644、NAVI 012FB4，以及外部 container 必需的 Tamriel WRLD 00003C 四個 override，零自有記錄。WRLD 和 CELL 都原樣保留最終贏家。
- `DatabaseVerifyForgottenCityNavigationDraft.pas`：只有 `VERIFY_ONLY=true` 一行不同；必須在新的 xEdit 程序重載候選後執行，不修改、不 export。
- 目前兩份 PAS 是 **v6 exact-source orphan-guard 版本**，權威清單為 `../plugin_integration/navi_unresolved_audit/stock_orphan_lookup_fix_manifest_v6.json`。`generate_drafts.py` 只保留早期基底產生器，**不得對目前草稿重新執行**，否則會移除 v4–v6 修正；需要變更時從 v6 frozen copy 建立新 revision。
- `verify_navigation_candidate.py`：來源預檢；有候選後比較所有 NVNM 位元組／tuple、邏輯差異只在 triangle 50、16／16 互惠，並以實際 `--navi-winning` 原檔為 witness 比較七筆精確 NVMI 與其餘全部 NAVI 資料。

執行順序：最終 VFS 三個來源先跑預檢 → 正常 defs 編譯／執行 builder → 獨立二進位後驗 → 候選 mod 隔離安裝 → 新程序完整 VFS 重載執行 verifier → 全插件原生及完整環境檢查。預檢命令（在本目錄執行）為：

```powershell
python verify_navigation_candidate.py --vanilla "E:/stock/Skyrim collection/Database/repairs/consistent_stock/Data/Skyrim.esm" --feature "E:/stock/Skyrim collection/Anno/iniRePather-Skyrim/mods/The Forgotten City/ForgottenCity.esp" --ussep "E:/stock/Skyrim collection/Database/xedit_runs/TuLED/Data/Unofficial Skyrim Special Edition Patch.esp"
```

保存候選執行前後 SHA、命令和對應日誌。僅獨立二進位通過時狀態是 `BINARY_PASS_TYPED_RELOAD_REQUIRED`；提供有 `FC_NAV_RELOAD_TYPED_PASS` 的同輪日誌才可記靜態完整通過。

草稿要求 final NAVM 七個來源仍是作者；重載時只有 108AB4 必須由候選最後覆蓋。最終有效 NVMI 若偏離作者先前版本、碰到其他來源贏家／新路徑資料或出現額外記錄，都停止。它不會為了啟用內容刪除診斷或猜新連接。

主記錄複製使用 `wbCopyElementToFile(source,target,false,true)`，最後的 true 才會複製 payload；false 只建立 shell。4.1.5f 的 `TwbMainRecord.AssignInternal` 不複製獨立 ChildGroup，故不會因此複製整個 Tamriel；同時會重設 VCS stamps，草稿立即以來源值明確還原 VCS1/VCS2/FormVersion。這些行為已對照 exact tag core，並非依參數名稱猜測。

父容器比較的精確例外以 4.1.5f 為準：WRLD 的 RNAM/Large References、OFST 帶 dfNoCopyAsOverride，容許複製時省略；若仍存在，內容必須完全相同。此版本的 MHDT 沒有 no-copy 標記，仍逐字段嚴格比較，不採用 latest-main 的不同定義。只有 Interior CELL（DATA bit 1）之 XCLW 按 wbCELLXCLWGetConflictPriority 的 cpIgnore 例外；外部 CELL 水高及所有其他字段的存在性和 typed 值均嚴格相同。目前 v6 草稿尚未經 xEdit 編譯／執行。

目前兩份 PAS 尚未經 xEdit 編譯／執行，候選 ESP 不存在。這是有界的靜態資料組合證據，不是遊戲內尋路驗證。
