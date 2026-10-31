"""Private JSON/trace fixtures only; never runs PG or saves a source NIF."""
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
from pg_nif_validate import sha
import pg_nif_lighting_validate as validator
from pbr_lighting_contract import trace_witness,apply_group_slots

def main():
    proof=json.loads((OUT/'pg_runs/nif_cpu_preflight_002/source_reaudit_ec513533833e/result.json').read_text(encoding='utf8'))
    contract_path=OUT/'pg_runs/nif_cpu_preflight_002/lighting_contract/contract.json';contract=json.loads(contract_path.read_text(encoding='utf8'))
    key=next(iter(proof['entries']));row=proof['entries'][key];source=json.loads(Path(row['typed_snapshot']).read_text(encoding='utf8'));lighting=validator.schema_snapshot(row['snapshot'])
    events=[{'mesh':key,'use':'Base','source_child_path':s['canonical_child_path'],'selected_group':None,'complete':True,'has_alternate_texture':False,'old_texture_slots':s['old_texture_slots'],'modified_texture_slots':s['old_texture_slots']} for s in contract['meshes'][key]['shapes']]
    def run(candidate,ls=None,witness=None):return validator.validate(source,candidate,lighting,ls or lighting,witness or {'events':events},key,True,contract['rules'])
    results=[];run(source);results.append({'case':'14shape identity','pass':True})
    def reject(name,mutation):
        candidate=copy.deepcopy(source);ls=copy.deepcopy(lighting);ev=copy.deepcopy(events);mutation(candidate,ls,ev)
        try:run(candidate,ls,{'events':ev})
        except (AssertionError,ValueError):results.append({'case':name,'rejected':True});return
        raise AssertionError('False pass '+name)
    for field in ('vertices','triangles','UVs','normals','bone_weights','partitions'):
        reject('changed '+field,lambda c,l,e,f=field:c['shapes'][0]['geometry'].__setitem__(f,'BAD'))
    reject('changed node transform',lambda c,l,e:c['nodes'][c['shapes'][0]['key']]['transform'].__setitem__('scale',2))
    reject('shape removal',lambda c,l,e:c['shapes'].pop())
    reject('unwitnessed shape',lambda c,l,e:e.pop())
    reject('lighting tangent undeclared',lambda c,l,e:l['shapes'][0]['tangent_encoding'][0].__setitem__(0,17))
    reject('vertex color hash undeclared',lambda c,l,e:c['shapes'][0].__setitem__('vertex_colors','BAD'))
    index=1
    while (OUT/('pg_runs/trace_fixture_'+str(index).zfill(3))).exists():index+=1
    run_dir=OUT/('pg_runs/trace_fixture_'+str(index).zfill(3));logdir=run_dir/'tool/log';logdir.mkdir(parents=True)
    lines=['[trace] TruePBR Config '+str(r['sequence'])+' Loaded: '+json.dumps(r['native_rule'],ensure_ascii=False,separators=(',',':')) for r in contract['rules']]
    for i,s in enumerate(contract['meshes'][key]['shapes']):
        prefix='[trace] ['+key.replace('/','\\')+'] [Base] ['+str(s['source_block_id'])+'/'+s['name']+'/'+str(i)+'] '
        text=','.join(s['old_texture_slots']);lines.extend([prefix+'Texture Slots: '+text,prefix+'Winning Match: Default /  / ',prefix+'Texture Slots Modified: '+text])
    (logdir/'PGPatcher.log').write_text('\n'.join(lines)+'\n',encoding='utf8');(run_dir/'lighting_contract').mkdir();trace_witness(run_dir,contract_path)
    w=json.loads((run_dir/'lighting_contract/native_trace_witness.json').read_text(encoding='utf8'));assert len(w['events'])==len(events);run(source,witness=w);results.append({'case':'native Base context + all loaded rule order + complete nine-slot trace','pass':True})
    r={'sequence':0,'native_rule':{'match_diffuse':'\\wood','rename':'\\oak','slot8':'lights\\back.dds'},'native_rule_sha256':'fixture'}
    group={'ordered_rule_sequences':[0]};slots=['textures\\tree\\wood.dds','textures\\tree\\wood_n.dds']+['']*7
    out=apply_group_slots(slots,group,[r]);assert out[0]=='textures\\pbr\\tree\\oak.dds' and out[5]=='textures\\pbr\\tree\\oak_rmaos.dds' and out[7]=='textures\\lights\\back.dds' and out[8]==''
    results.append({'case':'independent rename/RMAOS/explicit slot8/ninth-slot preservation','pass':True})
    receipt={'status':'JSON_AND_FAKE_TRACE_FIXTURES_PASS_NOT_ACTUAL_GENERATION','results':results,'source_key':key,'source_sha256':row['sha256'],'files':{n:sha(OUT/n) for n in ('pg_nif_reader.py','pg_nif_validate.py','pg_nif_lighting_validate.py','pbr_lighting_contract.py','test_pg_lighting_adapter.py')},'NIFs_modified':False,'PG_executed':False,'GUI_or_game_launched':False}
    (OUT/'PG_lighting_adapter_fixture.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8');print(json.dumps({'tests':len(results),'status':receipt['status']}))
if __name__=='__main__':main()
