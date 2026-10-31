"""Remove only four VMAD assignments whose properties do not exist in the actual PEX."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'rootcause'))
import plugin_binary
from moonstar_vmad import vmad

EXPECTED={0x02011E82:('MASCoreScript','MASCoreHPBar',0x02039A41),
          0x02011E84:('MASCoreScript','MASCoreHPBar',0x02039A43),
          0x02011E88:('MASCoreScript','MASCoreHPBar',0x02039A42),
          0x0200C054:('TIF__0200C054','MASSelyseDiscountQuest',0x0202CD4A)}


def cleaned(data,expected):
    decoded=vmad(data);ranges=[];counts=[];script_name,property_name,missing=expected
    for script in decoded['scripts']:
        if script['name'].casefold()!=script_name.casefold():continue
        matches=[p for p in script['properties'] if p['name'].casefold()==property_name.casefold()]
        assert len(matches)==1
        p=matches[0];assert p['type']==1 and p['value']['form_id']==f'{missing:08X}'
        ranges.append((p['start_offset'],p['end_offset']));counts.append((script['property_count_offset'],script['property_count']-1))
    assert len(ranges)==1
    updated=bytearray(data)
    for at,count in counts:struct.pack_into('<H',updated,at,count)
    for start,end in sorted(ranges,reverse=True):del updated[start:end]
    assert data[decoded['parsed_main_bytes']:]==bytes(updated)[vmad(updated)['parsed_main_bytes']:]
    return bytes(updated),{'script':script_name,'property':property_name,'missing_form_id':f'{missing:08X}',
      'removed_range':ranges[0],'old_vmad_bytes':len(data),'new_vmad_bytes':len(updated),
      'fragment_tail_bytes_preserved':decoded['trailing_fragment_bytes']}


def main():
    source=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))['source_plugins']['Anno']['moonandstar_mas.esp']
    declarations={};scripts=OUT/'moonstar_scripts'
    for name,prop,_ in EXPECTED.values():
        pex=scripts/'pex'/(name.casefold()+'.pex');asm=scripts/'assembly'/(name.casefold()+'.pas');psc=scripts/'author_source'/(name.casefold()+'.psc')
        assert prop.casefold().encode() not in pex.read_bytes().lower()
        assert not re.search(r'\b'+re.escape(prop)+r'\b',asm.read_text(encoding='utf-8'),re.I)
        assert not re.search(r'\b'+re.escape(prop)+r'\b',psc.read_text(encoding='utf-8-sig'),re.I)
        declarations[name]=re.findall(r'^\s*\.property\s+(\S+)',asm.read_text(encoding='utf-8'),re.M)
    c=sqlite3.connect((ROOT/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    keys=['scripts/mascorescript.pex','scripts/tif__0200c054.pex']
    loose=[dict(zip(('mod_id','relative_path'),r)) for r in c.execute('select mod_id,relative_path from files where path_key in (?,?) and virtual_candidate=1',keys)]
    assert not loose,'Unexpected loose overrides; inspect before repair.'
    target=OUT/'moonstar_cleanup_candidate/MoonAndStar_MAS.esp';target.parent.mkdir(exist_ok=True)
    changes=[]
    def change(record):
        if record['fid'] not in EXPECTED:return None
        fields=[];found=False
        for tag,value in record['fields']:
            if tag=='VMAD':
                value,proof=cleaned(value,EXPECTED[record['fid']]);changes.append({'signature':record['sig'],'form_id':f"{record['fid']:08X}"}|proof);found=True
            fields.append((tag,value))
        assert found
        return record['fid'],fields
    plugin_binary.rewrite(source['snapshot_path'],target,change)
    assert len(changes)==4
    am,aa=plugin_binary.read(source['snapshot_path']);bm,bb=plugin_binary.read(target)
    assert am==bm and len(aa)==len(bb)
    for a,b in zip(aa,bb):
        assert (a['sig'],a['fid'],a['flags'])==(b['sig'],b['fid'],b['flags'])
        expected_fields=[]
        for tag,value in a['fields']:
            if a['fid'] in EXPECTED and tag=='VMAD':value,_=cleaned(value,EXPECTED[a['fid']])
            expected_fields.append((tag,value))
        assert expected_fields==b['fields']
        if a['fid'] in EXPECTED:
            for tag,value in b['fields']:
                if tag=='VMAD':
                    for script in vmad(value)['scripts']:
                        declared={p.casefold() for p in declarations[script['name']]}
                        assert all(p['name'].casefold() in declared for p in script['properties'])
    report={'candidate':str(target),'candidate_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
      'source':source['snapshot_path'],'source_sha256':hashlib.sha256(Path(source['snapshot_path']).read_bytes()).hexdigest(),
      'record_count_including_header':len(aa),'masters':am,'changes':changes,'compiled_property_declarations':declarations,
      'loose_script_overrides':loose,'script_source_provenance':str(scripts/'provenance.json'),
      'verification':'Only four VMAD property entries and their exact property counts changed. All IDs, flags, masters and other decompressed ordered subrecords are byte-identical; fragment tail preserved. Both removed property names are absent from actual PEX bytes, assembly property table, and bundled author source.',
      'xedit_status':'Pending native and complete final-view validation; not activated here.'}
    (OUT/'moonstar_cleanup_evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
