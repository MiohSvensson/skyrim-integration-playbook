"""Compare both selected LOTD payloads without silently ignoring non-text data."""
import collections
import json
from pathlib import Path
import struct
import zlib

OUT=Path(__file__).resolve().parent
sources=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))['source_plugins']


def records(path):
    data=Path(path).read_bytes();rows={}
    def walk(start,end):
        while start<end:
            sig=data[start:start+4];size=struct.unpack_from('<I',data,start+4)[0]
            if sig==b'GRUP':walk(start+24,start+size);start+=size;continue
            flags,fid=struct.unpack_from('<II',data,start+8)
            raw=data[start+24:start+24+size]
            if flags&0x40000:raw=zlib.decompress(raw[4:])
            rows[sig.decode(),fid]=(flags&~0x40000,raw)
            start+=24+size
    walk(0,len(data));return rows


def subs(data):
    at=0;extended=None;out=[]
    while at<len(data):
        sig=data[at:at+4].decode();size=struct.unpack_from('<H',data,at+4)[0];at+=6
        if sig=='XXXX':extended=struct.unpack_from('<I',data,at)[0];at+=size;continue
        if extended is not None:size=extended;extended=None
        out.append((sig,data[at:at+size]));at+=size
    assert at==len(data)
    return out


def main():
    a=records(sources['Anno']['legacyofthedragonborn.esm']['snapshot_path'])
    b=records(sources['TuLED']['legacyofthedragonborn.esm']['snapshot_path'])
    changes=[];counts=collections.Counter();flagchanges=[]
    for key in sorted(set(a)&set(b)):
        af,ap=a[key];bf,bp=b[key]
        if af!=bf:flagchanges.append({'signature':key[0],'form_id':f'{key[1]:08X}','a':af,'b':bf})
        if ap==bp:continue
        aa=subs(ap);bb=subs(bp)
        if [s for s,v in aa]!=[s for s,v in bb]:
            changes.append({'signature':key[0],'form_id':f'{key[1]:08X}','kind':'subrecord_structure','a':[s for s,v in aa],'b':[s for s,v in bb]});continue
        for index,((tag,av),(_,bv)) in enumerate(zip(aa,bb)):
            if av==bv:continue
            counts[key[0]+'|'+tag]+=1
            text_pairs={('TES4','CNAM'),('TES4','SNAM'),('INFO','NAM1'),('INFO','RNAM'),
              ('ACTI','RNAM'),('BOOK','CNAM'),('FACT','MNAM'),('FACT','FNAM'),
              ('MGEF','DNAM'),('PERK','EPF2'),('QUST','CNAM'),('QUST','NNAM')}
            is_text=tag in ('FULL','DESC','SHRT','ITXT') or (key[0],tag) in text_pairs
            entry={'signature':key[0],'form_id':f'{key[1]:08X}','subrecord':tag,'index':index,'a_size':len(av),'b_size':len(bv),'known_text_field':is_text}
            if len(av)<180 and len(bv)<180:entry.update(a_hex=av.hex(),b_hex=bv.hex())
            changes.append(entry)
    result={'a':sources['Anno']['legacyofthedragonborn.esm']['snapshot_path'],'b':sources['TuLED']['legacyofthedragonborn.esm']['snapshot_path'],
      'a_records':len(a),'b_records':len(b),'only_a':[(s,f'{f:08X}') for s,f in set(a)-set(b)],'only_b':[(s,f'{f:08X}') for s,f in set(b)-set(a)],
      'flag_changes':flagchanges,'changed_subrecord_counts':dict(counts),'changes':changes,
      'non_text_or_structure_changes':[r for r in changes if not r.get('known_text_field')],
      'field_definition_evidence':{'path':str(OUT.parents[2]/'sources/TES5Edit/Core/wbDefinitionsTES5.pas'),
        'lines':{'ACTI_RNAM':3328,'BOOK_CNAM':4263,'FACT_MNAM_FNAM':[5048,5049],
          'PERK_EPF2':5973,'INFO_NAM1':7800,'INFO_RNAM':7818,'MGEF_DNAM':8216,
          'QUST_CNAM':8727,'QUST_NNAM':8752}},
      'scope':'TES4 flags excluding compression and decompressed ordered subrecords compared; record/group VC stamps and group labels are not compared.'}
    (OUT/'lotd_selected_payload_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v if k not in ('changes','non_text_or_structure_changes') else len(v) for k,v in result.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
