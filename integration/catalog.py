"""Complete original-mod decision registry; no original metadata is overwritten."""
import csv
import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from materialize import BASE, key, utc


def category(name):
    text = name.casefold()
    if re.search(r'output|synthesis|dyndolod|texgen|xlodgen|grass cache|parallaxgen|pgpatcher|pandora.*output', text):
        return 'generated_output_alternative'
    if re.search(r'bfco|vokrii|ordinat|perk overhaul|mco|nemesis|pandora|fn[i]?s|cbbe|3ba|bhunp|xpms|skeleton|race menu|racemenu|community shader|skse|engine fixes|(?:^| )enb|lux |nat |obsidian|weather', text):
        return 'framework_or_visual_alternative'
    if re.search(r'翻譯|汉化|漢化|chinese|korean|한글|translation|locali[sz]ation', text):
        return 'language_or_translation_variant'
    if re.search(r'city|cities|northern roads|whiterun|solitude|windhelm|winterhold|rorikstead|falkreath|landscape|navmesh|npc.*overhaul|npc.*appearance|replacer', text):
        return 'world_or_appearance_alternative'
    return 'nonbaseline_requires_evidence'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--final', action='store_true', help='Finalize the adopted scope while explicitly retaining unelected alternatives')
    args = ap.parse_args()
    source = sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro', uri=True)
    source.row_factory = sqlite3.Row
    originals = [dict(r) for r in source.execute('''select m.*,p.name pack,pm.enabled original_enabled,pm.list_order
      from mods m join packs p on p.id=m.pack_id
      left join profiles pr on pr.pack_id=p.id and pr.is_selected=1
      left join profile_mods pm on pm.mod_id=m.id and pm.profile_id=pr.id order by m.id''')]
    assert len(originals) == 6495, len(originals)
    base_mods = json.loads((BASE/'integration/baseline_mods.json').read_text(encoding='utf-8'))
    base_ids = {m['id']: m for m in base_mods}
    hashes = {r['mod_id']: dict(r) for r in source.execute("select * from mod_tree_hashes where status='complete'")}
    # Earlier tool versions use 'ok'; include only a populated completed digest.
    for row in source.execute("select * from mod_tree_hashes where content_sha256 is not null and content_sha256<>''"):
        if row['status'] in ('ok', 'complete', 'verified'):
            hashes[row['mod_id']] = dict(row)
    base_by_hash = {}
    for mid in base_ids:
        if mid in hashes:
            base_by_hash.setdefault(hashes[mid]['content_sha256'], []).append(mid)
    overrides = {}
    decisions_file = BASE/'integration/decision_overrides.json'
    if decisions_file.exists():
        for r in json.loads(decisions_file.read_text(encoding='utf-8')):
            mid = int(r['mod_id'])
            if mid not in overrides:
                overrides[mid] = dict(r)
                continue
            previous = overrides[mid]
            assert previous['decision'] == r['decision'], ('Conflicting decisions', mid)
            for field in ['reason', 'directory', 'evidence']:
                values = list(dict.fromkeys([v for v in [previous.get(field), r.get(field)] if v]))
                if values:
                    previous[field] = '; '.join(values)
    c = sqlite3.connect(BASE/'integration/integration.sqlite')
    c.executescript('''create table if not exists mod_decisions(
      mod_id integer primary key,pack text,name text,path text,nexus_id integer,version text,
      originally_enabled integer,decision text,category text,reason text,
      representative_mod_id integer,directory text,evidence text,updated_utc text);
      create table if not exists milestones(utc text,phase text,detail text);
      create table if not exists evidence(id text primary key,path text,sha256 text,scope text);
    ''')
    rows = []
    for mod in originals:
        mid = mod['id']
        representative = None
        directory = base_ids[mid]['directory'] if mid in base_ids else None
        evidence = 'integration/research/base_selection/base_selection.json'
        if mid in base_ids:
            decision, group, reason = 'enabled_baseline', 'selected_baseline', '保留 TuLED 原選用內容與相對資源優先序；具體修復與隔離另列。'
        elif mid in hashes and hashes[mid]['content_sha256'] in base_by_hash:
            representative = base_by_hash[hashes[mid]['content_sha256']][0]
            decision, group, reason = 'deduplicated_exact', 'full_mod_tree_sha256', '完整模組內容樹 SHA-256 與已採用來源相同（依既有驗證，排除根 meta.ini）；重用代表來源。'
            evidence = 'baseline/skyrim_research.sqlite:mod_tree_hashes'
        elif not mod['original_enabled']:
            decision, group, reason = 'retained_in_catalog', 'originally_disabled', '來源目前配置未啟用；保留完整來源目錄與資料，未經個別採納不自動開啟。'
        else:
            group = category(mod['name'])
            decision = 'not_enabled_pending_or_alternative'
            reason = {
                'generated_output_alternative': '另一套載入環境的生成產物；使用基底或依最終配置重建，不能整套疊加。',
                'framework_or_visual_alternative': '涉及框架或視覺來源；維持單一基底，個別有證據的增量另行採納。',
                'language_or_translation_variant': '譯文／語言候選；不能僅以不同名稱再啟用另一份同源插件。',
                'world_or_appearance_alternative': '世界／外觀候選；須有幾何、FaceGen及精確版本的相容證據再採納。',
                'nonbaseline_requires_evidence': '保留來源候選；沒有足夠記錄、資源或依賴證據的內容，不覆蓋已採用基底。',
            }[group]
        if mid in overrides:
            change = overrides[mid]
            decision = change['decision']
            group = change.get('category', group)
            reason = change['reason']
            directory = change.get('directory', directory)
            evidence = change.get('evidence', evidence)
            representative = change.get('representative_mod_id', representative)
        if decision == 'deduplicated_exact' and representative in overrides:
            representative_decision = overrides[representative]['decision']
            if representative_decision.startswith('disabled_'):
                decision = 'retained_exact_duplicate_of_disabled_source'
                reason = '完整內容樹 SHA-256 相同，但代表來源已明確停用；只保留重複關係與原始資料，不宣稱正式環境重用。'
            elif representative_decision == 'replaced_by_regenerated_output':
                decision = 'retained_exact_duplicate_of_replaced_generated_output'
                reason = '完整內容樹 SHA-256 與舊生成來源相同；正式環境使用依最終配置重新生成的輸出。'
        if args.final and decision == 'not_enabled_pending_or_alternative':
            decision = 'retained_source_alternative_not_adopted'
        row = {'mod_id': mid, 'pack': mod['pack'], 'name': mod['name'], 'path': mod['path'],
               'nexus_id': mod['nexus_id'], 'version': mod['version'], 'originally_enabled': mod['original_enabled'],
               'decision': decision, 'category': group, 'reason': reason,
               'representative_mod_id': representative, 'directory': directory, 'evidence': evidence, 'updated_utc': utc()}
        rows.append(row)
        c.execute('insert or replace into mod_decisions values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)', tuple(row.values()))
    c.commit()
    output = BASE/'integration/全模組採用目錄.csv'
    with output.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {'utc': utc(), 'original_mods': len(rows),
               'status': 'FINAL_ADOPTED_SCOPE_WITH_PRESERVED_SOURCE_ALTERNATIVES' if args.final else 'WORK_IN_PROGRESS_DECISIONS_WILL_BE_FINALIZED',
               'scope_note': 'Every original mod is catalogued. Unelected alternatives remain in their original packs; a final catalogue does not assert that every alternative is active or independently game-tested.',
               'decisions': c.execute('select decision,count(*) from mod_decisions group by decision').fetchall(),
               'sources_preserved': True, 'csv': str(output)}
    (BASE/'integration/catalog_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    c.close()
    source.close()


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
