import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'rootcause'))
import bsarch_readonly


def main():
    task=OUT/'moonstar_scripts';task.mkdir(exist_ok=True)
    c=sqlite3.connect((ROOT/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    keys=['scripts/mascorescript.pex','scripts/tif__0200c054.pex','scripts/source/mascorescript.psc','scripts/source/tif__0200c054.psc']
    rows=c.execute('''select a.path,e.path_key,e.sha256,e.size_bytes from bsa_entries e join bsa_archives a on a.id=e.archive_id
      join bsa_sources s on s.archive_id=a.id where s.mod_id=88 and e.path_key in (%s)'''%','.join('?'*len(keys)),keys).fetchall()
    assert len(rows)==4
    archive=Path(rows[0][0]);blobs=bsarch_readonly.extract_files(archive,{r[1]:r[2] for r in rows})
    manifest=[]
    for _,key,digest,size in rows:
        path=task/('author_source' if key.endswith('.psc') else 'pex')/Path(key).name;path.parent.mkdir(exist_ok=True);path.write_bytes(blobs[key])
        manifest.append({'archive':str(archive),'entry':key,'sha256':digest,'bytes':size,'extracted_path':str(path)})
    tool=ROOT/'tools/Champollion-1.3.2/Champollion.exe'
    for name in ['mascorescript.pex','tif__0200c054.pex']:
        r=subprocess.run([str(tool),str(task/'pex'/name),'-p',str(task/'decompiled'),'-a',str(task/'assembly'),'-d','-e'],capture_output=True,text=True)
        (task/(name+'.log')).write_text(r.stdout+'\n'+r.stderr,encoding='utf-8');assert r.returncode==0,(r.stdout,r.stderr)
    (task/'provenance.json').write_text(json.dumps({'files':manifest,'decompiler':str(tool),'decompiler_sha256':hashlib.sha256(tool.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Extracted 4 exact SHA-verified original BSA members and decompiled 2 PEX files with assembly.')


if __name__=='__main__':main()
