"""Import the two reviewed item batches and their exact resource closures."""
import hashlib
import json
import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from materialize import BASE, TARGET, SHARED_EXTENSIONS, add_file_mapping, build, connect, guard_destination, key, lp, sha, utc
from runtime_inventory import PROFILE, resolve

sys.path.insert(0, str(BASE/'rootcause'))
from bsarch_readonly import extract_files

LAYER = 'ZZ70 Imported equipment'


def main():
    ledger = BASE/'integration/imported_equipment.json'
    assert not ledger.exists(), 'Equipment already imported; inspect ledger'
    frozen = BASE/'integration/selection_snapshots'
    frozen.mkdir(exist_ok=True)
    inputs = []
    manifests = []
    for file_name in ['gear_builder_manifest_batch1_48.json', 'gear_builder_manifest_batch2.json']:
        file = BASE/'integration/research/plugin_integration'/file_name
        raw = file.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        snapshot = frozen/(digest[:12]+'_'+file_name)
        if not snapshot.exists():
            snapshot.write_bytes(raw)
        inputs.append({'path': str(snapshot), 'sha256': digest})
        manifests.append(json.loads(raw))
    plugins = [r for m in manifests for r in m['plugins']]
    assert len(plugins) == 52 and len({key(r['name']) for r in plugins}) == 52
    assets = {}
    for manifest in manifests:
        for asset_key, row in manifest['asset_sources'].items():
            if asset_key in assets:
                assets[asset_key]['requested_by'] = sorted(set(assets[asset_key]['requested_by']+row['requested_by']))
                assets[asset_key]['providers'] += row['providers']
            else:
                assets[asset_key] = json.loads(json.dumps(row))
    def provider_hash(provider):
        source = provider['source']
        return sha(source['path']) if source['kind'] == 'loose' else source['sha256']
    # A shared path with different authored content needs a separate decision.
    for asset_key, row in assets.items():
        if Path(asset_key).is_absolute() or '..' in Path(asset_key).parts:
            raise ValueError(f'Unsafe resource path: {asset_key}')
        if row['recommended_action'] == 'stage_explicit_source' and len(row['providers']) > 1:
            hashes = {provider_hash(p) for p in row['providers']}
            if len(hashes) != 1:
                raise RuntimeError(f'Unresolved equipment asset collision: {asset_key}')
    mappings = []
    selected = []
    source_mod_ids = set()
    for row in plugins:
        assert resolve(row['name'])[1] is None, f'Plugin already present: {row["name"]}'
        expected_source = row.get('source_sha256') or sha(BASE/'xedit_runs'/row['pack']/'Data'/row['name'])
        assert sha(row['source_path']) == expected_source
        source = row['source_path']
        replacement = row.get('validated_replacement')
        if replacement:
            source = replacement['candidate']
            assert sha(source) == replacement['candidate_sha256']
        mappings.append({'source': source, 'destination': f'mods/{LAYER}/{row["name"]}', 'storage': 'private'})
        selected.append(row | {'source_sha256': expected_source, 'selected_source': source, 'selected_sha256': sha(source)})
        source_mod_ids.add(row['source_mod_id'])
    archive_groups = defaultdict(dict)
    archive_sources = {}
    inherited = []
    for asset_key, row in assets.items():
        if row['recommended_action'] == 'inherit_base_then_validate':
            inherited.append({'path_key': asset_key, **row})
            continue
        assert row['recommended_action'] == 'stage_explicit_source'
        provider = row['providers'][0]
        source = provider['source']
        source_mod_ids.add(source['mod_id'])
        if source['kind'] == 'loose':
            if provider.get('nif_sha256'):
                assert sha(source['path']) == provider['nif_sha256'], asset_key
            mappings.append({'source': source['path'], 'destination': f'mods/{LAYER}/{asset_key}',
                             'bytes': source['size_bytes'],
                             'storage': 'shared' if Path(asset_key).suffix in SHARED_EXTENSIONS else 'private'})
        else:
            assert source['kind'] in ('bsa_same_content_candidates', 'bsa_associated_loadorder_candidate')
            archive_groups[source['archive_id']][asset_key] = source['sha256']
            archive_sources[source['archive_id']] = source['path']
    extracted = []
    archive_bytes = sum(row['providers'][0]['source'].get('size_bytes', 0) for row in assets.values()
                        if row['recommended_action'] == 'stage_explicit_source' and row['providers'][0]['source']['kind'] != 'loose')
    if shutil.disk_usage(BASE).free < 32*1024**3 + archive_bytes + 1024**3:
        raise RuntimeError('Insufficient space for verified BSA extraction and reserve')
    for archive_id, expected in archive_groups.items():
        # These batches contain a bounded texture set. Extraction verifies every member SHA.
        blobs = extract_files(archive_sources[archive_id], expected)
        for asset_key, blob in blobs.items():
            cache_file = BASE/'integration/extracted_assets'/str(archive_id)/asset_key
            assert cache_file.resolve().is_relative_to((BASE/'integration/extracted_assets').resolve())
            os.makedirs(lp(cache_file.parent), exist_ok=True)
            if cache_file.exists():
                assert sha(cache_file) == expected[asset_key]
            else:
                with open(lp(cache_file), 'xb') as stream:
                    stream.write(blob)
            assert sha(cache_file) == expected[asset_key]
            mappings.append({'source': str(cache_file), 'destination': f'mods/{LAYER}/{asset_key}',
                             'bytes': len(blob), 'storage': 'shared' if Path(asset_key).suffix in SHARED_EXTENSIONS else 'private'})
            extracted.append({'archive_id': archive_id, 'archive': archive_sources[archive_id], 'member': asset_key,
                              'sha256': expected[asset_key], 'bytes': len(blob), 'extracted': str(cache_file)})
        print(json.dumps({'archive': archive_id, 'extracted_members': len(blobs)}), flush=True)
    c = connect()
    assert not c.execute("select 1 from units where id='equipment_batches_1_2'").fetchone()
    add_file_mapping(c, 'equipment_batches_1_2', mappings,
                     '52 pure new item plugins plus explicit NIF/texture/physics closure; no global source scripts, DLLs or actor configuration')
    build(c)
    c.close()
    lines = (PROFILE/'modlist.txt').read_text(encoding='utf-8-sig').splitlines()
    lines.insert(0, '+'+LAYER)
    (PROFILE/'modlist.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    for file_name in ['plugins.txt', 'loadorder.txt']:
        path = PROFILE/file_name
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        insert_at = next((i for i, line in enumerate(lines) if key(line.lstrip('*')) == 'synthesis - patch.esp'), len(lines))
        lines[insert_at:insert_at] = [('*' if file_name == 'plugins.txt' else '')+row['name'] for row in selected]
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    overrides_file = BASE/'integration/decision_overrides.json'
    overrides = json.loads(overrides_file.read_text(encoding='utf-8'))
    for mid in sorted(source_mod_ids):
        names = [row['name'] for row in plugins if row['source_mod_id'] == mid]
        overrides.append({'mod_id': mid, 'decision': 'partially_adopted_explicit_files', 'category': 'validated_item_closure',
                          'reason': ('只採用明確裝備插件與專屬資源：'+', '.join(names)) if names else '只重用已列出並核對的裝備網格／貼圖資源，未採用其整套生成輸出或全局框架。',
                          'directory': LAYER, 'evidence': 'integration/imported_equipment.json'})
    overrides_file.write_text(json.dumps(overrides, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    result = {'utc': utc(), 'layer': LAYER, 'inputs': inputs, 'plugins': selected,
              'source_mod_ids': sorted(source_mod_ids), 'new_resources': len(mappings)-len(selected),
              'inherited_resources': inherited, 'extracted_bsa_members': extracted,
              'status': 'MATERIALIZED_PENDING_JOINT_VFS_AND_XEDIT_VALIDATION',
              'constraints': 'No source mixed library scripts/DLLs/OAR imported. Existing base global body/equipment resource winners retained.'}
    ledger.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'plugins': len(selected), 'new_resources': result['new_resources'],
                      'inherited_resources': len(inherited), 'extracted_members': len(extracted)}, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
