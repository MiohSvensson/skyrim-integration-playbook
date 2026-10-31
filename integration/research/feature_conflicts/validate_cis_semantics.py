"""Validate bounded CTDA/CIS normalizing behavior against real source bytes."""
import copy
import json
import struct
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT, canonical, candidate_condition_storage_issues, condition_groups, scan


def main():
    plan=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    seed=next(r for r in plan['priority_seed_records'] if r['origin']=='skyrim.esm' and r['object_id']=='0B1231')
    source=scan(seed['base_path'],wanted={('skyrim.esm',0xB1231)})[0][('skyrim.esm',0xB1231)]
    normalized=copy.deepcopy(source)
    targets=[]
    for index,g in condition_groups(source).items():
        if struct.unpack_from('<H',g['raw'],8)[0]!=629:continue
        assert g['strings']['CIS2']==b'::OwnerWhiterun_var\0'
        value=bytearray(g['raw']);value[16:20]=b'\0'*4
        normalized['fields'][index]=('CTDA',bytes(value));targets.append(index)
    assert len(targets)==1
    assert canonical(source)==canonical(normalized)
    assert candidate_condition_storage_issues(source)
    assert not candidate_condition_storage_issues(normalized)
    rows=[{'case':'exact typed variable U32 zero normalization','accepted':True},
          {'case':'candidate retains source unused U32 address','rejected':bool(candidate_condition_storage_issues(source))}]
    cis_index=next(i for i,(tag,value) in enumerate(normalized['fields']) if tag=='CIS2')
    changed=copy.deepcopy(normalized);changed['fields'][cis_index]=('CIS2',b'::OwnerRiften_var\0')
    assert canonical(changed)!=canonical(source)
    rows.append({'case':'changed resolved CIS text','rejected':True})
    missing=copy.deepcopy(normalized);missing['fields'].pop(cis_index)
    assert candidate_condition_storage_issues(missing) and canonical(missing)!=canonical(source)
    rows.append({'case':'missing paired CIS subrecord','rejected':True})
    moved=copy.deepcopy(normalized);pair=moved['fields'].pop(cis_index)
    first_ctda=next(i for i,(tag,value) in enumerate(moved['fields']) if tag=='CTDA')
    moved['fields'].insert(first_ctda+1,pair)
    assert canonical(moved)!=canonical(source)
    rows.append({'case':'same CIS bytes attached to a different CTDA','rejected':True})
    changed=copy.deepcopy(normalized);index=targets[0];value=bytearray(changed['fields'][index][1]);value[8:10]=struct.pack('<H',79);changed['fields'][index]=('CTDA',bytes(value))
    assert canonical(changed)!=canonical(source)
    rows.append({'case':'different function with same variable parameter type','rejected':True})
    changed=copy.deepcopy(normalized);value=bytearray(changed['fields'][index][1]);value[12]^=1;changed['fields'][index]=('CTDA',bytes(value))
    assert canonical(changed)!=canonical(source)
    rows.append({'case':'changed nonvariable UInt32/FormID parameter','rejected':True})
    audit=json.loads((OUT/'semantic_native_value_audit.json').read_text(encoding='utf-8'))
    negative=next(x for x in audit['typed_float_special_values'] if x['kind']=='negative_zero')
    name,obj=negative['record'].split('|');key=(name,int(obj,16))
    r=scan(negative['path'],wanted={key})[0][key];changed=copy.deepcopy(r)
    for index,(tag,value) in enumerate(changed['fields']):
        if tag==negative['field']:
            value=bytearray(value);off=negative['offset'];assert value[off:off+4]==b'\0\0\0\x80';value[off:off+4]=b'\0'*4;changed['fields'][index]=(tag,bytes(value));break
    assert canonical(r)!=canonical(changed)
    rows.append({'case':'negative-zero source bits replaced with positive zero','rejected':True,'record':negative['record']})
    result={'passed':True,'source_record':'skyrim.esm|0B1231','source_path':seed['base_path'],'cases':rows,
            'scope':'Read-only real-source/in-memory validator checks. No candidate ESP is written and no xEdit/game execution is claimed.'}
    (OUT/'cis_semantic_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Bounded CIS and strict numeric/float validator:',len(rows),'cases PASS')


if __name__=='__main__':main()
