"""Exact-tag bindings and real PACK source bytes for generic byte-vector checks."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

sys.dont_write_bytecode = True
from analyze_fields import OUT, scan


def main():
    plan = json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    seed = next(r for r in plan['priority_seed_records'] if r['origin']=='skyrim.esm' and r['object_id']=='09845C')
    r = scan(seed['base_path'], wanted={('skyrim.esm',0x9845C)})[0][('skyrim.esm',0x9845C)]
    pldt = []
    for tag, value in r['fields']:
        if tag not in ('PLDT','PLVD'): continue
        assert len(value)==12
        typ = struct.unpack_from('<i',value)[0]
        pldt.append({'tag':tag, 'raw_hex':value.hex(), 'type':typ, 'location_value_hex':value[4:8].hex(),
                     'radius':struct.unpack_from('<i',value,8)[0], 'exact_schema_member_is_bytearray4':typ in (2,3,7,10,11,12)})
    exact=OUT/'source_4_1_5f'
    misc=(exact/'xejviScriptAdapterMisc.pas').read_text(encoding='utf-8-sig', errors='replace')
    registered={}
    for cls, member in (('TBytesStream','Create'),('TBinaryReader','Create'),('TBinaryReader','ReadByte')):
        present=bool(re.search(r'AddGet\('+cls+r",\s*'"+member+"'",misc))
        assert present,(cls,member)
        registered[cls+'.'+member]=present
    report={'status':'SOURCE_AND_BINDING_EVIDENCE_NOT_COMPILED_OR_XEDIT_EXECUTED',
        'case':{'record':'skyrim.esm|09845C','provider':seed['base_file'],'path':seed['base_path'],
                'source_sha256':hashlib.sha256(Path(seed['base_path']).read_bytes()).hexdigest(),'PLDT_PLVD_fields':pldt},
        'registered_methods':registered,
        'primary_sources':[
            {'path':str(exact/'wbDefinitionsTES5.pas'),'lines':[5009,5048],
             'fact':'PLDT/PLVD Location Value is an active union; location types2/3/7/10/11/12 return a four-byte ByteArray. These bytes are compared exactly, not omitted under cpIgnore.'},
            {'path':str(exact/'wbInterface.pas'),'lines':[18543,18559],
             'fact':'ByteArrayDef.ToNativeValue copies all actual bytes into a TBytes vector.'},
            {'path':str(exact/'xejviScriptAdapterMisc.pas'),'lines':[689,713],
             'fact':'TBytesStream.Create casts native Variant to TBytes. TBinaryReader.Create wraps the stream and ReadByte returns each actual byte.'},
            {'path':str(exact/'xejviScriptAdapterMisc.pas'),'lines':[2053,2062],
             'fact':'TBytesStream and TBinaryReader classes/constructors and ReadByte are explicitly registered for Jv scripts.'},
            {'path':str(exact/'xejviScriptAdapterMisc.pas'),'lines':[212,220],
             'fact':'VarType and VarTypeAsText expose the real native Variant type, independent of a union wrapper DefType.'}],
        'guard_contract':[
            'LinksTo is compared first and symmetrically by canonical record identity.',
            'Only both-side native VarType8209 (Array Byte) enters the generic byte-vector path, independently of field names or wrapper DefType.',
            'TBytes conversion gives an explicit native byte-vector view; unsupported conversion shapes throw and block export.',
            'Equal stream Size and complete per-byte comparison through ReadByte, followed by both stream Positions equalling n, verify every native byte including zero-length vectors.',
            'No GetEditValue formatting, truncation, union-name/function whitelist or data omission is used to establish byte equality.',
            'Every other native Variant array and any ByteArray definition with an unexpected native type stops with DefType/VarType context.',
            'Typed builders/verifiers share the same helper. Actual compilation/execution and candidate reload remain separate required validations.']}
    (OUT/'native_byte_vector_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Native byte-vector bindings PASS; PACK location fields',[(x['type'],x['location_value_hex']) for x in pldt])


if __name__=='__main__':main()
