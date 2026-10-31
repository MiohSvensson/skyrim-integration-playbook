# 整合基底決策：TuLED

主代理已採納 TuLED 的選用配置為正式內容與框架基底。此決策不代表原包沒有既存問題，也不代表遊戲內驗證完成。

| 包 | 全部 mod 資料夾 | 選用啟用 mod | plugins.txt 啟用插件 | 已解析 mod 插件 full / light |
| --- | ---: | ---: | ---: | ---: |
| Anno | 1669 | 1481 | 1437 | 196 / 1239 |
| Burida | 2431 | 2265 | 930 | 155 / 774 |
| TuLED | 2395 | 2269 | 1011 | 127 / 883 |

表中 full/light 只計有模組提供者的已解析插件，不含五個基本主檔及隱式 CCC／依賴閉合，不能作最終載入數。原始 modlist/plugins 已重新讀取並保存 SHA；TuLED 的 2,271 個加號列中有兩個 _separator 標題，排除後為 2,269 個真實 mod，與資料庫一致。

TuLED 已有 LOTD／LOTD_HUB、Unslaad 3.0.4、Darkend 及任務附加、Inigo／Kaidan／Auri／Xelzaz；Burida 沒有整套 LOTD／Unslaad／Darkend。選 TuLED 可保留其現有展示與收集補丁鏈，並保留更多 full 插件空間。
版本更正：TuLED 的 LOTD 資料夾標籤為 v6.10.0，但 Anno 與 TuLED 的實際 TES4 SNAM 都是 v6.7.2。plugin_integration 對兩檔 122,968 筆記錄逐欄位比較，除 17,061 處文字欄位外無結構或非文字差異。應按實際相同主檔內容配補丁，不能依資料夾名稱判版本。證據：../plugin_integration/lotd_selected_payload_comparison.json；本報告 JSON 另保存原始標頭路徑及 SNAM。
Burida 與 TuLED 共有 720 個能比對提供者的同名插件，其中 685 個 SHA 完全相同，35 個不同。另有 1,850 對完整 mod 樹已證明相同；同名不等於同一版本。具體 35 項與來源路徑在 JSON。
直接聯集有 2,415 個插件名稱，其中 347 個名稱至少一個來源是 full 或無法解析的非 mod row；這不是精確引擎數量，仍足以排除原樣全啟用方案。

## 保留與改選

- **engine**：1.5.97.0 + SKSE 2.0.20 for all three source packs; coherent newer official data masters/archives must use the validated Database consistent stock set.
- **combat**：Keep TuLED Attack MCO-DXP 1.6.0.6 + SCAR/Stances + Valhalla 1.3.3 + Precision 2.0.4 + OAR 2.3.6. Do not enable Anno BFCO alongside MCO. Preserve only explicitly verified MCO variants of donor animations.
- **body**：Keep TuLED CBBE 2.0.3/CBBE 3BA 2.48/CBPC 1.6.4 skeleton, physics configuration and built body assets as one coherent set; donor armor must match 3BA or have verified fitting output.
- **perks_magic**：Keep Ordinator 9.31, Odin 3.1.3, Apocalypse 10.2.1 source lineage and matching compatibility patches. Do not enable Anno Vokrii and its Apocalypse patch in parallel.
- **renderer**：Keep Community Shader-Jiaye-Exp, source meta d2026.1.21.0; exact build version is not proven by this date-like meta version. Keep matching Slama/LED shader features and PBR source set. Do not overlay Anno CommunityShaders_AIO or another core DLL merely for a later date.
- **weather**：Keep NAT III Weather 3.1.1.0C-F and NAT.CS III 2.0.0.0. Do not add Obsidian Weathers as a second active weather overhaul.
- **lighting**：Keep TuLED [LED]True Light + [SLAMA1210] Ambient Templates 2.3 + Window Shadows Ultimate. Burida Lux Via/Lux Orbis and their meshes/patches are not part of the chosen TuLED lighting/location baseline.
- **start_survival**：Keep AlternatePerspective and iNeed/iNeed Extended lineage. Anno Live Another Life and SunHelm are inactive alternatives; Campfire can be an optional independent addition only with dependency/keyword/script winner checks.
- **cities**：Keep TuLED RedBag Falkreath/Pinewatch and its existing city/terrain source baseline. Do not import Anno Northern Roads, extensive alternate cities, navmesh and all matching patches as one overwrite block.
- **adult_framework**：Keep TuLED SexLab 1.63 and exact associated body/skeleton/PapyrusUtil/JContainers lineage. Burida-only gameplay modules must be imported with a complete typed/soft dependency group, architecture fixes and regenerated behavior; preserve tested repairs by exact input hash.
- **generated**：Keep existing output only as an immutable input/reference where still valid. Synthesis must be rebuilt for final sources; behavior output must reflect added animation definitions. LOD/PBR/body generation is scoped by actual changed inputs. Never stack all three packs generated outputs.

## 獨有任務的 full 增量

Anno 的 Glenmoril、Wyrmstooth、Forgotten City、Moon and Star、WorldInPainting ZeroHall，對 TuLED／Burida 的硬主檔閉合都是新增 5 full；UF6 是另 1 light 並依賴 ZeroHall。此數字只涵蓋根與硬依賴，還要逐一核對入口、資源、翻譯、相容補丁與 LOD。
反過來以 Burida 為底，新增 TuLED 的 LOTD、LOTD_HUB、Unslaad、Darkend、Darkend Quest Addon 就要 5 full 及 _ResourcePack.esl 的 1 light，另有大量展示補丁及資源鏈；因此 TuLED 更符合最多可驗證內容的目標。
Wyrmstooth PBR 是額外 1 full，Glenmoril Redux 音樂版也是額外 1 full，均非主模組的硬依賴。不能把所有美術與音樂附加算進「5 full」的承諾。
既有 Anno 修復版 UF6 應按其原輸入 SHA 使用；導入不等於原包城市補丁也自動相容。

## 語言、INI 與美術

原設定位置：`E:\stock\Skyrim collection\TuLED\File Mod Skyrim SE\profiles\TuLED`。Skyrim.ini 和 SkyrimCustom.ini 均使用 `sLanguage=ENGLISH`，MO2 介面為 en；已有中文字型、Chinese Localisation 和 DSD，同時還有來源韓文模組譯文。保留英語 Strings 檔名及現有翻譯層，不將單改 sLanguage 當成完整漢化。
原 profile settings.ini 設定 LocalSaves=true、LocalSettings=true；整合副本應把本地存檔留在 Database 的 profile。原 SkyrimCustom.ini 的截圖路徑仍為 D:\Game\Steam，整合副本須改為 Database。
SkyrimPrefs 與啟用的 SSEDisplayTweaks 設定是 2560×1440、無邊框視窗；VSync=false、tearing=true、flip_discard、無前景 FPS 上限，載入畫面 60。原版 TAA／SAO／SSR／體積光開關關閉。這些是原設定事實，並非效能測試。
美術核心：Community Shader-Jiaye-Exp（meta d2026.1.21，不能據此判為官方某穩定版），slama cs preset_20260121_Real（SettingsDefault／Theme／User + Slama pp Real JSON），NAT III Weather 3.1.1C-F + NAT.CS III 2.0，[LED]True Light + Ambient Templates 2.3 + Window Shadows Ultimate。
TuLED 沒有選用 Burida 的 Lux Via／Lux Orbis；導入 Burida 內容時要排除其整套照明 meshes 和補丁覆蓋。

## 生成產物的重用邊界

| 來源 | mod | 原檔案邏輯大小 GiB |
| --- | --- | ---: |
| Anno | PGPatcher_Output | 13.136 |
| Anno | Pandora Output | 0.013 |
| Burida | Body Slide Output | 26.040 |
| Burida | DynDOLOD Output V2 | 13.505 |
| Burida | ParallaxGen_Output V2 | 6.211 |
| Burida | xLODGen Output | 1.983 |
| Burida | TexGen Output | 0.489 |
| Burida | Synthesis Patch | 0.068 |
| Burida | Pandora Output | 0.019 |
| Burida | SKSE Output | 0.001 |
| TuLED | VramR Output v | 14.752 |
| TuLED | DynDOLOD Output (상) | 13.720 |
| TuLED | Body Slide Output | 11.305 |
| TuLED | ParallaxGen_Output (1.01) | 7.903 |
| TuLED | xLODGen Output (1.01) | 3.513 |
| TuLED | Grass Cache | 1.644 |
| TuLED | TexGen Output (중,상) | 0.393 |
| TuLED | Synthesis Patch (1.01) | 0.066 |
| TuLED | Pandora Output | 0.019 |
| TuLED | PoserDataGen | 0.000 |

此表不是重建空間上限。大資源可保持來源重用；整合後的 Synthesis、動畫行為與受改動影響的身形、PBR、LOD 輸出必須逐項產生或核對。不能同時啟用三包的整套生成輸出。TuLED 原 Synthesis 未因 Burida 的重建紀錄而自動得到驗證。

作者依據：[BFCO 相容性](https://www.nexusmods.com/skyrimspecialedition/mods/117052)、[Vokrii](https://www.nexusmods.com/skyrimspecialedition/mods/26176)、[DynDOLOD 更新說明](https://dyndolod.info/Updating)。網頁於 2026-10-31 查閱；來源安裝版本仍以本機檔案為準。

本研究沒有啟動遊戲、MO2 或 GUI，沒有修改原包或共用資料庫。機器可讀證據與全部來源路徑見 base_selection.json。
