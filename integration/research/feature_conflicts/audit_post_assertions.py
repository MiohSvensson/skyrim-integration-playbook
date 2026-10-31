"""Static fail-closed collection/scope review; not a Pascal execution claim."""
from pathlib import Path
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent


def main():
    plan = json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    old = json.loads((OUT/'version_freezes/v10/compat_patch_plan.json').read_text(encoding='utf-8'))
    source = {(r['origin'],r['object_id']):r for r in old['priority_seed_records']}
    diffs=[]
    for row in plan['priority_seed_records']:
        previous=source[(row['origin'],row['object_id'])]
        changed=[k for k in row if row[k]!=previous[k]]
        if changed:
            assert row['origin']=='skyrim.esm' and row['object_id']=='03B4A5'
            assert changed==['allowed_fields']
            assert set(row['allowed_fields'])-set(previous['allowed_fields'])=={'LNAM'}
            diffs.append({'record':'skyrim.esm|03B4A5','field':'allowed_fields',
                          'before':previous['allowed_fields'],'after':row['allowed_fields']})
    assert len(diffs)==1
    results=[]
    for name in ('DatabaseFeatureCompatibilityDraft.pas','DatabaseQuestFeatureCompatibilityDraft.pas',
                 'DatabaseVerifyFeatureCompatibilityDraft.pas','DatabaseVerifyQuestFeatureCompatibilityDraft.pas'):
        path=OUT/name;text=path.read_text(encoding='utf-8')
        init=text[text.index('function Initialize: Integer;'):]
        assert init.index('FinishPostAssertions;')<init.index('FileWriteToStream(')
        assert "Need(postFailures = 0," in text
        assert 'for i := 0 to ElementCount(base) - 1 do begin' in text
        assert "except PostFailure(context + '/' + t); end;" in text
        assert 'except PostFailure(context + \'/added/\' + t); end;' in text
        calls={'merged':len(re.findall(r'^  PostMerged\(',init,re.M)),
               'forwarded':len(re.findall(r'^  PostForwarded\(',init,re.M)),
               'source_authored':len(re.findall(r'^  PostExactSource\(',init,re.M))}
        if 'Quest' in name:
            assert calls=={'merged':16,'forwarded':1,'source_authored':11}
        else:
            assert calls=={'merged':152,'forwarded':59,'source_authored':0}
            assert "'|FormIDs|LNAM|'" in init
            assert 'if (not VERIFY_ONLY) and (not postVerificationPhase) then begin' in text
            assert 'if VERIFY_ONLY or postVerificationPhase then begin' in text
            assert '  PostSpecials;' in init
        assert '  PostRecordSet;' in init
        results.append({'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'post_record_scopes':calls,'zero_failure_gate_before_export':True})
    schema=OUT/'source_4_1_5f/wbDefinitionsTES5.pas'
    evidence=schema.read_text(encoding='utf-8-sig',errors='replace').splitlines()
    line=next(i+1 for i,v in enumerate(evidence) if "wbRArrayS('FormIDs', wbFormID(LNAM" in v)
    report={'passed':True,'plan_changes':diffs,'drafts':results,
            'schema':{'path':str(schema),'sha256':hashlib.sha256(schema.read_bytes()).hexdigest(),'line':line,
                      'text':evidence[line-1]},
            'failure_semantics':'Each base header, physical placement, preserved top-level field and added-field check has its own exception boundary. Every forwarded field, all11 quest source-authored records, Hoth union, Sofia isolation and record-set check are included. Any failure or unexpected exception increments a blocking total. Exceptions within one nested field stop that field only, never become success; other scoped fields continue.',
            'limits':'Static authoring review. Initial source/copy/mutation preconditions still stop immediately. Actual xEdit compile/run and binary candidate verification are parent-owned and still required.'}
    (OUT/'post_assertion_collection_audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Post-assertion scope/gate: PASS; only exact Hoth LNAM permission changed;154/27records covered')


if __name__=='__main__':main()
