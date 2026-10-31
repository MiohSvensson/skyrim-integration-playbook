import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from vfs_common import *
sys.path.insert(0,str(BASE/'integration'))
from runtime_inventory import resolve


def main():
    equipment=json.loads((BASE/'integration/imported_equipment.json').read_text(encoding='utf-8'));rows=[]
    for row in equipment['plugins']:
        source=Path(row['selected_source']);provider,clone=resolve(row['name']);s=plugin_header(source);v=plugin_header(clone)
        rows.append({'plugin':row['name'],'source_path':str(source),'source':s|{'owned_id_range':owned_id_range(source,len(s['masters']),s['is_light'])},
          'clone_path':str(clone),'clone_provider':provider,'clone':v|{'owned_id_range':owned_id_range(clone,len(v['masters']),v['is_light'])}})
    result={'scope':'Original selected source versus actual current integration clone; no files were modified.',
      'plugins':rows,'counts':{'plugins':len(rows),'source_invalid_light_range':sum(not r['source']['owned_id_range']['light_owned_id_range_valid'] for r in rows),
      'clone_invalid_light_range':sum(not r['clone']['owned_id_range']['light_owned_id_range_valid'] for r in rows)},
      'invalid_source_plugins':[r['plugin'] for r in rows if not r['source']['owned_id_range']['light_owned_id_range_valid']],
      'invalid_clone_plugins':[r['plugin'] for r in rows if not r['clone']['owned_id_range']['light_owned_id_range_valid']]}
    write_json(OWN/'gear_owned_id_preflight.json',result);print(json.dumps({k:v for k,v in result.items() if k!='plugins'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
