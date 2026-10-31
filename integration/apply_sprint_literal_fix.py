"""Verify and optionally stage the exact authored Sprint event spelling repair."""
import argparse
import json
import os
import struct
from pathlib import Path

from materialize import BASE, TARGET, add_file_mapping, connect, guard_destination, key, make_private, sha, utc

ap = argparse.ArgumentParser()
ap.add_argument('--install', action='store_true')
args = ap.parse_args()
root = BASE/'integration/research/feature_generation/sprint_event_candidate'
manifest_path = root/'manifest.json'
m = json.loads(manifest_path.read_text('utf-8'))
original = root/'original/Scripts/GHSprintSpellScript.pex'
candidate = root/'candidate/Scripts/GHSprintSpellScript.pex'
assert sha(original) == m['source_sha256'] == '03cb865de8b28696f254fcd01cc3849e076c09d5cc05015f7b36207bc30d0d67'
assert sha(candidate) == m['candidate_sha256'] == 'ed6175d49a9ded5c9bc02f1c24516c777481db209ddaa794c990de4b397f698e'
a, b = original.read_bytes(), candidate.read_bytes()
assert len(a) == 1813 and len(b) == 1812
offset = 606
old = b'ShoutSprintLongStart\t'
assert struct.unpack_from('>H', a, offset)[0] == len(old) == 21
assert a[offset+2:offset+2+len(old)] == old
expected = a[:offset]+struct.pack('>H', 20)+old[:-1]+a[offset+2+len(old):]
assert b == expected, 'Change extends beyond the single length-prefixed literal'
assert a[810:] == b[809:], 'PEX debug/properties/state/function/instruction body differs'
attachment = m['typed_VMAD_attachment_proof']
assert sha(attachment['path']) == attachment['sha256']
proof = json.loads(Path(attachment['path']).read_text('utf-8'))
assert len(proof['consumers']) == 1
consumer = proof['consumers'][0]
assert consumer['canonical'] == 'glenmoril.esm|01497A' and consumer['script_attached'] is True
assert sha(consumer['plugin_path']) == consumer['plugin_sha256']
assert sha(m['source']['archive_physical']) == m['source']['archive_sha256']
relative = Path('mods/ZZ86 Verified stale script assignments/Scripts/GHSprintSpellScript.pex')
destination = guard_destination(TARGET/relative)
result = {'utc': utc(), 'status': 'INDEPENDENT_EXACT_BYTE_REPAIR_VERIFIED',
          'manifest': str(manifest_path), 'manifest_sha256': sha(manifest_path),
          'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
          'changes': 'Exactly one string-table literal loses its final TAB; its BE ushort length decreases by one. Every other byte is preserved.',
          'native_execution_tested': False, 'installed': False}
if args.install:
    receipt = BASE/'integration/sprint_literal_fix.json'
    assert not receipt.exists() and not destination.exists()
    for name in ['Unified Build', 'Unified Skyrim']:
        assert '+ZZ86 Verified stale script assignments' in (TARGET/'profiles'/name/'modlist.txt').read_text('utf-8-sig').splitlines()
    c = connect()
    try:
        add_file_mapping(c, 'verified_glen_sprint_event_literal',
                         [{'source': str(candidate), 'destination': relative.as_posix(), 'storage': 'private', 'bytes': 1812}],
                         'Exact source-backed Sprint animation event literal TAB removal; complete byte and official author PEX parser proof')
        row = c.execute('select * from files where unit_id=?', ('verified_glen_sprint_event_literal',)).fetchone()
        destination.parent.mkdir(parents=True, exist_ok=True)
        digest = make_private(candidate, destination, os.stat(candidate))
        assert digest == m['candidate_sha256'] and destination.stat().st_nlink == 1
        c.execute("update files set status='materialized',sha256=? where id=?", (digest, row['id']))
        result.update(installed=True, status='MATERIALIZED_PENDING_FINAL_VFS', destination=str(destination))
        c.execute('insert into events values(?,?,?)', (utc(), 'verified_sprint_literal_fix', json.dumps(result)))
        c.commit()
        receipt.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    finally:
        c.close()
else:
    (root/'root_independent_byte_review.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result, indent=2))
