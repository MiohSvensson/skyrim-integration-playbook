"""Generate a read-only whole-source e-vs-e comparator self-audit script."""
from pathlib import Path
import hashlib
import json
import re

from analyze_fields import OUT
from comparator_scope import current_scope


def main():
    source=(OUT/'DatabaseFeatureCompatibilityDraft.pas').read_text(encoding='utf-8')
    helpers=source[source.index('procedure Need('):source.index('function ExcludeBase(')]
    guard=source[source.index('procedure GuardFile('):source.index('procedure AssertNativeByteVector(')]
    comparator=source[source.index('procedure AssertNativeByteVector('):source.index('procedure RemapRefs(')]
    scope=current_scope()
    script='''unit UserScript;

// Read-only comparator type coverage. No patch name, plugin creation or save.
// Enumerates its frozen source scope from Initialize; UI selection is irrelevant.
var
  selfAuditSeen, selfAuditKinds: TStringList;
  selfAuditKindCounts: array[0..8191] of Integer;
  selfAuditRecords, selfAuditLeaves, selfAuditFailures: Integer;

'''+helpers+guard+comparator+'''function Initialize: Integer;
begin
  Result := 1;
'''
    for g in scope['input_file_guards']:
        script+='  GuardFile('+repr(g['filename']).replace('"',"'")+", '"+g['crc32']+"');\n"
    script+='''  RunComparatorSelfAudit;
  AddMessage('COMPARATOR_SELF_AUDIT_PASSED');
  Result := 0;
end;
end.
'''
    # Every mutation/export API is absent even from unreachable helpers.
    forbidden=('AddNewFileName','wbCopyElementToFile','wbCopyElementToRecord','SetNativeValue','SetEditValue',
               'ElementAssign','FileWriteToStream','AddRequiredElementMasters','SortMasters','SetIsESL',
               'SetFormVersion','SetFormVCS1','SetFormVCS2','SaveToFile')
    assert not any(re.search(r'\b'+name+r'\s*\(',script,re.I) for name in forbidden)
    path=OUT/'DatabaseComparatorSelfAuditDraft.pas'
    path.write_text(script,encoding='utf-8')
    report={'source':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'input_guards':len(scope['input_file_guards']),'exact_record_scope_rows':len(scope['exact_records']),
            'visible_source_parent_scope_rows':len(scope['visible_source_parents']),
            'all_forbidden_plugin_mutation_and_export_calls_absent':True,
            'shared_comparator_source':str(OUT/'DatabaseFeatureCompatibilityDraft.pas'),
            'shared_comparator_sha256':hashlib.sha256(comparator.encode()).hexdigest(),
            'scope':'Generated from the same helper and complete scope as both builders. Read-only; actual compilation/execution remains required.'}
    (OUT/'comparator_self_audit_manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Read-only comparator self-audit:',report['sha256'],report['input_guards'],'guards',report['exact_record_scope_rows'],'exact +',report['visible_source_parent_scope_rows'],'parent scope rows')


if __name__=='__main__':main()
