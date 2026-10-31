"""Reconcile every frozen source-scope call with the actual read-only audit log."""
from pathlib import Path
import collections
import hashlib
import json
import re
import sys

sys.dont_write_bytecode=True
from analyze_fields import BASE, OUT, scan


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    run=BASE/'UnifiedSkyrim/validation/comparator_self_audit'
    result=json.loads((run/'result.json').read_text(encoding='utf-8'))
    prepared=json.loads((run/'prepared.json').read_text(encoding='utf-8'))
    inventory=json.loads((run/'input_inventory.json').read_text(encoding='utf-8'))
    scope=json.loads((OUT/'comparator_self_audit_scope.json').read_text(encoding='utf-8'))
    log=run/'logs/xedit.log';text=log.read_text(encoding='utf-8-sig',errors='replace')
    assert sha(log)==result['log_sha256']
    assert sha(prepared['script'])==prepared['script_sha256']==sha(OUT/'DatabaseComparatorSelfAuditDraft.pas')
    assert result['status']=='PASS' and result['return_code']==0
    assert not result['changed_input_plugins'] and not result['changed_profile_controls']
    start=text.rfind('COMPARATOR_SELF_AUDIT_BEGIN');assert start>=0;text=text[start:]
    assert 'COMPARATOR_SELF_AUDIT_PASSED' in text
    forbidden=('COMPARATOR_SELF_UNSUPPORTED\t','COMPARATOR_SELF_TRAVERSAL_EXCEPTION\t',
               'COMPARATOR_SELF_RECORD_EXCEPTION\t','COMPARATOR_SELF_PARENT_EXCEPTION\t')
    assert not any(x in text for x in forbidden)
    completed=re.findall(r'COMPARATOR_SELF_AUDIT_COMPLETED\t(\d+)\t(\d+)\t(\d+)',text)
    assert len(completed)==1
    total,leaves,failures=map(int,completed[0]);assert failures==0
    runtime=[]
    for line in text.splitlines():
        if not line.startswith('COMPARATOR_SELF_RECORD\t'):continue
        _,record,context=line.split('\t',2)
        m=re.fullmatch(r'(.+)\|([0-9A-F]{6}) \[(.+)\]/([A-Z0-9_]{4})',record);assert m,record
        origin,obj,provider,sig=m.groups()
        runtime.append({'origin':origin.casefold(),'object_id':obj,'provider':provider,'signature':sig,
                        'context':context,'runtime_identity':record,'sequence':len(runtime)})
    assert len(runtime)==total==333
    key=lambda r:(r['provider'].casefold(),r['origin'],r['object_id'])
    runtime_by_key={key(r):r for r in runtime};assert len(runtime_by_key)==len(runtime)
    exact={key(r):r for r in scope['exact_records']}
    actual_exact=[r for r in runtime if r['context'].endswith(' exact source')]
    actual_parents=[r for r in runtime if r['context'].endswith(' visible source parent')]
    assert len(actual_exact)==len(exact)==239
    assert {key(r) for r in actual_exact}==set(exact)
    introduced={}
    for r in actual_parents:
        context=r['context'][:-len(' visible source parent')]
        k=(context.casefold(),r['origin'],r['object_id'])
        assert k not in introduced;introduced[k]=r
    assert len(introduced)==94
    guards={r['filename'].casefold():r for r in scope['input_file_guards']}
    inputs={r['name'].casefold():r for r in inventory['plugins']}
    assert all(g['sha256']==inputs[n]['sha256'] for n,g in guards.items())
    physical_parents=collections.defaultdict(set)
    for r in scope['visible_source_parents']:
        physical_parents[guards[r['context_provider'].casefold()]['path']].add((r['origin'],int(r['object_id'],16)))
    physical={p:scan(p,wanted=keys)[0] for p,keys in physical_parents.items()}
    rows=[]
    for r in scope['visible_source_parents']:
        context=r['context_provider'];k=(context.casefold(),r['origin'],r['object_id'])
        if k in introduced:
            actual=introduced[k]
            rows.append(r|{'classification':'NEW_UNIQUE_PARENT_RECORD_TRAVERSED','runtime':actual})
            continue
        path=guards[context.casefold()]['path'];raw=physical[path].get((r['origin'],int(r['object_id'],16)))
        assert raw is not None,('Unlogged source parent does not have direct physical provider proof',r)
        expected=(context.casefold(),r['origin'],r['object_id'])
        assert expected in runtime_by_key and expected in exact,('Unlogged parent not proved as exact-source duplicate',r)
        first=runtime_by_key[expected];assert first['context'].endswith(' exact source')
        rows.append(r|{'classification':'DEDUP_ALREADY_TRAVERSED_EXACT_SOURCE_RECORD','physical_provider':path,
                       'first_runtime_record':first,'proof':'Same canonical origin/object and actual physical source provider was already traversed in the exact-source phase. AuditLoadedRecord intentionally deduplicates this exact runtime key.'})
    classes=collections.Counter(r['classification'] for r in rows)
    assert classes=={'NEW_UNIQUE_PARENT_RECORD_TRAVERSED':94,'DEDUP_ALREADY_TRAVERSED_EXACT_SOURCE_RECORD':13}
    kinds=[]
    for line in text.splitlines():
        if line.startswith('COMPARATOR_SELF_KIND_COUNT\t'):
            parts=line.split('\t');kinds.append({'definition':parts[1],'element':parts[2],'native':parts[3],
                                               'empty_container':len(parts)==6,'count':int(parts[-1])})
    assert sum(k['count'] for k in kinds)==leaves==23972
    report={'status':'FULL_FROZEN_SCOPE_RECONCILED_PASS','log':str(log),'log_sha256':sha(log),
        'prepared':str(run/'prepared.json'),'script_sha256':prepared['script_sha256'],
        'input_inventory':str(run/'input_inventory.json'),'input_inventory_sha256':sha(run/'input_inventory.json'),
        'all_43_guard_hashes_match_frozen_runtime_inventory':True,
        'frozen_scope_sha256':sha(OUT/'comparator_self_audit_scope.json'),
        'scope_calls':{'exact':239,'visible_parent':107,'total':346},
        'actual_unique_traversals':{'exact':239,'new_parents':94,'total':333},
        'deduplicated_parent_calls':13,'unsupported_or_lookup_or_traversal_failures':0,'leaf_comparisons':23972,
        'kind_counts':kinds,'parent_rows':rows,
        'unchanged_runtime_inputs_and_controls':True,
        'contract':'All346 frozen scope calls are accounted for.333 is the deliberately deduplicated actual provider+canonical-record count, not missing scope. This proves comparator self-kind coverage in this exact read-only run, not copy normalization, patch compatibility or runtime gameplay.'}
    (OUT/'comparator_runtime_coverage.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Scope coverage PASS: 239 exact + 107 parent calls = 333 unique + 13 proved exact-source duplicates;',len(kinds),'kinds;',leaves,'leaves')
    for r in rows:
        if r['classification'].startswith('DEDUP'):print('DEDUP',r['context_provider'],r['origin'],r['object_id'])


if __name__=='__main__':main()
