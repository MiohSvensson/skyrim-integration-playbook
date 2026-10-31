"""Exact remaining base records, compiled consumers and cross-pack evidence."""
from pathlib import Path
import collections
import hashlib
import json
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(OUT.parent / 'feature_conflicts'))
from analyze_fields import scan, formvalue, canonical
from vmad_audit import parse_vmad


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(r):
    return {'record': formvalue(r, r['fid']), 'signature': r['signature'], 'flags': f'{r["flags"]:08X}',
            'edid': next((v.rstrip(b'\0').decode('utf-8', 'replace') for t, v in r['fields'] if t == 'EDID'), ''),
            'groups': r['groups']}


def vmad_refs(r):
    return [p for t, v in r['fields'] if t == 'VMAD' for p in parse_vmad(v, lambda fid: formvalue(r, fid))['references']]


def target_records(item, records):
    result = []
    for f in item['fields']:
        m = re.search(r'\[(\w+):([0-9A-F]{8})\]', f['record'])
        if not m: continue
        sig, raw = m.groups()
        obj = int(raw[-3:] if raw.startswith('FE') else raw[-6:], 16)
        candidates = [r for k, r in records.items() if k[1] == obj and r['signature'] == sig]
        if len(candidates) != 1:
            prefix = f['record'].split(' "')[0].split(' [')[0]
            candidates = [r for r in candidates if label(r)['edid'] == prefix]
        assert len(candidates) == 1, (item['plugin'], f['record'], candidates)
        if candidates[0] not in result: result.append(candidates[0])
    return result


def main():
    base = json.loads((OUT.parent / 'base_diagnostics/base_diagnostics.json').read_text(encoding='utf-8'))
    selected = {r['plugin']: r for r in base['per_plugin']}
    db = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    index = sqlite3.connect((BASE / 'baseline/plugin_records.sqlite').as_uri() + '?mode=ro', uri=True)
    ids = sqlite3.connect((BASE / 'baseline/record_identifiers.sqlite').as_uri() + '?mode=ro', uri=True)
    missing = []
    for name, obj in (('darkend.esp', 0xAA0E), ('darkend.esp', 0x19D5B), ('legacyofthedragonborn.esm', 0x9D5B81)):
        hits = index.execute('''select p.pack,p.name,p.path,r.signature from records r join plugins p on p.id=r.plugin_id join origins o on o.id=r.origin_id where o.name_key=? and r.object_id=?''', (name, obj)).fetchall()
        missing.append({'record': f'{name}|{obj:06X}', 'all_indexed_packs_hits': hits})
        assert not hits
    output = {'missing_identity_search': missing, 'base_plugins': [], 'appearance': []}
    for name in ('GostedDimensionalRift.esp', 'Darkend.esp', 'DBM_RelicNotifications.esp'):
        item = selected[name]
        records, _, _ = scan(BASE / 'xedit_runs/TuLED/Data' / name)
        targets = target_records(item, records)
        data = {'plugin': name, 'source': str(BASE / 'xedit_runs/TuLED/Data' / name), 'source_sha256': digest(BASE / 'xedit_runs/TuLED/Data' / name),
                'targets': [label(r) | {'raw_subrecords': [{'tag': t, 'hex': v.hex()} for t, v in r['fields']], 'vmad_references': vmad_refs(r)} for r in targets]}
        if name == 'Darkend.esp':
            target_ids = {formvalue(r, r['fid']) for r in targets}
            spells = []
            for r in records.values():
                if r['signature'] not in ('SPEL', 'ENCH', 'ALCH', 'INGR'): continue
                links = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'EFID']
                if target_ids.intersection(links): spells.append(label(r) | {'bad_MGEF_effects': sorted(target_ids.intersection(links))})
            spell_ids = {r['record'] for r in spells}
            races = []
            for r in records.values():
                if r['signature'] != 'RACE': continue
                links = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'SPLO']
                if spell_ids.intersection(links): races.append(label(r) | {'affected_spells': sorted(spell_ids.intersection(links))})
            race_ids = {r['record'] for r in races}
            npcs = []
            for r in records.values():
                if r['signature'] != 'NPC_': continue
                links = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'SPLO']
                race = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'RNAM']
                if spell_ids.intersection(links) or race_ids.intersection(race):
                    npcs.append(label(r) | {'affected_spells': sorted(spell_ids.intersection(links)), 'affected_races': sorted(race_ids.intersection(race))})
            npc_ids = {r['record'] for r in npcs}
            placed = []
            leveled = []
            for r in records.values():
                if r['signature'] == 'ACHR':
                    for t, v in r['fields']:
                        if t == 'NAME' and formvalue(r, struct.unpack('<I', v)[0]) in npc_ids:
                            placed.append(label(r) | {'base_NPC': formvalue(r, struct.unpack('<I', v)[0])})
                if r['signature'] == 'LVLN':
                    for t, v in r['fields']:
                        if t == 'LVLO' and len(v) >= 8 and formvalue(r, struct.unpack_from('<I', v, 4)[0]) in npc_ids:
                            leveled.append(label(r) | {'NPC_entry': formvalue(r, struct.unpack_from('<I', v, 4)[0])})
            data['typed_consumption_graph'] = {'SPEL_EFID': spells, 'RACE_SPLO': races, 'NPC_SPLO_or_RNAM': npcs, 'ACHR_NAME': placed, 'LVLN_LVLO': leveled}
            data['cross_pack_same_EDID_sources'] = [dict(zip(('pack', 'plugin', 'path', 'fid', 'edid'), r)) for r in ids.execute('''select distinct s.pack,s.name,s.path,r.fid,r.edid from identified_records r join plugin_snapshots s on s.canonical_sha256=r.sha256 where r.edid_key='mihailfxrottenmaidenmournxjk' ''')]
        if name == 'DBM_RelicNotifications.esp':
            links = []
            sndr_ids = {formvalue(r, r['fid']) for r in targets}
            for r in records.values():
                if r['signature'] == 'SOUN':
                    for t, v in r['fields']:
                        if t == 'SDSC' and formvalue(r, struct.unpack('<I', v)[0]) in sndr_ids:
                            links.append(label(r) | {'field': 'SDSC', 'descriptor': formvalue(r, struct.unpack('<I', v)[0])})
                if r['signature'] == 'PROJ':
                    for t, v in r['fields']:
                        if t == 'DATA' and len(v) >= 44 and formvalue(r, struct.unpack_from('<I', v, 40)[0]) in sndr_ids:
                            links.append(label(r) | {'field': 'DATA/Sound offset40', 'descriptor': formvalue(r, struct.unpack_from('<I', v, 40)[0])})
            link_ids = {r['record'] for r in links}
            consumers = [label(r) | {'vmad_references': [v for v in vmad_refs(r) if v['form'] in link_ids]} for r in records.values() if any(v['form'] in link_ids for v in vmad_refs(r))]
            data['typed_sound_consumers'] = links
            data['typed_VMAD_consumers_of_SOUN'] = consumers
            data['script_PlayFX'] = {'path': str(OUT / 'scripts/archive_230/psc/rn_achivement_script_master.psc'),
                                    'lines': [77, 84], 'behavior': 'Declared Sound properties TCC_Ach_Sound and TCC_Ach_SoundBrass are Playandwait consumed for _Value 0 and 2.'}
            data['SNAM_nullable_primary'] = {'path': str(BASE / 'sources/TES5Edit/Core/wbDefinitionsTES5.pas'), 'line': 7498,
                'schema': "wbFormIDCk(SNAM, 'Alternate Sound For', [SNDR,NULL])", 'distinction': 'NULL is legal; the existing nonzero absent LOTD target is unresolved, so this does not prove either clearing it or guessing a replacement preserves intended behavior.'}
            data['Looping_primary'] = {'path': str(BASE / 'sources/TES5Edit/Core/wbDefinitionsTES5.pas'), 'lines': [7511, 7522], 'allowed': [0, 8, 16, 32], 'source_value': 64,
                'primary_online': 'https://ng.commonlib.dev/_b_g_s_standard_sound_def_8h_source.html', 'finding': 'CommonLibSSE-NG enum also lists only 0/8/16/32; no verified support for 64 found. Preserve unknown source value instead of selecting a guessed mode.'}
        output['base_plugins'].append(data)
    names = ('Replacing Female Resource.esp', 'Replacing Female Resource_2.esp', 'Female AIO Modding VN.esp',
             'WZOblivionArtifacts.esp', 'Tullius Hair 3 SMP.esp', '[Stella]PussycatSashaFollower.esp',
             'Apocalypse - Magic of Skyrim.esp', 'Full Random NPC Pack.esp', 'Inigo.esp')
    for name in names:
        item = selected[name]
        source = BASE / 'xedit_runs/TuLED/Data' / name
        records, _, _ = scan(source)
        targets = target_records(item, records)
        details = []
        for r in targets:
            x = label(r)
            fields = dict(r['fields'])
            if r['signature'] == 'NPC_':
                flags = struct.unpack_from('<I', fields['ACBS'])[0]
                x['ACBS_flags'] = f'{flags:08X}'
                x['CharGenFacePreset_bit2'] = bool(flags & 4)
                x['race'] = formvalue(r, struct.unpack('<I', fields.get('RNAM', b'\0'*4))[0])
                x['class'] = formvalue(r, struct.unpack('<I', fields.get('CNAM', b'\0'*4))[0])
                x['template'] = formvalue(r, struct.unpack('<I', fields.get('TPLT', b'\0'*4))[0])
                x['tint_indices'] = [struct.unpack('<H', v)[0] for t, v in r['fields'] if t == 'TINI']
            if r['signature'] == 'RACE':
                x['female_presets'] = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'RPRF']
                x['DATA_first64_hex'] = fields.get('DATA', b'')[:64].hex()
            if r['signature'] == 'HDPT':
                x['extra_parts'] = [formvalue(r, struct.unpack('<I', v)[0]) for t, v in r['fields'] if t == 'HNAM']
            target = formvalue(r, r['fid'])
            consumers = []
            for a in records.values():
                typed = {'NAME'} if a['signature'] == 'ACHR' else {'TPLT', 'RNAM'} if a['signature'] == 'NPC_' else {'RPRF', 'RPRM'} if a['signature'] == 'RACE' else {'HNAM'} if a['signature'] == 'HDPT' else set()
                for t, v in a['fields']:
                    if t in typed and len(v) == 4 and formvalue(a, struct.unpack('<I', v)[0]) == target:
                        consumers.append(label(a) | {'field': t})
            x['within_source_typed_consumers'] = consumers
            obj = r['fid'] & 0xFFFFFF
            # Capture both documented facegen branches for the canonical origin.
            stem = f'{obj:08x}'
            origin = formvalue(r, r['fid']).split('|')[0]
            paths = [f'meshes/actors/character/facegendata/facegeom/{origin}/{stem}.nif',
                     f'textures/actors/character/facegendata/facetint/{origin}/{stem}.dds']
            x['exact_facegen_inventory'] = []
            if r['signature'] == 'NPC_':
                for key in paths:
                    archived = [dict(zip(('archive_id', 'sha256', 'bytes'), row)) for row in db.execute('select archive_id,sha256,size_bytes from bsa_entries where path_key=?', (key,))]
                    loose = [dict(zip(('mod_id', 'mod', 'mod_path', 'relative_path'), row)) for row in db.execute('select f.mod_id,m.name,m.path,f.relative_path from files f join mods m on m.id=f.mod_id where f.path_key=?', (key,))]
                    x['exact_facegen_inventory'].append({'path': key, 'archived': archived, 'loose': loose})
            details.append(x)
        dependents = [dict(zip(('plugin', 'path', 'relative_path'), row)) for row in db.execute('''select distinct sp.plugin_name,m.path,p.relative_path from plugin_masters pm join plugin_files p on p.id=pm.plugin_id join mods m on m.id=p.mod_id join selected_plugin_resolution sp on sp.winning_plugin_id=p.id and sp.profile_id=7 where pm.master_key=?''', (name.casefold(),))]
        output['appearance'].append({'plugin': name, 'source': str(source), 'sha256': digest(source), 'records': details,
                                     'original_selected_hard_dependents': dependents, 'limits': 'Within-source typed consumers and all inventoried facegen candidates only; final asset winners and external dynamic distribution need final-VFS evidence.'})
    (OUT / 'base_record_semantics.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Remaining base:', len(output['base_plugins']), 'plugins;', len(output['appearance']), 'appearance sources')
    print('Darkend graph:', {k: len(v) for k, v in output['base_plugins'][1]['typed_consumption_graph'].items()})


if __name__ == '__main__': main()
