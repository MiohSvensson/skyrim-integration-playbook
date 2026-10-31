"""Inspect only original public author release copies in this research folder."""
import ctypes
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent;BASE=OWN.parents[2]
sys.path.insert(0,str(BASE/'rootcause'))
import bsarch_readonly as bs
from plugin_binary import read,brief


def main():
    release=Path(sys.argv[1]).resolve();assert release.is_relative_to(OWN)
    archive=release/'Wyrmstooth.bsa';h=bs.create();records={};hits=[];names=[]
    try:
        msg=bs.load(h,str(archive));assert msg.code>=0,msg.text
        @bs.callback
        def visit(a,name,record,folder,context):
            k=name.replace('\\','/').casefold();names.append(k)
            if k.endswith(('.pex','.psc')) or 'cricket' in k:records[k]=record
            return False
        msg=bs.iterate(h,visit,None);assert msg.code>=0,msg.text
        script_count=0
        for k,record in records.items():
            r=bs.extract(h,record)
            try:
                assert r.message.code>=0,r.message.text;b=ctypes.string_at(r.buffer.data,r.buffer.size)
            finally:
                if r.buffer.data:assert bs.freebuf(h,r.buffer).code>=0
            if k.endswith(('.pex','.psc')):script_count+=1
            if b'3943ab' in b.lower() or 'cricket' in k:
                dest=release/'matched_resources'/k;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
                hits.append({'member':k,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'path':str(dest),
                  'matching_strings':[t.decode('ascii','replace') for t in re.findall(rb'[\x20-\x7e]{4,}',b) if b'3943ab' in t.lower()]})
    finally:bs.close(h);bs.free(h)
    masters,recs=read(release/'Wyrmstooth.esp');targets=[brief(r) for r in recs if r['fid']&0xffffff in [0x3943ab,0x8bfae2,0x3943aa,0x3943a0]]
    result={'release':str(release),'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'member_count':len(names),'script_members_content_searched':script_count,
      'matching_names':[k for k in names if '3943ab' in k or 'cricket' in k],'matches':hits,'plugin_masters':masters,'target_plugin_records':targets}
    (release/'inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='target_plugin_records'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
