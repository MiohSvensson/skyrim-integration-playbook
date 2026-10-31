"""Prepare eight explicit complete-world CPU batches; never starts a generator."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import zlib
from datetime import datetime,timezone
sys.dont_write_bytecode=True
from runtime_common import OUT,OLD,TARGET,final_inputs,runtime_id,ri,sha,owned,fields
from audit_grass_identity import grasses

def coverage(plugins,world_ids):
    worlds={};cells={};lands={};land_by_cell={};cell_by_land={}
    for row in plugins:
        names=[m.lower() for m in row['masters']]+[row['name_key']]
        def ident(v):
            assert v>>24<len(names)
            return names[v>>24]+'|'+f'{v&0xFFFFFF:06X}'
        pending_lands=[];deleted_lands=[]
        with open(row['path'],'rb') as f:
            def walk(start,end,world=None,cell=None):
                p=start
                while p<end:
                    f.seek(p);h=f.read(24);assert len(h)==24;size=struct.unpack_from('<I',h,4)[0]
                    if h[:4]==b'GRUP':
                        assert size>=24 and p+size<=end;typ=struct.unpack_from('<i',h,12)[0];label=h[8:12];w=world;c=cell
                        go=True
                        if typ==0:go=label==b'WRLD'
                        elif typ==1:w=ident(struct.unpack('<I',label)[0]);c=None;go=w in world_ids
                        elif typ in (6,8,9,10):c=ident(struct.unpack('<I',label)[0])
                        if go:walk(p+24,p+size,w,c)
                    else:
                        flags=struct.unpack_from('<I',h,8)[0];sig=h[:4].decode('ascii');assert p+24+size<=end
                        if sig in ('WRLD','CELL','LAND'):
                            rid=ident(struct.unpack_from('<I',h,12)[0])
                            if flags&0x1000:p+=24+size;continue
                            if sig=='LAND':
                                if flags&0x20:deleted_lands.append(rid)
                                else:pending_lands.append({'id':rid,'cell':cell,'world':world,'plugin':row['name']})
                            else:
                                target=worlds if sig=='WRLD' else cells
                                if flags&0x20:target.pop(rid,None)
                                else:
                                    f.seek(p+24);data=f.read(size)
                                    if flags&0x40000:
                                        n=struct.unpack_from('<I',data)[0];data=zlib.decompress(data[4:]);assert len(data)==n
                                    fd=dict(fields(data));state=target.setdefault(rid,{'id':rid})
                                    state.update({'plugin':row['name'],'flags':flags})
                                    if world:state['world']=world
                                    for name in ('EDID','DATA','XCLC','WNAM','PNAM'):
                                        if name in fd:state[name]=fd[name].hex()
                        size+=24
                    p+=size
                assert p==end
            walk(0,os.fstat(f.fileno()).st_size)
        for land in pending_lands:
            rid=land['id'];cell=land['cell'];assert cell
            if rid in cell_by_land and cell_by_land[rid]!=cell:
                old=cell_by_land[rid]
                if land_by_cell.get(old)==rid:land_by_cell.pop(old,None)
            cell_by_land[rid]=cell;land_by_cell[cell]=rid;lands[rid]=land
        for rid in deleted_lands:
            if rid in cell_by_land:
                cell=cell_by_land.pop(rid)
                if land_by_cell.get(cell)==rid:land_by_cell.pop(cell,None)
            lands.pop(rid,None)
    result={w:[] for w in world_ids}
    for cell,rid in land_by_cell.items():
        c=cells.get(cell)
        if c is None or c.get('world') not in result or 'XCLC' not in c:continue
        xy=struct.unpack_from('<ii',bytes.fromhex(c['XCLC']))
        result[c['world']].append({'XY':list(xy),'cell':cell,'cell_runtime_id':f'{runtime_id(cell,plugins):08X}',
             'land':rid,'land_runtime_id':f'{runtime_id(rid,plugins):08X}','LAND_winner':lands[rid]['plugin'],'CELL_winner':c['plugin']})
    for w,values in result.items():
        assert len({tuple(v['XY']) for v in values})==len(values),'Duplicate effective LAND coordinates'
        values.sort(key=lambda r:r['XY'])
    return worlds,result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['Unified Build','Unified Skyrim'],default='Unified Build');args=parser.parse_args()
    profile,mods,plugins=final_inputs(args.profile)
    prior=json.loads((OLD/'offline_grass_plan.json').read_text(encoding='utf-8'))
    desired=[{'origin_id':'skyrim.esm|00003C','editor_id':'Tamriel','reason':'Regenerate full changed exterior world: authored MoonAndStar LAND and quest-entry/collision changes; avoids guessed collision-cell bounds.'},
        *[{**r,'reason':'New authored world has LAND and NoGrass is clear; no original world cache.'} for r in prior['new_grass_worlds']]]
    assert len(desired)==8 and len({r['origin_id'] for r in desired})==8
    worlds,coverage_rows=coverage(plugins,{r['origin_id'] for r in desired})
    watched=['plugins.txt','modlist.txt','loadorder.txt','Skyrim.ini','SkyrimPrefs.ini','SkyrimCustom.ini','settings.ini','archives.txt']
    snapshot={name:sha(profile/name) for name in watched if (profile/name).exists()};aux={}
    for rel in ('SKSE/Plugins/GrassControl.ini','SKSE/Plugins/GrassCacheHelperNG.ini'):
        provider,path=ri.resolve(rel,mods);assert path;aux[rel]={'provider':provider,'path':str(path),'sha256':sha(path)}
    batches=[]
    for item in desired:
        world=worlds[item['origin_id']];edid=bytes.fromhex(world['EDID']).rstrip(b'\0').decode('utf-8');assert edid==item['editor_id']
        data=int.from_bytes(bytes.fromhex(world.get('DATA','00')),'little');assert not data&128,'Selected world is NoGrass'
        cells=coverage_rows[item['origin_id']];assert cells
        batches.append({**item,'world_runtime_id':f'{runtime_id(item["origin_id"],plugins):08X}','final_WRLD_winner':world['plugin'],
            'expected_effective_LAND_cells':len(cells),'expected_cells':cells,'no_grass':False,
            'minimum_written_blades':1,'coverage_policy':'Inspect CSV must match independently parsed effective LAND cell+LAND canonical runtime IDs exactly; new caches must match inspect XY exactly, including zero-blade caches.'})
    allowed=[];limit_path=OUT/'known_missing_grass.json'
    if limit_path.exists():
        limits=json.loads(limit_path.read_text(encoding='utf-8'));assert limits['status']=='EXACT_PREEXISTING_SOURCE_LIMIT_ALLOWLIST_NOT_REPAIRED'
        final_grasses=grasses(plugins)
        for entry in limits['entries']:
            g=final_grasses[entry['canonical']]
            assert g['model']==entry['model'] and g['payload_sha256']==entry['final_GRAS_payload_sha256']==entry['original_GRAS_payload_sha256'],'Missing grass source limit payload/model drift; investigate'
            allowed.append({**entry,'runtime_id':g['runtime_id'],'allowed_occurrences':[{**o,'texture_runtime_id':f'{runtime_id(o["texture_canonical"],plugins):08X}'} for o in entry['allowed_occurrences']]})
    manifest={'status':'CPU_BULK_PREPARED_NOT_EXECUTED','utc':datetime.now(timezone.utc).isoformat(),'profile':args.profile,'profile_path':str(profile),
        'profile_sha256':snapshot,'plugins':plugins,'Skyrim_ccc_sha256':sha(TARGET/'Game/Skyrim.ccc'),'auxiliary':aux,
        'generator':{'path':str(OUT/'tools/FasterNGIO_1.6/FasterNGIO.exe'),'sha256':'e955a84cc48b1d1448adf92c796da896190e40c6ea1ac46d1b83282d3970331c'},
        'batches':batches,'reserve_GiB':32,'output_budget_GiB':8,'threads':4,'writers':1,
        'source_inspection_sha256':sha(OLD/'offline_grass_plan.json'),
        'constraints':['No GUI, game, --overwrite or --world all','Every world uses a new independent directory under research/lod_update/bulk_runs',
            'WhiterunWorld excluded: GrassCacheHelper ForceGrassWorlds is not read by FasterNGIO; preserve normalized old cache there.',
            'Generated caches must win above identity-only remap overlay; do not replace unselected worlds.',
            'Static CPU geometry cannot represent every Papyrus/BOS dynamic state. A successful output is not in-game verification.'],
        'root_invocation':['python','Database/integration/run_mo2_child.py','--profile',args.profile,'FRESH_TASK_NAME',str(OUT.parents[1]/'logged_child.py'),'FRESH_TASK_NAME',str(OUT/'faster_ngio_bulk_child.py'),'--manifest',str(OUT/'bulk_manifest.json'),'--run-name','FRESH_RUN_NAME'],
        'recommended_first_append':['--inspect-only'],'allowed_unloadable_grass':allowed,
        'known_missing_grass_sha256':sha(limit_path) if limit_path.exists() else None}
    assert snapshot=={name:sha(profile/name) for name in snapshot},'Profile drift during preparation'
    owned(OUT/'bulk_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'plugins':len(plugins),'worlds':[(b['editor_id'],b['world_runtime_id'],b['expected_effective_LAND_cells']) for b in batches]},ensure_ascii=False))
if __name__=='__main__':sys.stdout.reconfigure(encoding='utf-8');main()
