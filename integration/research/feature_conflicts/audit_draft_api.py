"""Check identifiers against actual registered APIs; not a Pascal compiler."""
from pathlib import Path
import hashlib
import json
import re

OUT = Path(__file__).resolve().parent
API = OUT / 'source_4_1_5f'


def main():
    registered = set()
    for path in API.glob('*.pas'):
        source = path.read_text(encoding='utf-8-sig', errors='replace')
        registered |= {s.casefold() for s in re.findall(r"AddFunction\([^\n]*?,\s*'([^']+)'", source)}
        registered |= {s.casefold() for s in re.findall(r"SameText\(Identifier,\s*'([^']+)'", source)}
    stdlib = {'assigned', 'inttohex', 'inttostr', 'sametext', 'fileexists', 'forcedirectories', 'extractfilepath',
              'pos', 'inc', 'create', 'indexof', 'if', 'for', 'while', 'case', 'not', 'and', 'or', 'copy', 'length', 'vartostr'}
    result = []
    for path in sorted(OUT.glob('Database*Draft.pas')):
        source = path.read_text(encoding='utf-8')
        text = re.sub(r'//[^\n]*|\{[^}]*\}|\(\*.*?\*\)', ' ', source, flags=re.S)
        text = re.sub(r"'(?:''|[^'])*'", ' ', text)
        local = {s.casefold() for s in re.findall(r'\b(?:function|procedure)\s+(\w+)', text, re.I)}
        calls = {s.casefold() for s in re.findall(r'\b(\w+)\s*\(', text)}
        unknown = sorted(calls - local - registered - stdlib)
        result.append({'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                       'call_identifiers': sorted(calls), 'unrecognized_identifiers': unknown, 'passed': not unknown})
    report = {'source_provenance': str(API / 'provenance.json'), 'files': result, 'passed': all(r['passed'] for r in result),
              'scope': 'Static registered xEdit API availability only. Not Pascal compilation, execution, final-VFS validation, or game runtime validation.'}
    (OUT / 'pascal_api_audit.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Draft API availability:', 'PASS' if report['passed'] else 'FAIL', len(result), 'files')
    assert report['passed']


if __name__ == '__main__': main()
