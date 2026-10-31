# MO2 虛擬環境與 xEdit 複查

更新日期：2026-10-30。這是對「先前 xEdit 結果是否由沒有經 MO2 啟動造成」的針對性複查，補充 `目前驗證報告.md`，不是遊戲執行測試或自動修復建議。

## 方法和範圍

三套包分別建立隔離的 MO2 2.5.2、配置和資料副本，全部位於 `Database/mo2_vfs/`。由該 MO2 啟動 xEdit 4.1.5f x64，探針確認進程注入 `usvfs_x64.dll`，並從虛擬 Data 實際開啟選定插件、計算雜湊。MO2 及 xEdit 的記錄保存在各包目錄。

這是**部分鏡像**：啟用模組的根目錄插件、根目錄 BSA 與 Strings 被複製，其餘模組散檔（例如 meshes、textures、scripts）未完整鏡像；停用模組主要保留目錄與中繼資料。MO2 自身及 overwrite 使用隔離副本。因此這能驗證本次插件及所載入 BSA 條件下的診斷，不能視為原始 MO2 虛擬檔案系統的完整重現，也不能證明遊戲內的行為。

全載入測試使用按所選配置建立的可載入插件清單；為讓其餘插件載入，排除了 Anno 一項、Burida 兩項已明確啟用但缺失主檔的目標。Burida 和 TuLED 各有 58 個 CCC 所列項目未在虛擬 Data 中找到；不能僅憑這點認定遊戲要求它們或實際載入它們。原始逐目標 Check for Errors 與全載入腳本是不同的檢查：前者只載入目標及主檔，xEdit 該模式會跳過 BSA；後者以 `-forcebsa` 載入 BSA，透過腳本逐欄呼叫 Check。兩者均未修改插件。

| 包／選用配置 | 虛擬 Data 插件候選 | 虛擬 Data BSA 候選 | 全載入插件檔案 | 日誌中 Loading Resources 的 BSA | 腳本遍歷記錄 | 腳本例外 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Anno / non chs | 1,529 | 327 | 1,517 | 326 | 2,680,997 | 0 |
| Burida / BGS REDive | 939 | 162 | 934 | 162 | 2,069,173 | 0 |
| TuLED / TuLED | 1,022 | 237 | 1,017 | 235 | 2,218,959 | 0 |

候選數是虛擬 Data 中可見的檔案數，並非啟用數。BSA 欄為 xEdit 日誌中的載入資源行數，不能推定候選中的每個 BSA 都會被遊戲載入。

## 針對先前結果的複查

| 包與目標 | MO2 逐目標結果：記錄／有診斷的記錄 | MO2 全載入及 BSA 腳本結果：記錄／有診斷的記錄 | 觀察 |
| --- | --- | --- | --- |
| Burida `hydra_slavegirls_retexture.esp` | 1,071／643 | 1,071／643 | 643 筆 NPC 記錄的 keyword 引用無法解析。 |
| Burida `AMatterOfTime.esp` | 9／8 | 未在全載入腳本中單獨複查 | 8 筆 HITME 警告。 |
| TuLED `HentairimMaleVoice.esp` | 121／120 | 121／120 | 音效分類引用無法解析：112 筆指向物件 `03C14F`，8 筆指向 `03C150`。 |
| Burida `HentairimMaleVoice.esp` | 121／0 | 未在全載入腳本中單獨複查 | 同一個插件在此配置下未出現這 120 筆診斷。 |
| Anno `Northern Roads - Hold Border Banners patch.esp` | 7／0 | 7／0 | 載入階段仍有 ACTI 被 REFR 覆蓋的警告，不能只看逐欄結果。 |
| Anno `(lilyrim)saiwaiqiusheng.esp` | 41／40 | 41／40 | 40 筆 HITME 警告。 |

這些已複查的結果與先前隔離檢查一致，因而不支持將這些特定診斷單純歸因於先前未經 MO2 啟動。FormID 的高位會隨載入順序改變；跨測試比較時須結合來源插件與低位物件 ID，而不是直接比較整個動態 FormID。診斷不等於已證實遊戲崩潰，也不代表應直接刪除或修改這些記錄。

## 同一插件、不同依賴版本

Burida 與 TuLED 的 `HentairimMaleVoice.esp` SHA-256 均為 `3c293ec39223ade030bb440c387bf298b40a1028262a336eeac1c8fbb60ac30d`，但其主插件 `IntelligentVoicedDirtyTalk.esp` 並不相同：

上述兩個檔案的各包雜湊均由注入 USVFS 的探針在對應虛擬 Data 中實際開檔計算，而非只依名稱推斷。

| 包 | 主插件 SHA-256 | 獨立二進位索引中 `03C14F`、`03C150` |
| --- | --- | --- |
| Burida | `04144e80c35c5e006f5450237259d3ba4289617866db75542b0df8a34907a403` | 各有一筆 `SNCT` 音效分類記錄 |
| TuLED | `52025d91076e704842fb6a19fc3e7cfc92438a3675754d51fd3120c1d8d9e20c` | 兩筆均未在該主插件的索引中找到 |

這與兩套配置不同的 xEdit 診斷相吻合，是主插件版本差異造成引用解析差異的強力證據。是否需要更換版本、製作補丁或如何處理，仍需先核對該模組的版本、授權和整體依賴；此處沒有進行修改。

## 證據與驗證

- `baseline/skyrim_research.sqlite` 新增 `mo2_vfs_runs`、`mo2_vfs_checks`、`mo2_cross_pack_evidence`；逐行保存數量、方法、原始日誌路徑及目標日誌 SHA-256。`baseline/plugin_records.sqlite` 保留獨立插件記錄索引。
- `mo2_vfs/<包>/logs/probe.json` 保存虛擬視圖的實際開檔和雜湊；`manifest.json` 保存鏡像時來源及副本的雜湊。`bsa_script/logs/xedit.log` 保存全載入腳本結果和載入警告；`xedit_checks/` 保存逐目標 xEdit 日誌。
- `mo2_vfs/<包>/MO2/logs/usvfs-*.log` 記錄對 xEdit 進程的注入及檔案 API 掛鉤，與探針中的模組載入證據互相補充。
- `cache/mo2_copy_validation.json` 保存複查後的配置檔和目標插件原件／副本雜湊比較。每包各七個配置檔檢查一致（兩側均不存在亦如實記錄）；本次抽查的目標及主插件副本均與原件和初始清單一致。這是範圍明確的抽查，不是對所有原始檔案的事後全量重讀。
- `import_mo2_results.py` 重新解析日誌、檢查目標與先前結果一致、交叉核對兩個主插件的記錄，再匯入資料庫；`validate_mo2_copies.py` 執行上述抽查。

本次未啟動 Skyrim，未對原始整合包插件做修復或改寫。所有本次研究副本、日誌和快取均置於 `Database`。
