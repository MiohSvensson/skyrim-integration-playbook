"""Strict post-audit: parser recovery logs never qualify as complete coverage.

Keeps run_preflight.py outputs unchanged. Run only after summary.json exists.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    original = json.loads((OWN / 'summary.json').read_text(encoding='utf8'))
    counts = collections.Counter()
    issues = []
    entries_count = 0
    with (OWN / 'entries.jsonl').open(encoding='utf8') as stream:
        for line in stream:
            row = json.loads(line)
            entries_count += 1
            row_issues = list(row['issues'])
            if row.get('parser_diagnostics'):
                row_issues.append({'kind': 'PARSER_DIAGNOSTIC_REQUIRES_EXPLICIT_REVIEW', 'diagnostics': row['parser_diagnostics'], 'reason': 'Official nifgen may log block-size/EOF recovery without raising. No logged recovery is silently accepted as complete schema coverage.'})
            if row_issues:
                issues.append({'path_key': row['path_key'], 'source_sha256': row['source_sha256'], 'issues': row_issues})
                counts['failed'] += 1
                counts.update('issue_' + one['kind'] for one in row_issues)
            else:
                counts['passed'] += 1
    assert entries_count == original['expected_formal_candidates'] == 3741
    result = dict(original)
    result['status'] = 'ALL_3741_STRICT_LIGHTING_SCHEMA_IDENTITY_PASS' if not issues else 'ALL_3741_ATTEMPTED_STRICT_SCHEMA_REVIEW_REQUIRED'
    result['strict_counts'] = dict(counts)
    result['strict_failure_paths'] = len(issues)
    result['strict_diagnostic_policy'] = 'Any captured parser output or diagnostic requires review, even if snapshot() returned. Neither recovery seek nor footer/EOF mismatch is silently allowed.'
    result['original_summary_sha256'] = sha(OWN / 'summary.json')
    result['entries_sha256'] = sha(OWN / 'entries.jsonl')
    result['strict_auditor_sha256'] = sha(__file__)
    result['frozen_module_current_sha256'] = sha(OWN.parent / 'lighting_schema.py')
    assert result['frozen_module_current_sha256'] == result['module_sha256']
    for filename, value in [('failures_strict.json', issues), ('summary_strict.json', result)]:
        (OWN / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: result[key] for key in ('status', 'strict_counts', 'strict_failure_paths')}, indent=2))

if __name__ == '__main__':
    main()
