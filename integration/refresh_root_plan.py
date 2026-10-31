"""Apply the finalized reviewed root mapping while the root units are still planned."""
import json
from materialize import BASE, connect, add_file_mapping, budget

c = connect()
mapping = json.loads((BASE/'integration/research/runtime_layout/root_payload_mapping.json').read_text(encoding='utf-8'))
for unit in ['game_root_payload', 'game_files']:
    states = c.execute('select distinct status from files where unit_id=?', (unit,)).fetchall()
    assert all(r[0] == 'planned' for r in states), f'{unit} already materialized'
    c.execute('delete from files where unit_id=?', (unit,))
    c.execute('delete from units where id=?', (unit,))
c.commit()
files = [{'source': r['source'], 'destination': 'Game/'+r['destination_relative'],
          'bytes': r['bytes'], 'storage': 'shared' if r['storage'].startswith('shared') else 'private'} for r in mapping['game_files']]
add_file_mapping(c, 'game_files', files, 'Reviewed complete game tree, consistent stock revision')
files = [{'source': r['winner']['source'], 'destination': 'Game/'+r['destination_relative'],
          'bytes': r['winner']['size_bytes'], 'storage': 'private'} for r in mapping['game_root_winners']]
add_file_mapping(c, 'game_root_payload', files,
                 'Final reviewed runtime root: official SKSE 2.0.20, Engine Fixes, no CK/CKPE/foreign ASI', replace_planned=True)
result = budget(c)
(BASE/'integration/baseline_budget.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
c.close()
