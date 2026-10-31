"""Apply only reviewed baseline repairs/isolations to the private integration."""
import hashlib
import json
import os
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from materialize import BASE, TARGET, add_unit, add_file_mapping, build, connect, guard_destination, key, sha, utc
from runtime_inventory import PROFILE, active_mods, header, resolve

CORE = 'ZZ85 Verified baseline repairs'
STOCK = 'ZZ80 Consistent stock data'
RIHAD = 'ZZ Rihad authored fixes'
KATANA = 'ZZ84 Bounded katana support'


def main():
    ledger = BASE/'integration/applied_baseline_repairs.json'
    assert not ledger.exists(), 'Repairs already applied; inspect ledger instead of repeating'
    actions = json.loads((BASE/'integration/research/base_diagnostics/recommended_actions.json').read_text(encoding='utf-8'))
    mods = active_mods()
    events = []
    mappings = []
    used = set()
    for row in sorted(actions['exact_repair_candidates'], key=lambda r: r['pack'] != 'TuLED'):
        name = row['plugin']
        if key(name) in used:
            continue
        provider, original = resolve(name, mods)
        if original is None or sha(original) != row['source_sha256']:
            continue
        assert sha(row['candidate']) == row['candidate_sha256']
        mappings.append({'source': row['candidate'], 'destination': f'mods/{CORE}/{name}', 'storage': 'private'})
        events.append({'kind': 'exact_repair', 'plugin': name, 'previous_provider': provider, **row})
        used.add(key(name))
    for row in actions['optional_pose_registry_candidates']:
        provider, original = resolve(row['plugin'], mods)
        assert original and sha(original) == row['source_sha256']
        assert sha(row['path']) == row['candidate_sha256']
        mappings.append({'source': row['path'], 'destination': f"mods/{CORE}/{row['plugin']}", 'storage': 'private'})
        events.append({'kind': 'direct_hotkeys_pose_registry', 'previous_provider': provider, **row})
    source_db = sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro', uri=True)
    source_db.row_factory = sqlite3.Row
    for row0 in source_db.execute("select * from upstream_restoration_validation where pack='TuLED'"):
        row = dict(row0)
        name = row['plugin']
        provider, original = resolve(name, mods)
        assert original
        snapshot = BASE/'xedit_runs/TuLED/Data'/name
        assert sha(original) == sha(snapshot), f'Changed upstream restoration input: {name}'
        assert sha(row['candidate_path']) == row['sha256']
        if name.casefold() != 'rihadswordsmanset.esl' and sha(original) != row['sha256']:
            mappings.append({'source': row['candidate_path'], 'destination': f'mods/{CORE}/{name}', 'storage': 'private'})
        events.append({'kind': 'verified_upstream_restoration', 'previous_provider': provider, **row})
    rihad_provider, rihad_original = resolve('RihadSwordsmanSet.esl', mods)
    assert rihad_original
    c = connect()
    assert c.execute("select count(*) from files where status='planned'").fetchone()[0] == 0
    add_unit(c, 'consistent_stock_overlay', BASE/'repairs/consistent_stock/Data', 'mods/'+STOCK,
             'Previously full-context verified coherent five masters, eighteen archives and Strings; must override old cleaned masters')
    add_file_mapping(c, 'verified_baseline_repairs', mappings,
                     'SHA-guarded exact repairs, direct Poser Hotkeys variant and upstream record restoration')
    add_unit(c, 'rihad_author_assets', BASE/'repairs/upstream/Rihad-Xtudo-512617', 'mods/'+RIHAD,
             'Author-required master/assets, immediately above original Rihad and below existing generated mesh overrides')
    add_unit(c, 'bounded_katana_support', BASE/'repairs/TuLED/variants/oldfire_katana_support', 'mods/'+KATANA,
             'Previously native/full-VFS verified bounded missing macro and hit-animation support, no full library import')
    build(c)
    lines = (PROFILE/'modlist.txt').read_text(encoding='utf-8-sig').splitlines()
    assert '+'+rihad_provider in lines
    lines.insert(lines.index('+'+rihad_provider), '+'+RIHAD)
    disabled_ids = {mid for row in actions['optional_disable_plan'] for mid in row['disable_mod_ids']}
    baseline = json.loads((BASE/'integration/baseline_mods.json').read_text(encoding='utf-8'))
    disabled_dirs = {m['directory'] for m in baseline if m['id'] in disabled_ids}
    lines = ['-'+line[1:] if line.startswith('+') and line[1:] in disabled_dirs else line for line in lines]
    lines = ['+'+CORE, '+'+KATANA, '+'+STOCK] + lines
    (PROFILE/'modlist.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    disabled_plugins = {key(n) for n in actions['disabled_plugin_union']}
    for file_name in ['plugins.txt', 'loadorder.txt']:
        path = PROFILE/file_name
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        if file_name == 'plugins.txt':
            lines = [line[1:] if line.startswith('*') and key(line[1:]) in disabled_plugins else line for line in lines]
        assert not any(key(line.lstrip('*')) == 'god of war.esp' for line in lines)
        lines.append(('*' if file_name == 'plugins.txt' else '')+'God of War.esp')
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    # This generated-plugin translation contains stale output FormIDs, not source IDs.
    quarantined = []
    for name, folder in active_mods():
        directory = folder/'SKSE/Plugins/DynamicStringDistributor/Synthesis - Patch.esp'
        if not directory.is_dir():
            continue
        for file in list(directory.glob('*.json')):
            guard_destination(file)
            assert file.stat().st_nlink == 1
            destination = guard_destination(BASE/'UnifiedSkyrim'/'quarantine'/'old_synthesis_dsd'/name/file.name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            assert not destination.exists()
            digest = sha(file)
            os.replace(file, destination)
            rel = file.relative_to(TARGET).as_posix()
            c.execute("update files set status='quarantined',error=? where dest_key=?", (str(destination), key(rel)))
            quarantined.append({'original_integration_path': str(file), 'quarantined_path': str(destination), 'sha256': digest})
    # Remove write-through paths from the private BodySlide configuration.
    edits = []
    for name, folder in active_mods():
        file = folder/'CalienteTools/BodySlide/Config.xml'
        if not file.is_file():
            continue
        guard_destination(file)
        assert file.stat().st_nlink == 1
        before = sha(file)
        tree = ET.parse(file)
        root = tree.getroot()
        changes = {
            'GameDataPath': str(TARGET/'Game/Data')+'\\',
            'GameDataPaths/SkyrimSpecialEdition': str(TARGET/'Game/Data')+'\\',
            'OutputDataPath': str(TARGET/'outputs/BodySlideFresh')+'\\',
            'Anim/DefaultSkeletonReference': str(TARGET/'Game/Data/meshes/actors/character/character assets female/skeleton_female.nif'),
        }
        for xpath, value in changes.items():
            item = root.find(xpath)
            assert item is not None, xpath
            item.text = value
        tree.write(file, encoding='utf-8', xml_declaration=True)
        edits.append({'path': str(file), 'before_sha256': before, 'after_sha256': sha(file), 'changes': changes})
    c.commit()
    c.close()
    source_db.close()
    overrides_file = BASE/'integration/decision_overrides.json'
    overrides = json.loads(overrides_file.read_text(encoding='utf-8')) if overrides_file.exists() else []
    for row in actions['optional_disable_plan']:
        for mid in row['disable_mod_ids']:
            overrides.append({'mod_id': mid, 'decision': 'disabled_optional_mismatched_addon',
                              'category': 'verified_isolation', 'reason': row['reason'],
                              'evidence': 'integration/research/base_diagnostics/recommended_actions.json'})
    overrides_file.write_text(json.dumps(overrides, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    data = {'utc': utc(), 'repairs': events, 'disabled_plugins': sorted(disabled_plugins),
            'disabled_mod_ids': sorted(disabled_ids), 'rihad_layer_below_existing_output': rihad_provider,
            'coherent_stock_overlay': STOCK, 'bounded_support_layer': KATANA,
            'quarantined_dsd': quarantined, 'private_configuration_edits': edits,
            'pending': ['final master closure', 'new content', 'Synthesis rebuild', 'actual complete VFS probe', 'full-context xEdit']}
    ledger.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'repairs': len(events), 'disabled_plugins': len(disabled_plugins),
                      'quarantined_dsd': len(quarantined), 'private_config_edits': len(edits)}, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
