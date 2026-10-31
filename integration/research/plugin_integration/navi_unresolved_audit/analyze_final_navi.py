"""Read all final active plugin headers once; audit every NAVI key canonically.

No source database/profile/plugin is changed. The sole expected absent key is
independently established from actual complete active record headers, rather
than assumed from a raw byte grep or from the final partial NAVI alone.
"""
import collections
import hashlib
import json
from pathlib import Path
import struct
import sys
import time
import zlib

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[3]
sys.path.insert(0,str(BASE/'integration/research/navmesh_patch'))
from verify_candidate import Plugin, fields, navi_model, nvmi_model, NAVI

ORPHAN='skyrim.esm|028E37'
FC_TARGETS={f'skyrim.esm|{n:06X}' for n in (0x10751B,0x107527,0x107528,0x107532,0x108AB4,0x108ABF,0x108BFA)}


def sha(blob):return hashlib.sha256(blob).hexdigest()
def pin(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':sha(path.read_bytes())}


def main():
    task=BASE/'UnifiedSkyrim/validation/fc_navigation_v2'
    inventory=json.loads((task/'input_inventory.json').read_text('utf-8'))['plugins']
    navis=[];present=collections.defaultdict(list);wrong_signature=[]
    counts=collections.Counter();start=time.monotonic()
    for load_index,row in enumerate(inventory):
        data=Path(row['path']).read_bytes()
        assert sha(data)==row['sha256'],('Source drift',row['name'])
        masters=[n.casefold() for n in row['masters']];selfname=row['name'].casefold();pos=0
        while pos<len(data):
            assert pos+24<=len(data)
            sig=data[pos:pos+4];size,flags,fid=struct.unpack_from('<III',data,pos+4)
            if sig==b'GRUP':
                assert size>=24 and pos+size<=len(data);pos+=24;continue
            assert pos+24+size<=len(data);counts['records']+=1
            index=fid>>24
            if index<=len(masters):
                owner=masters[index] if index<len(masters) else selfname
                identity=f'{owner}|{fid&0xffffff:06X}'
                if identity==ORPHAN:
                    wrong_signature.append({'signature':sig.decode('ascii'),'plugin':row['name'],'flags':flags})
                if sig==b'NAVM':
                    present[identity].append({'plugin':row['name'],'flags':flags,'raw_form_id':f'{fid:08X}'})
                    counts['NAVM_records']+=1
                elif sig==b'NAVI' and identity==NAVI:
                    p=Plugin(row['path']);r=p.get(NAVI,'NAVI');payload=p.payload(r)
                    model=navi_model(p,r)
                    raw_infos=[b for t,b in fields(payload) if t=='NVMI']
                    navis.append({'plugin':row['name'],'path':row['path'],'sha256':row['sha256'],
                                  'load_index':load_index,'record':r,'payload_sha256':sha(payload),
                                  'model':model,'raw_infos':raw_infos})
            pos+=24+size
        assert pos==len(data)
    summary=[];missing=[];deleted=[];orphan_rows=[]
    for n in navis:
        absent=[k for k in n['model']['infos'] if k!='NULL' and k not in present]
        nulls=[k for k in n['model']['infos'] if k=='NULL']
        gone=[k for k in n['model']['infos'] if k in present and present[k][-1]['flags']&0x20]
        summary.append({k:n[k] for k in ('plugin','path','sha256','load_index','record','payload_sha256')}|
                       {'nvmi_count':len(n['model']['infos']),'NULL_keys':nulls,'absent_NAVM_keys':absent,
                        'final_deleted_NAVM_keys':gone})
        missing.extend({'source_plugin':n['plugin'],'identity':k} for k in absent)
        deleted.extend({'source_plugin':n['plugin'],'identity':k,'final_winner':present[k][-1]} for k in gone)
        for ordinal,raw in enumerate(n['raw_infos']):
            if struct.unpack_from('<I',raw)[0]==0x28E37 and n['plugin'].casefold()=='skyrim.esm':
                model=nvmi_model(Plugin(n['path']),raw)
                orphan_rows.append({'source_plugin':n['plugin'],'source_file_sha256':n['sha256'],
                                    'source_file_crc32':f'{zlib.crc32(Path(n["path"]).read_bytes()):08X}',
                                    'navi_identity':NAVI,'NVMI_ordinal_in_serialized_file':ordinal,
                                    'NVMI_bytes':len(raw),'NVMI_payload_sha256':sha(raw),'NVMI_payload_hex':raw.hex(),
                                    'NVMI_model':model,'first_XYZ_floats':list(struct.unpack_from('<fff',raw,8))})
    assert missing==[{'source_plugin':'Skyrim.esm','identity':ORPHAN}],missing
    assert wrong_signature==[] and len(orphan_rows)==1
    assert not any(n['NULL_keys'] for n in summary)
    usage=[]
    for n in navis:
        m=n['model'];pre=m['precomputed']
        edges=[{'NVMI':k,'field':field} for k,v in m['infos'].items() for field in ('edges','preferred_edges') if ORPHAN in v[field]]
        paths=[i for i,path in enumerate(pre['paths']) if ORPHAN in path] if pre else []
        roads=[x for x in pre['roadmarkers'] if x['navmesh']==ORPHAN] if pre else []
        if edges or paths or roads or ORPHAN in m['deleted_navmeshes']:
            usage.append({'plugin':n['plugin'],'NVMI_edges':edges,'NVPP_path_indices':paths,'NVPP_roadmarkers':roads,
                          'NVSI_contains_orphan':ORPHAN in m['deleted_navmeshes']})
    winner=navis[-1]
    winner_keys=[]
    for key in winner['model']['infos']:
        winner_keys.append({'identity':key,'NAVM_winner':present.get(key,[])[-1] if key in present else None})
    report={'schema':'skyrim.final_navi_key_audit.v1','status':'EXACT_ONE_PREEXISTING_STOCK_ORPHAN_IDENTIFIED_NO_RECORD_REPAIR',
            'task':str(task),'input_inventory':pin(task/'input_inventory.json'),'file_map':pin(task/'file_map.json'),
            'plugin_count':len(inventory),'counts':dict(counts)|{'unique_NAVM':len(present),'NAVI_overrides':len(navis),
                'absent_NVMI_keys':len(missing),'deleted_NAVM_source_rows':len(deleted),
                'unique_deleted_NAVM_keys':len({r['identity'] for r in deleted})},
            'all_input_plugin_SHA_verified':True,'all_NVMI_layouts_and_unique_keys_binary_parsed':True,
            'orphan':orphan_rows[0],'any_loaded_record_of_any_signature_at_orphan_identity':wrong_signature,
            'other_references_to_orphan':usage,'source_summary':summary,'deleted_source_rows':deleted,
            'final_NAVI_source':{k:winner[k] for k in ('plugin','path','sha256','payload_sha256')},
            'final_NAVI_keys':winner_keys,'FC_targets_intersect_orphan':bool(FC_TARGETS&{ORPHAN}),
            'predicted_abort':'InfoFor starts with the Skyrim.esm NAVI, so its sole absent028E37 key aborts before checking override entries. Existing native log reported only a generic nil; this binary audit identifies the only absence, not a newly observed native key log.',
            'bounded_algorithm':['Only for original Skyrim.esm NAVI012FB4, exact fileSHA06a988...ffa91/CRC66212483 and exact NVMI key028E37/payload8a220f...a7304 may an unresolved key be ignored for target lookup.','Never ignore a matching target; keep duplicate target checking. All other nil keys stop. Shared/target classification returnsFalse only for this same guarded original source row.','Do not remove/change the orphan or any unrelated source entry. The final Kurone NAVI has13 keys, all resolve and none are deleted, so this lookup exception does not import the orphan into new outputs.','Retain strict complete binary equality for all nontarget NVMI/NVPP/NVSI and scalar fields, plus typed xEdit reload and Check diagnostics.'],
            'limitations':['Header/typed-schema binary lookup does not replace final native LinksTo validation.','Deleted existing records are recorded separately and are not treated as missing/nil.','This audit does not repair the upstream orphan, mutate any plugin/profile, or start any application.'],
            'seconds':round(time.monotonic()-start,3)}
    (OWN/'final_navi_key_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'plugin_count':len(inventory),'counts':report['counts'],'orphan':orphan_rows[0],
                      'other_usage':usage,'seconds':report['seconds']},indent=2))


if __name__=='__main__':main()
