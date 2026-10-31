"""Private exact-one Skyrim PEX string-table edit; never deploy or edit a pack."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2];ROOT=OUT/'sprint_event_candidate'
sys.path.insert(0,str(DB/'integration'));import runtime_inventory as ri
sys.path.insert(0,str(OUT.parent/'vfs_validation'));from vfs_common import ResourceCatalog,active_archive_names,key
sys.path.insert(0,str(DB/'rootcause'));from bsarch_readonly import extract_files
sys.path.insert(0,str(OUT.parent/'navmesh_patch'));from verify_candidate import Plugin,fields
from pg_nif_validate import physical_view
OLD=b'ShoutSprintLongStart\t';NEW=b'ShoutSprintLongStart';EXPECTED='03cb865de8b28696f254fcd01cc3849e076c09d5cc05015f7b36207bc30d0d67'

def sha(data):return hashlib.sha256(data).hexdigest()
def parse_strings(data):
    p=0
    def n(fmt):
        nonlocal p
        v=struct.unpack_from('>'+fmt,data,p)[0];p+=struct.calcsize(fmt);return v
    def s():
        nonlocal p
        offset=p;size=n('H');v=data[p:p+size];assert len(v)==size;p+=size;return {'length_offset':offset,'end':p,'value':v}
    assert data[:4]==b'\xfa\x57\xc0\xde';p=4
    major=n('B');minor=n('B');game=n('H');stamp=n('Q');header=[s() for _ in range(3)]
    assert major==3 and minor==2 and game==1
    count=n('H');strings=[s() for _ in range(count)]
    return {'major':major,'minor':minor,'game':game,'timestamp':stamp,'header':header,'strings':strings,'body_offset':p}

def main():
    assert not ROOT.exists(),'Preserve first candidate/evidence';ROOT.mkdir()
    ri.PROFILE=DB/'UnifiedSkyrim/profiles/Unified Build';mods=ri.active_mods();names=ri.plugin_names(mods)
    controls={n:sha((ri.PROFILE/n).read_bytes()) for n in ('plugins.txt','modlist.txt','loadorder.txt')}
    member='scripts/ghsprintspellscript.pex';provider,path=ri.resolve(member,mods)
    if path:data=Path(path).read_bytes();loc={'kind':'loose','provider':provider,'path':str(path),'sha256':sha(data)}
    else:
        physical=physical_view(mods,set());archives,_=active_archive_names(ri.PROFILE,names,physical)
        cat=ResourceCatalog(physical,{key(n):dict(physical[key(n)],order=i) for i,n in enumerate(archives)});loc=cat.resolve(member)
        assert loc['kind']=='bsa';data=extract_files(loc['archive_physical'],{member:loc['sha256']})[member]
    assert sha(data)==EXPECTED,'Different actual source PEX requires fresh audit'
    parsed=parse_strings(data);hits=[(i,s) for i,s in enumerate(parsed['strings']) if s['value']==OLD];assert len(hits)==1
    index,entry=hits[0];candidate=data[:entry['length_offset']]+struct.pack('>H',len(NEW))+NEW+data[entry['end']:];new=parse_strings(candidate)
    assert data[:entry['length_offset']]==candidate[:entry['length_offset']]
    assert data[entry['end']:]==candidate[new['strings'][index]['end']:]
    assert data[parsed['body_offset']:]==candidate[new['body_offset']:],'Instructions/properties/states/functions/debug must remain byte-identical'
    assert len(parsed['strings'])==len(new['strings'])
    assert all(a['value']==b['value'] for i,(a,b) in enumerate(zip(parsed['strings'],new['strings'])) if i!=index)
    closure=json.loads((OUT/'behavior_closure.json').read_text(encoding='utf8'))
    actual_graphs=[{'path_key':k,**{n:v[n] for n in ('location','xml','xml_sha256')}} for k,v in closure['graphs'].items() if NEW.decode() in v.get('events',[])]
    assert any(r['path_key']=='meshes/actors/character/behaviors/0_master.hkx' for r in actual_graphs)
    assert not any(OLD.decode() in v.get('events',[]) for v in closure['graphs'].values())
    for branch,blob in [('original',data),('candidate',candidate)]:
        dest=ROOT/branch/'Scripts/GHSprintSpellScript.pex';dest.parent.mkdir(parents=True);dest.write_bytes(blob)
        for kind in ('asm','decompiled'):(ROOT/branch/kind).mkdir()
        exe=DB/'tools/Champollion-1.3.2/Champollion.exe';command=[str(exe),str(dest),'-p',str(ROOT/branch/'decompiled'),'-a',str(ROOT/branch/'asm'),'--debug-funcs','--no-debug-line']
        proc=subprocess.run(command,capture_output=True,text=True)
        (ROOT/branch/'author_reader.json').write_text(json.dumps({'command':command,'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr,'exe_sha256':sha(exe.read_bytes())},indent=2)+'\n')
        assert proc.returncode==0 and '1 files processed' in proc.stdout
    before=(ROOT/'original/asm/GHSprintSpellScript.pas').read_text(encoding='utf8');after=(ROOT/'candidate/asm/GHSprintSpellScript.pas').read_text(encoding='utf8')
    assert before.count('ShoutSprintLongStart\\t')==1 and before.replace('ShoutSprintLongStart\\t','ShoutSprintLongStart')==after,'Full typed author disassembly differs outside intended literal'
    # First identify any attached VMAD script, then select the complete final
    # winner for those canonical records, including overrides which REMOVE it.
    targets=set();plugins=[];needle=b'ghsprintspellscript'
    for name in names:
        provider,path=ri.resolve(name,mods);assert path
        if needle in Path(path).read_bytes().lower():
            pl=Plugin(path)
            for r in pl.records:
                if r['signature']=='TES4':continue
                if any(needle in v.lower() for t,v in fields(pl.payload(r)) if t=='VMAD'):targets.add(r['id'])
        plugins.append((name,provider,path))
    winners={};chains={k:[] for k in targets}
    for name,provider,path in plugins:
        pl=Plugin(path)
        for r in pl.records:
            if r['id'] in targets:
                fs=fields(pl.payload(r));attached=any(needle in v.lower() for t,v in fs if t=='VMAD');edid=next((v.rstrip(b'\0').decode('utf8','replace') for t,v in fs if t=='EDID'),'')
                detail={'canonical':r['id'],'signature':r['signature'],'editor_id':edid,'plugin':name,'provider':provider,'plugin_path':str(path),'plugin_sha256':sha(Path(path).read_bytes()),'script_attached':attached}
                winners[r['id']]=detail;chains[r['id']].append(detail)
    assert controls=={n:sha((ri.PROFILE/n).read_bytes()) for n in controls},'Profile changed during consumer scan'
    report={'status':'PRIVATE_SINGLE_STRING_PEX_CANDIDATE_PROVEN_NOT_DEPLOYED','source':loc,'source_sha256':EXPECTED,'candidate_sha256':sha(candidate),'source_bytes':len(data),'candidate_bytes':len(candidate),
      'candidate_path':str(ROOT/'candidate/Scripts/GHSprintSpellScript.pex'),'script_name':'GHSprintSpellScript','string_table_index':index,'string_count':len(parsed['strings']),
      'old_literal':OLD.decode(),'new_literal':NEW.decode(),'changed_length_prefix':{'offset':entry['length_offset'],'before':len(OLD),'after':len(NEW)},
      'unchanged_typed_body_sha256':sha(data[parsed['body_offset']:]),'original_body_offset':parsed['body_offset'],'candidate_body_offset':new['body_offset'],
      'all_other_string_entries_exact':True,'all_properties_variables_states_functions_instructions_debug_bytes_exact':True,'full_author_disassembly_only_one_literal_difference':True,
      'author_parser_source':json.loads((OUT/'primary_sources/Champollion/manifest.json').read_text()),'actual_correct_event_graphs':actual_graphs,'VMAD_final_winners':list(winners.values()),'VMAD_override_chains':chains,
      'context':'OnEffectStart distance512..768 branch uses Long between Short/Medium/Longest; correct Long event exists in actual final human/firstperson/master/shout tables, trailingTAB event does not.',
      'profile_control_sha256':controls,'native_execution_tested':False,'deployment':'Parent may install exactly this one private script in a new output layer after review; do not edit BSA/source or regenerate Pandora.'}
    (ROOT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({k:report[k] for k in ('status','source_sha256','candidate_sha256','candidate_bytes','string_table_index')},ensure_ascii=True))
if __name__=='__main__':main()
