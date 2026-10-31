"""Remove two assignments not declared by the exact selected compiled script."""
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
sys.path.insert(0, str(OUT.parent / 'plugin_integration'))
import plugin_binary
from moonstar_vmad import vmad


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    base = json.loads((OUT.parent / 'base_diagnostics/base_diagnostics.json').read_text(encoding='utf-8'))
    selected = next(r['selected_provider'] for r in base['per_plugin'] if r['plugin'] == 'GostedDimensionalRift.esp')
    source = Path(selected['mod_path']) / selected['relative_path']
    assert digest(source) == selected['sha256']
    pex = OUT / 'scripts/archive_189/pex/gostteleportlocked.pex'
    asm = OUT / 'scripts/archive_189/asm/gostteleportlocked.pas'
    psc = OUT / 'scripts/archive_189/psc/gostteleportlocked.psc'
    assert digest(pex) == '5ed6d4988d8a17d9c7d2a279fa913462c1df880215ef5f089a589a8f7a8f38f6'
    absent = {'dimriftplayerangleyg': 0x2F2640, 'dimriftplayeranglezg': 0x2F2641}
    for name in absent:
        assert name.encode() not in pex.read_bytes().lower()
        assert not re.search(r'\b' + name + r'\b', asm.read_text(encoding='utf-8'), re.I)
        assert not re.search(r'\b' + name + r'\b', psc.read_text(encoding='utf-8'), re.I)
    db = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    loose = db.execute("select mod_id,relative_path from files where path_key='scripts/gostteleportlocked.pex' and virtual_candidate=1").fetchall()
    assert not loose
    variants = db.execute("select archive_id,path_key,sha256 from bsa_entries where path_key='scripts/gostteleportlocked.pex'").fetchall()
    assert variants and all(r[2] == digest(pex) for r in variants)
    masters, before = plugin_binary.read(source)
    expected_fid = (len(masters) << 24) | 0x2ED53E
    target_record = next(r for r in before if r['fid'] == expected_fid)
    old = dict(target_record['fields'])['VMAD']
    decoded = vmad(old)
    script = next(s for s in decoded['scripts'] if s['name'].casefold() == 'gostteleportlocked')
    matches = [p for p in script['properties'] if p['name'].casefold() in absent]
    assert len(matches) == 2
    proof = []
    for p in matches:
        assert p['type'] == 1 and int(p['value']['form_id'], 16) == (len(masters) << 24) | absent[p['name'].casefold()]
        proof.append({'property': p['name'], 'missing_raw_form_id': p['value']['form_id'],
                      'start_offset': p['start_offset'], 'end_offset': p['end_offset'],
                      'removed_bytes_hex': old[p['start_offset']:p['end_offset']].hex()})
    new = bytearray(old)
    struct.pack_into('<H', new, script['property_count_offset'], script['property_count'] - 2)
    for p in sorted(matches, key=lambda p: p['start_offset'], reverse=True): del new[p['start_offset']:p['end_offset']]
    new = bytes(new)
    after_vmad = vmad(new)
    assert decoded['trailing_fragment_bytes'] == after_vmad['trailing_fragment_bytes']
    assert old[decoded['parsed_main_bytes']:] == new[after_vmad['parsed_main_bytes']:]
    changes = []
    def change(r):
        if r['fid'] != expected_fid: return None
        assert r['sig'] == 'REFR'
        fields = [(t, new if t == 'VMAD' else v) for t, v in r['fields']]
        changes.append(r['fid'])
        return r['fid'], fields
    target = OUT / 'rift_stale_property_candidate/GostedDimensionalRift.esp'
    plugin_binary.rewrite(source, target, change)
    after_masters, after = plugin_binary.read(target)
    assert after_masters == masters and len(before) == len(after) and changes == [expected_fid]
    for a, b in zip(before, after):
        assert (a['sig'], a['fid'], a['flags']) == (b['sig'], b['fid'], b['flags'])
        expected = [(t, new if a['fid'] == expected_fid and t == 'VMAD' else v) for t, v in a['fields']]
        assert b['fields'] == expected
    report = {'candidate': str(target), 'candidate_sha256': digest(target), 'source': str(source), 'source_sha256': digest(source),
              'record': f'GostedDimensionalRift.esp|2ED53E', 'raw_form_id': f'{expected_fid:08X}',
              'records_including_header': len(before), 'masters_unchanged': masters, 'removed': proof,
              'property_count_offset': script['property_count_offset'], 'property_count_before': script['property_count'], 'property_count_after': script['property_count'] - 2,
              'old_vmad_hex': old.hex(), 'new_vmad_hex': new.hex(), 'pex': str(pex), 'pex_sha256': digest(pex),
              'assembly': str(asm), 'decompiled': str(psc), 'known_archive_variants': variants, 'loose_overrides': loose,
              'unchanged_proof': 'All IDs/flags/masters and every other decompressed ordered subrecord match exactly. Only the two named property byte ranges and exact script property count change; VMAD fragment tail unchanged.',
              'retained': ['DimRiftPlayerAngleXG is declared and SetValue consumed by actual PEX', 'AngleMarker assignment is resolved but unused; preserved',
                           'REFR|1B3A4B refToDisable -> absent own2DE1E6 remains; declared/consumed ObjectReference property, not safely clearable'],
              'guard': 'Recheck final VFS gostteleportlocked.pex SHA equals this exact selected script and original plugin SHA matches source before applying only to integration copy.',
              'xedit_status': 'NOT ACTIVATED. Pending native/full final-VFS validation; expected historical missing VMAD count 3 -> 1, not runtime validated.'}
    (OUT / 'rift_stale_property_evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Rift candidate: two stale VMAD properties only;', len(before), 'records preserved;', report['candidate_sha256'])


if __name__ == '__main__': main()
