"""Materialize reviewed quest/follower sources; never edit original packs."""
import json
import sys
from pathlib import Path

from materialize import BASE, TARGET, SHARED_EXTENSIONS, add_file_mapping, build, connect, key, sha, utc
from runtime_inventory import PROFILE, header


def main():
    ledger=BASE/'integration/imported_features.json'
    assert not ledger.exists(), 'Already imported; inspect ledger'
    plan=json.loads((BASE/'integration/features_preflight.json').read_text('utf-8'))
    assert plan['base_collisions']==[], 'Every collided path needs an explicit per-file decision'
    mappings=[]
    for row in plan['mappings']:
        mappings.append({'source':row['source'],'destination':row['destination'],
                         'storage':'shared' if Path(row['relative']).suffix.casefold() in SHARED_EXTENSIONS else 'private'})
    repair_layer='ZZ81 Authored quest resource repairs'
    extra=[]
    for name in ['BenDoonSSE.seq','ForgottenMagic_Redone.seq']:
        source=BASE/'integration/research/remaining_base_semantics/seq_candidate/seq'/name
        expected={'BenDoonSSE.seq':'6bc70402','ForgottenMagic_Redone.seq':'620d0002630d0002'}[name]
        assert source.read_bytes().hex()==expected
        extra.append({'source':str(source),'relative':'seq/'+name,'reason':'xEdit fixed file FormIDs of exact enabled SGE quests; primary-source verified SEQ layout'})
    source=TARGET/'validation/moonstar_author_compile/output/MASLuckOfTheEmperorScript.pex'
    assert sha(source)=='a1f332888cbeef1905e104a8375aeaeae972d05b06eb45eaa997f71e53633e80'
    extra.append({'source':str(source),'relative':'scripts/'+source.name,
                  'reason':'Unmodified 421-byte included author PSC compiled successfully, PEX decompiled and properties/events/GetValue/SetValue independently checked'})
    for row in extra:
        mappings.append({'source':row['source'],'destination':f'mods/{repair_layer}/{row["relative"]}','storage':'private'})
    c=connect()
    add_file_mapping(c,'quest_follower_features',mappings,'14 selected plugins, 12 standalone roots, bounded SEQ and exact author-source script restoration')
    build(c)
    c.close()
    layers=list(dict.fromkeys(r['layer'] for r in plan['mods']))
    lines=(PROFILE/'modlist.txt').read_text('utf-8-sig').splitlines()
    lines.insert(0,'+'+repair_layer)
    lines.extend('+'+layer for layer in reversed(layers))
    (PROFILE/'modlist.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    master_rows=[r for r in plan['plugins'] if header(Path(r['selected_source']))['is_master']]
    regular_rows=[r for r in plan['plugins'] if r not in master_rows]
    for filename in ['plugins.txt','loadorder.txt']:
        file=PROFILE/filename
        lines=file.read_text('utf-8-sig').splitlines()
        # Glenmoril and Wyrmstooth are ESM-flagged and depend only on stock
        # masters. Put them before the existing Underground master so its
        # reviewed base NAVM is the patch-builder input winner.
        index=next(i for i,line in enumerate(lines) if key(line.lstrip('*'))=='akskyrimunderground.esm')
        lines[index:index]=[('*' if filename=='plugins.txt' else '')+r['name'] for r in master_rows]
        index=next((i for i,line in enumerate(lines) if key(line.lstrip('*'))=='synthesis - patch.esp'),len(lines))
        lines[index:index]=[('*' if filename=='plugins.txt' else '')+r['name'] for r in regular_rows]
        file.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    overrides=BASE/'integration/decision_overrides.json'
    decisions=json.loads(overrides.read_text('utf-8'))
    for row in plan['mods']:
        decisions.append({'mod_id':row['id'],'decision':'adopted_standalone_feature_resources',
                          'category':'quest_follower_feature','reason':row['feature']+'：採用獨立原作資源及明確選定插件；安裝選項與無關補丁未啟用。',
                          'directory':row['layer'],'evidence':'integration/imported_features.json'})
    for row in plan['plugins']:
        if row['source_mod_id'] not in {m['id'] for m in plan['mods']}:
            decisions.append({'mod_id':row['source_mod_id'],'decision':'partially_adopted_explicit_files',
                              'category':'selected_feature_patch','reason':'只採用已核對版本與master的補丁 '+row['name'],
                              'directory':row['layer'],'evidence':'integration/imported_features.json'})
    overrides.write_text(json.dumps(decisions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    features=[]
    for name in dict.fromkeys(r['feature'] for r in plan['plugins']):
        features.append({'feature':name,'plugins':[r for r in plan['plugins'] if r['feature']==name]})
    result={'utc':utc(),'status':'MATERIALIZED_PENDING_JOINT_COMPATIBILITY_AND_RESOURCE_VALIDATION',
            'features':features,'plugins':plan['plugins'],'layers':layers,'source_mods':plan['mods'],'resource_repairs':extra,
            'source_manifest_sha256':plan['source_sha256'],'preflight_sha256':sha(BASE/'integration/features_preflight.json'),
            'known_upstream_resource_issues':'See research/wyrmstooth_restoration and research/remaining_base_semantics; author records preserved, no invented script behavior.'}
    ledger.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'plugins':len(plan['plugins']),'mappings':len(mappings),'layers':len(layers)+1},indent=2))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
