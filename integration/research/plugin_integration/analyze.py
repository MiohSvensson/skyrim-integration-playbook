"""Read-only evidence-backed source, slot and bounded addon planning."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STOCK = {'skyrim.esm','update.esm','dawnguard.esm','hearthfires.esm','dragonborn.esm'}
GEAR = {'TES4','ARMA','ARMO','WEAP','TXST','COBJ','KYWD','MATT','OTFT','LVLI','ENCH','MGEF','SPEL','BOOK','FLST','EXPL','PROJ','STAT','ARTO','EFSH','SOUN','SNDR','SNCT','SOPM','IPDS','IDLM','EQUIP'}
WORLD = {'WRLD','CELL','NAVM','NAVI','LAND','ROAD','REFR','ACHR','LCTN'}
ACTOR = {'NPC_','RACE','HDPT','CLAS','FACT','PACK','CSTY','DOFT','DLVW','DIAL','INFO','SCEN','QUST','PERK','AVIF'}


def connect(name):
    c=sqlite3.connect((ROOT/'baseline'/name).as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    deadline=time.monotonic()+90
    c.set_progress_handler(lambda:int(time.monotonic()>deadline),100000)
    return c


def header(path):
    with open(path,'rb') as f:
        data=f.read(24)
        if data[:4]!=b'TES4':raise ValueError(path)
        flags=struct.unpack_from('<I',data,8)[0]
        payload=f.read(struct.unpack_from('<I',data,4)[0])
    pos=0;extended=None;masters=[];version=None
    while pos+6<=len(payload):
        typ=payload[pos:pos+4];size=struct.unpack_from('<H',payload,pos+4)[0];pos+=6
        if typ==b'XXXX':extended=struct.unpack_from('<I',payload,pos)[0];pos+=size;continue
        if extended is not None:size=extended;extended=None
        val=payload[pos:pos+size];pos+=size
        if typ==b'MAST':masters.append(val.rstrip(b'\0').decode('utf-8',errors='replace'))
        if typ==b'HEDR':version=struct.unpack_from('<f',val)[0]
    return {'header_flags':flags,'is_light':bool(flags&0x200),'header_version':version,'masters':masters}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    main=connect('skyrim_research.sqlite');rec=connect('plugin_records.sqlite');identity=connect('record_identifiers.sqlite')
    mods={r['id']:dict(r) for r in main.execute('select * from mods')}
    profiles={r['pack']:dict(r) for r in main.execute('select p.name as pack,r.* from profiles r join packs p on p.id=r.pack_id where is_selected=1')}
    winners={}
    for row in main.execute('''select p.name as pack,pf.*,pm.list_order from profile_mods pm
      join profiles r on r.id=pm.profile_id join packs p on p.id=r.pack_id
      join plugin_files pf on pf.mod_id=pm.mod_id where pm.enabled=1 and r.is_selected=1
      and instr(pf.relative_path,char(92))=0 and instr(pf.relative_path,'/')=0
      order by pm.list_order desc'''):
        winners[row['pack'],row['name_key']]=dict(row)
    resolved={(r['pack'],r['plugin_key']):dict(r) for r in main.execute('''select p.name as pack,s.*
      from selected_plugin_resolution s join profiles r on r.id=s.profile_id join packs p on p.id=r.pack_id where r.is_selected=1''')}
    fps={r['sha256']:dict(r) for r in identity.execute('select * from plugin_identity_fingerprints')}
    diagnostics={(r['pack'],r['plugin_key']):dict(r) for r in main.execute('select * from xedit_plugin_checks')}
    ledger=json.loads((ROOT/'repairs/diagnostic_ledger.json').read_text(encoding='utf-8-sig'))
    ledger_by=collections.defaultdict(list)
    for row in ledger:ledger_by[row['pack'],row['plugin'].casefold()].append(row)
    repaired={}
    for row in json.loads((ROOT/'repairs/candidate_manifest.json').read_text(encoding='utf-8-sig'))['files']:
        repaired[row['pack'],row['plugin'].casefold()]=row
    stats=collections.defaultdict(dict)
    own=collections.Counter();override=collections.Counter()
    for r in rec.execute('''select rr.plugin_id,rr.signature,count(*) n,
      sum(case when o.name_key=p.name_key then 1 else 0 end) own
      from records rr join plugins p on p.id=rr.plugin_id join origins o on o.id=rr.origin_id
      group by rr.plugin_id,rr.signature'''):
        stats[r['plugin_id']][r['signature']]=r['n'];own[r['plugin_id']]+=r['own'];override[r['plugin_id']]+=r['n']-r['own']
    packs={p:{} for p in profiles}
    for rr in rec.execute('select * from plugins order by pack,id'):
        row=dict(rr);pack=row['pack'];key=row['name_key'];source=winners.get((pack,key));mod=mods.get(source['mod_id']) if source else None
        row['snapshot_path']=row.pop('path')
        row['source_path']=str(Path(mod['path'])/source['relative_path']) if mod else None
        row['source_mod_id']=mod['id'] if mod else None;row['source_mod']=mod['name'] if mod else 'StockGame or unresolved provider'
        row['resolution_crosscheck']=None if not source or (pack,key) not in resolved else source['mod_id']==resolved[pack,key]['winning_mod_id']
        row.update(header(row['snapshot_path']))
        row['record_signatures']=stats[row['id']];row['owned_records']=own[row['id']];row['override_records']=override[row['id']]
        row['identity']=fps.get(row['sha256'])
        diag=diagnostics.get((pack,key),{})
        row['native_reported_errors']=diag.get('reported_errors');row['native_status']=diag.get('status')
        row['diagnostic_families']=dict(collections.Counter(r['cause_family'] for r in ledger_by[pack,key]))
        row['diagnostic_dispositions']=list(dict.fromkeys(r['disposition'] for r in ledger_by[pack,key]))
        if (pack,key) in repaired:
            row['validated_replacement']=repaired[pack,key]
        packs[pack][key]=row

    def slots(values):
        rows=list(values);light=sum(r['is_light'] for r in rows)
        return {'total':len(rows),'full':len(rows)-light,'light':light,'full_headroom_to_254':254-(len(rows)-light),'light_headroom_to_4096':4096-light}

    summaries={p:slots(rows.values()) for p,rows in packs.items()}
    collisions=[]
    for a,b in [('Anno','Burida'),('Anno','TuLED'),('Burida','TuLED')]:
        shared=set(packs[a])&set(packs[b]);same=[k for k in shared if packs[a][k]['sha256']==packs[b][k]['sha256']]
        collisions.append({'packs':[a,b],'shared_names':len(shared),'same_sha256':len(same),'different_sha256':len(shared)-len(same),'different_names_same_identity':[]})
        by_id=collections.defaultdict(list)
        for row in packs[a].values():
            f=row.get('identity')
            if f and f['owned_edid_count']>=5:by_id[f['owned_identifier_sha256'],f['record_count']].append(row)
        for row in packs[b].values():
            f=row.get('identity')
            if not f or f['owned_edid_count']<5:continue
            for ar in by_id.get((f['owned_identifier_sha256'],f['record_count']),[]):
                if ar['name_key']!=row['name_key']:collisions[-1]['different_names_same_identity'].append({'a':ar['name'],'b':row['name'],'owned_edids':f['owned_edid_count'],'evidence':'identity candidate, not binary or field equality'})
    result={'scope':'Original selected snapshots; final repaired profile additions and removals must be applied separately. No source files were changed.',
      'slots':summaries,'cross_pack_collisions':collisions,'source_plugins':packs,'base_additions':{}}
    for base in packs:
        base_id=collections.defaultdict(list)
        for row in packs[base].values():
            f=row.get('identity')
            if f and f['owned_edid_count']>=5:base_id[f['owned_identifier_sha256'],f['record_count']].append(row)
        candidates=[]
        for donor in packs:
            if donor==base:continue
            for key,row in packs[donor].items():
                if key in packs[base]:continue
                item={k:row[k] for k in ['pack','name','name_key','sha256','snapshot_path','source_path','source_mod_id','source_mod','is_light','masters','record_count','record_signatures','owned_records','override_records','native_reported_errors','native_status','diagnostic_families','diagnostic_dispositions']}
                signatures=set(row['record_signatures'])-{'TES4'}
                reasons=[];status='needs_semantic_review'
                f=row.get('identity');sameid=base_id.get((f['owned_identifier_sha256'],f['record_count']),[]) if f and f['owned_edid_count']>=5 else []
                item['identity_matches_in_base']=[r['name'] for r in sameid]
                missing=[m for m in row['masters'] if m.casefold() not in packs[base]]
                item['masters_absent_in_base']=missing
                variants=[]
                for m in row['masters']:
                    k=m.casefold()
                    if k in STOCK or k not in packs[base] or k not in packs[donor]:continue
                    if packs[base][k]['sha256']!=packs[donor][k]['sha256']:variants.append({'master':m,'base_sha':packs[base][k]['sha256'],'donor_sha':packs[donor][k]['sha256']})
                item['master_version_variants']=variants
                if sameid:
                    status='disable_identity_variant';reasons.append('Same owned EDID/type/count fingerprint under different name; select existing base edition pending semantic proof, not coactivation.')
                elif row.get('invalid_formids') or row['status']!='ok':
                    status='disable_invalid_or_unindexed';reasons.append('Binary record index is incomplete or contains invalid FormID scope.')
                elif key.startswith('cc') or key in STOCK:
                    status='conditional_official_content';reasons.append('Official content needs matching complete archives and consistent stock, not a loose plugin import.')
                elif re.search(r'(synthesis|dyndolod|occlusion|pg_\d|nemesis|fnis|bashed patch|merged patch)',key):
                    status='replace_generated_output';reasons.append('Generated/merged output belongs to its exact original input configuration and must be rebuilt or retained with that configuration.')
                elif row['diagnostic_families'] and (donor,key) not in repaired:
                    status='disable_known_unresolved_diagnostics';reasons.append('Existing diagnostic ledger contains unclosed source issues; no silent record deletion or guessed remapping.')
                elif missing:
                    status='conditional_dependency_closure';reasons.append('Requires donor-only masters; add a dependency-complete feature set before validation.')
                elif variants:
                    status='conditional_master_version';reasons.append('Donor compiled against a different non-stock master; typed-reference and field conflict validation required.')
                elif signatures and signatures<=GEAR and row['override_records']==0:
                    status='eligible_bounded_new_items';reasons.append('Only bounded item/effect support signatures and no overrides of other origins; final joint xEdit and asset closure still required.')
                elif signatures & WORLD:
                    status='needs_world_conflict_review';reasons.append('Touches world/cell/placement/navigation records; requires record-level conflict and geometry/LOD resolution.')
                elif signatures & ACTOR:
                    status='needs_actor_quest_framework_review';reasons.append('Touches actor, appearance, quests, dialogue, perks or game systems; choose coherent framework and patch set.')
                else:
                    status='needs_semantic_review';reasons.append('Signature set is not a bounded standalone item bundle; inspect intended behavior and resource/soft-dependency consumers.')
                if (donor,key) in repaired:item['validated_replacement']=repaired[donor,key]
                item['status']=status;item['reasons']=reasons;candidates.append(item)
        by_name=collections.defaultdict(list)
        for row in candidates:by_name[row['name_key']].append(row)
        eligible=[]
        for key,rows in by_name.items():
            ok=[r for r in rows if r['status']=='eligible_bounded_new_items']
            if ok:
                # Prefer donor byte-identical to the other candidate, otherwise preserve choice for the integrator.
                eligible.append(ok[0])
                for r in ok[1:]:
                    r['status']='duplicate_donor_candidate' if r['sha256']==ok[0]['sha256'] else 'alternative_donor_version'
                    r['reasons'].append('Choose one source for this plugin name; not an additional slot.')
        result['base_additions'][base]={'candidates':candidates,'status_counts':dict(collections.Counter(r['status'] for r in candidates)),
          'eligible_unique':len(eligible),'eligible_slot_projection':slots(list(packs[base].values())+eligible),
          'eligible_names':[r['name'] for r in eligible]}
    (OUT/'plugin_candidates.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# 三包插件整合：來源、slot 與追加候選','','這是原選用快照的規劃；未變更原插件、未啟動遊戲。可追加分類仍須通過組裝後完整 xEdit、資源與軟依賴驗證。','','## 實際標頭 slot','','| 原包 | 全部快照 | Full | Light | Full 剩餘（254上限） |','|---|---:|---:|---:|---:|']
    for p,s in summaries.items():lines.append(f"| {p} | {s['total']} | {s['full']} | {s['light']} | {s['full_headroom_to_254']} |")
    lines+=['','含5官方主檔與快照中實際載入的 Creation Club。不能直接從 `.esp` 副檔名推定 full/light；數字由 TES4 flags 計算。已完成修復設定的增刪另計。','','## 同名來源碰撞','']
    for r in collisions:lines.append(f"- {r['packs'][0]} / {r['packs'][1]}：共有 {r['shared_names']} 名；{r['same_sha256']} 份相同 SHA、{r['different_sha256']} 份不同 SHA；另 {len(r['different_names_same_identity'])} 組異名自有識別指紋候選。")
    lines+=['','## 各基底的有界新增物品候選','']
    for base,r in result['base_additions'].items():
        lines += [f"### {base}",'',f"無已知未決診斷、依賴已在基底、非 stock 主檔 SHA 一致、僅新增有界物品類記錄且不覆蓋其他來源：{r['eligible_unique']} 份。投影 full/light = {r['eligible_slot_projection']['full']}/{r['eligible_slot_projection']['light']}。",'',json.dumps(r['status_counts'],ensure_ascii=False),'']
        lines += [f"- {name}" for name in r['eligible_names']]
    lines+=['','## 判讀與排除規則','','- 同名不同 SHA 保留基底版本，另一版須逐欄位評估，不直接覆蓋。異名同 owned EDID/type/count 只當身分線索，不宣稱等價。','- 原有 diagnostic_ledger 的世界、NAVM、NPC 外觀、任務別名及合併 FLST 等未決項目會阻擋自動追加；已驗證修復可使用明確候選路徑。','- 新生成輸出不得跨配置沿用。純新物品簽名不保證模型、貼圖、腳本、OAR 或 SPID 軟依賴已閉合；後續必須檢查來源整個 mod 的輸出/覆蓋。','- slot 上限依舊版 SSE 常規 254 full/4096 light；不自行 compact 或僅改 ESL flag。BEES 的低 FormID 擴充與 slot 數是不同問題。','- `plugin_candidates.json` 提供每個來源、記錄類型、自有/覆蓋數、master 版本差異、診斷和候選修補，供正式 manifest 決策。']
    (OUT/'插件整合候選.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'slots':summaries,'collisions':[{k:v for k,v in x.items() if k!='different_names_same_identity'} for x in collisions],
      'base_additions':{b:{k:v for k,v in r.items() if k!='candidates'} for b,r in result['base_additions'].items()}},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
