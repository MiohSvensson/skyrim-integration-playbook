"""Decode the four known missing VMAD property targets without changing bytes."""
import json
from pathlib import Path
import struct
import sys

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'rootcause'))
import plugin_binary


def vmad(data):
    pos=0
    def read(fmt):
        nonlocal pos
        value=struct.unpack_from('<'+fmt,data,pos);pos+=struct.calcsize('<'+fmt)
        return value[0] if len(value)==1 else value
    def string():
        nonlocal pos
        length=read('H');out=data[pos:pos+length].decode('utf-8','replace');pos+=length;return out
    version,objfmt,count=read('HHH');out=[]
    def value(typ):
        if typ==1:
            if objfmt==2:
                unused,alias,fid=read('HhI')
            else:fid,alias,unused=read('IhH')
            return {'form_id':f'{fid:08X}','alias':alias,'unused':unused}
        if typ==2:return string()
        if typ in (3,4):return read('i' if typ==3 else 'f')
        if typ==5:return read('B')
        if typ in (11,12,13,14,15):return [value(typ-10) for _ in range(read('I'))]
        raise ValueError((typ,pos,len(data)))
    for _ in range(count):
        name=string();status=read('B');properties=[];count_offset=pos;property_count=read('H')
        for _ in range(property_count):
            begin=pos;pn=string();typ=read('B');ps=read('B');off=pos;v=value(typ)
            properties.append({'name':pn,'type':typ,'status':ps,'value':v,'value_offset':off,'start_offset':begin,'end_offset':pos})
        out.append({'name':name,'status':status,'properties':properties,'property_count_offset':count_offset,'property_count':property_count})
    return {'version':version,'object_format':objfmt,'scripts':out,'parsed_main_bytes':pos,'trailing_fragment_bytes':len(data)-pos}


def main():
    source=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))['source_plugins']['Anno']['moonandstar_mas.esp']
    masters,records=plugin_binary.read(source['snapshot_path']);targets={0x0202CD4A,0x02039A41,0x02039A42,0x02039A43};rows=[]
    for record in records:
        for tag,data in record['fields']:
            if tag!='VMAD' or not any(struct.pack('<I',target) in data for target in targets):continue
            decoded=vmad(data);rows.append({'signature':record['sig'],'form_id':f"{record['fid']:08X}",'edid':record['edid'],
              'vmad_bytes':len(data),'decoded':decoded})
    result={'plugin':source['snapshot_path'],'masters':masters,'targets':[f'{t:08X}' for t in sorted(targets)],'records':rows}
    (OUT/'moonstar_vmad_evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
