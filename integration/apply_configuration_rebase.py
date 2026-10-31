"""Apply the reviewed four-value private configuration migration, atomically."""
import json
import os
from pathlib import Path
import runtime_inventory as runtime
from materialize import BASE, TARGET, add_file_mapping, connect, guard_destination, key, make_private, sha, utc

plan_path=BASE/'integration/research/catalog_decision_review/configuration_rebase/config_rebase_plan.json'
assert sha(plan_path)=='89ed07c5d29abe5315ca00645e3fe84b6df0f0fc908d7fc5108b5f46f4492360'
plan=json.loads(plan_path.read_text('utf-8'))
receipt=BASE/'integration/configuration_rebase_applied.json'
assert not receipt.exists()
operations=plan['operations'];assert len(operations)==2
for p in plan['profile_preflight']:
    profile=Path(p['profile'])
    assert sha(profile/'modlist.txt')==p['modlist_sha256']
    assert sha(p['current_winner'])==p['current_winner_sha256']
for proof in plan['original_control_manifest']['checks']:
    assert sha(proof['path'])==proof['expected_sha256']
for op in operations:
    candidate=op['staged_candidate'];source=op.get('before',op.get('source_read_only'))
    assert sha(source['path'])==source['sha256'] and Path(source['path']).stat().st_nlink==1
    assert sha(candidate['path'])==candidate['sha256'] and Path(candidate['path']).stat().st_nlink==1
    raw=Path(source['path']).read_bytes()
    for edit in op['line_replacements']:
        old,new=bytes.fromhex(edit['old_line_bytes_hex']),bytes.fromhex(edit['new_line_bytes_hex'])
        assert raw.count(old)==1
        raw=raw.replace(old,new,1)
    assert raw==Path(candidate['path']).read_bytes(), 'Unexpected configuration changes'
    destination=guard_destination(op['destination'])
    if op['kind']=='new_private_overlay_file':assert not destination.exists()
    else:assert destination==Path(source['path'])
    if op.get('preset_dependency'):assert sha(op['preset_dependency']['path'])==op['preset_dependency']['sha256']
for directory in plan['directory_creation_list']:
    guard_destination(directory['path']).mkdir(parents=True,exist_ok=True)
root_op,overlay_op=operations
root_dest,overlay_dest=Path(root_op['destination']),Path(overlay_op['destination'])
backup=guard_destination(root_op['backup']['path'])
if backup.exists():
    assert sha(backup)==root_op['before']['sha256'] and backup.stat().st_nlink==1
else:make_private(root_dest,backup,os.stat(root_dest))
unit='verified_private_configuration_rebase'
c=connect();root_changed=False;overlay_created=False
try:
    old_row=dict(c.execute('select f.*,u.source from files f join units u on f.unit_id=u.id where f.dest_key=?',(key(root_dest.relative_to(TARGET)),)).fetchone())
    add_file_mapping(c,unit,[{'source':overlay_op['staged_candidate']['path'],'destination':overlay_dest.relative_to(TARGET).as_posix(),'storage':'private'}], 'Exact private CrashLogger cache/log directory migration')
    for op in operations:
        candidate=Path(op['staged_candidate']['path']);dest=Path(op['destination'])
        make_private(candidate,dest,os.stat(candidate))
        if dest==root_dest:root_changed=True
        else:overlay_created=True
        assert sha(dest)==op['staged_candidate']['sha256'] and dest.stat().st_nlink==1
    for name in ['Unified Skyrim','Unified Build']:
        runtime.PROFILE=TARGET/'profiles'/name
        provider,winner=runtime.resolve('SKSE/Plugins/CrashLogger.ini')
        assert provider=='ZZ86 Verified stale script assignments' and winner.resolve()==overlay_dest.resolve()
    assert sha(overlay_op['source_read_only']['path'])==overlay_op['source_read_only']['sha256']
    for proof in plan['original_control_manifest']['checks']:assert sha(proof['path'])==proof['expected_sha256']
    candidate=Path(root_op['staged_candidate']['path']);st=candidate.stat()
    source_root=Path(old_row['source']).resolve()
    assert candidate.resolve().is_relative_to(source_root)
    c.execute('update files set relative_path=?,size_bytes=?,mtime_ns=?,sha256=? where id=?',
              (candidate.relative_to(source_root).as_posix(),st.st_size,st.st_mtime_ns,sha(candidate),old_row['id']))
    c.execute("update files set status='materialized',sha256=? where unit_id=?",(sha(overlay_dest),unit))
    result={'utc':utc(),'status':'APPLIED_PRIVATE_FOUR_VALUE_REBASE','plan':str(plan_path),'plan_sha256':sha(plan_path),
            'destinations':[{'path':op['destination'],'sha256':sha(op['destination']),'nlink':Path(op['destination']).stat().st_nlink} for op in operations],
            'root_backup':str(backup),'previous_root_journal_mapping':old_row,'original_controls_unchanged':145,'game_started':False}
    c.execute('insert into events values(?,?,?)',(utc(),'private_configuration_rebase',json.dumps(result)))
    c.commit()
    receipt.write_text(json.dumps(result,indent=2)+'\n','utf-8')
except BaseException:
    c.rollback()
    if root_changed:make_private(backup,root_dest,os.stat(backup))
    if overlay_created:
        assert sha(overlay_dest)==overlay_op['staged_candidate']['sha256']
        guard_destination(overlay_dest).unlink()
    c.execute('delete from files where unit_id=?',(unit,));c.execute('delete from units where id=?',(unit,));c.commit()
    raise
finally:c.close()
print(json.dumps({'status':result['status'],'files':len(operations),'values':4,'original_controls_unchanged':145},indent=2))
