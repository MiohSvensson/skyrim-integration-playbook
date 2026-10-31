"""Diagnose quarantined v10 GRUP relocation, never certify its failed export."""
import copy
import hashlib
import json
import sys

sys.dont_write_bytecode=True
from analyze_fields import BASE, OUT, scan
from placement_contract import check_physical_groups, encode_groups


def main():
    producer=json.loads((BASE/'UnifiedSkyrim/validation/feature_compat_v10/result.json').read_text(encoding='utf-8'))
    assert producer['status']=='FAIL' and not producer['marker_seen'] and producer['candidate_sha256'] is None
    isolated=producer['isolated_script_autosave'];path=isolated['quarantined']
    with open(path,'rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    assert digest==isolated['sha256']
    contract=json.loads((OUT/'physical_placement_contract.json').read_text(encoding='utf-8'))
    plan=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    records=scan(path)[0];rows=[]
    for seed in plan['priority_seed_records']:
        key=(seed['origin'],int(seed['object_id'],16));assert key in records
        expected=contract['rows'][f'{key[0]}|{key[1]:06X}']
        issues=check_physical_groups(records[key],expected)
        assert not issues,(key,issues)
        rows.append({'record':expected['record'],'physical_groups_match':True,'persistent_change':seed['persistent'],
                     'expected_groups':expected['expected_groups'],'actual_groups':encode_groups(records[key]['groups'])})
    assert len(records)==154 and len(rows)==152
    source_path=next(g['path'] for g in plan['input_file_guards'] if g['filename'].casefold()=='sofiafollower.esp')
    source=scan(source_path,wanted={('sofiafollower.esp',0xAA58),('skyrim.esm',0x9845C)})[0]
    own=[(k,r) for k,r in records.items() if k[0]=='database feature compatibility.esp'];assert len(own)==1
    for key,record,original in ((own[0][0],own[0][1],source[('skyrim.esm',0x9845C)]),
                                (('sofiafollower.esp',0xAA58),records[('sofiafollower.esp',0xAA58)],source[('sofiafollower.esp',0xAA58)])):
        assert encode_groups(record['groups'])==encode_groups(original['groups'])
        rows.append({'record':f'{key[0]}|{key[1]:06X}','physical_groups_match':True,
                     'expected_groups':encode_groups(original['groups']),'actual_groups':encode_groups(record['groups'])})
    tests=[]
    for name,operation in (
        ('wrong CELL label',lambda r:r['groups'].__setitem__(-1,(8,('skyrim.esm',0x96ED)))),
        ('wrong subgroup type',lambda r:r['groups'].__setitem__(-1,(9,('skyrim.esm',0xD74)))),
        ('cross-WRLD placement',lambda r:r['groups'].__setitem__(1,(1,('skyrim.esm',0x1A26F))))):
        changed=copy.deepcopy(records[('skyrim.esm',0x23DD1)]);operation(changed)
        assert check_physical_groups(changed,contract['rows']['skyrim.esm|023DD1'])
        tests.append({'case':name,'rejected':True})
    changed=copy.deepcopy(records[('skyrim.esm',0x23DD1)])
    for index,(tag,value) in enumerate(changed['fields']):
        if tag=='DATA':
            value=bytearray(value);value[0]^=1;changed['fields'][index]=(tag,bytes(value));break
    assert check_physical_groups(changed,contract['rows']['skyrim.esm|023DD1'])
    tests.append({'case':'changed source DATA coordinate bits','rejected':True})
    result={'status':'QUARANTINED_FAILED_RUN_PLACEMENT_DIAGNOSTIC_ONLY_NOT_INSTALLABLE',
        'quarantined_path':path,'sha256':digest,'producer_status':'FAIL','explicit_export_absent':True,
        '154_payload_GRUP_contexts_match':True,'18_persistent_moves_match':True,
        'record_count_in_quarantine':len(records),'seed_checks':rows,'negative_cases':tests,
        'limits':'This proves the observed SetIsPersistent relocations and preservation of DATA, not successful producer execution. The failed automatic save remains quarantined; only a fresh exported, independently verified candidate may be installed.'}
    (OUT/'placement_contract_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Quarantined v10 diagnostic: all154payload groups/18intended moves/DATA match;4wrong-context cases rejected. NOT INSTALLABLE.')


if __name__=='__main__':main()
