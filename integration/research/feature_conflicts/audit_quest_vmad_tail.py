"""Bind exact v13 tail remaps and test strict preservation outside typed IDs."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT,scan,formvalue
from vmad_audit import parse_vmad
from quest_vmad_tail import canonical_quest_tail
from verify_compatibility_v14 import quest_canonical


def s(v):
    raw=v.encode();return struct.pack('<H',len(raw))+raw


def main():
    exact=json.loads((OUT/'v13_sofia_quest_exact_diff.json').read_text())
    source=scan(exact['source'],wanted={('sofiafollower.esp',0xAA58)})[0][('sofiafollower.esp',0xAA58)]
    candidate=scan(exact['candidate'])[0][('sofiafollower.esp',0xAA58)]
    sourceVMAD=next(v for t,v in source['fields'] if t=='VMAD');actualVMAD=next(v for t,v in candidate['fields'] if t=='VMAD')
    parsed=parse_vmad(sourceVMAD,lambda fid:formvalue(source,fid))
    actualParsed=parse_vmad(actualVMAD,lambda fid:formvalue(candidate,fid))
    tail=bytes.fromhex(parsed['tail_hex']);actualTail=bytes.fromhex(actualParsed['tail_hex'])
    a=canonical_quest_tail(tail,parsed['object_format'],lambda fid:formvalue(source,fid))
    b=canonical_quest_tail(actualTail,actualParsed['object_format'],lambda fid:formvalue(candidate,fid))
    assert a==b and a['typed_form_count']==2
    assert [x['form'] for x in a['chunks'] if 'form' in x]==['sofiafollower.esp|00AA58']*2
    assert len(tail)==len(actualTail)==70
    raw_diffs=[i for i,(x,y) in enumerate(zip(tail,actualTail)) if x!=y]
    assert raw_diffs==[14,69] and all(tail[i]==2 and actualTail[i]==5 for i in raw_diffs)
    checks=[];form_ranges=set(range(11,15))|set(range(66,70))
    for i in range(len(tail)):
        if i in form_ranges:continue
        changed=bytearray(tail);changed[i]^=1
        try:rejected=canonical_quest_tail(bytes(changed),2,lambda fid:formvalue(source,fid))!=a
        except (ValueError,IndexError,struct.error):rejected=True
        assert rejected,i
        checks.append({'case':'changed non-FormID tail byte','offset':i,'rejected':True})
    for i in (11,66):
        changed=bytearray(tail);changed[i]^=1
        assert canonical_quest_tail(bytes(changed),2,lambda fid:formvalue(source,fid))!=a
        checks.append({'case':'changed typed quest object identity','offset':i,'rejected':True})
    for label,data in (('truncated tail',tail[:-1]),('extra unknown tail byte',tail+b'\0')):
        try:canonical_quest_tail(data,2,lambda fid:formvalue(source,fid))
        except (ValueError,IndexError,struct.error):checks.append({'case':label,'rejected':True})
        else:raise AssertionError(label)
    synthetic=bytes((2,))+struct.pack('<H',0)+s('')+struct.pack('<H',1)+struct.pack('<HhI',0,0,0x0200AA58)+struct.pack('<HHH',5,2,1)+s('FloatContract')+bytes((0,))+struct.pack('<H',1)+s('F')+bytes((4,1))
    x=synthetic+struct.pack('<I',0x3f800000);y=synthetic+struct.pack('<I',0x3f800001)
    assert canonical_quest_tail(x,2,lambda fid:formvalue(source,fid))!=canonical_quest_tail(y,2,lambda fid:formvalue(source,fid))
    checks.append({'case':'adjacent f32 in alias script property','rejected':True})
    expected=quest_canonical(source);actual=quest_canonical(candidate);redirects=0
    for pair in expected['fields']:
        if pair==['ALPC','skyrim.esm|09845C']:
            pair[1]='database feature compatibility.esp|000800';redirects+=1
    assert redirects==1 and expected==actual
    definition=OUT/'source_4_1_5f/wbDefinitionsTES5.pas'
    files=['verify_compatibility_v14.py','quest_vmad_tail.py','audit_quest_vmad_tail.py']
    report={'passed':True,'candidate':exact['candidate'],'candidate_sha256':exact['candidate_sha256'],
            'source':exact['source'],'source_sha256':exact['source_sha256'],
            'tail_length':70,'tail_typed_form_count':2,'typed_tail_references':a,
            'changed_source_master_index_offsets':[14,69],'source_master_index':2,'candidate_master_index':5,
            'source_and_candidate_alias_object_identity':'sofiafollower.esp|00AA58','quest_only_payload_change':'Alias1 ALPC->new own PACK000800',
            'negative_checks':checks,'source_schema':{'path':str(definition),'sha256':hashlib.sha256(definition.read_bytes()).hexdigest(),
                'object_layout_lines':[4687,4707],'quest_fragment_lines':[4805,4826],'quest_alias_tail_lines':[4929,4940]},
            'files':[{'path':str(OUT/n),'sha256':hashlib.sha256((OUT/n).read_bytes()).hexdigest()} for n in files],
            'limits':'Independent binary verification only. It does not install the export or prove final VFS reload/game runtime. Original frozen v13 PAS, old verifier and manifest remain unchanged.'}
    (OUT/'quest_vmad_tail_audit_v14.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Exact v13 Sofia VMAD tail PASS:2 canonical FormID remaps, all other bytes strict;',len(checks),'negative cases PASS')
    for row in report['files']:print(Path(row['path']).name,row['sha256'])


if __name__=='__main__':main()
