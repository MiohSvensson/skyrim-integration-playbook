# 正式 LOD / CPU 草地子進程交付

此目錄僅準備及記錄 Database 內的工作；本研究代理沒有啟動 MO2 或任何 GUI。舊研究保留在 `../runtime_layout/lod_update/`，此處是 parent 實跑使用的執行層。

## CPU smoke：先刷新、再由 parent 啟動

`prepare_smoke.py --profile "Unified Build"` 重新解析目前 profile、物化 providers、header/master/light flags 和實際 plugin 順序，生成 `smoke_manifest.json`。讀取之前與之後都核 profile/來源未變。不能沿用舊時間點的 plugin index；FasterNGIO 固定使用的 TESWorld commit `763aee7622b336e05bf33893a372e3382b2431a4` 之 `PrepareLoadOrder` 依實際列表分別計 full/light slot，此計算法與原碼對照在 `source_evidence/`。

此快照 Unified Build 有 1074 plugins，Wyrmstooth full slot `18`、Glenmoril `19`；這些只是目前觀測，下一次準備會重新計算。完整 world identity → runtime FormID、final full WRLD source、CELL/LAND slot override chains、所有 plugin SHA 都在 manifest。

兩個最小對照格均為 Tamriel：

| case | XY | 原 provider cache 的實測 | 此快照最終 LAND | 必須檢查的結果 |
|---|---|---|---|---|
| positive | -1,-1 | 16,815 blades，合法單段 CGID | Update.esm | inspect 為 LAND、blades > 0；CPU rejection 後新 CGID 仍 > 0，結構完整 |
| empty | -1,-31 | 0 blades（57-byte legacy group，0 blocks） | Skyrim.esm | inspect 為 LAND、blades = 0；明確 `--write-empty-cells` 後新檔必須恰為 `00 00 00 00` |

這是由原 cache 確定的控制格，並非假定新 source 永遠不變。current inspect CSV 若不符合預期，child 停下保留差異，不能把控制格重新標籤成另一類繼續。它還核 expected CELL full FormID、csv status、單一 world/cell 檔名、CGID 全字段/stride/payload/SHA。格式通過不表示遊戲內渲染通過。

由 parent 執行（本代理沒有執行此命令）：

```powershell
python "Database/integration/research/lod_update/prepare_smoke.py" --profile "Unified Build"
python "Database/integration/run_mo2_child.py" --profile "Unified Build" lod_cpu_smoke "E:/stock/Skyrim collection/Database/integration/research/lod_update/faster_ngio_child.py" --manifest "E:/stock/Skyrim collection/Database/integration/research/lod_update/smoke_manifest.json" --run-name cpu_smoke_NEW
```

`faster_ngio_child.py` 強制 usvfs_x64、私人固定 SHA exe、CPU backend、vanilla placement、新 out、空 cache overlay；不允許 GUI、`--overwrite` 或其他 executable。run 內保留完整 `manifest_used.json`、每階段 argv/PID/log、VFS proof、CSV、CGID 與 result。parent wrapper 也會在自己的 validation 目錄記錄 MO2 執行證據，全部仍在 Database。

**已知 smoke001 前置失敗**：Python 3.13 `Path.is_file()` 可能走未被 hook 的 `GetFileInformationByName`，不能以此判斷 virtual plugin 缺失。child v2 已移除該門檻，改用既有 `vfs_common.file_identity` 的 CreateFileW/handle FileID 比較，再 long-path open/SHA。新錯誤列出 virtual path、expected physical provider 和原始 Win32 例外；零 phase 的前置失敗標記為 `PRECHECK_FAIL_GENERATOR_NOT_STARTED`，不是生成器失敗。001 原始結果保留。

工具 release/source/單純 CLI help 的來源證據在舊研究目錄；現在執行用的 binary 已私人實體複製到此目錄 `tools/FasterNGIO_1.6/`。不能用 GPU backend：該固定版本會經 Windows Known Folder 建立真 LocalAppData shadercache，環境變數不能可靠改掉；CPU 路線不進入 shader constructor。

## 私人工具

`tool_staging_manifest.json` 記錄每個 source/target、SHA 和私人 preset 重定向。FasterNGIO 11 檔 / 52.7 MB；DynDOLOD 1053 檔 / 144.2 MB；xLODGen 46 檔 / 55.0 MB。都是私人 copy，nlink=1，沒有建立硬連結或更動原工具屬性。

原 DynDOLOD Cache/Export/Summary/Logs、原 xLODGen logs 不作當前輸入。初次複製發現 xLODGen 把 88 個舊 `LODGen_Terrain_*.bin/.txt` 放在 Edit Scripts 根層，其中有舊 `C:\Modding 2` 寫出路徑；只有本目錄自己的私人副本被移到 `quarantine/obsolete_private_xlodgen_exports/`，原 TuLED 一律不動，ledger 為 `obsolete_private_exports_moved.json`。正式工具 active 目錄不含這些舊 export。

`stage_private_tools.py` 不啟動工具，使用 exclusive create、reparse/link/hash guards。工具/preset 已有 intentional changes 時不會覆蓋；不要在某個 GUI 正寫設定時重做 staging。

## Terrain / TexGen / DynDOLOD：可執行 argv 與 batch

`prepare_lod_batch.py` 寫出新 batch 的 frozen runtime plugins/INI 副本、私人 cache/temp/backup/log/output paths、精確 argv、preset 及 source hashes；它不改 profile、不啟動程式。每個 batch 從 `tool_staging_manifest.json` 複製並逐檔雜湊固定自己的完整 DynDOLOD 或 xLODGen 工具樹；DynDOLOD preset 只修改該 batch 的副本，不再改寫共用 staging preset。`lod_tool_child.py` 啟動前重新核對完整工具檔案集合、每檔 SHA/nlink、batch 內 executable 與 preset，拒絕缺失或額外未固定的工具檔案。沒有虛構的 CLI world 選擇旗標：world 列表會準備在 batch 私人 DynDOLOD preset，parent 仍要在工具正式 UI 核對選取。TexGen/xLODGen 的 UI 選項同樣由 parent 確認。

舊 terrain Wyrm 例子保留在 `batches/terrain_wyrm_preview_001/batch_manifest.json`，僅作歷史證據。它使用修改前 schema，沒有逐 batch `tool_root`／`tool_files`，目前 child 會拒絕它；profile 也已改變。正式執行必須用新 batch name 重新準備，不能沿用或修補該 preview manifest。

```powershell
python "Database/integration/research/lod_update/prepare_lod_batch.py" --stage terrain --name terrain_wyrm_NEW --profile "Unified Build" --world WyrmstoothWorld --world Dimfrost
python "Database/integration/research/lod_update/prepare_lod_batch.py" --stage texgen --name texgen_NEW --profile "Unified Build"
python "Database/integration/research/lod_update/prepare_lod_batch.py" --stage dyndolod --name dyndolod_wyrm_NEW --profile "Unified Build" --world WyrmstoothWorld --world Dimfrost --grass off
python "Database/integration/research/lod_update/prepare_lod_batch.py" --stage dyndolod --name dyndolod_glen_big_NEW --profile "Unified Build" --world zRevNamiraRealm --world zRevDreamsleevesWorld --grass off
python "Database/integration/research/lod_update/prepare_lod_batch.py" --stage occlusion --name occlusion_NEW --profile "Unified Build" --world Tamriel --world WyrmstoothWorld --world Dimfrost
```

這些是模板，不能跳過前置狀態：

1. 先完成/安裝全部 feature + FC + Glen gameplay patches，保存最終字段證據。
2. 判定 MoonAndStar 的 35 LAND 最終來源。需要的 terrain 先生成/安裝，保留無受影響的原地形。
3. TexGen 前須停用舊 TexGen output（目前 T5881 是啟用）；preparer 會拒絕在它仍 active 時繼續，不會擅自改 profile。生成後驗證並安裝新 TexGen。
4. 增量 DynDOLOD 須把私人既有 DynDOLOD Output 加回最終 load order。現在 Unified Build 的 T4621 為停用、沒有 DynDOLOD.esm/esp，所以當前不符合 update 前置；preparer 會停止。DynDOLOD.esm 應位於其他同類 master 之後，DynDOLOD.esp 應在其他普通插件之後，若有 Occlusion.esp 則在其緊接最後。
5. 每個 batch 成功/字段檢查/安裝後才準備下一批，讓它繼承上一批的新 generated plugins。分世界產物覆蓋在新的私人 output mod，原 source 不改。
6. `--grass off` 不宣稱新世界草 LOD 已完成；等整個指定世界的新 cache coverage 經審核後可用 `--grass current --grass-evidence <JSON>`。只通過兩格 smoke 不足以接受整世界 cache，contract 要求 CURRENT_GRASS_BATCH_VERIFIED、files_validated、worlds 與同一 plugins hash。原 Tamriel cache 可明確選 `--grass retained`，但保留其不完全符合新增地形/建物的限制；它不能用來涵蓋新世界。
7. 全部 terrain/object 批次安裝後做最終 occlusion。上例只列三個世界，正式需補全部本次受影響世界。完成後 audit 非選定世界資源/generated records/swap data 仍保留，以及最終 CELL/WRLD gameplay 沒被生成器回退。

由 parent 經 MO2 啟動已準備的 batch：

```powershell
python "Database/integration/run_mo2_child.py" --profile "Unified Build" lod_BATCHNAME "E:/stock/Skyrim collection/Database/integration/research/lod_update/lod_tool_child.py" --manifest "E:/stock/Skyrim collection/Database/integration/research/lod_update/batches/BATCHNAME/batch_manifest.json"
```

`lod_tool_child.py` 只允許私人 TexGenx64/DynDOLODx64/xLODGenx64，要求真正 MO2 VFS，對全部 plugin 做 FileID/SHA。這三個是需要 parent 控制的生成 GUI，**研究代理不執行此 child**。它只標記 process exit，絕不把 exit0 當作 generation PASS；必須看每世界成功訊息、輸出檔及 fresh xEdit/字段結果。

## 官方證據與實際邊界

作者的 [Command Line Argument](https://dyndolod.info/Help/Command-Line-Argument) 指出支援 xEdit path switches；此處 argv 使用 `-sse -d -p -m -i -o -t -c -b -r`，分別固定 game Data、plugins、INI、output、temp/cache/backups/log。額外 cache/backup/log switches 亦見 [xEdit Command Line Switches](https://tes5edit.github.io/docs/2-overview.html#CommandLineSwitches)。runtime snapshot 是此 profile 實際給遊戲的檔案副本，放在 batch 自有 runtime 目錄，沒有把任意舊 profile 當遊戲設定。

[Updating](https://dyndolod.info/Updating) 支援已安裝 output 的分世界 update，並提醒 CELL/WRLD forwarding 可能要手動處理；[Advanced Mode](https://dyndolod.info/Help/Advanced-Mode) 說明 eligible LODSettings/world UI 與私人 output 路徑；[Occlusion Data](https://dyndolod.info/Help/Occlusion-Data) 要求在組合後的 terrain/object 後完成。詳細來源 inventory、低空間 caps 與無遊戲 offline 候選限制仍在舊研究 `generation_plan.json`、`offline_grass_plan.json`。

所有 source parsing、private staging、manifest 與 Python syntax checks 已完成；正式 smoke/generation 的成功與否以 parent 實跑 retained logs 為準。
