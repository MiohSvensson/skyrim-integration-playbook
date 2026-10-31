"""Read-only source inventory and current-volume budget; never builds a mod view."""
import json
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
RESERVE = 32 * 1024**3
PRIVATE_EXTENSIONS = (
    '.esp', '.esm', '.esl', '.ini', '.json', '.toml', '.yaml', '.yml',
    '.xml', '.txt', '.cfg', '.config', '.psc', '.pex', '.dll', '.exe',
)


def main():
    connection = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    connection.execute('pragma temp_store=memory')
    deadline = time.monotonic() + 45
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 100000)
    connection.execute('create temp table active_mods(mod_id integer primary key)')
    connection.execute('''insert into active_mods
        select distinct pm.mod_id from profile_mods pm join profiles r on r.id=pm.profile_id
        where pm.enabled=1 and r.is_selected=1 and pm.mod_id is not null''')
    private_ext = ','.join('?' for _ in PRIVATE_EXTENSIONS)
    query = f'''select p.name,count(*),sum(f.size_bytes),
        sum(case when lower(f.extension) in ('.esp','.esm','.esl') then f.size_bytes else 0 end),
        sum(case when lower(f.extension) in ({private_ext}) then f.size_bytes else 0 end)
        from files f join mods m on m.id=f.mod_id join packs p on p.id=m.pack_id
        {{active_join}} group by p.id'''

    def inventory(active=False):
        rows = connection.execute(query.format(active_join='join temp.active_mods a on a.mod_id=m.id' if active else ''), PRIVATE_EXTENSIONS)
        keys = ('pack', 'file_count', 'logical_bytes', 'plugin_bytes', 'private_candidate_bytes')
        return [dict(zip(keys, row)) for row in rows]

    all_mods = inventory()
    selected = inventory(active=True)
    capacity = shutil.disk_usage(BASE)
    result = {
        'measured_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'PREFLIGHT_ONLY_NO_SOURCE_OR_PROFILE_CHANGES',
        'volume': {'path': str(BASE.anchor), 'total_bytes': capacity.total,
                   'free_bytes': capacity.free, 'reserve_bytes': RESERVE,
                   'additional_budget_after_reserve_bytes': max(0, capacity.free - RESERVE)},
        'inventory_database': str(BASE / 'baseline/skyrim_research.sqlite'),
        'inventory_note': 'Logical file lengths from existing database snapshot; not a new physical allocation scan. Excludes stock games and downloads.',
        'all_mods': all_mods,
        'selected_profile_mods': selected,
        'profiles': [dict(zip(('pack', 'name'), row)) for row in connection.execute(
            'select p.name,r.name from profiles r join packs p on p.id=r.pack_id where r.is_selected=1')],
        'private_candidate_extensions': list(PRIVATE_EXTENSIONS),
        'limitations': [
            'This is not an estimate of the final regenerated BodySlide, behavior, parallax or LOD output.',
            'Private candidate totals include every inventoried matching file, including duplicates and disabled mods, but exclude stock games and runtime copies.',
            'Hard links share content, attributes and file security. They are neither backups nor copy-on-write isolation.',
            'Source hard links have not been created by this preflight.',
            'A single final delivery can still require several small verifiable checkpoints.',
            'No Skyrim process is launched and no in-game stability claim is made.',
        ],
    }
    connection.close()
    out = BASE / 'integration/space_preflight.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    gib = lambda value: f'{value / 1024**3:,.2f} GiB'
    lines = [
        '# 空間盤點與低空間整合約束', '',
        f"測量時間（UTC）：{result['measured_utc']}", '',
        f"E 槽可用：**{gib(capacity.free)}**。暫定保留 {gib(RESERVE)}，新增檔案預算約 **{gib(max(0, capacity.free - RESERVE))}**。",
        '32 GiB 是這次工作採用的保留額，並非已證明足夠的工具需求。', '',
        '| 原包 | 庫內檔案數 | 模組邏輯體積 | 全部插件體積 | 擬獨立保存的插件、設定、腳本與程式體積 |',
        '| --- | ---: | ---: | ---: | ---: |',
    ]
    for item in all_mods:
        lines.append(f"| {item['pack']} | {item['file_count']:,} | {gib(item['logical_bytes'])} | {gib(item['plugin_bytes'])} | {gib(item['private_candidate_bytes'])} |")
    lines += [
        '',
        f"三包模組邏輯體積合計：**{sum(item['logical_bytes'] for item in all_mods) / 1024**4:,.3f} TiB**。原始 StockGame、下載檔案不在此表；數字取自既有目錄資料庫。",
        '擬獨立保存檔案的統計是類型篩選，並非最終整合的新增用量。', '',
        '## 執行約束', '',
        '1. 保留三個原包作為來源；不製作三份完整備份，不搬走或刪除原模組。整合工作、快取、資料庫與輸出都放在 Database。',
        '2. 先產生可審查的來源選擇、優先序及差異清單，再建立整合視圖。預計重用大型資源檔；實際方式須能避免編輯工具回寫原件。',
        '3. 插件、設定、腳本及其他可能被改寫的檔案使用獨立副本。任何需要修改的共用檔案，先複製為獨立檔案再交給工具。',
        '4. 硬連結會共用同一檔案資料，屬性與檔案安全性也共用；不是備份，也沒有寫入時複製。不能靠對連結加唯讀屬性，宣稱原包已隔離。目錄連接同樣不能隔離寫入。',
        '5. 工具的輸出、overwrite、暫存及快取指向 Database 的專用位置。會就地修改資源的工具，必須先確認其完整寫入範圍並準備獨立副本。',
        '6. 以小型變更集、前後雜湊、前一版修補檔與設定保存回退點。已驗證大型輸出若要被替換，先預算替換時的同時占用；不假設可以先刪後驗。',
        '7. 逐項預算 BodySlide、動畫、ParallaxGen、TexGen／DynDOLOD 等重新產物。舊輸出的體積不能直接等同新產物上限。目前尚未證明剩餘空間足以容納全部最終產物。',
        '8. 每一批寫入前重查剩餘空間與新增量；可能低於保留額時停止該批，不自動清理原包或既有證據。',
        '9. 交付可以是一個最終整合包，製作過程仍需多個可回退的驗證步驟。空間限制無法保證首次組合即完全正確。依使用者要求，不啟動遊戲。', '',
        '本次只建立空間盤點與工作約束，沒有建立來源硬連結、改變原包或啟用新的整合設定。', '',
        '技術依據：[Microsoft：Hard Links and Junctions](https://learn.microsoft.com/en-us/windows/win32/fileio/hard-links-and-junctions)。',
    ]
    (BASE / '低空間整合方案.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
