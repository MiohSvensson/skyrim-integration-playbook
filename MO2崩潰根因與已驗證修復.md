# MO2 崩潰根因與已驗證修復

已查清該次 MO2 的 `C0000409` 崩潰來源，並完成最小變更對照。此結論針對工具崩潰；整合包內其他插件缺件與版本問題另列於《根因與修復進度》。沒有啟動 Skyrim，也沒有修改原整合包。

## 原因

Windows WER 轉儲 `ModOrganizer.exe.43052.dmp` 中，例外是 CRT 的 **FAST_FAIL_INVALID_ARG（子碼 5）**。雖然一般錯誤文字把 `C0000409` 稱為 stack buffer overrun，此次堆疊實際顯示的是無效參數終止。

關鍵路徑為 `UIAutomationCore` 的 C++ 例外 → FOMOD Plus 的全域 vectored exception handler → `std::cout` 寫入 `Exception caught: 0x` → `fwrite/isatty` → CRT 終止。

FOMOD Plus 安裝器啟動時無條件註冊這個全域處理器，並在過濾例外之前寫入標準輸出。這與轉儲中的失敗位置吻合。[固定提交的原始碼](https://github.com/aglowinthefield/mo2-fomod-plus/blob/76871ae46156eab889c8ba8d44b5875c8cbd4278/installer/lib/CrashHandler.cpp#L41)。當時的 Qt5／Qt6 插件拒載警告仍是獨立問題，不能據此取代已取得的崩潰堆疊證據。

## 修復與對照

在 `mo2_vfs/Anno/MinimalMO2` 建立完整隔離副本，唯一停用的程式檔為：

`plugins/fomod_plus_installer.dll` → `disabled_plugins/fomod_plus_installer.dll`

原 DLL SHA-256：`3cb43d0170dfd2b9f3bf248482743c2a26488149a58045d21dbb504ac0686355`。

其餘 **2,502 個程式檔案雜湊相同**。實際載入模組確認該安裝器沒有載入，`installer_fomod`、`installer_fomod_csharp` 與 FOMOD Plus scanner 仍在。這個方案暫停 FOMOD Plus 專用安裝器功能，保留標準 FOMOD 安裝器。

在這份最小修復副本中，xEdit 載入完整 Anno 選用環境，共處理 **2,680,985 筆記錄**；五份候選插件的 **2,480 筆目標記錄全部零診斷**。同時完成 UI Automation 查詢，再正常關閉，**MO2 結束碼為 0**。三個 Qt5 拒載警告仍存在，卻沒有重現該次崩潰。官方乾淨版 MO2 2.5.2 也已通過完整環境檢查，可作另一個選擇。

## 證據位置

- `rootcause/mo2_crash/dbgeng_analysis.log`：使用微軟官方 DbgEng 與符號的離線堆疊解析。
- `rootcause/mo2_crash/provenance.json`：轉儲來源、複本與雜湊；未上傳轉儲。
- `rootcause/mo2_crash/minimal_live_modules.json`：最小修復副本的實際載入模組。
- `repairs/minimal_mo2_fix.json`：檔案對照、來源提交與驗證結果。
- `repairs/Anno/verify-full-MinimalMO2/logs/xedit.log`：完整 xEdit 驗證日誌。

原包中的 MO2 尚未替換。上述已驗證副本及所有分析、符號快取和日誌都位於 Database。
