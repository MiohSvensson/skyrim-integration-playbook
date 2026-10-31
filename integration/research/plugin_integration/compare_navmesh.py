"""Read specific indexed NAVM bytes; compare geometry sections with named FormIDs."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import zlib

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
SOURCES=json.loads((OUT/'plugin_candidates.json').read_text(encoding='utf-8'))['source_plugins']


def sha(v):return hashlib.sha256(v).hexdigest()


def subrecords(data):
    pos=0;ext=None;out=[]
    while pos<len(data):
        tag=data[pos:pos+4].decode();n=struct.unpack_from('<H',data,pos+4)[0];pos+=6
        if tag=='XXXX':ext=struct.unpack_from('<I',data,pos)[0];pos+=n;continue
        if ext is not None:n=ext;ext=None
        out.append((tag,data[pos:pos+n]));pos+=n
    assert pos==len(data);return out


def nvnm(data,masters,self_name):
    pos=0
    def read(fmt):
        nonlocal pos
        values=struct.unpack_from('<'+fmt,data,pos);pos+=struct.calcsize('<'+fmt)
        return values[0] if len(values)==1 else values
    def blob(n):
        nonlocal pos
        out=data[pos:pos+n];pos+=n;assert len(out)==n;return out
    def form(fid):
        if not fid:return 'NULL'
        i=fid>>24;name=masters[i] if i<len(masters) else self_name
        return name.casefold()+'|'+f'{fid&0xffffff:06X}'
    version=read('I');assert version in (12,13),version
    crc=read('I');world=read('I');cell=read('I')
    pathing={'crc':crc,'world':form(world),'cell_or_coords':form(cell) if not world else struct.unpack('<hh',struct.pack('<I',cell))}
    n=read('I');vertices=blob(n*12);vn=n
    n=read('I');triangles=blob(n*16);tn=n
    n=read('I');edges=[]
    for _ in range(n):
        typ,ref,tri=read('IIh');edges.append({'type':typ,'navmesh':form(ref),'triangle':tri})
    n=read('I');doors=[]
    for _ in range(n):
        tri,crc,ref=read('hII');doors.append({'triangle':tri,'crc':crc,'door':form(ref)})
    n=read('I');cover=blob(n*2)
    grid=blob(len(data)-pos)
    return {'version':version,'pathing':pathing,'vertex_count':vn,'vertices_sha256':sha(vertices),
      'triangle_count':tn,'triangles_sha256':sha(triangles),'edges':edges,'doors':doors,
      'cover_count':n,'cover_sha256':sha(cover),'grid_bytes':len(grid),'grid_sha256':sha(grid),
      '_triangles':[list(struct.unpack_from('<HHHhhhHH',triangles,i*16)) for i in range(tn)]}


def main():
    c=sqlite3.connect((ROOT/'baseline/plugin_records.sqlite').as_uri()+'?mode=ro',uri=True)
    c.row_factory=sqlite3.Row
    origin=c.execute("select id from origins where name_key='skyrim.esm'").fetchone()[0]
    targets=[0x016F5D,0x0EC466,0x0EC469,0x108AB4]
    result={'schema_source':str(ROOT/'sources/TES5Edit/Core/wbDefinitionsTES5.pas'),'schema_lines':[5469,5560],'records':{}}
    for obj in targets:
        rows=[]
        for r in c.execute('''select p.pack,p.name,p.path,p.id,r.byte_offset from records r
          join plugins p on p.id=r.plugin_id where r.origin_id=? and r.object_id=? and r.signature='NAVM'
          order by p.pack,p.id''',(origin,obj)):
            if r['pack']=='Burida':continue
            if r['name'].casefold() not in {'skyrim.esm','glenmoril.esm','akskyrimunderground.esm','ancientland2.esp',"redbag's falkreath.esp",'forgottencity.esp','unofficial skyrim special edition patch.esp'}:continue
            source=SOURCES[r['pack']][r['name'].casefold()]
            with open(r['path'],'rb') as f:
                f.seek(r['byte_offset']);header=f.read(24);length=struct.unpack_from('<I',header,4)[0];flags=struct.unpack_from('<I',header,8)[0];body=f.read(length)
            if flags&0x40000:body=zlib.decompress(body[4:])
            fields=subrecords(body);geometry=nvnm(next(v for k,v in fields if k=='NVNM'),source['masters'],source['name'])
            rows.append({'pack':r['pack'],'plugin':r['name'],'snapshot_path':r['path'],'record_byte_offset':r['byte_offset'],
              'flags':flags,'field_tags':[k for k,v in fields],'nvnm':geometry,
              'other_field_hashes':[(k,sha(v)) for k,v in fields if k!='NVNM']})
        vanilla=next(r['nvnm'] for r in rows if r['pack']=='TuLED' and r['plugin']=='Skyrim.esm')
        for row in rows:
            g=row['nvnm']
            if g['vertices_sha256']==vanilla['vertices_sha256'] and g['triangle_count']==vanilla['triangle_count']:
                g['changed_triangles_against_vanilla']=[{'index':i,'vanilla':a,'candidate':b} for i,(a,b) in enumerate(zip(vanilla['_triangles'],g['_triangles'])) if a!=b]
        for row in rows:row['nvnm'].pop('_triangles')
        result['records'][f'Skyrim.esm|{obj:06X}']=rows
    (OUT/'navmesh_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for key,rows in result['records'].items():
        print(key)
        for row in rows:
            g=row['nvnm'];print(row['pack'],row['plugin'],'vertices',g['vertex_count'],g['vertices_sha256'][:12],'triangles',g['triangle_count'],g['triangles_sha256'][:12],'doors',g['doors'])


if __name__=='__main__':main()
