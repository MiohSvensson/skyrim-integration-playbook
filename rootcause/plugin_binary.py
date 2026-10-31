import pathlib, struct, zlib

def subs(data):
    pos=0; extended=None; out=[]
    while pos<len(data):
        assert pos+6<=len(data),(pos,len(data))
        tag=data[pos:pos+4].decode('ascii'); n=struct.unpack_from('<H',data,pos+4)[0]; pos+=6
        if tag=='XXXX':
            assert n==4; extended=struct.unpack_from('<I',data,pos)[0]; pos+=4; continue
        if extended is not None:n,extended=extended,None
        assert pos+n<=len(data),(tag,pos,n,len(data))
        out.append((tag,data[pos:pos+n]));pos+=n
    return out

def read(path):
    data=pathlib.Path(path).read_bytes(); records=[]
    def walk(start,end,groups):
        pos=start
        while pos<end:
            assert pos+24<=end
            sig=data[pos:pos+4].decode('ascii'); n=struct.unpack_from('<I',data,pos+4)[0]
            if sig=='GRUP':
                assert n>=24 and pos+n<=end
                label,kind=struct.unpack_from('<Ii',data,pos+8)
                walk(pos+24,pos+n,groups+[(label,kind,pos)]); pos+=n
            else:
                assert pos+24+n<=end
                flags,fid=struct.unpack_from('<II',data,pos+8); payload=data[pos+24:pos+24+n]
                if flags&0x40000:
                    size=struct.unpack_from('<I',payload)[0];payload=zlib.decompress(payload[4:]);assert size==len(payload)
                fields=subs(payload)
                records.append({'sig':sig,'fid':fid,'flags':flags,'offset':pos,'groups':groups,'fields':fields,'edid':next((v.rstrip(b'\0').decode('utf-8','replace') for k,v in fields if k=='EDID'),'')})
                pos+=24+n
        assert pos==end
    walk(0,len(data),[])
    masters=[v.rstrip(b'\0').decode('utf-8','replace') for k,v in records[0]['fields'] if k=='MAST']
    return masters,records

def brief(rec):
    return {k:v for k,v in rec.items() if k!='fields'}|{'fields':[(k,v.hex() if k not in ('EDID','FULL','CNAM','SNAM','MAST','MODL') else v.rstrip(b'\0').decode('utf-8','replace')) for k,v in rec['fields']]}

def encode_subs(fields):
    parts=[]
    for k,v in fields:
        if len(v)>65535:parts.append(b'XXXX'+struct.pack('<HI',4,len(v))); n=0
        else:n=len(v)
        parts.append(k.encode('ascii')+struct.pack('<H',n)+v)
    return b''.join(parts)

def rewrite(path,out,change,prune_empty_groups=False):
    data=pathlib.Path(path).read_bytes(); _,records=read(path); bypos={r['offset']:r for r in records}
    def walk(start,end):
        parts=[];pos=start
        while pos<end:
            n=struct.unpack_from('<I',data,pos+4)[0];header=bytearray(data[pos:pos+24])
            if data[pos:pos+4]==b'GRUP':
                body=walk(pos+24,pos+n);struct.pack_into('<I',header,4,24+len(body))
                if body or not prune_empty_groups:parts.append(bytes(header)+body)
                pos+=n
            else:
                r=bypos[pos];result=change(r)
                if result is False:pass
                elif result is None:parts.append(data[pos:pos+24+n])
                else:
                    fid,fields=result;body=encode_subs(fields)
                    if r['flags']&0x40000:body=struct.pack('<I',len(body))+zlib.compress(body)
                    struct.pack_into('<I',header,4,len(body));struct.pack_into('<I',header,12,fid);parts.append(bytes(header)+body)
                pos+=24+n
        return b''.join(parts)
    pathlib.Path(out).parent.mkdir(parents=True,exist_ok=True);pathlib.Path(out).write_bytes(walk(0,len(data)))
