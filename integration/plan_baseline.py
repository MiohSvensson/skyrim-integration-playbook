"""Prepare the complete TuLED baseline without writing the runtime tree."""
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from materialize import BASE, TARGET, add_file_mapping, add_unit, budget, connect


def label(mod_id, name):
    # Short stable physical names avoid adding path length to the source layout.
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .')[:70].rstrip(' .')
    return f'T{mod_id:04d} {name}'


def main():
    source_db = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro', uri=True)
    source_db.row_factory = sqlite3.Row
    mods = [dict(r) for r in source_db.execute('''select m.*,pm.list_order from mods m
       join profile_mods pm on pm.mod_id=m.id join profiles r on r.id=pm.profile_id
       join packs p on p.id=m.pack_id where p.name='TuLED' and r.is_selected=1 and pm.enabled=1
       order by pm.list_order desc''')]
    assert len(mods) == 2269, len(mods)
    c = connect()
    for mod in mods:
        unit_id = f"mod_{mod['id']}"
        mod['directory'] = label(mod['id'], mod['name'])
        mod['pack'] = 'TuLED'
        mod['role'] = 'baseline'
        if not c.execute('select 1 from units where id=?', (unit_id,)).fetchone():
            count = add_unit(c, unit_id, mod['path'], 'mods/'+mod['directory'], 'Selected TuLED baseline mod; preserve original relative priority')
            print(json.dumps({'mod_id': mod['id'], 'files_planned': count}, ensure_ascii=False), flush=True)
    mapping_path = BASE / 'integration/research/runtime_layout/root_payload_mapping.json'
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if not c.execute("select 1 from units where id='game_files'").fetchone():
        game_files = [{'source': r['source'], 'destination': 'Game/'+r['destination_relative'],
                       'bytes': r['bytes'], 'storage': 'shared' if r['storage'].startswith('shared') else 'private'} for r in mapping['game_files']]
        add_file_mapping(c, 'game_files', game_files, 'Reviewed complete game tree with consistent stock data')
    if not c.execute("select 1 from units where id='game_root_payload'").fetchone():
        root_files = [{'source': r['winner']['source'], 'destination': 'Game/'+r['destination_relative'],
                       'bytes': r['winner']['size_bytes'], 'storage': 'private'} for r in mapping['game_root_winners']]
        add_file_mapping(c, 'game_root_payload', root_files,
                         'Reviewed runtime root payload; CreationKit/CKPE omitted, Engine Fixes runtime wins', replace_planned=True)
    if not c.execute("select 1 from units where id='base_overwrite'").fetchone():
        source = source_db.execute("select base_path from packs where name='TuLED'").fetchone()[0]
        add_unit(c, 'base_overwrite', Path(source)/'overwrite', 'mods/ZZ TuLED original overwrite',
                 'Complete original selected overwrite preserved above baseline resources')
    result = budget(c)
    (BASE/'integration/baseline_mods.json').write_text(json.dumps(mods, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (BASE/'integration/baseline_budget.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    c.close()
    source_db.close()
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
