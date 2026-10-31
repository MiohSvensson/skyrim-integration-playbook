"""Freeze reviewed standalone roots and audit path collisions before importing."""
import json
import os
import sys
from pathlib import Path

from materialize import BASE, TARGET, key, lp, sha, utc
from runtime_inventory import active_mods, resolve


def main():
    research = BASE/'integration/research/plugin_integration'
    file = research/'feature_builder_manifest.json'
    original = json.loads(file.read_text('utf-8'))
    frozen = BASE/'integration/selection_snapshots'/(sha(file)[:12]+'_'+file.name)
    if not frozen.exists():
        frozen.write_bytes(file.read_bytes())
    allowed = {'meshes','textures','scripts','source','sound','seq','video','interface','strings','skse','music','grass'}
    mappings, plugins, mods, excluded = [], [], [], []
    for ordinal, feature in enumerate(original['features']+original['followers'], 1):
        layer = f'F{ordinal:02d} '+feature['feature'].replace('/', '-').replace(':','')[:66]
        selected = feature['plugins']+feature.get('optional_selected_patches', [])
        selected_names = {key(r['name']) for r in selected}
        for mod in feature['mods']:
            root = Path(mod['path'])
            mods.append({'feature': feature['feature'], 'id': mod['id'], 'source': str(root), 'layer': layer})
            for walk_root, dirs, files in os.walk(lp(root)):
                current = Path(walk_root.removeprefix('\\\\?\\'))
                rel_dir = current.relative_to(root)
                if not rel_dir.parts:
                    skipped = [d for d in dirs if key(d) not in allowed]
                    excluded.extend({'source': str(current/d), 'reason':'non-runtime installer/docs/alternative directory'} for d in skipped)
                    dirs[:] = [d for d in dirs if key(d) in allowed]
                for name in files:
                    path = current/name
                    relative = path.relative_to(root)
                    if name.casefold().endswith('.mohidden') or key(name) == 'meta.ini':
                        continue
                    if path.suffix.casefold() in ('.esp','.esm','.esl'):
                        continue  # exact source winner selected separately below
                    if len(relative.parts)==1 and path.suffix.casefold() not in ('.bsa','.ini'):
                        continue
                    mappings.append({'source':str(path), 'relative':relative.as_posix(), 'destination':f'mods/{layer}/{relative.as_posix()}',
                                     'mod_id':mod['id'], 'feature':feature['feature']})
        for row in selected:
            assert sha(row['source_path']) == row['sha256'], row['name']
            source = row['source_path']
            replacement = row.get('validated_replacement')
            if replacement:
                source = replacement['candidate']
                assert sha(source) == replacement['candidate_sha256']
            if key(row['name']) == 'moonandstar_mas.esp':
                source = str(research/'moonstar_cleanup_candidate'/row['name'])
                assert sha(source) == '6182033b97b4fd106f2d8ecfe8174defef1788ca4e9f4dc059534b8d57ffb90e'
            assert resolve(row['name'])[1] is None, row['name']
            plugins.append(row | {'selected_source':source, 'selected_sha256':sha(source),'layer':layer,'feature':feature['feature']})
            mappings.append({'source':source,'relative':row['name'],'destination':f'mods/{layer}/{row["name"]}',
                             'mod_id':row['source_mod_id'],'feature':feature['feature']})
    # Duplicate source layers may contain the same runtime path; only the nominated
    # plugin is special. Other conflicting authored files require an explicit choice.
    by_dest = {}
    translation_overrides = []
    for row in mappings:
        k=key(row['destination'])
        if k in by_dest:
            old = by_dest[k]
            if sha(old['source']) != sha(row['source']):
                if old['mod_id']==1163 and row['mod_id']==59 and key(row['relative'])=='interface/translations/glenmoril_english.txt':
                    translation_overrides.append({'old':old,'selected':row,'reason':'Nominated original English translation follows GLENMORIL source resources'})
                else:
                    raise ValueError(f'Unreviewed within-feature collision: {k}')
        by_dest[k]=row
    mappings=list(by_dest.values())
    collisions=[]
    base_mods=active_mods()
    requested={key(r['relative']) for r in mappings}
    base_winners={}
    for provider,folder in base_mods+[('Game/Data',TARGET/'Game/Data')]:
        for walk_root,dirs,files in os.walk(lp(folder)):
            current=Path(walk_root.removeprefix('\\\\?\\'))
            for name in files:
                path=current/name
                relative=key(path.relative_to(folder).as_posix())
                if relative in requested:
                    base_winners.setdefault(relative,(provider,path))
    print(json.dumps({'phase':'collision_hashes','candidate_paths':len(mappings),'base_collision_count':len(base_winners)}),flush=True)
    for row in mappings:
        provider, winner=base_winners.get(key(row['relative']),(None,None))
        if winner:
            collisions.append({'relative':row['relative'],'feature':row['feature'],'source':row['source'],
                               'source_sha256':sha(row['source']),'base_provider':provider,'base_path':str(winner),
                               'base_sha256':sha(winner),'same':sha(row['source'])==sha(winner),
                               'proposed_action':'keep_base_winner_and_validate_feature_resource_binding'})
    result={'utc':utc(),'source_manifest':str(frozen),'source_sha256':sha(frozen),'mods':mods,'plugins':plugins,
            'mappings':mappings,'base_collisions':collisions,'translation_overrides':translation_overrides,'excluded_paths':excluded,'status':'PLANNED_PENDING_COLLISION_REVIEW'}
    (BASE/'integration/features_preflight.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'mods':len(mods),'plugins':len(plugins),'mapped_files':len(mappings),'collisions':len(collisions),
                      'different_collision_paths':[r['relative'] for r in collisions if not r['same']]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
