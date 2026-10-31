# Synthesis 重建與未決來源

已使用作者官方 GUI 0.36.6，按原設定及六個鎖定提交重建 Burida 的 `Synthesis - Patch.esp`。先在 MO2 外完成編譯，再在 MO2 虛擬環境執行。Windows Code Integrity 對自行建置 CLI 的阻擋仍保留原事件證據，沒有修改安全設定。

GUI 的缺失檔案檢查會包含停用的清單項目。隔離清單只移除六個未啟用且未鏡像的項目，926 個啟用插件順序完全不變；「忽略缺失模組」仍關閉。實際補丁器輸入採原輸出位置之前的清單，未把整套後置插件任意加入補丁範圍。

輸出包含 ESP 及 Experience 的 `SKSE/Plugins/Experience/Races/GeneratedExperiencePatch.ini`；兩者都保存在 `repairs/Synthesis_GUI_v2/output/`。原作者管線、首次重建及更新來源前的上一輪輸出都保留。

更新 Rihad／Egil 來源後再次執行，輸出共有 **138 個主檔、18,278 筆記錄**。與更新前一輪相比，主檔清單與記錄編號集合完全相同，唯一資料差異是 `RihadCuirassAA` 的種族清單隨作者主檔更新。Egil 的五筆升級記錄保留在來源插件，管線沒有為它們產生不必要的覆蓋。

後續加入 `Database Kardia Texture Fix.esp`，保留原補丁位置之前的輸入範圍，再次執行相同六個鎖定版本。與上一輪相比，主檔清單和記錄編號集合仍完全相同；唯一差異是 `NiseKardiaGauntletsBlackAA` 的 `MO3S`／`MO5S` 兩個陣列，各移除一個指向 NULL 的無效項目。原來有效的 PGPatcher 視差材質、模型路徑、種族和其他記錄資料都保留。

VAE、Lola 與 Kardia 的舊錯誤已不再被生成補丁覆蓋回來。最新原生及完整 MO2 檢查均剩 **20 個記錄、24 個欄位診斷**，並非全套已修復：

| 來源 | 記錄數 | 已核實情況 |
|---|---:|---|
| GPPoses／Colly | 18 | 原有動作包殘留魔法效果的 VMAD 引用；先前完整環境掃描有相同來源診斷。可選的純動作版與完整戒指／法術恢復是不同方案 |
| EldenRingSkyRim_OLDFIRE | 1 | 原魔法效果缺失 Hit Effect Art，且聲音欄位為 NULL；不是重建新增的來源內容 |
| Skyrim.esm LAND 0001B539 | 1 | 三包原版主檔均含相同的四個缺失 LTEX 00000844 引用；位於 CWTestHold／TestCWCampSons。已比對原始位元組、父群組與來源 SHA，不猜測替代貼圖 |

## 證據

- `official_release_provenance.json`、`compiled_patcher_provenance.json`：官方工具與八個已編譯項目的來源；實際執行第一組六個補丁器。
- `gui_listing_adjustment.json`：僅調整停用清單的證據與啟用順序雜湊。
- `input_manifest.json`、`work/r4du3qwg.5ky/Workspace/Synthesis - Patch/Plugins.txt`：來源快照及實際輸入清單。輸出本身不作為輸入插件載入。
- `completed_output_manifest.json`：ESP／Experience sidecar 雜湊。
- `restored_input_output_difference.json`：來源恢復前後的唯一欄位差異。
- `kardia_output_difference.json`：加入材質修正後的唯一記錄／兩欄位差異。
- `xedit_validation.json`、`full_validation.json`：原生與完整 MO2 檢查。
- `remaining_diagnostic_provenance.json`、`vanilla_land_source_proof.json`：剩餘來源診斷的交叉證據。

以上相對路徑均位於 `repairs/Synthesis_GUI_v2/`。此輸出只存在 Database 的測試配置，未套用原包，也未做遊戲或存檔測試。

最新 ESP SHA-256：`22d9932b0a54a25f910946e070ce2c6de95c114880c6f91f61a958c91476fe9b`。完整檢查載入 934 個檔案，處理 2,061,556 筆記錄；八份既有修正與新增材質補丁均零診斷，MO2 結束碼 0。修正前的 21 筆結果及原輸出保存在 `history/before_kardia_correction/`，資料庫中的歷史輸出路徑也已指向相應保存版本。

## Kardia 補丁的來源和版本條件

Anno 以 `ADD BEST.esp`、Burida 以最高覆蓋的 `PG_1.esp` 為來源，各建立一筆 ARMA 的小型覆蓋。Burida 的有效材質指向 `PGPatcher.esp|0000AA`；保留來源 1.71 標頭後，原生 A/B 檢查確認這個低編號 ESL 引用可正確解析。使用 1.70 標頭的失敗記錄另存，沒有把有效材質改回舊版來掩蓋問題。

三個原包都啟用相同 SHA 的 `BackportedESLSupport.dll`；[作者說明](https://github.com/Nukem9/skyrimse-backported-esl-support/blob/master/README.md)列出對 1.5.97 和擴充 ESL 範圍的支援。本次只核對安裝和檔案，沒有啟動 SKSE／遊戲驗證 DLL 執行。

兩份補丁都已通過原生與完整 MO2 檢查：Anno 載入 1,516 檔、處理 2,680,987 筆環境記錄；Burida 載入 934 檔。兩個 MO2 程序均正常結束。`repairs/kardia_full_validation.json`、`repairs/kardia_null_texture_patch.json`、`repairs/kardia_model_inventory.json` 和 `repairs/backported_esl_support_audit.json` 保存補丁、模型及版本證據。這仍是靜態資料修正，沒有宣稱遊戲內外觀已驗證。

## 動作來源補充稽核

`repairs/pose_preset_closure.json` 核對兩包的實際選用預設：每包 1,134 個 GP、405 個 Colly 動作，都能對上 FNIS 定義、IDLE 事件和已安裝 HKX。可選純動作版完整保留原 IDLE／ANIO 的編號、旗標及資料，但尚未完成其獨立完整 MO2 配置與生成補丁整合，也不等於恢復戒指／法術或驗證遊戲播放。

`repairs/oldfire_upstream_comparison.json` 證實兩包太刀插件與[作者檔案 419988](https://www.nexusmods.com/skyrimspecialedition/mods/99063?tab=files&file_id=419988)逐位元組相同。`repairs/oldfire_payload_static_audit.json` 另外發現 39 份動畫內的 `$JTUI`、`$THzp`、`$Zxyingzhi01` 缺少選用的 INI 定義。三個名稱在[作者列出的前置庫](https://www.nexusmods.com/skyrimspecialedition/mods/92910)原檔 395249／517205 中都有精確定義，合計五個入口法術編號。Payload Interpreter 的原始碼以原生檔案系統載入設定並依名稱查找，支援這項缺件判斷；參考提交 `5362647070a18737650039941c3d012171878682`。

兩個作者前置版本分別檢查 140／157 筆記錄，都有三筆原生診斷：無效聲音型別、NULL 的任務別名法術、缺失 PERK 能力。1.3 的 39 份 OAR JSON 中另有一份截斷而無法解析。型別圖顯示五個入口法術的記錄依賴只有 16 筆且自身沒有這三筆診斷；但原始 VMAD 還有不一致的主檔索引樣本。原始整庫仍未啟用，來源證據在 `repairs/oldfire_dependency_source_audit.json`，主資料庫 `upstream_dependency_audit` 明確記為「僅調查」。以下限定候選另有序列化、腳本、動畫及完整環境證據。

## 限定太刀受擊支援候選

兩包各建立 `Database katana support candidate` 獨立配置，僅加入太刀動畫實際呼叫的 `$JTUI`、`$THzp`、`$Zxyingzhi01`。五條指令與入口 SPEL 均取自作者 1.0.0 原檔；其依賴閉合為 16 筆原記錄，配合兩份原始 DAR 條件和 97 份相同版本的作者 HKX。現有 OAR 支援舊 DAR 條件格式，相關條件的 MGEF 編號也已逐項對上候選。

xEdit 原始碼及實測確認：超出主檔數量的索引會被容錯解析為自身。因此「零診斷」本身不足以證明原始引用正確；單純重存也沒有改變這些欄位。本候選經 xEdit 的型別連結重設 12 個 `04xxxxxx → 03xxxxxx` 自身引用，全部保留完整 24 位元物件編號，並逐位元斷言其餘記錄欄位、旗標、編號及主檔清單不變。xEdit 匯出省略的一個零值 KSIZ 亦補回，以維持原欄位資料。修改狀態重設方式曾使 4.1.5f 匯出觸發 GRUP 大小斷言；使用保留修改狀態的副本匯出後成功，失敗與成功日誌均保留。

另從 BSA 抽取三個不同 SHA 的 `magicCastAnotherSpellScript.pex`，以官方 Champollion 1.3.2 同時反編譯及輸出組譯。三份 `OnEffectStart` 邏輯在排除大小寫、註解與空白後完全相同；預設 `AimAtTargets=False`，使用 VMAD 的 `CastSpellName` 從施法者施放，沒有額外的檔名或動態 FormID 查找。實際 VFS 選中的原版腳本雜湊也與已核對版本一致。這僅建立該函式的語意等價證據，沒有把三個不同檔案泛稱為整個模組相同。

兩包已完成原生和完整 MO2 檢查，候選均為 17 筆記錄、零診斷。Burida 載入 935 檔、處理 2,061,573 筆環境記錄；TuLED 載入 1,018 檔、處理 2,219,822 筆。每包 101 個支援檔案雜湊均與候選相同，全部七個太刀所用巨集名稱都有設定，五個新增呼叫都指向存在的 SPEL；兩份動畫條件指向存在的 MGEF。兩個 xEdit 與 MO2 均正常結束。

候選保留作者的 VMAD 版本／Object Format 宣告，並沒有測試引擎對這些宣告的實際接收、動畫播放或連續受擊行為。原 `EldenRingSkyRim_OLDFIRE.esp` 的缺失視覺等其他診斷仍保留，Synthesis 的既有 20 筆來源診斷也未宣稱因此修好。候選只在上述獨立配置啟用，原包、既有預設啟動配置及完整作者 God of War 模組都未替換。

本節證據均在 `repairs/oldfire_katana_support/`：`preparation.json`、`normalization_differences.json`、`resource_closure.json`、`full_validation.json`。兩包 VFS 探針在 `repairs/probes/`；原版腳本的組譯、反編譯及來源清單在 `repairs/oldfire_dependency_graph/script_audit/`。資料庫新增 `bounded_dependency_validation` 和 `script_equivalence_evidence`。
