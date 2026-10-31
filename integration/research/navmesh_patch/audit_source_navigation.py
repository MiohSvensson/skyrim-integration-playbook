"""Reproduce source-only NVMI/NVPP evidence; does not create a plugin."""
import json
import struct
from pathlib import Path
from verify_candidate import Plugin, fields, nvmi_model, nvpp_model, TARGET, NAVI, sha

BASE = Path(__file__).resolve().parent
SOURCES = [
    BASE.parents[2]/'xedit_runs/TuLED/Data/Skyrim.esm',
    BASE.parents[2]/'xedit_runs/Anno/Data/Glenmoril.esm',
    BASE.parents[2]/'xedit_runs/TuLED/Data/AKSkyrimUnderground.esm',
]


def main():
    navi_rows, path_rows = [], []
    for path in SOURCES:
        plugin = Plugin(path)
        record = plugin.get(NAVI,'NAVI')
        entries, path_entries = [], []
        for tag,data in fields(plugin.payload(record)):
            if tag == 'NVMI':
                if plugin.identity(struct.unpack_from('<I',data)[0]) != TARGET:
                    continue
                model = nvmi_model(plugin,data)
                entries.append({'NAVI_record':record['id'],'model':model,
                                'raw_NVMI_hex':data.hex(),'raw_NVMI_sha256':sha(data),
                                'NVMI_bytes':len(data)})
            elif tag == 'NVPP':
                model = nvpp_model(plugin,data)
                hits = [{'index':i,'refs':refs} for i,refs in enumerate(model['paths']) if TARGET in refs]
                markers = [m for m in model['roadmarkers'] if m['navmesh'] == TARGET]
                path_entries.append({'NAVI':record['id'],'NVPP_bytes':len(data),'NVPP_sha256':sha(data),
                    'path_count':len(model['paths']),'path_ref_count':sum(map(len,model['paths'])),
                    'target_paths':hits,'roadmarker_count':len(model['roadmarkers']),'target_roadmarkers':markers})
        assert len(entries) == 1
        navi_rows.append({'file':str(plugin.path),'entries':entries})
        path_rows.append({'source':str(plugin.path),'NVPP':path_entries})
    (BASE/'navi_source_audit.json').write_text(json.dumps(navi_rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (BASE/'nvpp_source_audit.json').write_text(json.dumps(path_rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'NVMI_entries':sum(len(row['entries']) for row in navi_rows),
                      'NVPP_digests':[row['NVPP'][0]['NVPP_sha256'] for row in path_rows],
                      'plugins_written':0},indent=2))


if __name__ == '__main__':
    main()
