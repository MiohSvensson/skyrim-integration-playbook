"""Refresh an executable, profile-pinned two-cell CPU smoke manifest."""
import argparse
import json
import struct
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,TARGET,Mini,final_inputs,runtime_id,sha,owned,ri
sys.path.insert(0,str(OLD))
from verify_cgid import parse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['Unified Build','Unified Skyrim'],default='Unified Build');args=parser.parse_args()
    profile,mods,plugins=final_inputs(args.profile)
    watched=['plugins.txt','modlist.txt','loadorder.txt','Skyrim.ini','SkyrimPrefs.ini','SkyrimCustom.ini','settings.ini','archives.txt']
    snapshot={name:sha(profile/name) for name in watched if (profile/name).exists()}
    world_sources={}
    def collect(record,raw,reader):
        data=dict(raw)
        if record['flags']&0x1000:return
        if record['flags']&0x20:world_sources.pop(record['id'],None);return
        if record['flags']&0x4000:return
        world_sources[record['id']]={**record,'editor_id':data.get('EDID',b'').rstrip(b'\0').decode('utf-8','replace'),
                'DATA':int.from_bytes(data.get('DATA',b'\0'),'little')}
    for row in plugins:Mini(row).read('worlds',collect)
    worlds=[]
    for identity,row in sorted(world_sources.items()):
        if identity.startswith(('glenmoril.esm|','wyrmstooth.esp|')) or row['editor_id'] in ('Tamriel','WindhelmWorld'):
            worlds.append({**row,'full_runtime_FormID':f'{runtime_id(identity,plugins):08X}','no_grass':bool(row['DATA']&128)})
    assert any(w['editor_id']=='Tamriel' and w['full_runtime_FormID']=='0000003C' for w in worlds)
    coordinates={(-1,-1):'positive',(-1,-31):'empty'};stock=next(row for row in plugins if row['name_key']=='skyrim.esm');cells={}
    def find(record,raw,reader):
        data=dict(raw)
        if 'XCLC' in data:
            xy=tuple(struct.unpack_from('<ii',data['XCLC']))
            if xy in coordinates:cells[record['id']]={'xy':list(xy),'role':coordinates[xy],'stock':record}
    Mini(stock).read('find',find)
    assert len(cells)==2,'Both controlled Tamriel cells must have stock CELL data'
    chains={identity:{'CELL':[],'LAND':[]} for identity in cells}
    def target(record,raw,reader):
        identity=record['id'] if record['signature']=='CELL' else record['cell']
        data=dict(raw);value={**record}
        if record['signature']=='CELL':
            value['cell_flags']=int.from_bytes(data.get('DATA',b'\0'),'little')
            value['XY']=list(struct.unpack_from('<ii',data['XCLC'])) if 'XCLC' in data else None
        else:
            value['LAND_DATA']=int.from_bytes(data.get('DATA',b'\0'),'little')
            value['texture_ids']=sorted({reader.identity(struct.unpack_from('<I',data)[0]) for tag,data in raw if tag in ('BTXT','ATXT')})
        chains[identity][record['signature']].append(value)
    for row in plugins:Mini(row).read('targets',target,set(cells))
    cases=[]
    for identity,info in cells.items():
        eligible_cells=[row for row in chains[identity]['CELL'] if not row['flags']&(0x1000|0x4000)]
        eligible_lands=[row for row in chains[identity]['LAND'] if not row['flags']&0x1000]
        assert eligible_cells and eligible_lands
        assert not eligible_cells[-1]['flags']&0x20 and not eligible_lands[-1]['flags']&0x20
        cache=f"Tamrielx{info['xy'][0]:04d}y{info['xy'][1]:04d}.cgid"
        provider,path=ri.resolve('Grass/'+cache,mods);assert path is not None
        observed=parse(path)
        assert (observed['blades']>0)==(info['role']=='positive'),'Historical cache expectation changed'
        cases.append({'role':info['role'],'world_origin':'skyrim.esm|00003C','world_full_runtime_FormID':f'{runtime_id("skyrim.esm|00003C",plugins):08X}',
          'cell_origin':identity,'cell_full_runtime_FormID':f'{runtime_id(identity,plugins):08X}','XY':info['xy'],
          'source_cache':{'provider':provider,'path':str(path),'sha256':observed['sha256'],'bytes':observed['bytes'],'blades':observed['blades']},
          'final_CELL':eligible_cells[-1],'final_LAND_slot':eligible_lands[-1],'record_chains':chains[identity],
          'inspect_expected':{'status':'land','blades_min':1 if info['role']=='positive' else 0,'blades_max':None if info['role']=='positive' else 0},
          'cache_expected':{'blades_min':1 if info['role']=='positive' else 0,'blades_max':None if info['role']=='positive' else 0,
                            'empty_exact_bytes':None if info['role']=='positive' else '00000000'},
          'expectation_scope':'Historical source cache establishes a populated/empty control; final CELL/LAND chains are pinned. Current inspect CSV must confirm before generation; mismatch stops for investigation, never silently relabels a changed cell.'})
    auxiliary={}
    for relative in ('SKSE/Plugins/GrassControl.ini','SKSE/Plugins/GrassCacheHelperNG.ini'):
        provider,path=ri.resolve(relative,mods);assert path is not None
        auxiliary[relative]={'provider':provider,'path':str(path),'sha256':sha(path)}
    manifest={'status':'PREPARED_NOT_EXECUTED_REFRESH_AFTER_PROFILE_CHANGES','utc':datetime.now(timezone.utc).isoformat(),
      'profile':args.profile,'profile_path':str(profile),'profile_sha256':snapshot,'plugins':plugins,'world_mapping':worlds,
      'Skyrim_ccc_sha256':sha(TARGET/'Game/Skyrim.ccc'),'auxiliary':auxiliary,'cases':sorted(cases,key=lambda row:row['role']=='empty'),
      'generator':{'path':str(OUT/'tools/FasterNGIO_1.6/FasterNGIO.exe'),'sha256':'e955a84cc48b1d1448adf92c796da896190e40c6ea1ac46d1b83282d3970331c'},
      'reader_evidence':{'FasterNGIO':'1.6 commit 5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40',
        'TESWorld':'763aee7622b336e05bf33893a372e3382b2431a4 Plugins.cpp2373-2410 counts full/light slots in actual plugin sequence; no assumed fixed master index'},
      'constraints':['CPU only; no GUI/game','New output under research/lod_update/runs only','Explicit --write-empty-cells to hide stale lower cache','No --overwrite of any original/input cache','No --world all; explicit dynamically resolved IDs'],
      'root_invocation':['python','Database/integration/run_mo2_child.py','--profile',args.profile,'lod_cpu_smoke',str(OUT/'faster_ngio_child.py'),'--manifest',str(OUT/'smoke_manifest.json')]}
    assert snapshot=={name:sha(profile/name) for name in snapshot},'Profile changed during preparation'
    owned(OUT/'smoke_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'plugins':len(plugins),'worlds':[(row['editor_id'],row['full_runtime_FormID']) for row in worlds],
                      'cases':[(row['role'],row['XY'],row['source_cache']['blades'],row['final_LAND_slot']['plugin']) for row in cases]},ensure_ascii=False))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
