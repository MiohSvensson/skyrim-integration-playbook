"""Resolve and read real winning actor behavior references; never regenerate."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(DB/'integration'));import runtime_inventory as ri
sys.path.insert(0,str(OUT.parent/'vfs_validation'));from vfs_common import ResourceCatalog,active_archive_names,key
sys.path.insert(0,str(DB/'rootcause'));from bsarch_readonly import extract_files

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ri.PROFILE=DB/'UnifiedSkyrim/profiles/Unified Build';mods=ri.active_mods();physical={}
    for provider,folder in mods+[('Game/Data',DB/'UnifiedSkyrim/Game/Data')]:
        if not folder.is_dir():continue
        for f in folder.iterdir():
            if f.is_file():physical.setdefault(key(f.name),{'relative_path':f.name,'physical_path':str(f),'provider':provider,'size_bytes':f.stat().st_size})
    names=ri.plugin_names(mods);anames,_=active_archive_names(ri.PROFILE,names,physical)
    cat=ResourceCatalog(physical,{key(n):dict(physical[key(n)],order=i) for i,n in enumerate(anames)})
    existing=json.loads((OUT/'final_graph_conversion.json').read_text());queue=[(key(r['path_key']),None) for r in existing]
    # The remaining two script event names target vanilla creature projects,
    # including Glen's authored ChaplainHopRace(Scrib male/Skeever female).
    queue += [(p,'creature_event_context') for p in ('meshes/actors/dlc02/scrib/scribproject.hkx','meshes/actors/skeever/skeeverproject.hkx','meshes/actors/atronachfrost/atronachfrostproject.hkx','meshes/actors/icewraith/icewraithproject.hkx')]
    seen={};edges=[];errors=[];all_events=collections.defaultdict(list)
    old={key(r['path_key']):r for r in existing};cache=OUT/'behavior_private_inputs';cache.mkdir(exist_ok=True)
    while queue:
        path,parent=queue.pop(0)
        if path in seen:continue
        provider,source=ri.resolve(path,mods)
        if source:loc={'kind':'loose','provider':provider,'physical_path':str(source),'sha256':sha(source)}
        else:
            loc=cat.resolve(path)
            if loc['kind']=='missing':errors.append({'path':path,'parent':parent,'error':'existing_final_graph_reference_missing'});seen[path]={'status':'MISSING','location':loc};continue
            data=extract_files(loc['archive_physical'],{path:loc['sha256']})[path];source=cache/(loc['sha256']+'.hkx')
            if source.exists():assert sha(source)==loc['sha256']
            else:source.write_bytes(data)
        if path in old and old[path]['source_sha256']==loc['sha256']:
            xml=Path(old[path]['destination']);assert sha(xml)==old[path]['output_sha256']
        else:
            xml=OUT/'hkx_xml'/('closure_'+loc['sha256']+'.xml')
            if not xml.exists():
                proc=subprocess.run([str(DB/'tools/dotnet/dotnet.exe'),str(OUT/'tools/HkxAudit/HkxAudit.dll'),str(source),str(xml)],capture_output=True,text=True)
                if proc.returncode or not xml.exists():
                    errors.append({'path':path,'error':'author_HKX2_reader_failed','returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr});seen[path]={'status':'PARSE_FAIL','location':loc};continue
        tree=ET.parse(xml);events=[];refs=[]
        for e in tree.iter('hkparam'):
            if e.attrib.get('name')=='eventNames':events += [x.text or '' for x in e]
            if e.attrib.get('name') in ('behaviorName','behaviorFilename') and e.text:refs.append(e.text)
            if e.attrib.get('name')=='characterFilenames':refs += [x.text for x in e if x.text]
        for event in events:all_events[event].append(path)
        seen[path]={'status':'AUTHOR_READER_PASS','location':loc,'xml':str(xml),'xml_sha256':sha(xml),'event_count':len(events),'events':events,'behavior_references':refs}
        for ref in sorted(set(refs)):
            ref=key(ref)
            # HKB references are relative to the actor character project root.
            if ref.startswith('meshes/'):target=ref
            elif '/behaviors' in path:
                prefix=path[:path.index('/behaviors')]
                target=prefix+'/'+ref if '/' in ref else path.rsplit('/',1)[0]+'/'+ref
            elif '/characters/' in path:target=path[:path.index('/characters/')]+ '/'+ref
            else:target=path.rsplit('/',1)[0]+'/'+ref
            edges.append({'source':path,'reference':ref,'target':target});queue.append((target,path))
        print(json.dumps({'parsed':len(seen),'pending':len(queue),'path':path,'events':len(events)}),flush=True)
        assert len(seen)<250,'Unexpected expansion; audit root resolution'
    calls=json.loads((OUT/'decompiled_animation_calls.json').read_text());literals=collections.defaultdict(list)
    for c in calls:
        if not re.search(r'(SendAnimationEvent|RegisterForAnimationEvent)',c['text'],re.I):continue
        quoted=re.findall(r'"((?:\\.|[^"\\])*)"',c['text'])
        if not quoted:continue
        event=quoted[-1].replace('\\t','\t')
        literals[event].append(c)
    event_report=[]
    for event,uses in sorted(literals.items()):
        exact=all_events.get(event,[]);caseonly=sorted({p for e,ps in all_events.items() if e.lower()==event.lower() for p in ps}) if not exact else []
        event_report.append({'event':event,'status':'EXACT_FINAL_EVENT_TABLE' if exact else 'CASE_ONLY_FINAL_EVENT_TABLE' if caseonly else 'NOT_IN_CHECKED_ACTOR_GRAPH_CLOSURE','graphs':exact or caseonly,'uses':uses})
    src=json.loads((OUT/'source_inspection.json').read_text(encoding='utf8'));sql=sqlite3.connect((DB/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);sql.row_factory=sqlite3.Row;vanilla=[]
    for row in src['HKX']:
        canonical=row['path_key'].replace('/revenant/','/')
        matches=[dict(r) for r in sql.execute('select distinct a.path,a.sha256 archive_sha256,e.sha256,e.size_bytes from bsa_entries e join bsa_archives a on a.id=e.archive_id where e.path_key=? and e.sha256=?',(canonical,row['sha256']))]
        vanilla.append({'incoming_path':row['path_key'],'canonical_path':canonical,'sha256':row['sha256'],'identical_canonical_BSA_sources':matches})
    report={'status':'READ_ONLY_ACTUAL_FINAL_GRAPH_CLOSURE','profile_plugins_sha256':sha(ri.PROFILE/'plugins.txt'),'profile_modlist_sha256':sha(ri.PROFILE/'modlist.txt'),
      'graphs':seen,'edges':edges,'errors':errors,'script_event_literals':event_report,'imported_HKX_vanilla_duplicates':vanilla,
      'new_generator_input_paths':src['generator_inputs'],'plugin_animation_records':src['plugin_animation_records'],
      'not_a_runtime_test':True,'limits':['Event table existence is necessary static routing evidence, not proof of successful in-game event/quest execution.',
        'Unresolved literals may belong to NIF object behavior projects, rather than these actor graphs; never invent registrations or regenerate Pandora solely to hide them.']}
    (OUT/'behavior_closure.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'graphs':len(seen),'errors':len(errors),'event_statuses':dict(collections.Counter(r['status'] for r in event_report))},indent=2))
if __name__=='__main__':main()
