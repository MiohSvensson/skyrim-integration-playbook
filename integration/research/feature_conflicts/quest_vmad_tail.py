"""Pinned 4.1.5f QUST VMAD tail: preserve bytes, canonicalize typed FormIDs.

Only version5 script-entry layouts are accepted. All other bytes, including
float bits, string lengths/bytes, fragment data and alias indices remain raw.
"""
import struct


def canonical_quest_tail(data,object_format,form):
    pos=0;references=[]

    def take(size):
        nonlocal pos
        if size<0 or pos+size>len(data):raise ValueError('Truncated QUST VMAD tail')
        start=pos;pos+=size
        return data[start:pos]

    def integer(fmt):return struct.unpack('<'+fmt,take(struct.calcsize('<'+fmt)))[0]

    def string():take(integer('H'))

    def obj(fmt):
        nonlocal pos
        start=pos
        if fmt==1:
            fid=integer('I');take(4);offset=start
        elif fmt==2:
            take(4);offset=pos;fid=integer('I')
        else:raise ValueError('Unsupported QUST VMAD object format')
        references.append({'offset':offset,'canonical':form(fid)})

    def value(typ,fmt):
        if typ==0:return
        if typ==1:obj(fmt);return
        if typ==2:string();return
        if typ in (3,4):take(4);return
        if typ==5:take(1);return
        if typ in (11,12,13,14,15):
            count=integer('I')
            if count>len(data):raise ValueError('Unbounded QUST VMAD array')
            for _ in range(count):value(typ-10,fmt)
            return
        raise ValueError('Unsupported QUST VMAD property type '+str(typ))

    if not data:return {'chunks':[],'typed_form_count':0}
    extra_bind=integer('b')
    if extra_bind!=2:raise ValueError('Unsupported QUST VMAD extra bind version')
    fragments=integer('H');string()
    if fragments>len(data):raise ValueError('Unbounded QUST VMAD fragment count')
    for _ in range(fragments):
        take(2+2+4+1);string();string()
    alias_count=integer('H')
    if alias_count>len(data):raise ValueError('Unbounded QUST VMAD alias count')
    for _ in range(alias_count):
        obj(object_format)
        version=integer('h');local_format=integer('h')
        if version!=5:raise ValueError('Unsupported QUST VMAD alias script version')
        if local_format not in (1,2):raise ValueError('Unsupported QUST VMAD alias object format')
        script_count=integer('H')
        if script_count>len(data):raise ValueError('Unbounded QUST VMAD alias script count')
        for _ in range(script_count):
            string();take(1);props=integer('H')
            if props>len(data):raise ValueError('Unbounded QUST VMAD property count')
            for _ in range(props):
                string();typ=integer('B');take(1);value(typ,local_format)
    if pos!=len(data):raise ValueError('Unconsumed QUST VMAD tail bytes')
    previous=0;chunks=[]
    for ref in references:
        offset=ref['offset']
        assert offset>=previous
        chunks.append({'raw':data[previous:offset].hex()})
        chunks.append({'form':ref['canonical']})
        previous=offset+4
    chunks.append({'raw':data[previous:].hex()})
    return {'chunks':chunks,'typed_form_count':len(references)}
