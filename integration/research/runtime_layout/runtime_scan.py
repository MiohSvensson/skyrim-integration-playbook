"""Read-only source/mirror measurements for the integration runtime design."""
import collections
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
DB = OUT.parents[2]
SHARED_EXTENSIONS = {'.bsa', '.dds', '.nif', '.hkx', '.tri', '.fuz', '.wav', '.xwm', '.osd', '.bto', '.btr', '.bik', '.lip', '.cgid'}
ASSET_DIRECTORIES = {'meshes', 'textures', 'sound', 'music', 'video'}


def lp(path):
    return '\\\\?\\' + str(Path(path).absolute())


def scan_tree(root):
    root = Path(root)
    totals = collections.defaultdict(lambda: {'files': 0, 'bytes': 0})
    errors, reparses = [], []
    pending = [(root, '')]
    while pending:
        folder, prefix = pending.pop()
        try:
            with os.scandir(lp(folder)) as entries:
                for entry in entries:
                    rel = f'{prefix}/{entry.name}'.lstrip('/')
                    try:
                        st = entry.stat(follow_symlinks=False)
                        if st.st_file_attributes & 0x400:
                            reparses.append(rel)
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append((folder / entry.name, rel))
                        elif entry.is_file(follow_symlinks=False):
                            top = rel.split('/', 1)[0] if '/' in rel else '[root files]'
                            totals[top]['files'] += 1
                            totals[top]['bytes'] += st.st_size
                    except OSError as exc:
                        errors.append({'path': rel, 'error': str(exc)})
        except OSError as exc:
            errors.append({'path': prefix, 'error': str(exc)})
    return {'path': str(root), 'file_count': sum(v['files'] for v in totals.values()),
            'logical_bytes': sum(v['bytes'] for v in totals.values()), 'top_level': dict(totals),
            'skipped_reparse_points': reparses, 'errors': errors}


def category(name):
    if re.search(r'body ?slide output|body slide output', name, re.I): return 'bodyslide_output'
    if re.search(r'pandora output', name, re.I): return 'behavior_output'
    if re.search(r'(parallaxgen|pgpatcher)[_ ]output', name, re.I): return 'parallax_output'
    if re.search(r'dyndolod[_ ]output', name, re.I): return 'dyndolod_output'
    if re.search(r'texgen[_ ]output', name, re.I): return 'texgen_output'
    if re.search(r'xlodgen[_ -]output', name, re.I): return 'terrain_output'
    if re.search(r'synthesis patch', name, re.I): return 'synthesis_output'
    if re.search(r'^SKSE Output', name, re.I): return 'skse_output'
    if re.search(r'VramR Output', name, re.I): return 'vramr_output'
    return None


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    con = sqlite3.connect((DB / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    con.row_factory = sqlite3.Row
    con.execute('pragma temp_store=memory')
    con.execute('create temp table active(mod_id integer primary key,pack text,name text,ord integer)')
    con.execute('''insert or ignore into active select m.id,p.name,m.name,pm.list_order
        from mods m join packs p on p.id=m.pack_id join profile_mods pm on pm.mod_id=m.id
        join profiles r on r.id=pm.profile_id where r.is_selected=1 and pm.enabled=1''')
    packs = [dict(row) for row in con.execute('select * from packs')]
    outputs = []
    mods = {}
    for row in con.execute('''select a.mod_id,a.pack,a.name,a.ord,count(*) file_count,sum(f.size_bytes) logical_bytes
                              from active a join files f on f.mod_id=a.mod_id group by a.mod_id'''):
        row = dict(row)
        mods[row['mod_id']] = row
        kind = category(row['name'])
        if kind:
            row['kind'] = kind
            row['source_path'] = con.execute('select path from mods where id=?',(row['mod_id'],)).fetchone()[0]
            outputs.append(row)
    by_pack = {}
    for pack in packs:
        name = pack['name']
        print('scanning', name, flush=True)
        info = {'game': scan_tree(pack['game_path']),
                'overwrite': scan_tree(Path(pack['base_path'])/'overwrite'),
                'existing_partial_game': scan_tree(DB/'mo2_vfs'/name/'Game'),
                'existing_partial_mods': scan_tree(DB/'mo2_vfs'/name/'instance/mods'),
                'selected_mods': sum(1 for row in mods.values() if row['pack'] == name),
                'selected_mod_file_count': 0, 'selected_mod_logical_bytes': 0,
                'share_candidate_file_count': 0, 'share_candidate_logical_bytes': 0,
                'private_file_count': 0, 'private_logical_bytes': 0,
                'root_mods': [], 'outputs': [row for row in outputs if row['pack'] == name]}
        by_pack[name] = info
    root_mods = collections.defaultdict(lambda: {'files': 0, 'bytes': 0})
    for row in con.execute('''select a.mod_id,a.pack,a.name,f.path_key,f.extension,f.size_bytes
        from active a join files f on f.mod_id=a.mod_id'''):
        info = by_pack[row['pack']]
        key = row['path_key'].replace('\\','/').lower()
        ext = (row['extension'] or '').lower()
        first = key.split('/', 1)[0]
        shared = ext in SHARED_EXTENSIONS and (first in ASSET_DIRECTORIES or (ext == '.bsa' and '/' not in key))
        info['selected_mod_file_count'] += 1
        info['selected_mod_logical_bytes'] += row['size_bytes']
        info['share_candidate_file_count' if shared else 'private_file_count'] += 1
        info['share_candidate_logical_bytes' if shared else 'private_logical_bytes'] += row['size_bytes']
        if first == 'root':
            value = root_mods[(row['pack'], row['mod_id'], row['name'])]
            value['files'] += 1
            value['bytes'] += row['size_bytes']
    for (pack, mod_id, name), value in root_mods.items():
        by_pack[pack]['root_mods'].append({'mod_id': mod_id, 'name': name, **value})
    usage = shutil.disk_usage(DB)
    result = {'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'READ_ONLY_MEASUREMENTS_NO_SOURCE_LINKS_CREATED',
              'source_inventory_note': 'Selected mod counts/lengths are from existing database snapshot; game/overwrite/partial mirror measurements are current directory walks. Logical bytes are not physical allocation.',
              'share_policy': {'extensions': sorted(SHARED_EXTENSIONS), 'directories': sorted(ASSET_DIRECTORIES), 'exception': 'root BSA files allowed; all other paths private', 'limitation': 'This policy is only safe for explicitly read-only shared assets and dedicated fresh tool output; it is not write isolation.'},
              'volume_free_bytes': usage.free,
              'packs': by_pack}
    (OUT/'runtime_measurements.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:{kk:vv for kk,vv in v.items() if kk not in ('outputs','root_mods','game','overwrite','existing_partial_game','existing_partial_mods')} for k,v in by_pack.items()}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
