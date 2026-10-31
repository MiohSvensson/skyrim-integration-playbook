"""Read-only consumers and fragment-tail audit for newly found source gaps."""
from pathlib import Path
import collections
import hashlib
import json
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(OUT.parent / 'feature_conflicts'))
from analyze_fields import scan, formvalue, canonical
from vmad_audit import parse_vmad


def describe(r):
    return {'record': formvalue(r, r['fid']), 'signature': r['signature'], 'flags': f'{r["flags"]:08X}',
            'edid': next((v.rstrip(b'\0').decode('utf-8', 'replace') for t, v in r['fields'] if t == 'EDID'), ''),
            'groups': r['groups'], 'raw_subrecords': [{'tag': t, 'hex': v.hex()} for t, v in r['fields']],
            'canonical': canonical(r), 'offset': r['offset']}


def fragment_tail(rec):
    vm = parse_vmad(dict(rec['fields'])['VMAD'], lambda fid: formvalue(rec, fid))
    data = bytes.fromhex(vm['tail_hex'])
    pos = 0
    def read(fmt):
        nonlocal pos
        vals = struct.unpack_from('<' + fmt, data, pos); pos += struct.calcsize('<' + fmt)
        return vals[0] if len(vals) == 1 else vals
    def string():
        nonlocal pos
        n = read('H'); v = data[pos:pos+n]; pos += n
        assert len(v) == n
        return v.decode('utf-8')
    version, flags = read('BB')
    filename = string()
    names = ('OnBegin', 'OnEnd') if rec['signature'] == 'INFO' else ('OnBegin', 'OnEnd', 'OnChange')
    parts = []
    for bit, name in enumerate(names):
        if flags & (1 << bit):
            fragment_version = read('B')
            parts.append({'event': name, 'version': fragment_version, 'script': string(), 'function': string()})
    assert pos == len(data)
    return {'vmad_scripts': vm['scripts'], 'tail_version': version, 'tail_flags': flags,
            'filename': filename, 'fragments': parts, 'raw_tail_hex': data.hex(),
            'note': 'Fragment_0 is an actual named function, not proof of an empty/dormant function.'}


def raw_candidates(records, target):
    needle = struct.pack('<I', target['fid'])
    out = []
    for r in records.values():
        if r is target: continue
        for tag, value in r['fields']:
            off = value.find(needle)
            while off >= 0:
                out.append({'record': formvalue(r, r['fid']), 'signature': r['signature'], 'tag': tag, 'offset': off})
                off = value.find(needle, off + 1)
    return out


def main():
    feature = json.loads((OUT.parent / 'feature_conflicts/raw_field_comparison.json').read_text(encoding='utf-8'))['features']
    inputs = {f['plugin']: f for f in feature}
    answer = {'scope': 'Exact selected source records, known typed consumers, full source-file byte candidate search. External dynamic scripts and game execution are not proved by absence of literal bytes.', 'plugins': []}
    for name in ('Wyrmstooth.esp', 'BenDoonSSE.esp', '[longshou]UF6.esp'):
        f = inputs[name]
        records, counts, own = scan(f['path'])
        info = {'plugin': name, 'path': f['path'], 'sha256': hashlib.sha256(Path(f['path']).read_bytes()).hexdigest(), 'record_counts': counts}
        if name == 'Wyrmstooth.esp':
            qkey = ('wyrmstooth.esp', 0x3943A0)
            relevant = [records[k] for k in (('wyrmstooth.esp', 0x3943AB), ('wyrmstooth.esp', 0x3943AA), qkey, ('wyrmstooth.esp', 0x3920D5), ('wyrmstooth.esp', 0x8BFAE2))]
            info['missing_fragment'] = describe(relevant[0]) | {'fragment_tail': fragment_tail(relevant[0])}
            info['quest_context'] = [describe(r) for r in relevant[1:4]]
            topics = []
            for k, r in records.items():
                if r['signature'] == 'DIAL' and any(t == 'QNAM' and formvalue(r, struct.unpack('<I', v)[0]) == 'wyrmstooth.esp|3943A0' for t, v in r['fields']):
                    children = [a for a in records.values() if a['signature'] == 'INFO' and any(typ == 7 and tuple(label) == k for typ, label in a['groups'])]
                    topics.append({'topic': describe(r), 'responses': [describe(a) | ({'fragment_tail': fragment_tail(a)} if 'VMAD' in dict(a['fields']) else {}) for a in children]})
            info['all_same_quest_topics'] = topics
            sound = relevant[-1]
            info['missing_crickets'] = describe(sound) | {'raw_candidates': raw_candidates(records, sound), 'typed_region_consumers': []}
            for r in records.values():
                if r['signature'] != 'REGN': continue
                for tag, data in r['fields']:
                    if tag != 'RDSA': continue
                    assert len(data) % 12 == 0
                    for i in range(0, len(data), 12):
                        fid, flags, chance = struct.unpack_from('<IIf', data, i)
                        if formvalue(r, fid) == 'wyrmstooth.esp|8BFAE2':
                            key = formvalue(r, r['fid'])
                            cells = [formvalue(a, a['fid']) for a in records.values() if a['signature'] == 'CELL'
                                     and any(t == 'XCLR' and any(formvalue(a, x[0]) == key for x in struct.iter_unpack('<I', v)) for t, v in a['fields'])]
                            info['missing_crickets']['typed_region_consumers'].append({'region': key, 'edid': describe(r)['edid'],
                                'RDSA_index': i // 12, 'RDSA_count': len(data)//12, 'flags': flags, 'chance': chance,
                                'world': [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'WNAM'],
                                'region_polygon_subrecords': {t: len(v) for t, v in r['fields'] if t in ('RPLI', 'RPLD')},
                                'CELL_XCLR_consumers': cells})
        elif name == 'BenDoonSSE.esp':
            r = records[('bendoonsse.esp', 0x4A1A3)]
            info['missing_package_fragment'] = describe(r) | {'fragment_tail': fragment_tail(r), 'whole_source_raw_reference_candidates': raw_candidates(records, r)}
            # All PKID and alias ALPC values are unambiguous typed package links.
            typed = []
            for a in records.values():
                for t, v in a['fields']:
                    if t in ('PKID', 'ALPC') and len(v) == 4 and formvalue(a, struct.unpack('<I', v)[0]) == 'bendoonsse.esp|04A1A3':
                        typed.append({'record': formvalue(a, a['fid']), 'signature': a['signature'], 'field': t})
            info['missing_package_fragment']['typed_PKID_ALPC_consumers'] = typed
        else:
            rows = []
            for obj in range(0x801, 0x806):
                r = records[('[longshou]uf6.esp', obj)]
                placements = []
                for a in records.values():
                    if a['signature'] in ('REFR', 'ACHR'):
                        for t, v in a['fields']:
                            if t == 'NAME' and len(v) == 4 and formvalue(a, struct.unpack('<I', v)[0]) == formvalue(r, r['fid']):
                                placements.append(describe(a))
                rows.append(describe(r) | {'typed_NAME_placements': placements, 'whole_source_raw_reference_candidates': raw_candidates(records, r)})
            info['missing_furniture'] = rows
            info['attached_VMAD_count'] = sum(t == 'VMAD' for r in records.values() for t, v in r['fields'])
        answer['plugins'].append(info)
    c = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    answer['external_master_dependents'] = {}
    for name in ('bendoonsse.esp', '[longshou]uf6.esp'):
        answer['external_master_dependents'][name] = [dict(zip(('plugin', 'mod_id', 'mod', 'mod_path'), r)) for r in c.execute('''select p.name,m.id,m.name,m.path from plugin_masters pm join plugin_files p on p.id=pm.plugin_id join mods m on m.id=p.mod_id where pm.master_key=?''', (name,))]
    (OUT / 'feature_missing_consumers.json').write_text(json.dumps(answer, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Consumer evidence written:', [(r['plugin'], sum(r['record_counts'].values())) for r in answer['plugins']])


if __name__ == '__main__': main()
