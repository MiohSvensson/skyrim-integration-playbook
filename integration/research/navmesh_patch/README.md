# GLENMORIL／Skyrim Underground 有界導航補丁草稿

**目前只有草稿與只讀來源驗證，沒有產生 ESP。** PAS 尚未在 xEdit 編譯或執行，不是已驗證成品。所有本子任務輸出都在本資料夾；沒有改原包、共用 Edit Scripts、遊戲設定或啟動 GUI。

## 已確定的來源差異

NAVM `Skyrim.esm|016F5D` 的三份來源具有相同 470 個頂點、532 個三角形、Pathing Cell、空 Edge Links／Cover Triangles，以及相同網格資料。Glen 只在 triangle 502 加 Door 旗標與作者門；AK 只在 triangle 404 加同類資料。兩個作者指向不同三角形，無需推算新幾何。

另確認三份來源都覆蓋 NAVI `Skyrim.esm|012FB4`，其中對應 `016F5D` 的 NVMI：

| 來源 | NVMI 長度 | 門參照 |
| --- | ---: | --- |
| Skyrim | 57 bytes | Skyrim `07BD1B` |
| Glen | 65 bytes | Skyrim `07BD1B`、Glen `0122F4` |
| AK | 65 bytes | Skyrim `07BD1B`、AK `2C376B` |

三份目標 NVMI 的 Category、XYZ 位元組、Preferred Merges、Edge Links、Preferred Edge Links、Is Island 和 PathingCell 相同。門 CRC 全為作者原值 `3834344435`。TuLED USSEP 的 NAVI 存在，但沒有此目標 NVMI。

三份 NAVI 的 NVPP 都是 25,696 bytes、100 條路徑、6,302 個參照、10 個 roadmarkers，**都不包含 `016F5D`**。原始 SHA 不同；Glen 與 AK 經 FormID／排序正常化後的 NVPP 一致，與 Skyrim 的路徑排列不同。因此草稿不合併整份作者 NVPP，只保留最終已選贏家的整組路徑與索引；若最終其他來源已讓 NVPP 或 NVSI 涉及目標，立即停止。

可重現資料：`audit_source_navigation.py`、`navi_source_audit.json`、`nvpp_source_audit.json`、`source_preflight.json`。獨立來源驗證程式還實際解析了 Skyrim 的 15,462 個 NVMI（8,664 islands）、Glen 的 1,000 個（330 islands）、AK 的 338 個（146 islands）。

## xEdit 版本及 typed 路徑

使用本機既有 repository 的 `git show xedit-4.1.5f:...`，固定 commit `f5c00f3fa3ee39511185515802647246c807f759`；原樹未變更。精確副本及 SHA 在 `source_4_1_5f/provenance.json`。

4.1.5f 與較新主線的欄名不同：

- `NVNM\Triangles`：以已驗證的 array ordinal 選 triangle 502；其 typed `Flags` 從 2048 轉成 Glen 作者的 3072。defs 8042–8054 明確定義 bit 10 為 Door、bit 11 為 Found。
- `NVNM\Door Triangles`：entry `Door Triangle`，欄名是 `Triangle before door`、`CRC Hash`、`Door Ref`。新主線的 `Door Links` 不能直接套用這裡。
- `NVNM\Pathing Cell\Parent` 是會解析為 Parent Cell 的 union scalar；不是憑空添加一層 `Parent Cell` 子容器。依 wbImplementation 21594–21608 的 union 初始化行為確認。
- NAVI 的 `Navmesh Infos` 裡各 NVMI，含 `Navmesh` key 及 `Door Links`；其門 entry 的欄名為 `CRC Hash`、`Door Ref`。

本次必須使用**正常記錄定義**。`SimpleRecords=true` 時 vertices／triangles 是 byte arrays，門欄名也不同，草稿會停止且沒有 raw-offset 後備寫入。專用設定檔的 `[Options] SimpleRecords=false` 必須有效：xeInit 514–516 先讀 executable 旁的 app/tool INI，沒有才讀 plugins.txt 同名 `.sseviewsettings`；`-I:` 的 Skyrim.ini 並不是這個開關。不要啟用 QuickClean 來取得正常模式。

API 已對照同 tag adapter／host：`ElementAssign`、`AddRequiredElementMasters`、`wbCopyElementToFile`、`RecordByFormID`、`LoadOrderFormIDtoFileFormID`、`LinksTo`、`SetEditValue`、`SetIsESL` 及 stream export。`HighInteger` 是舊版確實註冊的 append 常數。export 使用 `FileWriteToStream(...,0)`，避免已在其他候選證實的 reset-modified serializer assertion。

主記錄 payload 複製的確切參數是 `wbCopyElementToFile(source,target,false,true)`；最後 false 只建立空 shell。`CopyOverride` 還依 core 8554 起的行為，明確還原 copy 時會被重設的來源 VCS1／VCS2 和 FormVersion。主記錄 Assign 不包含獨立 ChildGroup。

## 草稿將做甚麼

`DatabaseBoundedNavmeshDraft.pas` 的 `VERIFY_ONLY=false`：

1. 在任何新建／修改前，核對完整 loaded NAVM chain，只容許 Skyrim、Glen、AK，並要求 AK 為最後來源。三份來源逐 typed 葉比較幾何與預期門資料。
2. 搜尋整條 loaded NAVI chain 對目標的 NVMI 提供者，要求最後有效提供者為已審查 AK。最末 NAVI 本身可以沒有此 entry；若未知來源也提供了目標，停止調查。
3. 取得最終已選 CELL 與 NAVI 贏家並記錄來源名稱；不以其中一份作者的大包覆蓋全部內容。
4. 新建 ESL-flag ESP，先加必要 masters。複製既有 CELL `016D72` 作為 container，完整保留最終 CELL 贏家；複製 AK 的 NAVM，僅更動 triangle 502 Flags 並轉送 Glen 的完整 typed Door Triangle。
5. 複製最終 NAVI 贏家，若缺目標 NVMI 就精確轉送 AK entry，再只加入 Glen 的完整 typed Door Link。保留其他所有 NVMI 與 NAVI 的 NVPP／NVSI／其他欄位。
6. 新轉送結構的 FormID 都以來源 `LinksTo` 的實際 record 為依據，交由 xEdit 的 load-order FormID／EditValue 轉譯；不搬 raw master-index 數值。
7. 驗證只有既有 Skyrim 的 NAVM、CELL、NAVI 三個 override，零自有 FormID；全部 typed 內容符合後，才 export 到本目錄 `candidate/`。任一錯誤不 export。

複製 NAVM 時 xEdit 會遞迴建立 container。不能未驗證就刪除 CELL，因而草稿明確保留其不變 override。若實際 xEdit 建立額外記錄，record whitelist 會停止，需重新審查。

## 根代理的執行與後驗順序

1. 使用最終 MO2 VFS 探針確認實際解析到的三個來源檔案。將它們分別交給 `verify_candidate.py --vanilla ... --glen ... --ak ... --output <本目錄內的新報告>`；它會對照既有 NAVM／NVMI 靜態證據，有差異即停止。已對研究快照執行，結果 `SOURCE_PREFLIGHT_PASS`；這不能代替最終 VFS 預檢。
2. 把 PAS **複製到該次專用工具的私有 Edit Scripts**，先讓 xEdit 編譯；本子任務沒有動共用腳本。使用正常 defs 及最終完整載入環境執行 builder。需要保留 `BOUNDED_NAVM_CELL_SOURCE`、`BOUNDED_NAVM_NAVI_SOURCE` 和 export／PASS 標記。候選已存在則拒絕覆寫。
3. 程序結束時不要把尚未審查的新插件或其他檔案另存到 VFS。若編譯／執行／後驗失敗，保留錯誤日誌和候選，不啟用。
4. 二進位後驗用 `verify_candidate.py` 加上 `--candidate` 及 `--navi-winning`（builder 記錄的最終來源 NAVI 實體檔）。它只接受 NAVM、CELL、NAVI 三個既有 override；核對 NAVM 所有幾何位元組、三角形、門引用與標頭語意，並正常化驗證 NAVI，要求只有目標 NVMI 的作者門清單差異。此時狀態仍是 `BINARY_PASS_TYPED_RELOAD_REQUIRED`。
5. 將候選放入專用候選 mod，在**新 xEdit 程序**以相同完整環境重載，執行 `DatabaseVerifyBoundedNavmeshDraft.pas`。這份檔案與 builder 僅 `VERIFY_ONLY=true` 一行不同，完全不修改／export。它重新核對 typed CELL、NAVM、NAVI、來源 chain 與所有其餘 NVMI，要求 patch 為最後 NAVM／NAVI 贏家。完整靜態驗證還要另跑全插件原生及完整環境檢查。
6. 重載成功後再把該次日誌交給 `--typed-log`。根代理須保存 candidate 在該次執行前後的 SHA、實際命令與對應日誌，避免將不同輪的檔案與 PASS 混配。程式才會輸出 `STATIC_BINARY_AND_TYPED_RELOAD_PASS`。

獨立二進位 reader 只讀不寫插件；header 和 NVNM／NVMI／NVPP 的布局來自已保存的同版本定義。未知 NAVI subrecord、來源變動、額外記錄、索引超界與布局尾部差異都停止，不嘗試修正。三角形只讀解析不是 xEdit typed 編輯的替代。

## 仍然有效的關卡

這個草稿處理一處拓撲相同的門資料衝突。它不解決 GLENMORIL 與 AncientLand 的另外兩處真實幾何差異，不推算任何新座標或 CRC，也沒有遊戲內跨門尋路驗證。即使此候選完成靜態通過，GLENMORIL 的其餘關卡仍須成立才可啟用。
