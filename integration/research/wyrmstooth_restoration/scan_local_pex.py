"""Search every workspace loose PEX and every inventoried BSA PEX, read-only."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent;BASE=OWN.parents[2];WORKSPACE=BASE.parent
sys.path.insert(0,str(BASE/'rootcause'))
from bsarch_readonly import extract_files
NEEDLES=[b'3943ab',b'wt_amb_crickets01']


def main():
    start=time.time();hits=[];errors=[];seen=set();counts=collections.Counter()
    paths=subprocess.run(['rg','--files','--hidden','--no-ignore','-g','*.pex','-g','*.PEX',str(WORKSPACE)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout.decode('utf-8').splitlines()
    (OWN/'loose_pex_paths.json').write_text(json.dumps(paths,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(b,location):
        sha=hashlib.sha256(b).hexdigest();counts['logical_pex_objects']+=1
        if sha in seen:return
        seen.add(sha);counts['unique_pex_bytes']+=len(b);counts['unique_pex_contents']+=1
        lower=b.lower()
        if any(n in lower for n in NEEDLES):
            tokens=[v.decode('ascii','replace') for v in re.findall(rb'[\x20-\x7e]{4,}',b) if any(n in v.lower() for n in NEEDLES)]
            row={'location':location,'sha256':sha,'bytes':len(b),'matching_ascii_strings':tokens}
            dest=OWN/'local_hits'/(sha+'.pex');dest.parent.mkdir(exist_ok=True);dest.write_bytes(b);row['saved_copy']=str(dest);hits.append(row)
            print('HIT',json.dumps(row,ensure_ascii=False),flush=True)
    for n,path in enumerate(paths):
        try:check(Path(path).read_bytes(),{'kind':'loose','path':path});counts['loose_pex_scanned']+=1
        except Exception as e:errors.append({'path':path,'error':repr(e)})
        if n%10000==0:print('loose PEX',n,'/',len(paths),flush=True)
    db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    groups={}
    for r in db.execute("select a.id,a.path,a.sha256 archive_sha,e.path_key,e.sha256 from bsa_entries e join bsa_archives a on a.id=e.archive_id where e.path_key like 'scripts/%.pex' and e.status='ok' order by a.id=117 desc,a.id"):
        g=groups.setdefault(r['archive_sha'],{'archive':r['path'],'archive_id':r['id'],'members':{}})
        if r['id']==g['archive_id']:g['members'][r['path_key']]=r['sha256']
        counts['bsa_logical_member_rows']+=1
    for n,g in enumerate(groups.values()):
        try:
            blobs=extract_files(g['archive'],g['members'])
            for k,b in blobs.items():check(b,{'kind':'BSA','archive':g['archive'],'member':k})
            counts['unique_archives_scanned']+=1;counts['bsa_pex_scanned']+=len(blobs)
        except Exception as e:errors.append({'archive':g['archive'],'error':repr(e)})
        if n%20==0:print('BSA PEX archives',n+1,'/',len(groups),'hits',len(hits),flush=True)
    result={'scope':'All discoverable loose PEX below workspace, including hidden/ignored files; all unique inventoried BSA contents containing scripts/*.pex regardless of activation. Not a runtime loading claim.',
      'needles':[v.decode() for v in NEEDLES],'counts':dict(counts),'hits':hits,'errors':errors,'elapsed_seconds':time.time()-start}
    (OWN/'local_pex_scan.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='scope'},ensure_ascii=False),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
