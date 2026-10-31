"""Read-only Skyrim VMAD script/property decoder; unsupported types stay explicit."""
import struct


def parse_vmad(data,form):
    pos=0
    def take(fmt):
        nonlocal pos
        vals=struct.unpack_from('<'+fmt,data,pos);pos+=struct.calcsize('<'+fmt)
        return vals[0] if len(vals)==1 else vals
    def string():
        nonlocal pos
        n=take('H');raw=data[pos:pos+n];assert len(raw)==n;pos+=n
        return raw.decode('utf-8','replace')
    version,object_format,count=take('HHH')
    assert version in (3,4,5,6),version
    assert object_format in (1,2),object_format
    def value(typ):
        if typ==1:
            if object_format==1:fid,alias,unused=take('IhH')
            else:unused,alias,fid=take('HhI')
            return {'form':form(fid),'alias':alias}
        if typ==2:return string()
        if typ==3:return take('i')
        if typ==4:return {'float_bits':take('I')}
        if typ==5:return take('B')
        if typ in (11,12,13,14,15):return [value(typ-10) for _ in range(take('I'))]
        raise ValueError(f'Unsupported VMAD property type {typ}')
    scripts=[];references=[]
    for _ in range(count):
        name=string();status=take('B') if version>=4 else None;props=[]
        for _ in range(take('H')):
            pname=string();typ=take('B');pstatus=take('B') if version>=4 else None
            val=value(typ);props.append({'name':pname,'type':typ,'status':pstatus,'value':val})
            if typ==1:references.append({'script':name,'property':pname,**val})
            elif typ==11:
                references.extend({'script':name,'property':pname,'array_index':i,**obj} for i,obj in enumerate(val))
        scripts.append({'name':name,'status':status,'properties':sorted(props,key=lambda p:(p['name'].casefold(),p['type']))})
    return {'version':version,'object_format':object_format,'scripts':sorted(scripts,key=lambda s:s['name'].casefold()),
        'tail_hex':data[pos:].hex(),'consumed_script_bytes':pos,'references':references}
