"""Read-only final-profile resolution and task-owned output guards."""
import hashlib
import os
import struct
import sys
import zlib
from pathlib import Path

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
INTEGRATION=OUT.parents[1]
DB=OUT.parents[2]
TARGET=DB/'UnifiedSkyrim'
OLD=OUT.parent/'runtime_layout/lod_update'
sys.path.insert(0,str(INTEGRATION))
import runtime_inventory as ri
sys.path.insert(0,str(OUT.parent/'navmesh_patch'))
from verify_candidate import fields


def sha(path):
    value=os.path.abspath(path)
    if not value.startswith('\\\\?\\'):value='\\\\?\\'+value
    with open(value,'rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def owned(path):
    path=Path(path).absolute()
    assert path!=OUT and path.resolve().is_relative_to(OUT.resolve()),'Output must stay under research/lod_update'
    for ancestor in [path,*path.parents]:
        if ancestor==OUT.parent:break
        if ancestor.exists():assert not ancestor.stat().st_file_attributes&0x400,'Reparse output forbidden'
    return path


def final_inputs(profile_name):
    assert profile_name in ('Unified Build','Unified Skyrim')
    profile=TARGET/'profiles'/profile_name
    initial={name:sha(profile/name) for name in ('plugins.txt','modlist.txt')}
    ri.PROFILE=profile
    mods=ri.active_mods()
    assert all(folder.resolve().is_relative_to((TARGET/'mods').resolve()) and folder.is_dir() for _,folder in mods)
    names=ri.plugin_names(mods)
    rows=[];full=light=0
    for name in names:
        provider,path=ri.resolve(name,mods)
        assert path is not None,f'Missing active plugin {name}'
        stat=path.stat();header=ri.header(path)
        assert stat.st_mtime_ns==path.stat().st_mtime_ns,f'Plugin changed during read: {path}'
        kind='light' if header['is_light'] else 'full'
        slot=light if kind=='light' else full
        if kind=='light':light+=1
        else:full+=1
        rows.append({'name':name,'name_key':name.lower(),'provider':provider,'path':str(path),
                     'size':stat.st_size,'mtime_ns':stat.st_mtime_ns,'kind':kind,'slot':slot,**header})
    assert full<=254 and light<=4096,'Plugin slot budget exceeded'
    keys={row['name_key'] for row in rows}
    assert all(master.lower() in keys for row in rows for master in row['masters']),'Enabled plugin has absent master'
    assert initial=={name:sha(profile/name) for name in initial},'Profile changed during source resolution; refresh preparation'
    assert all(Path(row['path']).stat().st_mtime_ns==row['mtime_ns'] and Path(row['path']).stat().st_size==row['size'] for row in rows),'Plugin changed during preparation'
    return profile,mods,rows


def runtime_id(identity,plugins):
    origin,object_id=identity.split('|');owner=next(row for row in plugins if row['name_key']==origin.lower())
    value=int(object_id,16)
    if owner['kind']=='light':assert value<=0xFFF;return 0xFE000000|(owner['slot']<<12)|value
    assert value<=0xFFFFFF;return (owner['slot']<<24)|value


class Mini:
    def __init__(self,row):
        self.row=row;self.path=Path(row['path']);self.names=[name.lower() for name in row['masters']]+[row['name_key']]
    def identity(self,value):
        if value==0:return 'NULL'
        index=value>>24
        assert index<len(self.names),f'Unmapped typed FormID {value:08X} in {self.path}'
        return self.names[index]+'|'+f'{value&0xFFFFFF:06X}'
    def read(self,mode,callback,cell_ids=()):
        with self.path.open('rb') as stream:
            def walk(start,end,world=None,cell=None):
                pos=start
                while pos<end:
                    stream.seek(pos);h=stream.read(24);assert len(h)==24
                    size=struct.unpack_from('<I',h,4)[0]
                    if h[:4]==b'GRUP':
                        assert size>=24 and pos+size<=end
                        typ=struct.unpack_from('<i',h,12)[0];label=h[8:12]
                        descend=True;w=world;c=cell
                        if typ==0:descend=label==b'WRLD'
                        if typ==1:
                            w=self.identity(struct.unpack('<I',label)[0]);c=None
                            descend=mode!='worlds' and w=='skyrim.esm|00003C'
                        if typ in (6,8,9,10):
                            c=self.identity(struct.unpack('<I',label)[0])
                            descend=mode=='targets' and c in cell_ids
                        if descend:walk(pos+24,pos+size,w,c)
                    else:
                        assert pos+24+size<=end
                        signature=h[:4].decode('ascii')
                        record_id=self.identity(struct.unpack_from('<I',h,12)[0]) if signature in ('WRLD','CELL','LAND') else None
                        take=(mode=='worlds' and signature=='WRLD') or (mode=='find' and signature=='CELL' and world=='skyrim.esm|00003C') or (mode=='targets' and ((signature=='CELL' and record_id in cell_ids) or (signature=='LAND' and cell in cell_ids)))
                        if take:
                            flags=struct.unpack_from('<I',h,8)[0];stream.seek(pos+24);data=stream.read(size)
                            if flags&0x40000:
                                length=struct.unpack_from('<I',data)[0];data=zlib.decompress(data[4:]);assert len(data)==length
                            callback({'id':record_id,'signature':signature,'flags':flags,'offset':pos,'world':world,'cell':cell,
                                      'plugin':self.row['name'],'path':str(self.path),'payload_sha256':hashlib.sha256(data).hexdigest()},list(fields(data)),self)
                        size+=24
                    pos+=size
                assert pos==end
            walk(0,self.path.stat().st_size)
