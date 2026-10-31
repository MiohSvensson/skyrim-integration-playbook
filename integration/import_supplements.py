"""Install only the individually verified generated and author resource closure."""
import json
from pathlib import Path
from materialize import BASE,TARGET,add_file_mapping,build,connect,key,sha,utc

ledger=BASE/'integration/imported_supplements.json'
assert not ledger.exists()
source=BASE/'integration/research/supplemental_import/supplemental_import_plan.json'
assert sha(source)=='9098579e7698316259b1760d83dddbcec9f1acc939bc96521ce6283e4c736148'
plan=json.loads(source.read_text('utf-8'))
for row in plan['provenance']:assert sha(row['path'])==row['sha256']
layer='ZZ83 Verified generated item and quest assets'
rows=plan['imports'];assert len(rows)==148
assert len({key(r['destination_relative']) for r in rows})==148
mappings=[]
for row in rows:
    assert sha(row['source_path'])==row['source_sha256'],row['destination_relative']
    assert Path(row['source_path']).stat().st_size==row['size_bytes']
    relative=Path(row['destination_relative'])
    assert not relative.is_absolute() and '..' not in relative.parts
    mappings.append({'source':row['source_path'],'destination':f'mods/{layer}/{relative.as_posix()}',
                     'storage':'private','bytes':row['size_bytes']})
c=connect();add_file_mapping(c,'verified_supplemental_outputs',mappings,
    '94 NIF + 47 exact matching TRI with bounded stale binding fixes, 1 author effect texture, 3 author display meshes and 3 fixed-namespace SEQ')
build(c);c.close()
for profile in ['Unified Skyrim','Unified Build']:
    p=TARGET/'profiles'/profile/'modlist.txt'
    lines=p.read_text('utf-8-sig').splitlines();lines.insert(0,'+'+layer)
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
result={'utc':utc(),'status':'MATERIALIZED_PENDING_FINAL_VFS_GRAPH','layer':layer,
        'plan':str(source),'plan_sha256':sha(source),'files':rows,'counts':plan['counts']}
ledger.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(rows),'private_bytes':sum(r['size_bytes'] for r in rows)},indent=2))
