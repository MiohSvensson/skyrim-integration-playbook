"""Extract/decompile the inventoried Sofia PEX set into this research directory."""
from pathlib import Path
import hashlib
import concurrent.futures
import json
import os
import re
import sqlite3
import subprocess
import sys

sys.dont_write_bytecode=True
BASE=Path(r'E:\stock\Skyrim collection\Database')
OUT=Path(__file__).resolve().parent/'sofia_scripts'
sys.path.insert(0,str(BASE/'rootcause'))
from bsarch_readonly import extract_files


def main():
    c=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    archive=Path(c.execute('select path from bsa_archives where id=465').fetchone()[0])
    expected={key:sha for key,sha in c.execute("select path_key,sha256 from bsa_entries where archive_id=465 and path_key like 'scripts/%.pex'")}
    data=extract_files(archive,expected)
    assert len(data)==323
    for folder in ('pex','psc','asm','tmp'):(OUT/folder).mkdir(parents=True,exist_ok=True)
    for key,value in data.items():(OUT/'pex'/Path(key).name).write_bytes(value)
    tool=BASE/'tools/Champollion-1.3.2/Champollion.exe'
    env=os.environ.copy();env['TEMP']=env['TMP']=str(OUT/'tmp')
    old_log=OUT/'decompiler.log'
    if old_log.exists() and b'Unable to open file' in old_log.read_bytes():
        (OUT/'decompiler.directory-attempt.log').write_bytes(old_log.read_bytes())
        (OUT/'directory-attempt-status.json').write_text(json.dumps({'status':'FAILED_DIRECTORY_ARGUMENT','psc_generated':0,'finding':'Tool returned 0 despite directory-open errors; not used as decompilation evidence.'},indent=2)+'\n',encoding='utf-8')
    def decompile(path):
        args=[str(tool),str(path),'-p',str(OUT/'psc'),'-a',str(OUT/'asm'),'--no-debug-line']
        result=subprocess.run(args,cwd=OUT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
        return {'script':path.name,'return_code':result.returncode,'stdout':result.stdout.decode('utf-8','replace')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        runs=list(pool.map(decompile,sorted((OUT/'pex').glob('*.pex'))))
    (OUT/'decompiler.log').write_text('\n'.join(r['script']+'\n'+r['stdout'] for r in runs),encoding='utf-8')
    psc=list((OUT/'psc').glob('*.psc'));assembly=list((OUT/'asm').glob('*'))
    patterns={
        'exact_old_pack_id':re.compile(r'(?i)(0x0*9845c\b|\b623708\b)'),
        'named_pack':re.compile(r'(?i)(PlayerHorseStayPut|SofiaHorseStayPut)'),
        'dynamic_lookup':re.compile(r'(?i)\b(?:Game\.)?GetForm(?:FromFile)?\s*\('),
    }
    matches={key:[] for key in patterns}
    for path in psc:
        for n,line in enumerate(path.read_text(encoding='utf-8-sig',errors='replace').splitlines(),1):
            for key,pattern in patterns.items():
                if pattern.search(line):matches[key].append({'path':str(path),'line':n,'text':line.strip()})
    metadata={'archive':str(archive),'archive_id':465,'extracted_scripts':len(data),
        'all_extracted_sha256_match_inventory':True,'decompiler':str(tool),'decompiler_sha256':hashlib.sha256(tool.read_bytes()).hexdigest(),
        'command_pattern':[str(tool),'<one inventoried PEX>','-p',str(OUT/'psc'),'-a',str(OUT/'asm'),'--no-debug-line'],
        'runs':runs,'failed_runs':[r for r in runs if r['return_code'] or 'ERROR:' in r['stdout']],
        'psc_files':len(psc),'assembly_files':len(assembly),
        'matches':matches,'log':str(OUT/'decompiler.log'),
        'scope':'All 323 Sofia BSA PEX scripts decompiled. Literal absence does not exclude calculated dynamic lookup; examine actual GetForm call sites and preserve direct alias package semantics.'}
    (OUT/'audit.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in metadata.items() if k not in ('matches','command_pattern','runs')}|{'match_counts':{k:len(v) for k,v in matches.items()},'dynamic_calls':matches['dynamic_lookup']},ensure_ascii=False,indent=2))
    assert len(psc)==len(data) and not metadata['failed_runs'],'Some scripts did not decompile successfully; do not claim a complete script audit.'


if __name__=='__main__':main()
