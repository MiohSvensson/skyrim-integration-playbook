"""Real VMAD zero-property array witness for the v8 empty-container failure."""
import hashlib
import json
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT, scan
from vmad_audit import parse_vmad


def main():
    plan=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    seed=next(r for r in plan['priority_seed_records'] if r['origin']=='skyrim.esm' and r['object_id']=='095123')
    r=scan(seed['base_path'],wanted={('skyrim.esm',0x95123)})[0][('skyrim.esm',0x95123)]
    value=dict(r['fields'])['VMAD'];parsed=parse_vmad(value,lambda fid:f'{fid:08X}')
    scripts=[{'script':s['name'],'properties':len(s['properties'])} for s in parsed['scripts']]
    assert any(s['properties']==0 for s in scripts)
    exact=OUT/'source_4_1_5f'
    result={'record':'skyrim.esm|095123','provider':seed['base_file'],'path':seed['base_path'],
        'vmad_sha256':hashlib.sha256(value).hexdigest(),'VMAD_version':parsed['version'],'VMAD_object_format':parsed['object_format'],
        'scripts':scripts,'fragment_tail_hex':parsed['tail_hex'],
        'primary_sources':[
            {'path':str(exact/'wbDefinitionsTES5.pas'),'lines':[4743,4757],'fact':'Script Properties is a defined wbArrayS with a 16bit count prefix; count zero is a valid empty collection.'},
            {'path':str(exact/'wbDefinitionsTES5.pas'),'lines':[4896,4910],'fact':'VMAD Scripts is a defined array of Script structs, each with the Properties array.'},
            {'path':str(exact/'wbImplementation.pas'),'lines':[21288,21291],'fact':'TwbArray reports structural element type etArray.'},
            {'path':str(exact/'wbInterface.pas'),'lines':[19355,19358],'fact':'Base value-definition NativeValue can be unassigned for a collection. No scalar numeric equality should be inferred from zero children.'}],
        'guard':'Both definition names/types, element types, signatures and child counts are checked first. Only explicit array/struct/chapter definition and structural-element combinations with zero children return as empty containers. Scalars and unknown unions retain strict native rules.',
        'binary_rule':'VMAD script/property arrays are independently parsed; source properties=[] remains explicit canonical data, so a removed or added property changes the binary canonical comparison.'}
    (OUT/'empty_container_evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Empty container witness:',scripts)


if __name__=='__main__':main()
