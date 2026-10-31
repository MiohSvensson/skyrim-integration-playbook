"""Keep all authored FormIDs; clear the invalid light flag on one new item plugin."""
import json
import os
import struct
from pathlib import Path

from materialize import BASE, TARGET, guard_destination, sha, utc
from runtime_inventory import resolve

name = '(lilyrim)lingzhuyinyue.esp'
ledger = BASE/'integration/lingzhuyinyue_light_flag_fix.json'
assert not ledger.exists(), 'Already repaired'
gear = json.loads((BASE/'integration/imported_equipment.json').read_text(encoding='utf-8'))
source = next(r for r in gear['plugins'] if r['name'] == name)
provider, path = resolve(name)
guard_destination(path)
assert path.stat().st_nlink == 1 and sha(path) == source['selected_sha256']
before = path.read_bytes()
assert before[:4] == b'TES4'
flags = struct.unpack_from('<I', before, 8)[0]
assert flags & 0x200
after = bytearray(before)
struct.pack_into('<I', after, 8, flags & ~0x200)
changed_bytes = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
assert changed_bytes == [9]
assert before[:8] == after[:8] and before[12:] == after[12:]
temp = guard_destination(path.with_name(path.name+'.flag-repair'))
assert not temp.exists()
temp.write_bytes(after)
os.replace(temp, path)
assert path.stat().st_nlink == 1
record = {'utc': utc(), 'plugin': name, 'path': str(path), 'provider': provider,
          'source_sha256': source['selected_sha256'], 'candidate_sha256': sha(path),
          'old_header_flags': flags, 'new_header_flags': flags & ~0x200,
          'changed_byte_offsets': changed_bytes, 'all_record_payloads_and_FormIDs_unchanged': True,
          'reason': 'Eight authored own ObjectIDs 0012CC-0012D3 exceed the light 12-bit range. Use one full slot; no compaction or renumbering.',
          'failure_evidence': str(TARGET/'validation/equipment_stage/result.json'),
          'status': 'CANDIDATE_PENDING_FULL_CONTEXT_RECHECK'}
ledger.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(record, ensure_ascii=False, indent=2))
