"""Prove small float-bit differences remain visible to the binary normalizer."""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT, canonical
from verify_compatibility import pack_canonical, quest_canonical


def rec(sig,fields):
    return {'signature':sig,'fields':fields,'flags':0,'masters':['Skyrim.esm'],
            'plugin':'Probe.esp','localized':False,'path':'synthetic test','fid':0x1000800}


def string(value):
    data=value.encode('utf-8');return struct.pack('<H',len(data))+data


def vmad(bits):
    return struct.pack('<HHH',5,2,1)+string('FloatContract')+b'\0'+struct.pack('<H',1)+string('Probe')+bytes((4,0))+struct.pack('<I',bits)


def main():
    checks=[]
    for label,a,b in (('adjacent finite f32',0x3f800000,0x3f800001),
                      ('positive/negative zero',0,0x80000000),
                      ('distinct NaN payload',0x7fc00001,0x7fc00002),
                      ('positive/negative infinity',0x7f800000,0xff800000)):
        bitsA=struct.pack('<I',a);bitsB=struct.pack('<I',b)
        cases=[('REFR DATA',canonical,rec('REFR',[('DATA',bitsA+b'\0'*20)]),rec('REFR',[('DATA',bitsB+b'\0'*20)])),
               ('WRLD MHDT',canonical,rec('WRLD',[('MHDT',bitsA)]),rec('WRLD',[('MHDT',bitsB)])),
               ('exterior CELL XCLW',canonical,rec('CELL',[('DATA',b'\0'),('XCLW',bitsA)]),rec('CELL',[('DATA',b'\0'),('XCLW',bitsB)])),
               ('PACK opaque float',pack_canonical,rec('PACK',[('PLDT',bitsA)]),rec('PACK',[('PLDT',bitsB)])),
               ('VMAD scalar float',canonical,rec('QUST',[('VMAD',vmad(a))]),rec('QUST',[('VMAD',vmad(b))])),
               ('Sofia quest VMAD float',quest_canonical,rec('QUST',[('VMAD',vmad(a))]),rec('QUST',[('VMAD',vmad(b))]))]
        for field,normalizer,left,right in cases:
            assert normalizer(left)!=normalizer(right),(label,field)
            checks.append({'case':label,'field':field,'left_bits':bitsA.hex(),'right_bits':bitsB.hex(),'difference_detected':True})
        ctdaA=bytearray(32);ctdaB=bytearray(32);ctdaA[4:8]=bitsA;ctdaB[4:8]=bitsB
        assert canonical(rec('INFO',[('CTDA',bytes(ctdaA))]))!=canonical(rec('INFO',[('CTDA',bytes(ctdaB))]))
        checks.append({'case':label,'field':'CTDA comparison float','left_bits':bitsA.hex(),'right_bits':bitsB.hex(),'difference_detected':True})
    names=('analyze_fields.py','vmad_audit.py','verify_compatibility.py','verify_quest_extension.py')
    report={'passed':True,'checks':checks,'source_files':[{'path':str(OUT/n),'sha256':hashlib.sha256((OUT/n).read_bytes()).hexdigest()} for n in names],
            'normalization':'No binary float decode/round/re-encode: default fields use raw hex/hash; VMAD float type4 and arrays14 retain unsigned32 float_bits; CTDA comparison uses raw4bytes, or canonicalFormID for its global flag; typed numeric parameter arguments retain their exact unsigned32 bits. PACK and Sofia quest retain opaque raw fields. Documented no-copy/derived fields remain explicit exceptions.',
            'native_limit':'Pinned xEdit4.1.5f TwbFloatDef rounds to6decimal digits before NativeValue. Native equality is semantic evidence only and is not a bitwise float guarantee. Independent exported-candidate binary verification remains mandatory.',
            'limits':'Synthetic negative cases prove these binary normalizer branches retain f32 bit distinctions; actual candidate verification and final normal-schema reload remain separately required. No source or runtime files changed.'}
    (OUT/'binary_float_contract_audit.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Binary float-bit distinction: PASS',len(checks),'negative cases')


if __name__=='__main__':main()
