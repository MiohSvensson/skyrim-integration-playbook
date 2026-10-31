"""Read-only SSE BS100 geometry and BodySlide TRIP topology inspection."""
import hashlib
import math
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent;BASE=OWN.parents[2]
sys.path.insert(0,str(BASE/'rootcause'))
from nif_inventory import inventory


class Reader:
    def __init__(self,b,pos=0,end=None):self.b=b;self.pos=pos;self.end=len(b) if end is None else end
    def raw(self,n):
        if n<0 or self.pos+n>self.end:raise ValueError(('Read outside typed block',self.pos,n,self.end))
        v=self.b[self.pos:self.pos+n];self.pos+=n;return v
    def get(self,fmt):
        v=struct.unpack('<'+fmt,self.raw(struct.calcsize('<'+fmt)));return v[0] if len(v)==1 else v
    def name(self):return self.raw(self.get('B')).decode('utf-8')


def vertex_view(raw,stride,desc):
    assert stride>0 and len(raw)%stride==0 and stride==(desc&15)*4,(stride,hex(desc),len(raw))
    count=len(raw)//stride;attrs=desc>>44;positions=[]
    if attrs&1:
        for n in range(count):
            xyz=struct.unpack_from('<fff',raw,n*stride)
            if not all(math.isfinite(v) for v in xyz):raise ValueError(('Nonfinite vertex',n,xyz))
            positions.append(xyz)
    if attrs&2:
        uv_offset=((desc>>8)&15)*4
        assert uv_offset+4<=stride
        for n in range(count):
            uv=struct.unpack_from('<ee',raw,n*stride+uv_offset)
            if not all(math.isfinite(v) for v in uv):raise ValueError(('Nonfinite UV',n,uv))
    return {'vertex_count':count,'stride':stride,'vertex_desc':f'{desc:016X}',
      'vertex_buffer_sha256':hashlib.sha256(raw).hexdigest(),
      'position_min':[min((v[i] for v in positions),default=0) for i in range(3)],
      'position_max':[max((v[i] for v in positions),default=0) for i in range(3)]}


def skin_partition(b,block):
    r=Reader(b,block['offset'],block['offset']+block['bytes'])
    n,size,stride,desc=r.get('IIIQ');v=vertex_view(r.raw(size),stride,desc);alltri=[];parts=[]
    for _ in range(n):
        nv,nt,nb,ns,nw=r.get('5H');r.raw(nb*2)
        has_map=r.get('B');vm=list(struct.unpack('<'+str(nv)+'H',r.raw(nv*2))) if has_map else []
        if r.get('B'):r.raw(nv*nw*4)
        strips=[r.get('H') for _ in range(ns)]
        if r.get('B'):
            r.raw(sum(strips)*2 if ns else nt*6)
        if r.get('B'):r.raw(nv*nw)
        lod,global_vb,pdesc=r.get('BBQ');tri=r.raw(nt*6)
        for face in struct.iter_unpack('<HHH',tri):
            if max(face)>=v['vertex_count']:raise ValueError(('Skin triangle outside global vertex buffer',face,v['vertex_count']))
        if vm and max(vm)>=v['vertex_count']:raise ValueError('Skin vertex map out of range')
        alltri.append(tri);parts.append({'vertices':nv,'triangles':nt,'bones':nb,'weights_per_vertex':nw,'global_vb':global_vb,'lod':lod})
    assert r.pos==r.end,('Unconsumed NiSkinPartition bytes',r.pos,r.end)
    v.update(triangle_count=sum(p['triangles'] for p in parts),triangle_stream_sha256=hashlib.sha256(b''.join(alltri)).hexdigest(),partitions=parts)
    return v


def nif(path):
    path=Path(path);b=path.read_bytes();inv=inventory(path);shapes=[];bodytri=[];partcache={}
    for block in inv['blocks']:
        o=block['offset'];typ=block['type']
        if typ=='NiStringExtraData':
            assert block['bytes']==8;ni,vi=struct.unpack_from('<II',b,o)
            name=inv['strings'][ni] if ni!=0xffffffff else '';value=inv['strings'][vi] if vi!=0xffffffff else ''
            if name.upper()=='BODYTRI':bodytri.append(value)
        if typ in ('NiTriShape','NiTriStrips'):raise ValueError('Legacy geometry is not accepted as generated SSE output: '+typ)
        if typ not in ('BSTriShape','BSDynamicTriShape','BSSubIndexTriShape'):continue
        extra=struct.unpack_from('<I',b,o+4)[0];skin,shader=struct.unpack_from('<II',b,o+88+4*extra)
        desc,nt,nv,size=struct.unpack_from('<QHHI',b,o+100+4*extra)
        if size:
            start=o+116+4*extra;stride=(desc&15)*4;v=vertex_view(b[start:start+nv*stride],stride,desc)
            assert size==nv*stride+nt*6
            faces=b[start+nv*stride:start+size]
            for face in struct.iter_unpack('<HHH',faces):
                if max(face)>=nv:raise ValueError('Shape triangle out of range')
            v.update(triangle_count=nt,triangle_stream_sha256=hashlib.sha256(faces).hexdigest(),partitions=[])
        else:
            assert skin!=0xffffffff,('No shape data and no skin',block['name'])
            sb=inv['blocks'][skin];assert sb['type'] in ('NiSkinInstance','BSDismemberSkinInstance'),sb['type']
            partition=struct.unpack_from('<I',b,sb['offset']+4)[0]
            if partition not in partcache:
                pb=inv['blocks'][partition];assert pb['type']=='NiSkinPartition';partcache[partition]=skin_partition(b,pb)
            v=partcache[partition]
        shapes.append({'name':block['name'],'type':typ,'block':block['index'],'skin_block':skin,'shader_block':shader,**v})
    if len({s['name'] for s in shapes})!=len(shapes):raise ValueError('Duplicate shape names')
    return {'path':str(path),'sha256':inv['sha256'],'bytes':len(b),'shapes':shapes,'bodytri_references':bodytri,'header_version':[inv['user_version'],inv['bs_version']]}


def tri(path):
    # C++ "TRIP"_mci is the numeric FourCC 0x54524950, serialized little-endian.
    path=Path(path);b=path.read_bytes();r=Reader(b);assert r.raw(4)==b'PIRT','Expected BodySlide TRIP integer FourCC / on-disk PIRT';groups=[]
    def group(kind,components):
        names=set()
        for _ in range(r.get('H')):
            name=r.name();assert name and name not in names;names.add(name);morphs=[];mnames=set()
            for _ in range(r.get('H')):
                mn=r.name();assert mn and mn not in mnames;mnames.add(mn);scale,count=r.get('fH');assert math.isfinite(scale) and scale>=0
                ids=[]
                for _ in range(count):
                    v=r.get('H'+'h'*components);ids.append(v[0])
                assert len(set(ids))==len(ids),('Duplicate morph indices',name,mn)
                morphs.append({'name':mn,'vertex_offsets':count,'maximum_vertex_index':max(ids,default=-1),'scale':scale})
            groups.append({'shape':name,'kind':kind,'morphs':morphs})
    group('position',3)
    if r.pos<len(b):group('uv',2)
    assert r.pos==len(b),('Trailing TRI bytes',r.pos,len(b))
    return {'path':str(path),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'groups':groups}
