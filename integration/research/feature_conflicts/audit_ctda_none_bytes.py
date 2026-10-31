"""Preserve exact source bytes and definition evidence for the v5 union case."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
from analyze_fields import OUT, CONDITIONS, scan


def main():
    plan = json.loads((OUT / 'compat_patch_plan.json').read_text(encoding='utf-8'))
    seed = next(r for r in plan['priority_seed_records'] if r['origin'] == 'skyrim.esm' and r['object_id'] == '01A18E')
    record = scan(seed['base_path'], wanted={('skyrim.esm', 0x1A18E)})[0][('skyrim.esm', 0x1A18E)]
    conditions = []
    for tag, raw in record['fields']:
        if tag != 'CTDA': continue
        assert len(raw) == 32
        fn = struct.unpack_from('<H', raw, 8)[0]; definition = CONDITIONS[fn]
        conditions.append({'function': fn, 'definition': definition, 'raw_CTDA_hex': raw.hex(),
                           'parameter_1_hex': raw[12:16].hex(), 'parameter_2_hex': raw[16:20].hex(),
                           'parameter_2_is_exact_ptNone_bytearray4': definition.get('param2', 'ptNone') == 'ptNone'})
    exact = OUT / 'source_4_1_5f'
    result = {'record': 'skyrim.esm|01A18E', 'provider': seed['base_file'], 'path': seed['base_path'],
              'source_sha256': hashlib.sha256(Path(seed['base_path']).read_bytes()).hexdigest(),
              'conditions': conditions, 'primary_sources': [
                  {'path': str(exact / 'wbDefinitionsTES5.pas'), 'lines': [2759, 2808], 'fact': 'Function descriptor ParamType + 1 selects active member. Alias/packdata flags only affect ObjectReference/Actor/Package, never ptNone.'},
                  {'path': str(exact / 'wbDefinitionsTES5.pas'), 'lines': [5924, 5989], 'fact': 'Both parameter unions have active ptNone member wbByteArray(None,4), with no text formatter.'},
                  {'path': str(exact / 'wbInterface.pas'), 'lines': [18543, 18615], 'fact': 'ByteArray native value returns TBytes; edit representation emits every actual byte in hexadecimal separated by spaces.'},
                  {'path': str(exact / 'xejviScriptAdapter.pas'), 'lines': [384, 405], 'fact': 'DefType returns Element.ValueDef.DefType, hence a union leaf retains dtUnion rather than dtByteArray.'}],
              'guard': 'Current common AssertTree no longer special-cases CTDA. It requires native Array Byte type 8209 on both sides, constructs complete TBytesStream vectors and checks equal native size plus every byte with TBinaryReader. LinksTo checks precede native byte-vector comparison; other non-byte Variant arrays fail. See native_byte_vector_evidence.json.'}
    assert conditions[0]['parameter_2_is_exact_ptNone_bytearray4']
    (OUT / 'ctda_none_bytes_evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('CTDA union case:', [(r['function'], r['definition']['name'], r['parameter_2_hex']) for r in conditions])


if __name__ == '__main__': main()
