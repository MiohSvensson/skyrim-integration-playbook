"""Read-only worldspace/LOD inventory for bounded integration generation."""
import collections
import hashlib
import json
import re
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
DB = OUT.parents[3]
ROOT = DB.parent
sys.path.insert(0, str(OUT.parents[1] / 'navmesh_patch'))
from verify_candidate import Plugin, fields


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def grouped(plugin):
    records = {record['offset']: record for record in plugin.records}
    result = collections.defaultdict(collections.Counter)
    shared_lands = []
    with plugin.path.open('rb') as stream:
        def walk(start, end, world=None, cell=None):
            pos = start
            while pos < end:
                stream.seek(pos)
                header = stream.read(24)
                assert len(header) == 24
                size = struct.unpack_from('<I', header, 4)[0]
                if header[:4] == b'GRUP':
                    assert size >= 24
                    typ = struct.unpack_from('<i', header, 12)[0]
                    next_world = plugin.identity(struct.unpack_from('<I', header, 8)[0]) if typ == 1 else world
                    next_cell = plugin.identity(struct.unpack_from('<I', header, 8)[0]) if typ in (6,8,9,10) else cell
                    if typ == 1:
                        next_cell = None
                    walk(pos + 24, pos + size, next_world, next_cell)
                else:
                    record = records[pos]
                    if world:
                        result[world][record['signature']] += 1
                        if record['signature'] == 'LAND' and not world.startswith(plugin.name + '|'):
                            shared_lands.append({'record': record['id'], 'world': world, 'cell': cell})
                    size += 24
                pos += size
            assert pos == end
        walk(0, plugin.path.stat().st_size)
    for row in shared_lands:
        cell_record = plugin.get(row['cell'], 'CELL')
        cell_data = dict(fields(plugin.payload(cell_record)))
        row['cell_XY'] = list(struct.unpack_from('<ii', cell_data['XCLC']))
        row['overlap_LOD_quads_lower_bound'] = {str(level): [(row['cell_XY'][0]//level)*level,(row['cell_XY'][1]//level)*level]
           for level in (4,8,16,32)}
    return {key: dict(value) for key, value in result.items()}, shared_lands


def asset_summary(rows):
    result = {}
    for path, size in rows:
        path = path.lower().replace('\\', '/')
        parts = path.split('/')
        world, kind = None, None
        if len(parts) > 3 and parts[:2] in (['meshes', 'terrain'], ['textures', 'terrain']):
            world = parts[2]
            suffix = Path(path).suffix
            kind = {'.btr': 'terrain_mesh', '.bto': 'object_lod_mesh', '.btt': 'tree_lod', '.dds': 'terrain_or_lod_texture'}.get(suffix, 'other_terrain_asset')
        elif len(parts) == 2 and parts[0] == 'lodsettings':
            world, kind = Path(parts[1]).stem, 'lodsettings'
        elif len(parts) == 2 and parts[0] in ('grass', 'grasscache') and path.endswith('.cgid'):
            world = re.sub(r'x-?\d+y-?\d+.*$', '', Path(parts[1]).stem)
            kind = 'grass_cache'
        if world is None:
            continue
        value = result.setdefault(world, {}).setdefault(kind, {'files': 0, 'logical_bytes': 0})
        value['files'] += 1
        value['logical_bytes'] += size
    return result


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    feature_report = json.loads((OUT.parents[1] / 'feature_conflicts/raw_field_comparison.json').read_text(encoding='utf-8'))
    paths = {row['plugin']: Path(row['path']) for row in feature_report['features']
             if row['plugin'] in ('Wyrmstooth.esp', 'ForgottenCity.esp', '[LongShou]WorldInPainting_ZeroHall.esp', '[longshou]UF6.esp')}
    paths['Glenmoril.esm'] = DB / 'xedit_runs/Anno/Data/Glenmoril.esm'
    paths['MoonAndStar_MAS.esp'] = ROOT / 'Anno/iniRePather-Skyrim/mods/Moon and Star/MoonAndStar_MAS.esp'
    database = sqlite3.connect('file:' + (DB / 'baseline/skyrim_research.sqlite').as_posix() + '?mode=ro', uri=True)
    database.row_factory = sqlite3.Row
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'status': 'READ_ONLY_SOURCE_SCOPE', 'features': []}
    for name, path in paths.items():
        plugin = Plugin(path)
        worlds = []
        grouped_records, shared_lands = grouped(plugin)
        for record in plugin.records:
            if record['signature'] != 'WRLD':
                continue
            data = dict(fields(plugin.payload(record)))
            flags = int.from_bytes(data.get('DATA', b'\0'), 'little')
            parent = plugin.identity(struct.unpack('<I', data['WNAM'])[0]) if 'WNAM' in data else None
            parent_flags = int.from_bytes(data.get('PNAM', b'\0')[:1], 'little')
            worlds.append({'id': record['id'], 'own': record['id'].startswith(plugin.name + '|'),
                           'editor_id': data.get('EDID', b'').rstrip(b'\0').decode('utf-8', 'replace'),
                           'flags': flags, 'small_world': bool(flags & 1), 'no_landscape': bool(flags & 16),
                           'no_grass': bool(flags & 128), 'parent': parent, 'parent_flags': parent_flags,
                           'uses_parent_land': bool(parent_flags & 1), 'uses_parent_LOD': bool(parent_flags & 2),
                           'record_counts': grouped_records.get(record['id'], {})})
        provider_rows = database.execute('''SELECT DISTINCT m.id,m.name,m.path,p.name pack FROM mods m JOIN packs p ON p.id=m.pack_id
          JOIN plugin_files pf ON pf.mod_id=m.id WHERE p.name='Anno' AND pf.name_key=?''', (name.lower(),)).fetchall()
        provider_assets = []
        for provider in provider_rows:
            loose = list(database.execute('SELECT relative_path,size_bytes FROM files WHERE mod_id=?', (provider['id'],)))
            archives = database.execute('''SELECT ba.id,ba.path,ba.size_bytes FROM bsa_archives ba JOIN bsa_sources bs ON bs.archive_id=ba.id
              WHERE bs.mod_id=?''', (provider['id'],)).fetchall()
            members = []
            for archive in archives:
                members.extend(database.execute('SELECT path,size_bytes FROM bsa_entries WHERE archive_id=?', (archive['id'],)))
            provider_assets.append({'provider': dict(provider), 'loose': asset_summary(loose), 'BSA': asset_summary(members),
                                    'archives': [dict(row) for row in archives]})
        report['features'].append({'plugin': name, 'path': str(path), 'sha256': sha(path), 'worlds': worlds,
                                   'world_children_counts': grouped_records, 'shared_world_LAND_cells': shared_lands,
                                   'provider_assets': provider_assets})
    final_files = sqlite3.connect('file:' + (DB / 'integration/files.sqlite').as_posix() + '?mode=ro', uri=True)
    rows = final_files.execute('''SELECT relative_path,size_bytes FROM files WHERE
      lower(relative_path) LIKE 'meshes/terrain/%' OR lower(relative_path) LIKE 'textures/terrain/%' OR
      lower(relative_path) LIKE 'meshes\\terrain\\%' OR lower(relative_path) LIKE 'textures\\terrain\\%' OR
      lower(relative_path) LIKE 'lodsettings/%' OR lower(relative_path) LIKE 'lodsettings\\%' OR
      lower(relative_path) LIKE 'grass/%' OR lower(relative_path) LIKE 'grass\\%' OR lower(relative_path) LIKE 'grasscache/%' ''')
    report['planned_materialized_lod_assets_all_providers'] = asset_summary(rows)
    unit_rows = final_files.execute('''SELECT u.id,u.source,COUNT(*) files,SUM(f.size_bytes) logical_bytes
      FROM units u JOIN files f ON f.unit_id=u.id GROUP BY u.id''').fetchall()
    report['existing_generated_output_units'] = [dict(zip(('unit','source','files','logical_bytes'), row)) for row in unit_rows
      if any(token in row[1].lower() for token in ('dyndolod output','dyndolod_output','texgen output','xlodgen output','grass cache'))]
    inventory = json.loads((DB / 'integration/physical_runtime_inventory.json').read_text(encoding='utf-8'))
    report['existing_generated_plugins'] = [row for row in inventory['plugins'] if row['name'].lower() in ('dyndolod.esm', 'dyndolod.esp', 'occlusion.esp')]
    report['measurement_notes'] = ['SQLite inventory is a source snapshot, not a current physical winner manifest.',
        'All provider counts include duplicates; BSA size_bytes are uncompressed member sizes.',
        'Worldspace small/no-landscape/parent flags need official tool eligibility checks; record presence alone does not require LOD.',
        'Other features/followers/equipment may add existing-world references and must be included in a final winner sweep.']
    (OUT / 'scope_inventory.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': str(OUT / 'scope_inventory.json'), 'features': [{'plugin': row['plugin'], 'worlds': len(row['worlds']),
        'world_children': len(row['world_children_counts'])} for row in report['features']]}, ensure_ascii=False))


if __name__ == '__main__':
    main()
