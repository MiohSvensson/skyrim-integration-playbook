"""Read-only cache runtime-ID/GRAS-model audit. Never patches or activates caches."""
import collections
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib
sys.dont_write_bytecode=True
from runtime_common import OUT,DB,TARGET,final_inputs,runtime_id,ri,sha,fields

SOURCE=DB.parent/'TuLED/File Mod Skyrim SE'
STOCK=DB.parent/'TuLED/STOCK GAME/Skyrim Special Edition'
def norm(p):return p.lower().replace('\\','/').removeprefix('meshes/')

def source_plugins(profile):
    mods=[(line[1:],SOURCE/'mods'/line[1:]) for line in (profile/'modlist.txt').read_text(encoding='utf-8-sig').splitlines() if line.startswith('+')]
    candidates=[('overwrite',SOURCE/'overwrite'),*mods,('stock',STOCK/'Data')];providers={}
    for provider,folder in candidates:
        if not folder.is_dir():continue
        for f in folder.iterdir():
            if f.is_file() and f.suffix.lower() in ('.esm','.esp','.esl'):providers.setdefault(f.name.lower(),(provider,f))
    names=['Skyrim.esm','Update.esm','Dawnguard.esm','HearthFires.esm','Dragonborn.esm']
    ccc=STOCK/'Skyrim.ccc'
    if ccc.exists():names.extend(s for s in ccc.read_text(encoding='utf-8-sig').splitlines() if s.strip() and not s.startswith('#') and s.lower() in providers)
    names.extend(line[1:] for line in (profile/'plugins.txt').read_text(encoding='utf-8-sig').splitlines() if line.startswith('*'))
    seen=set();rows=[];slots=collections.Counter();missing=[]
    for name in names:
        key=name.lower()
        if key in seen:continue
        seen.add(key)
        if key not in providers:missing.append(name);continue
        provider,path=providers[key];h=ri.header(path);kind='light' if h['is_light'] else 'full'
        rows.append({'name':name,'name_key':key,'path':str(path),'provider':provider,'kind':kind,'slot':slots[kind],**h});slots[kind]+=1
    assert not missing,missing
    return rows

def grasses(rows):
    result={}
    for row in rows:
        names=[m.lower() for m in row['masters']]+[row['name_key']]
        with open(row['path'],'rb') as f:
            end=os.fstat(f.fileno()).st_size;pos=0
            while pos<end:
                f.seek(pos);h=f.read(24);assert len(h)==24
                size=struct.unpack_from('<I',h,4)[0]
                if h[:4]==b'GRUP':
                    assert size>=24 and pos+size<=end
                    if h[8:12]==b'GRAS':
                        at=pos+24
                        while at<pos+size:
                            f.seek(at);rh=f.read(24);rs,flags,fid=struct.unpack_from('<III',rh,4)[0],struct.unpack_from('<I',rh,8)[0],struct.unpack_from('<I',rh,12)[0]
                            assert rh[:4]==b'GRAS' and at+24+rs<=pos+size
                            if flags&0x1000:at+=24+rs;continue
                            assert fid>>24<len(names)
                            ident=names[fid>>24]+'|'+f'{fid&0xFFFFFF:06X}'
                            if flags&0x20:result.pop(ident,None)
                            else:
                                payload=f.read(rs)
                                if flags&0x40000:
                                    length=struct.unpack_from('<I',payload)[0];payload=zlib.decompress(payload[4:]);assert len(payload)==length
                                fd=dict(fields(payload));model=fd.get('MODL',b'').rstrip(b'\0').decode('utf-8','replace')
                                result[ident]={'canonical':ident,'runtime_id':f'{runtime_id(ident,rows):08X}','model':model,
                                    'editor_id':fd.get('EDID',b'').rstrip(b'\0').decode('utf-8','replace'),'winner':row['name'],
                                    'payload_sha256':hashlib.sha256(payload).hexdigest()}
                            at+=24+rs
                        assert at==pos+size
                else:size+=24
                pos+=size
            assert pos==end
    return result

def scan(path):
    data=path.read_bytes();p=0;groups=[]
    def u32():
        nonlocal p
        assert p+4<=len(data);v=struct.unpack_from('<I',data,p)[0];p+=4;return v
    count=u32();assert count<=4096
    for n in range(count):
        size=u32();assert 1<size<=1024 and p+size+15<=len(data)
        model=data[p:p+size];p+=size;assert model[-1]==0 and b'\0' not in model[:-1]
        wave=data[p:p+4].hex();p+=4;offset=p;fid=u32();flags=data[p:p+3].hex();p+=3;blocks=u32();assert blocks<65536
        blades=0
        for b in range(blocks):
            assert p+36<=len(data);vals=struct.unpack_from('<9I',data,p);p+=36
            bc,stride=vals[7:];assert 0<bc<=8191 and stride==16
            p+=bc*stride*2;assert p<=len(data);blades+=bc
        groups.append({'group':n,'model':model[:-1].decode('utf-8','replace'),'form_id':f'{fid:08X}','id_offset':offset,'wave_bytes':wave,'flags_bytes':flags,'blocks':blocks,'blades':blades})
    # Never silently discard malformed/trailing source bytes. Some originals repeat entire prefixes.
    repeats=len(data)//p if len(data)%p==0 and data==data[:p]*(len(data)//p) else None
    return {'path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'groups':groups,'parsed_prefix_bytes':p,'trailing_bytes':len(data)-p,'whole_prefix_repeats':repeats}

def main():
    profile,mods,newrows=final_inputs('Unified Build');new=grasses(newrows)
    olds={};oldrows={}
    for folder in (SOURCE/'profiles').iterdir():
        if not (folder/'plugins.txt').exists():continue
        try:
            rows=source_plugins(folder);oldrows[folder.name]=rows;olds[folder.name]=grasses(rows)
            print('profile',folder.name,len(rows),len(olds[folder.name]),flush=True)
        except Exception as e:print('profile error',folder.name,repr(e),flush=True)
    # Only baseline source Grass Cache assets, not newly generated smoke files.
    files=sorted((SOURCE/'mods/Grass Cache/grass').glob('*.cgid'));assert files
    results=[];errors=[];statistics={name:collections.Counter() for name in olds};ids=collections.Counter();models={}
    maps={name:{r['runtime_id']:r for r in gs.values()} for name,gs in olds.items()}
    for i,path in enumerate(files):
        try:r=scan(path)
        except Exception as e:errors.append({'path':str(path),'error':repr(e)});continue
        for g in r['groups']:
            ids[g['form_id']]+=1;models.setdefault(g['form_id'],set()).add(norm(g['model']))
            g['profile_resolution']={}
            for name,mapping in maps.items():
                source=mapping.get(g['form_id']);status='UNMAPPED' if source is None else ('MATCH' if norm(source['model'])==norm(g['model']) else 'MODEL_MISMATCH')
                statistics[name][status]+=1
                if source is not None:
                    dest=new.get(source['canonical']);g['profile_resolution'][name]={'status':status,'canonical':source['canonical'],'old_model':source['model'],
                        'final_runtime_id':dest['runtime_id'] if dest else None,'final_model':dest['model'] if dest else None,
                        'same_GRAS_payload':source['payload_sha256']==dest['payload_sha256'] if dest else None}
        results.append(r)
        if (i+1)%2000==0:print('caches',i+1,flush=True)
    report={'status':'READ_ONLY_CACHE_IDENTITY_AUDIT','final_profile':str(profile),'final_plugins_sha256':sha(profile/'plugins.txt'),
        'final_modlist_sha256':sha(profile/'modlist.txt'),'source_profiles':{n:{'plugins':rows,'GRAS':olds[n]} for n,rows in oldrows.items()},
        'final_plugins':newrows,'final_GRAS':new,'files':len(results),'bytes':sum(r['bytes'] for r in results),'groups':sum(len(r['groups']) for r in results),
        'source_file_errors':errors,'statistics':{n:dict(v) for n,v in statistics.items()},'unique_ids':dict(ids),
        'models_per_id':{k:sorted(v) for k,v in models.items()},'results':results}
    (OUT/'grass_identity_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','files','bytes','groups','source_file_errors','statistics')},ensure_ascii=False),flush=True)
if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
