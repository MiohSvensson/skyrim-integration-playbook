"""One proven stale-property cleanup and a disposable private producer sidecar."""
import json,sqlite3
from pathlib import Path
from materialize import BASE,TARGET,add_file_mapping,build,connect,sha,utc
from runtime_inventory import resolve

ledger=BASE/'integration/semantic_cleanup_and_writer.json'
assert not ledger.exists()
evidence=BASE/'integration/research/remaining_base_semantics/rift_stale_property_evidence.json'
rift=json.loads(evidence.read_text('utf-8'))
provider,plugin=resolve('GostedDimensionalRift.esp')
assert sha(plugin)==rift['source_sha256']
assert sha(rift['candidate'])==rift['candidate_sha256']
assert resolve('scripts/gostteleportlocked.pex')[1] is None
archive_provider,archive=resolve('GostedDimensionalRift.bsa')
assert sha(archive)=='b158a064422fa2807fbf0f41180d3a68c8f08dd8cb71da823111fa2e48f81f52'
c=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
variants=c.execute("select distinct sha256 from bsa_entries where path_key='scripts/gostteleportlocked.pex'").fetchall()
assert variants==[(rift['pex_sha256'],)]
c.close()
relative='skse/plugins/experience/races/GeneratedExperiencePatch.ini'
side_provider,sidecar=resolve(relative)
assert sidecar is not None and sidecar.stat().st_nlink==1
rift_layer='ZZ86 Verified stale script assignments'
writer_layer='ZZ88 Private synthesis sidecar workspace'
rows=[{'source':rift['candidate'],'destination':f'mods/{rift_layer}/GostedDimensionalRift.esp','storage':'private'},
      {'source':str(sidecar),'destination':f'mods/{writer_layer}/{relative}','storage':'private'}]
c=connect();add_file_mapping(c,'bounded_semantic_cleanup_and_private_writer',rows,
    'Only two undeclared Rift VMAD properties removed; exact author PEX guard. Independent disposable Synthesis INI to contain its deliberate output write.')
build(c);c.close()
for name in ['Unified Skyrim','Unified Build']:
    p=TARGET/'profiles'/name/'modlist.txt'
    lines=p.read_text('utf-8-sig').splitlines()
    lines[:0]=['+'+writer_layer,'+'+rift_layer]
    p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
result={'utc':utc(),'status':'MATERIALIZED_PENDING_FINAL_NATIVE_AND_VFS_VALIDATION',
        'rift':{'layer':rift_layer,'source_provider':provider,'before_sha256':rift['source_sha256'],
                'after_sha256':rift['candidate_sha256'],'evidence':str(evidence),'evidence_sha256':sha(evidence),
                'script_sha256':rift['pex_sha256'],'script_archive_provider':archive_provider,'script_archive_sha256':sha(archive)},
        'private_sidecar':{'layer':writer_layer,'path':str(TARGET/'mods'/writer_layer/relative),
                           'source_provider':side_provider,'initial_sha256':sha(sidecar),
                           'final_action':'Disable this workspace layer after capturing and installing the final generated sidecar; preserve its small rollback evidence.'}}
ledger.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'rift_sha256':rift['candidate_sha256'],'private_sidecar':result['private_sidecar']['path']},ensure_ascii=False))
