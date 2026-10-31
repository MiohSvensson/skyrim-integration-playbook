# 低空間完整執行環境方案

正式基底採 TuLED，保持其戰鬥、身形、動畫與視覺框架。本文及 JSON 是建立環境的來源映射與空間證據；本子任務沒有啟動遊戲、MO2、生成工具或 GUI，也沒有向三個原包建立連結或寫入。

## 可直接消費的輸出

- `root_payload_mapping.json`：完整 game 檔案、Root 提供者及贏家、官方 SKSE 覆蓋、overwrite 位置、工具路徑與寫入位置、共用白名單和副本預算。
- `runtime_measurements.json`：三包目前 game／overwrite／研究鏡像的實際目錄走訪，以及既有資料庫內的選用模組檔案及生成產物統計。體積均為邏輯長度，未宣稱實體配置。
- `file_staging_validation.json`：限定合成檔案的八項 NTFS 驗證，全部 PASS；`safe_files.py` 可供中央建置程式參考。
- `skse_binary_comparison.json`：官方 2.0.20、TuLED 和 Anno 三個 SKSE 根檔案的位元組／SHA 對照。
- `primary_sources/manifest.json`：與本機版本相同的 BodySlide 5.7.0、PGPatcher 0.9.9.5、Pandora 4.0.4 原始碼／文件的固定提交、下載 URL 和 SHA。

## 完整資源範圍

| 包 | 選用模組庫檔案 | 現有研究鏡像模組檔案 | 原 overwrite 檔案 | 原 overwrite 邏輯體積 |
| --- | ---: | ---: | ---: | ---: |
| Anno | 457,265 | 3,993 | 27,488 | 23.59 GB |
| Burida | 1,039,312 | 4,949 | 4,905 | 243.01 MB |
| TuLED | 486,065 | 4,960 | 5,156 | 253.14 MB |

原 game 走訪：Anno 12,104 檔／16.54 GB（含許多工具）；Burida 37 檔／13.63 GB；TuLED 38 檔／13.84 GB。現有部分鏡像缺少大量鬆散資源與根目錄執行環境。TuLED 全 game 映射另加入既有已驗證 coherent stock 資料中的缺項，共 44 檔；仍需中央建置依實際來源逐一核對。Data 中原版插件使用私有副本，既有驗證 BSA 可共用。

Anno overwrite 的 meshes 約 23.29 GB，不能遺漏。正式基底 TuLED 的原 overwrite 也完整保存為一個專用匯入 mod，保留原最高優先序；新 overwrite 從空目錄開始。原 Root／歷史日誌不應當成一般 Data 輸入。

## 共用與私有檔案

新版規則取代最初「僅 meshes/textures/sound/music/video 可共用」的保守盤點。副檔名白名單詳見 JSON，涵蓋大型資源、僅讀 ShapeData、除錯符號、原圖、影片、字體、SWF 和封存。所有 Root 檔案一律私有，其餘未知副檔名預設私有；插件、PEX／PSC、設定、DLL、EXE 和腳本沒有列入共用白名單。

| 包 | 私有檔案數 | 私有檔案內容量 | 僅讀共用 ShapeData |
| --- | ---: | ---: | ---: |
| Anno | 48,573 | 2.45 GiB | 42.74 GiB |
| Burida | 53,150 | 2.53 GiB | 38.78 GiB |
| TuLED | 40,446 | 2.45 GiB | 17.44 GiB |

TuLED 私有內容精確為 2,631,926,268 bytes；共用 445,619 檔／473,315,735,965 bytes。此數字是完整選用 mod 庫的檔案長度，尚不包括 NTFS 目錄／連結配置、game 私有檔案、外部工具、新增模組和新生成產物。game 私有映射約 406.64 MB，選中的 Root payload 約 35.94 MB（改用官方 loader 後更小）。

硬連結共用內容、屬性和安全性，沒有寫入時複製。此次合成測試證實：未斷開連結而寫入會改到來源；原子替換為獨立檔案後再寫入，來源 SHA 不變。私有檔案檢查要求 link count=1；目的地超出允許目錄或經過 reparse point 會被拒絕。這個 helper 不會攔截第三方工具的任意寫入，因此所有可寫來源仍需事先成為獨立副本。若唯讀來源屬性令替換失敗，應拒絕啟動該工具並建立新的私有路徑，不可對共用檔案 chmod 或修改 ACL。[Microsoft 技術依據](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions)。

## TuLED 根目錄

JSON 保存 114 個原 Root 提供者條目。原 modlist 是從高優先序向低優先序保存，較小 list_order 會贏；重建時由較大值向較小值套用。Root payload 全部複製為獨立檔案，無需 RootBuilder。

- SKSE 三個核心根檔案使用官方 2.0.20。TuLED 原 loader 為 963,584 bytes／SHA `c1743055...`，與官方的 224,256 bytes／SHA `fecc9f5d...` 不同；Anno 原 loader 與官方完全相同。兩個核心 DLL 三方一致。原 TuLED loader 保留在 ledger，不執行；JSON 的贏家直接指向官方包內已驗證檔案。官方明確提供 2.0.20 對應 1.5.97。[SKSE 官方頁](https://skse.silverlock.org/)。
- Engine Fixes Part 2：私有 `d3dx9_42.dll`、`tbb.dll`、`tbbmalloc.dll`，保留 TuLED 的來源版本。
- Creation Kit／CKPE 的 Root 不落入遊戲根目錄。其 tbb、winhttp 若照原 modlist 盲目重放，會覆蓋另一套 runtime 檔案；來源保留供獨立工具環境使用，這不等於已證明原 RootBuilder 實際採用了相同規則。
- TuLED Reshade 根 payload 以私有副本保存，設定的搜尋路徑、preset 路徑及寫入位置須改成新根目錄。歷史 `.log` 不作 runtime 輸入。
- Burida 的 `dinput8.dll` 為 x64 Ultimate ASI Loader 8.2.0，`S33BUR5CH.asi` 為 x64、版本 1.0.0.0；兩者不在官方 SKSE 2.0.20 包內，也不在 TuLED 選用 Root，沒有合併依據，僅保存來源稽核，不匯入正式遊戲根目錄。

乾淨 MO2 的 app、profiles、INI、saves、overwrite、cache、logs、tmp 都須使用 Database 路徑。不要搬用原 MO2 內的 C:/Modding 2 工具參數。環境變數只設定子程序 TEMP/TMP；不全域替換 USERPROFILE／APPDATA 或改機器登錄。Windows 原生 known-folder API 不必然遵從環境變數，工具仍需各自指定位置。

## 生成工具與可重用條件

本機版本已讀取 PE 版本：BodySlide 5.7.0、Pandora 4.0.4、PGPatcher 0.9.9.5、DynDOLOD／TexGen 3.0.0.197、xLODGen 4.1.4。沒有更新這些版本。

BodySlide 原 Config.xml 仍指向原 TuLED game、Body Slide Output 和骨架路徑。必須先私有化並改為新路徑。5.7.0 固定提交證實 `-gbuild`、`-t`、`-p`、`-tri` 支援；可對經審查的新增服裝群組生成到全新輸出。保持 CBBE 3BA 和既有 preset 時，原身形輸出可作基底；新增服裝須驗證預生成 NIF／TRI 相容，不需要為新增一件服裝就整包重做。[同版本程式](https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/ca5c2fa30e4ee57793906637b69eba48b4966b85/src/program/BodySlideApp.cpp)。

Pandora 必須顯式指定 `-o` 到新輸出，並用 `--tesv` 指向新 game root；其作者文件明確說明 MO2 的自動 output 選項仍可能寫回來源。ActiveMods.json、PreviousOutput、Engine.log 和 executable tree 都是私有的。只有已證明沒有改變 graph／FNIS 自訂事件／配對動作輸入時才重用舊行為輸出；OAR／DAR 替換仍需逐模組判斷。[4.0.4 文件](https://github.com/Monitor221hz/Pandora-Behaviour-Engine-Plus/blob/ffef0811a1b7cff5a156201428a2ebf29f1525c3/README.md)。

PGPatcher 0.9.9.5 用 executable 旁的 `cfg/user.json`，必須設定 `params.game.dir`、`params.modmanager.mo2instancedir`、`params.output.dir`，並關閉重複 ZIP 輸出節省空間。其 CLI 此版僅列 autostart/highmem/console，不能套用別版的 `--output` 參數。所有 cfg、logs/cache 和 fresh output 都私有。原 PGPatcher.esp／NIF／材質引用作為同一組保留，不能從另一包整套疊入生成輸出。[同版本設定程式](https://github.com/hakasapl/PGPatcher/blob/bf2333af2077384102bd250969ede87eb4c99367/PGPatcher/src/ParallaxGenConfig.cpp)。

DynDOLOD 產物代表生成當時的資源與載入順序；新增 mod 不自動等同必須全部重做。保留原世界的贏家和產物，對新增世界採作者自帶 LOD 或官方更新流程，再作記錄衝突檢查；若改到原世界物件、地形、LOD 資源則處理受影響的世界。工具 Edit Scripts/Export、設定、日誌與輸出皆私有，`-D:`／`-o:` 改到新視圖及新輸出。[作者更新說明](https://dyndolod.info/Updating)。

## 空間門檻

TuLED 既有輸出邏輯量：BodySlide 11.305 GiB、DynDOLOD 13.720 GiB、ParallaxGen 7.903 GiB、TexGen 0.393 GiB、xLODGen 3.513 GiB、Pandora 0.019 GiB、Synthesis 0.066 GiB、VRAMr 14.752 GiB，連同少量 SKSE 輸出共 51.672 GiB。這些數字不能當成新輸出上限。

在原視覺框架和世界贏家保持一致、僅新增有相容證據的獨立內容時，共用原輸出可以省去完整重建用量。若必須重建，先預算該工具的暫存、fresh output 與仍要保留的上一版；新產物驗證前不能先刪舊產物。每一批開始前重新核對 E 槽自由空間，仍保留中央設定的 32 GiB 工作額。未啟動遊戲，因此沒有播放、碰撞、外觀或載入穩定性的 runtime 結論。
