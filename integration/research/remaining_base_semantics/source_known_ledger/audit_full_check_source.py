"""Static exact-tag API and non-mutation allowlist audit; not a Pascal compiler."""
from pathlib import Path
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
API = OUT.parents[1] / 'feature_conflicts/source_4_1_5f'


def main():
    source_path = OUT / 'UnifiedReadOnlyFullAudit.pas'
    source = source_path.read_text(encoding='utf-8')
    registered = set()
    for path in API.glob('*.pas'):
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        registered |= {s.casefold() for s in re.findall(r"AddFunction\([^\n]*?,\s*'([^']+)'", text)}
        registered |= {s.casefold() for s in re.findall(r"SameText\(Identifier,\s*'([^']+)'", text)}
    text = re.sub(r'//[^\n]*|\{[^}]*\}|\(\*.*?\*\)', ' ', source, flags=re.S)
    text = re.sub(r"'(?:''|[^'])*'", ' ', text)
    local = {s.casefold() for s in re.findall(r'\b(?:function|procedure)\s+(\w+)', text, re.I)}
    calls = {s.casefold() for s in re.findall(r'\b(\w+)\s*\(', text)}
    stdlib = {'assigned', 'inttohex', 'inttostr', 'sametext', 'stringreplace', 'extractfileext',
              'copy', 'indexof', 'add', 'create', 'if', 'for', 'while', 'case', 'not', 'and', 'or'}
    read_only_api_allowlist = {
        'addmessage', 'path', 'fullpath', 'check', 'elementcount', 'elementbyindex',
        'filebyindex', 'getfilename', 'fileformidtoloadorderformid', 'mastercount',
        'recordcount', 'getfile', 'name', 'signature', 'getloadorderformid',
    }
    direct_calls = {s.casefold() for s in re.findall(r'(?<![\w.])\b(\w+)\s*\(', text)}
    api_calls = (direct_calls & registered) - stdlib
    unknown = sorted(calls - local - registered - stdlib)
    not_read_only = sorted(api_calls - read_only_api_allowlist)
    result = {'source': str(source_path), 'sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
              'source_provenance': str(API / 'provenance.json'), 'api_calls': sorted(api_calls),
              'unrecognized_calls': unknown, 'api_calls_outside_explicit_read_only_allowlist': not_read_only,
              'passed': not unknown and not not_read_only,
              'scope': 'Exact xEdit 4.1.5f registration availability and API allowlist only. No compilation, xEdit execution or runtime pass is claimed.'}
    (OUT / 'full_check_source_audit.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('Read-only full audit static API:', 'PASS' if result['passed'] else 'FAIL', result['sha256'])
    assert result['passed'], result


if __name__ == '__main__': main()
