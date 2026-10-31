"""Stage a private PG0.9.9.5 and isolate only its unsigned managed output-name strings."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys
import pefile
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]

def sha(b):return hashlib.sha256(b).hexdigest()
def compressed(data,p):
    a=data[p]
    if a&0x80==0:return a,1
    if a&0xC0==0x80:return ((a&0x3f)<<8)|data[p+1],2
    assert a&0xE0==0xC0
    return ((a&0x1f)<<24)|(data[p+1]<<16)|(data[p+2]<<8)|data[p+3],4

def isolate(data):
    pe=pefile.PE(data=data);cli=pe.get_offset_from_rva(pe.OPTIONAL_HEADER.DATA_DIRECTORY[14].VirtualAddress)
    assert pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].Size==0,'Authenticode signed binary forbidden'
    assert struct.unpack_from('<I',data,cli+36)[0]==0 and not struct.unpack_from('<I',data,cli+16)[0]&8,'Strong-named binary forbidden'
    md=pe.get_offset_from_rva(struct.unpack_from('<I',data,cli+8)[0]);assert data[md:md+4]==b'BSJB'
    n=struct.unpack_from('<I',data,md+12)[0];p=(md+16+n+3)&~3;count=struct.unpack_from('<H',data,p+2)[0];p+=4;streams={}
    for i in range(count):
        offset,size=struct.unpack_from('<II',data,p);p+=8;end=data.index(b'\0',p);name=data[p:end].decode('ascii');p=(end+1+3)&~3;streams[name]=(md+offset,size)
    start,size=streams['#US'];p=start+1;entries=[]
    while p<start+size:
        length,head=compressed(data,p)
        if length==0:p+=head;continue
        assert length%2==1 and p+head+length<=start+size
        raw=data[p+head:p+head+length-1];text=raw.decode('utf-16-le');entries.append({'text':text,'offset':p+head,'entry_start':p,'entry_bytes':head+length,'heap_offset':p-start,'header_bytes':head,'terminator':data[p+head+length-1]});p+=head+length
    patched=bytearray(data);edits=[]
    for old,new in [('PGPatcher.esp','DBPatcher.esp'),('PG_','DB_')]:
        selected=[r for r in entries if r['text']==old];assert len(selected)==1 and data.count(old.encode('utf-16-le'))==1
        entry=selected[0];a=old.encode('utf-16-le');b=new.encode('utf-16-le');assert len(a)==len(b)
        at=entry['offset'];assert data[at:at+len(a)]==a;patched[at:at+len(a)]=b
        section=next(s for s in pe.sections if s.PointerToRawData<=at<s.PointerToRawData+s.SizeOfRawData)
        edits.append({**entry,'old':old,'new':new,'old_utf16_hex':a.hex(),'new_utf16_hex':b.hex(),'section':section.Name.rstrip(b'\0').decode('ascii'),'replacement_bytes':len(a)})
    allowed={i for e in edits for i in range(e['offset'],e['offset']+e['replacement_bytes'])};changed=[i for i,(a,b) in enumerate(zip(data,patched)) if a!=b]
    assert len(data)==len(patched) and set(changed)<=allowed and changed
    maskedA=bytearray(data);maskedB=bytearray(patched)
    for i in allowed:maskedA[i]=maskedB[i]=0
    assert maskedA==maskedB
    sections=[]
    for s in pe.sections:
        a=s.PointerToRawData;b=a+s.SizeOfRawData
        sections.append({'name':s.Name.rstrip(b'\0').decode('ascii'),'raw_offset':a,'raw_size':s.SizeOfRawData,'original_sha256':sha(data[a:b]),'patched_sha256':sha(patched[a:b]),'bytes_changed':sum(x!=y for x,y in zip(data[a:b],patched[a:b]))})
    ledger={'unsigned_authenticode_and_no_strong_name':True,'metadata_root_offset':md,'US_stream_offset':start,'US_stream_bytes':size,'edits':edits,
        'source_sha256':sha(data),'patched_sha256':sha(patched),'changed_offsets':changed,'changed_bytes':len(changed),'all_other_bytes_sha256':sha(maskedA),'sections':sections,
        'intent':'Only equal-length #US output ModKey/filename namespace and shared TXST EDID prefix. IL, native exports, APIs, security configuration and every other byte are unchanged.',
        'source_locations':['PGMutagen.cs157 OutMod ModKey','PGMutagen.cs1043 TXST EDID prefix','PGMutagen.cs1097-1139 modified-record split filename and SkyrimMod ModKey use same newPluginName']}
    return bytes(patched),ledger

def main():
    source=DB.parent/'TuLED/File Mod Skyrim SE/mods/PGPatcher-0.9.9/PGPatcher';dest=OUT/'tools/PGPatcher-0.9.9.5-private';assert not dest.exists(),'Preserve staged tool; no restaging over it'
    rows=[];skipped=[]
    for p in source.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(source)
        if p.suffix.lower()=='.pdb' or rel.parts[0].lower() in ('log','logs','cache','output','cfg'):
            skipped.append(str(rel));continue
        q=dest/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);data=q.read_bytes();assert q.stat().st_nlink==1 and data==p.read_bytes()
        rows.append({'source':str(p),'destination':str(q),'bytes':len(data),'source_sha256':sha(data),'destination_sha256':sha(data)})
    managed=dest/'PGMutagen.dll';original=managed.read_bytes();evidence=OUT/'upstream_binaries/PGMutagen.original.dll';evidence.parent.mkdir(exist_ok=True);evidence.write_bytes(original)
    patched,ledger=isolate(original);managed.write_bytes(patched);assert managed.stat().st_nlink==1 and (source/'PGMutagen.dll').read_bytes()==original
    (OUT/'PGMutagen_namespace_ledger.json').write_text(json.dumps(ledger,indent=2)+'\n')
    for r in rows:
        if Path(r['destination'])==managed:r['destination_sha256']=sha(patched);r['namespace_isolation_ledger']=str(OUT/'PGMutagen_namespace_ledger.json')
    (OUT/'private_pg_tool_manifest.json').write_text(json.dumps({'status':'STAGED_PRIVATE_NOT_EXECUTED','source_version':'0.9.9.5','source_commit':'bf2333af2077384102bd250969ede87eb4c99367',
        'destination':str(dest),'private_namespace':{'TXST_owner':'DBPatcher.esp','override_plugins':'DB_<n>.esp','EDID_prefix':'DB_'},'files':rows,'skipped_nonruntime':skipped,
        'original_managed_evidence':str(evidence),'original_managed_sha256':sha(original),'patched_managed_sha256':sha(patched),'net8_manifest':str(OUT/'cache/net8/manifest.json')},indent=2)+'\n')
    print('staged',len(rows),'files',sum(r['bytes'] for r in rows),'bytes; modified only',ledger['changed_bytes'],'bytes in #US')
if __name__=='__main__':main()
