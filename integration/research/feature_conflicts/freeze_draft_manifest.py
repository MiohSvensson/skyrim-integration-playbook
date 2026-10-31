"""Freeze research scripts and the exact schema evidence; does not run xEdit."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json

OUT = Path(__file__).resolve().parent
VERSION='v13'


def main():
    names = ['DatabaseFeatureCompatibilityDraft.pas', 'DatabaseQuestFeatureCompatibilityDraft.pas',
             'DatabaseVerifyFeatureCompatibilityDraft.pas', 'DatabaseVerifyQuestFeatureCompatibilityDraft.pas',
             'compatibility_template.pas', 'compat_patch_plan.json', 'quest_extension_plan.json',
             'pascal_api_audit.json', 'copy_contract_audit.json', 'ctda_none_bytes_evidence.json', 'native_byte_vector_evidence.json',
             'semantic_exception_contract.json', 'semantic_native_value_audit.json', 'cis_semantic_validation.json',
             'analyze_fields.py', 'verify_compatibility.py', 'verify_quest_extension.py',
             'DatabaseComparatorSelfAuditDraft.pas', 'comparator_self_audit_manifest.json',
             'comparator_self_audit_scope.json', 'empty_container_evidence.json',
             'physical_placement_contract.json','placement_contract.py','persistent_placement_audit.json',
             'placement_contract_validation.json','comparator_runtime_coverage.json',
             'build_compat_plan.py','build_quest_extension.py','comparator_scope.py',
             'audit_post_assertions.py','post_assertion_collection_audit.json']
    rows = [{'path': str(OUT/n), 'sha256': hashlib.sha256((OUT/n).read_bytes()).hexdigest()} for n in names]
    report = {'frozen_utc': datetime.now(timezone.utc).isoformat(), 'schema': 1,'version':VERSION,
              'authority':'Latest research authoring freeze. Explicit older exact PAS freezes are preserved in version_freezes/v9, v10, v11 and v12.',
              'change': 'Only Hoth exact FLST03B4A5 allows the pinned RArray signature LNAM alongside FormIDs. Final merged base fields, forwarded fields, source-authored quest records and special union/redirect/record-set assertions collect all scoped failures and require one zero-failure summary before export. Source/copy/mutation preconditions, strict MHDT, normal-schema gate, all43guards and18 physical placement contracts remain unchanged.',
              'provenance': str(OUT/'source_4_1_5f/provenance.json'), 'files': rows,
              'contract': 'Research authoring freeze only. Parent owns actual compilation/execution, exported candidate verification and final runtime-profile checks. These are never evidence that a failed autosaved partial candidate completed.'}
    text=json.dumps(report,indent=2)+'\n'
    (OUT/'draft_version_manifest.json').write_text(text,encoding='utf-8')
    (OUT/('draft_version_manifest.'+VERSION+'.json')).write_text(text,encoding='utf-8')
    for version in ('v9','v10','v11','v12'):
        folder=OUT/'version_freezes'/version
        entries=[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(folder.glob('Database*Draft.pas'))]
        (folder/('manifest.'+version+'.json')).write_text(json.dumps({'version':version,'files':entries,'status':'Exact SHA-verified prior PAS bodies; not latest authoring files'},indent=2)+'\n',encoding='utf-8')
    for r in rows[:4]: print(Path(r['path']).name, r['sha256'])


if __name__ == '__main__': main()
