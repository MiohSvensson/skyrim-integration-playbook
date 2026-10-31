"""Copy generator programs/resources privately under this research task only.

Never starts a program. Exclusive creation and link/reparse guards protect
source data. Existing identical private files support interrupted staging.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,DB,owned,sha


def excluded(relative):
    parts=relative.as_posix().lower().split('/')
    return (parts[0] in ('logs','summary','cache','backups') or any(part.endswith('_output') for part in parts[:-1]) or
      parts[:2]==['edit scripts','export'] or parts[:3]==['edit scripts','dyndolod','cache'] or
      relative.name.lower().endswith(('_log.txt','.log','.bak','.refcache')) or relative.name.lower()=='bugreport.txt' or
      (parts[0]=='edit scripts' and relative.name.lower().startswith('lodgen_terrain_') and relative.suffix.lower() in ('.bin','.txt')))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tool',choices=['all','FasterNGIO','DynDOLOD','xLODGen'],default='all');parser.add_argument('--plan-only',action='store_true');args=parser.parse_args()
    roots={'FasterNGIO':OLD/'FasterNGIO_1.6/binary','DynDOLOD':DB.parent/'TuLED/Tool/DynDOLOD','xLODGen':DB.parent/'TuLED/Tool/xLODGen'}
    names=['FasterNGIO','DynDOLOD','xLODGen'] if args.tool=='all' else [args.tool]
    report={'status':'PLANNED_ONLY' if args.plan_only else 'PRIVATE_TOOLS_STAGED_NO_PROGRAM_STARTED','tools':{}}
    for name in names:
        source=roots[name].resolve(strict=True);target=owned(OUT/'tools'/('FasterNGIO_1.6' if name=='FasterNGIO' else name));rows=[]
        for folder,dirs,files in os.walk(source):
            dirs[:]=[part for part in dirs if not excluded((Path(folder)/part).relative_to(source))]
            for file in files:
                path=Path(folder)/file;relative=path.relative_to(source)
                if excluded(relative):continue
                assert not path.stat().st_file_attributes&0x400,'Source reparse file forbidden'
                digest=sha(path);destination=owned(target/relative)
                expected=digest;rebased=None
                if name=='DynDOLOD' and relative.suffix.lower() in ('.ini','.txt','.patch') and 'presets' in relative.as_posix().lower():
                    data=path.read_bytes()
                    try:
                        text=data.decode('utf-8-sig')
                        changed=text.replace('C:\\Modding 2\\Tool\\DynDOLOD',str(target)).replace('C:\\Modding 2\\STOCK GAME\\Skyrim Special Edition\\Data',str(DB/'UnifiedSkyrim/Game/Data'))
                        if changed!=text:rebased=changed.encode('utf-8');expected=hashlib.sha256(rebased).hexdigest()
                    except UnicodeError:pass
                if not args.plan_only:
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    if destination.exists():
                        assert destination.is_file() and destination.stat().st_nlink==1,'Only private existing tool files allowed'
                        assert sha(destination)==expected,f'Existing private tool differs; preserve it: {destination}'
                    else:
                        with destination.open('xb') as output:
                            if rebased is not None:output.write(rebased)
                            else:
                                with path.open('rb') as stream:shutil.copyfileobj(stream,output,8*1024*1024)
                        assert sha(destination)==expected and destination.stat().st_nlink==1
                rows.append({'relative':relative.as_posix(),'source':str(path),'target':str(destination),'bytes':destination.stat().st_size if destination.exists() else path.stat().st_size,
                             'source_sha256':digest,'target_sha256':expected,'rebased_private_preset':rebased is not None})
        report['tools'][name]={'source':str(source),'target':str(target),'files':rows,'logical_bytes':sum(row['bytes'] for row in rows)}
    owned(OUT/'tool_staging_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'tools':{name:{'files':len(value['files']),'bytes':value['logical_bytes']} for name,value in report['tools'].items()}}))


if __name__=='__main__':main()
