import collections
import json
from pathlib import Path
import struct
import sys

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'rootcause'))
import nif_inventory


def main():
    rows=[];counts=collections.Counter();seen=set()
    for batch in ['gear_builder_manifest_batch1_48.json','gear_builder_manifest_batch2.json']:
        j=json.loads((OUT/batch).read_text(encoding='utf-8'))
        for key,entry in j['asset_sources'].items():
            if not key.endswith('.nif'):continue
            for provider in entry['providers']:
                source=provider['source'];path=Path(source['path']) if source['kind'] in ('loose','stock_loose') else OUT/'nif_samples'/(source['sha256']+'.nif')
                if str(path).casefold() in seen:continue
                seen.add(str(path).casefold());win=str(path.absolute());win=win if win.startswith('\\\\?\\') else '\\\\?\\'+win
                inv=nif_inventory.inventory(win);data=Path(win).read_bytes()
                for block in inv['blocks']:
                    counts[block['type']]+=1
                    if block['type'] in ('BSBehaviorGraphExtraData','NiSourceTexture','NiSourceCubeMap','BSShaderPPLightingProperty','NiTexturingProperty'):
                        row={'batch':batch,'path_key':key,'physical_path':str(path),'requested_by':entry['requested_by'],'block_type':block['type'],'block_bytes':block['bytes']}
                        if block['type']=='BSBehaviorGraphExtraData':
                            name,value=struct.unpack_from('<II',data,block['offset']);row['name']=inv['strings'][name] if name!=0xffffffff else '';row['behavior_file']=inv['strings'][value] if value!=0xffffffff else ''
                        rows.append(row)
    output={'nif_files_inspected':len(seen),'block_counts':dict(counts),'external_blocks_beyond_basic_texture_and_extra_data':rows}
    (OUT/'nif_external_block_audit.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'nif_files_inspected':len(seen),'external_blocks':rows},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
