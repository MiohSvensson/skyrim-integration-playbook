# 最終 LOD、terrain 與草地的低空間更新方案

此交付包含唯讀來源分析、固定作者工具來源、機器可讀更新計畫與獨立 CGID 檢查器。沒有執行遊戲、MO2、xEdit、xLODGen、TexGen 或 DynDOLOD；只執行了不開視窗的 FasterNGIO `--help`。來源及原整合包沒有任何改動。

## 實際新增範圍

| 內容 | 實際 WRLD/地形情況 | 更新範圍 |
|---|---|---|
| Wyrmstooth | 2 個自有世界：WyrmstoothWorld、Dimfrost。各有作者 BSA 內 terrain/object LOD 與 LODSettings。 | 納入最終 object/tree/dynamic；terrain mesh 按輸入等價條件重用，紋理需比對最終框架。兩個世界需要草地 cache。 |
| Forgotten City | 沒有自有 WRLD。Tamriel 入口附近 9 CELL、25 REFR、8 NAVM，沒有 LAND。主要城市是內部 CELL。 | Tamriel 的新增/移動物件與 occlusion；沒有可獨立勾選的「FC 世界」地形生成。 |
| ZeroHall | 沒有 WRLD，也沒有 world children。 | 內部場景；不新增世界 LOD。 |
| UF6 | Small World `00UF6`，5 CELL、274 REFR、1 NAVM，沒有 LAND、LODSettings 或作者 LOD。 | 保留作者近景小世界；不能因有 WRLD 就擅自製作不存在的地形/LOD。 |
| Moon and Star | 沒有自有 WRLD。修改 Tamriel 43 CELL、1140 REFR、40 NAVM、**35 LAND**；另有 WindhelmWorld 1 CELL/1 REFR，使用 parent LOD。 | 若採用，Tamriel 的最終地形及物件都受影響；必須先決定最終 LAND winner，不能宣稱全部原 terrain/草地仍精確相同。 |
| Glenmoril | 15 個自有世界；14 個有作者 terrain/object LOD、LODSettings，AirshipExtRealm 沒有 LAND/LODSettings。另改 Tamriel 16 CELL/268 REFR/8 ACHR/8 NAVM，沒有 Tamriel LAND。 | 14 世界的最終 object/tree/dynamic，及 Tamriel 物件。僅 5 個自有世界未設 NoGrass 且有 LAND，需要 cache；其餘按作者 NoGrass 意圖。 |

`scope_inventory.json` 保存所有 world FormID、EditorID、flags、parent flags、record counts、作者 loose/BSA LOD 統計，以及 MoonAndStar 的 35 個 LAND 所屬 CELL/座標。LOD quad 列表僅是這些格子相交的最小範圍，沒有宣稱包含生成工具的邊界/gutter 依賴。

以上是來源範圍，**不是已完成的最終 winning-data 證明**。正式 profile/materialization/兼容 patch 完成後需重新解析最終 winners，包含其他任務、followers 及配件是否放置外部 STAT/TREE。

## 作者支援的增量路線

作者支援載入現有 DynDOLOD output，將同類型的 DynDOLOD ESM/ESP 排在其他同類插件之後，只選受影響世界重新生成，再把新輸出覆蓋到現有輸出上。可分世界分批；更新可能沒有轉送所有新 CELL/WRLD gameplay 變更，因此仍須做字段衝突檢查。這裡用獨立最高優先序輸出 mod 實現覆蓋，原檔不變。僅材質變更可用 Rebuild Atlas、僅模型變更可用 Execute LODGen；本案新增插件/物件應走正常選定世界生成，而不是直接重跑舊 export。[官方更新說明](https://dyndolod.info/Updating)

world 清單取決於可讀的 LODSettings、BSA 載入和工具 ignore list，不能按 Small World flag 單獨推定。自有 Wyrm/Glen 的 16 個作者 LOD 世界已有設定，TuLED 的 ignore list 沒有將它們排除。工具輸出必須指定在遊戲及 MO2 管理目錄之外；本計畫使用 `Database/workspace/lod_generation/`。沒有發明 world 選擇 CLI 參數，採正式世界清單/私人 preset。[Advanced Mode](https://dyndolod.info/Help/Advanced-Mode)

terrain 由 xLODGen 處理；DynDOLOD 不生成 terrain/water LOD。先確立最後 LAND、高度、水位、LTEX/TXST 和 full textures，再生成必要 terrain，才做 object LOD。原 TuLED 城市/世界框架仍是輸入基底；重建其受影響輸出不等於換掉框架。[Terrain LOD](https://dyndolod.info/Help/Terrain-LOD-and-Water-LOD)

Occlusion 在所有 terrain/object 批次安裝後再統一生成。現有 TuLED source 確有 Occlusion.esp，但此次快照 profile 將它停用；不可因此推論無 occlusion 需求。新插件放最後，並檢查其 CELL/WRLD gameplay 字段有無回退。[Occlusion Data](https://dyndolod.info/Help/Occlusion-Data)

## 原產物重用條件

author terrain mesh 只有在該世界 EditorID/LODSettings、全部貢獻 LAND 高度、CELL/WRLD 水位及相關 flags 與生成時相同時才可直接重用。terrain textures 還依賴 LAND layers/vertex colors/normals、LTEX/TXST 和 full texture bytes；若 TuLED 替換了這些材質，原作者 terrain textures 只能算作者原版外觀，不能稱為與整合框架精確匹配。新世界的作者 terrain mesh 可以先作有條件輸入，將必要 textures 按世界分批重建。

無受影響的原 TuLED 世界保留全部原資源；新輸出只在獨立 mod 覆蓋生成檔。每批比較非選定世界的資源、generated records、masters 及 swap/runtime data 是否保留。最終 xEdit 比較 CELL/WRLD gameplay 字段，只允許明確的生成字段更新。導航 patches 必須在 LOD 前完成並驗證；不能把含舊父容器的導航 patch 放到新 DynDOLOD/Occlusion 後面覆蓋生成字段。

## 草地：可避免啟動遊戲的新方案

原 TuLED 啟用的 GrassControl.ini 為 Use-grass-cache=true、Only-load-from-cache=true、DynDOLOD-Grass-Mode=1；舊 cache 沒有新增 Wyrm/Glen 世界。若直接保留此設定而不補 cache，需要草的新世界連近景草也不會自行生成。舊 cache 也不能因仍存在就宣稱在新增建物/35 LAND 變更後完全符合當前配置。草 LOD 應使用當前 precache；改變草記錄、模型、位置密度等會使它過期。[Grass LOD](https://dyndolod.info/Help/Grass-LOD)

目前可行的無遊戲候選是作者 **FasterNGIO 1.6**，可離線生成 NGIO-compatible CGID。已固定 commit `5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40`，下載官方 19,416,366-byte Windows release，SHA-256 與 GitHub asset digest 一致；`--help` 在 CREATE_NO_WINDOW 下 exit 0。尚未在最終 MO2 VFS 生成草地，不能稱為已完成的 end-to-end pass。[固定版本作者原碼](https://github.com/panthuncia/FasterNGIO/tree/5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40)

執行計畫在 `offline_grass_plan.json`。核心是全新 out、`--placement vanilla --reject cpu --write-empty-cells`、顯式最終 world FormID。CPU 避免 GPU constructor 以 Windows Known Folder 寫入真 LocalAppData 的 shadercache，符合工作檔全在 Database 的限制。新 overlay 要寫空格子的四 byte 空 cache，否則 omitted 檔案會露出下面的過時舊 cache。不要用 `--world all`，原 Only-pregenerate 清單沒有新世界；不要把舊 cache provider 當輸出。

需要新草 cache 的世界共 7 個：WyrmstoothWorld、Dimfrost、zRevNamiraRealm、zGHFelixRealm、zGHDunmerCampWorld、zGHCradleWoodsWorld、zRevDreamsleevesWorld。其他 Glen 世界保留作者 NoGrass。還應更新確實受改的 Tamriel 草地，或用可證明涵蓋影響區的有界範圍。FasterNGIO 1.6 不讀 GrassCacheHelperNG 的 ForceGrassWorlds 例外；TuLED 在 runtime 強制 WhiterunWorld 有草，因此不能盲目清理/重建此世界。離線靜態碰撞也不等於所有 runtime script/BOS swap 狀態。

`verify_cgid.py` 獨立解析全部新 CGID，檢查 filename/world/cell、model paths、flags、block counts、有限 bounds、stride、payload 長度和無尾隨資料，並保存每檔 SHA。三個原 Tamriel cache 已完整解析 PASS（44,305 blades）。另三個 Alftand 原檔是合法首段重複四次，僅記錄差異，不把它們標作新輸出 PASS、不修剪。生成後還需核對模型可讀性、預期 cell coverage、missing/unsupported 訊息及 placement CSV；結構通過不等於遊戲內渲染驗證。

## 工具與空間

本機 DynDOLOD/TexGen 均為 **3.0.0.197**，xLODGen 為 **4.1.4.0**。`primary_source_manifest.json` 固定 binary SHA、作者頁及原 INI。原 preset、rules、export 仍含 `C:\Modding 2`，包含 PathData、PathOutput、PathGrass、TerrainData、TextureAtlasMap、Resource；禁止原樣 Execute LODGen。私人工具複製後重定向設定，舊 Cache/Export 不作當前來源。

原 active 輸出邏輯大小為 DynDOLOD 13.72 GiB、xLODGen 3.51 GiB、Grass Cache 1.64 GiB、TexGen 0.39 GiB。原資源可共享唯讀，寫出全部獨立；不能就地改 hardlink。計畫時 E 約 101 GiB free，保留 32 GiB。`generation_plan.json` 用 **51 GiB operational caps** 覆蓋私人工具、TexGen、terrain、Tamriel/new-world LOD、temp/journal、可選離線草 cache；尚有約 18 GiB margin。這是停止閾值，不是生成結果大小保證。每世界串行、批次前重新量空間，長 writer 監控 reserve；不用生成期 ZIP，驗證後同碟移入獨立 output mod，避免 copy/zip 的額外峰值。

官方記載 `-sse`、`-d:`、`-p:`、`-m:`、`-t:`、`-o:` 的路徑形式；具體 argv 保存在 JSON。正式執行須在 MO2 子進程中核對 log 的 game、INI、plugins、BSA、output/temp paths；不能只相信命令字串。[Command Line Argument](https://dyndolod.info/Help/Command-Line-Argument)

## 交付

- `scope_inventory.json`：來源 world/LAND/LOD/grass 範圍。
- `generation_plan.json`：更新範圍、條件、順序、paths、space caps。
- `offline_grass_plan.json`：固定 FasterNGIO 1.6 的 CPU CLI 實作計畫與來源行號證據。
- `FasterNGIO_1.6/manifest.json`、`help_probe.json`：官方 binary/source digest 與無 GUI help 驗證。
- `verify_cgid.py`：獨立唯讀 CGID verifier。
- `primary_source_manifest.json`：七個官方作者頁、本機設定與 binary digest。

沒有把工具 help、來源解析或檔案 hash 等同於最終生成成功；所有尚未執行的 generation 及遊戲內驗證限制均保留在 JSON 中。
