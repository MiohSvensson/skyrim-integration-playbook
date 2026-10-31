"""Bind four missing Skin Tint fallback names to the selected base skin set."""
import json
from materialize import BASE, TARGET, add_file_mapping, build, connect, sha, utc
from runtime_inventory import PROFILE

ledger = BASE/'integration/rihad_skin_fallback_aliases.json'
assert not ledger.exists(), 'Aliases already applied'
evidence_path = BASE/'integration/research/vfs_validation/graph_issue_evidence.json'
evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
aliases = evidence['rihad']['fallback_aliases']
assert len(aliases) == 4 and {r['slot_index'] for r in aliases} == {0, 1, 2, 7}
layer = 'ZZ82 Skin Tint fallback aliases'
mappings = []
for row in aliases:
    assert sha(row['source_physical']) == row['sha256']
    mappings.append({'source': row['source_physical'], 'destination': f"mods/{layer}/{row['destination']}", 'storage': 'shared'})
c = connect()
add_file_mapping(c, 'rihad_skin_fallback_aliases', mappings,
                 'Explicit base 3BA Skin Tint diffuse/normal/subsurface/specular fallbacks; both boot weight NIFs and actor skin overrides unchanged')
build(c)
c.close()
path = PROFILE/'modlist.txt'
path.write_text('+'+layer+'\n'+path.read_text(encoding='utf-8-sig'), encoding='utf-8')
ledger.write_text(json.dumps({'utc': utc(), 'layer': layer, 'aliases': aliases, 'evidence': str(evidence_path),
    'policy': 'Use the selected TuLED/Glass 3BA skin set for otherwise missing fallback paths. This is an integration choice, not a claim to restore missing COR assets.',
    'nif_geometry_materials_and_actor_skin_bindings_unchanged': True,
    'status': 'MATERIALIZED_PENDING_VFS_RECHECK'}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Added four explicit Skin Tint fallback aliases without modifying any NIF')
