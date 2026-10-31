"""Read only current physical configuration winners and report absolute paths."""
from pathlib import Path
from datetime import datetime,timezone
import argparse
import collections
import hashlib
import json
import re
import sqlite3
import sys

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
TARGET=BASE/'UnifiedSkyrim'
sys.path.insert(0,str(BASE/'integration/research/vfs_validation'))
from vfs_common import walk,key,lp

EXT={'.ini','.json','.toml','.xml','.cfg','.config','.yaml','.yml','.txt'}
ABS=re.compile(r'(?i)(?<![a-z0-9])[a-z]:[\\/]+[^\r\n\"<>|;,{}]*')


def sha(data):return hashlib.sha256(data).hexdigest()


def norm(text):return re.sub(r'\\+',r'\\',str(text).replace('/','\\')).casefold()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--profile',choices=('Unified Skyrim','Unified Build'),default='Unified Skyrim')
    parser.add_argument('--output-subdir',default='')
    args=parser.parse_args()
    reportdir=(OUT/args.output_subdir).resolve()
    if not reportdir.is_relative_to(OUT.resolve()):raise ValueError('Reports must remain in this research directory')
    reportdir.mkdir(parents=True,exist_ok=True)
    profile=TARGET/'profiles'/args.profile
    modlist=profile/'modlist.txt';before=sha(modlist.read_bytes())
    mods=[(line[1:],TARGET/'mods'/line[1:]) for line in modlist.read_text(encoding='utf-8-sig').splitlines() if line.startswith('+')]
    db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    packs=[{'name':name,'root':str(Path(path).parents[0]) if name=='Anno' else str(Path(path).parents[0])} for name,path in db.execute('select name,base_path from packs')]
    # Use the named pack root, including sibling STOCK GAME/MO2 directories.
    roots={r['name']:norm(BASE.parent/r['name']) for r in packs}
    winners={};candidate_count=0
    for provider,folder in mods+[('Game/Data',TARGET/'Game/Data')]:
        for relative,path,stat in walk(folder):
            if Path(relative).suffix.casefold() not in EXT:continue
            candidate_count+=1;winners.setdefault(key(relative),(provider,relative,path))
    files=[('data',provider,relative,path) for provider,relative,path in winners.values()]
    for path in (TARGET/'Game').iterdir():
        if path.is_file() and path.suffix.casefold() in EXT:files.append(('game-root','Game',path.name,path))
    for folder,label in ((TARGET/'profiles/Unified Skyrim','final-profile'),(TARGET/'profiles/Unified Build','build-profile'),(TARGET/'MO2','MO2')):
        for path in folder.iterdir():
            if path.is_file() and path.suffix.casefold() in EXT and not path.name.endswith('.bak'):
                files.append((label,label,path.name,path))
    findings=[];old=[];manifest=[];errors=[];byte_count=0;extensions=collections.Counter()
    for scope,provider,relative,path in sorted(files,key=lambda row:(row[0],key(row[2]))):
        try:
            data=Path(lp(path)).read_bytes();byte_count+=len(data)
            text=data.decode('utf-16') if data.startswith((b'\xff\xfe',b'\xfe\xff')) else data.decode('utf-8-sig',errors='replace')
            digest=sha(data);extensions[path.suffix.casefold()]+=1
            manifest.append({'scope':scope,'provider':provider,'relative':relative,'path':str(path),'sha256':digest,'bytes':len(data)})
            for lineno,line in enumerate(text.splitlines(),1):
                for match in ABS.finditer(line):
                    absolute=match[0].strip();normalized=norm(absolute)
                    row={'scope':scope,'provider':provider,'relative':relative,'path':str(path),'sha256':digest,'line':lineno,'absolute_path_text':absolute[:1000]}
                    row['old_source_packs']=[name for name,root in roots.items() if root in normalized]
                    findings.append(row)
                    if row['old_source_packs']:old.append(row)
        except Exception as exc:errors.append({'path':str(path),'error':str(exc)})
    after=sha(modlist.read_bytes())
    report={'utc':datetime.now(timezone.utc).isoformat(),'status':'READ_ONLY_CURRENT_PHYSICAL_CONFIGURATION_WINNERS',
            'profile':str(profile),'modlist_sha256_before':before,'modlist_sha256_after':after,'modlist_unchanged':before==after,
            'active_mod_roots':len(mods),'candidate_configurations':candidate_count,'unique_winning_data_configurations':len(winners),
            'scanned_files':len(manifest),'scanned_bytes':byte_count,'extensions':dict(extensions),'absolute_path_matches':len(findings),
            'old_source_pack_path_matches':old,'absolute_paths':findings,'errors':errors,
            'limits':['Physical resolution follows current final-profile MO2 modlist priority and Game/Data fallback; it is not an injected usvfs probe.',
                      'Only loose configuration/text files with the enumerated extensions are scanned. BSA payloads, binary embedded strings, executables, tools excluded from game data, comments versus active settings and computed/dynamic paths are not semantically evaluated.',
                      'Game-root files and immediate final/build profile/MO2 configuration files are included; file contents were never modified.',
                      'No old source path match does not prove every absolute path is appropriate; all matches are preserved for review. Profile is still being built and later producer/install steps require final refresh.']}
    (reportdir/'active_configuration_absolute_paths.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (reportdir/'active_configuration_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Physical winning configs',len(winners),'scanned total',len(manifest),'absolute matches',len(findings),'old-pack matches',len(old),'errors',len(errors),'modlist unchanged',before==after)
    for row in old:print('OLD_SOURCE_PATH',row)


if __name__=='__main__':main()
