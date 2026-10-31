"""Selected source evidence only; final typed consumers come from actual xEdit."""
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from quest_resource_seeds import records, plugin_header, text


def main():
    preview_path = BASE / 'integration/research/vfs_validation/quest_all15_source_preview_rev6.json'
    preview = json.loads(preview_path.read_text(encoding='utf-8'))
    output = []
    for name, objects in [('Glenmoril.esm', [0xF5DF, 0xC8CD]), ('ForgottenCity.esp', [0xE2673])]:
        path = next(x['path'] for x in preview['plugins'] if x['name'] == name)
        h = plugin_header(path)
        fids = {(len(h['masters']) << 24) | n: [] for n in objects}
        relevant = {}
        consumers = {fid: [] for fid in fids}
        all_brief = {}
        for record in records(path, masters=h['masters'], name=name):
            def brief(r):
                return {k: v for k, v in r.items() if k != 'fields'} | {
                    'edid': next((text(v) for t, v in r['fields'] if t == 'EDID'), None)}
            all_brief[record['fid']] = brief(record)
            if record['fid'] in fids:
                relevant[record['identity']] = {**brief(record), 'fields': [{'tag': t, 'hex': v.hex(), 'text': text(v)} for t, v in record['fields']]}
            for fid in fids:
                needle = struct.pack('<I', fid)
                for tag, value in record['fields']:
                    at = value.find(needle)
                    if at >= 0 and record['fid'] != fid:
                        consumers[fid].append({'record': brief(record), 'tag': tag, 'offset': at,
                            'bytes': len(value), 'value_hex': value.hex() if len(value) <= 1024 else None,
                            'typed': record['sig'] == 'ARMO' and tag == 'MODL' and len(value) == 4
                                or record['sig'] == 'STAT' and tag == 'DNAM' and at == 4 and len(value) in (8, 12)})
        # Follow precise ARMO armature -> RACE skin/NPC custom skin and race links.
        arma = (len(h['masters']) << 24) | 0xF5DF
        armor_ids = {x['record']['fid'] for x in consumers.get(arma, []) if x['typed']}
        armor_links = []
        race_ids = set()
        for record in records(path, masters=h['masters'], name=name, signatures={'RACE', 'NPC_'}):
            for tag, value in record['fields']:
                if tag == 'WNAM' and len(value) == 4 and struct.unpack('<I', value)[0] in armor_ids:
                    armor_links.append({**all_brief[record['fid']], 'field': 'WNAM', 'armor_raw_id': f'{struct.unpack("<I", value)[0]:08X}'})
                    if record['sig'] == 'RACE':
                        race_ids.add(record['fid'])
        actors = []
        for record in records(path, masters=h['masters'], name=name, signatures={'NPC_'}):
            race = next((struct.unpack('<I', v)[0] for t, v in record['fields'] if t == 'RNAM' and len(v) == 4), None)
            if race in race_ids:
                acbs = next((v for t, v in record['fields'] if t == 'ACBS'), b'')
                flags = struct.unpack_from('<I', acbs)[0] if len(acbs) >= 4 else None
                actors.append({**all_brief[record['fid']], 'race_raw_id': f'{race:08X}', 'ACBS_hex': acbs.hex(),
                    'base_Female_flag': bool(flags & 1) if flags is not None else None,
                    'template_raw_id': next((f'{struct.unpack("<I", v)[0]:08X}' for t, v in record['fields'] if t == 'TPLT' and len(v) == 4), None),
                    'note': 'Base ACBS gender only. Final template flags, winning overrides and player-accessible usage are not certified here.'})
        output.append({'plugin': name, 'path': path, 'sha256': h['sha256'], 'target_records': relevant,
            'full_source_subrecord_byte_candidates': {f'{k:08X}': v for k, v in consumers.items()},
            'typed_armor_skin_links': armor_links, 'typed_race_NPC_links': actors,
            'scope': 'Direct ARMO Armature MODL, RACE/NPC WNAM and NPC RNAM are typed. Other byte hits remain candidates pending xEdit LinksTo/BuildRef validation. No exception or restoration is granted.'})
    target = OWN / 'new_feature_resource_gap_evidence.json'
    target.write_text(json.dumps({'status': 'SOURCE_CONSUMERS_RESEARCH_NOT_FINAL_TYPED_PASS', 'plugins': output}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(target), 'summary': [{'plugin': p['plugin'], 'targets': list(p['target_records']),
        'raw_consumer_candidate_counts': {k: len(v) for k, v in p['full_source_subrecord_byte_candidates'].items()},
        'skin_links': len(p['typed_armor_skin_links']), 'NPC_race_links': len(p['typed_race_NPC_links'])} for p in output]}))


if __name__ == '__main__':
    main()
