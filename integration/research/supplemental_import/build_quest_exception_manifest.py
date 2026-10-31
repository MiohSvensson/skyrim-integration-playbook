"""Freeze exact authored resource-gap contracts; never changes any plugin."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from quest_resource_seeds import records, plugin_header, vmad_scripts, runtime_path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    return {'path': str(path), 'sha256': sha(path)}


def raw_payload(path, raw_id):
    data = Path(path).read_bytes()
    pos = 0
    while pos < len(data):
        sig = data[pos:pos+4]
        size = struct.unpack_from('<I', data, pos+4)[0]
        if sig == b'GRUP':
            pos += 24
            continue
        flags, fid = struct.unpack_from('<II', data, pos+8)
        payload = data[pos+24:pos+24+size]
        if fid == raw_id:
            if flags & 0x40000:
                n = struct.unpack_from('<I', payload)[0]
                payload = zlib.decompress(payload[4:])
                assert n == len(payload)
            return payload
        pos += 24 + size
    raise KeyError(hex(raw_id))


def main():
    consumer_path = BASE / 'integration/research/remaining_base_semantics/feature_missing_consumers.json'
    consumers = json.loads(consumer_path.read_text(encoding='utf-8'))
    wyrm_path = BASE / 'integration/research/wyrmstooth_restoration/final_disposition.json'
    wyrm = json.loads(wyrm_path.read_text(encoding='utf-8'))
    plugins = {x['plugin'].lower(): x for x in consumers['plugins']}
    preview=json.loads((BASE/'integration/research/vfs_validation/quest_all15_source_preview_rev6.json').read_text(encoding='utf-8'))
    for plugin in preview['plugins']:
        if plugin['name'].lower() in ('glenmoril.esm','forgottencity.esp'):
            plugins[plugin['name'].lower()]={'plugin':plugin['name'],'path':plugin['path'],'sha256':plugin['sha256']}
    cases = []
    descriptors = [
        ('wyrmstooth.esp', 0x3943AB, 'known_upstream_active_fragment_gap',
         'The authored Unwanted Guests entry INFO actually invokes Fragment_0 on dialogue end. Missing script is not proved harmless and has not been reconstructed.', False),
        ('wyrmstooth.esp', 0x8BFAE2, 'known_upstream_active_ambient_gap',
         'The authored cricket SNDR is consumed by WyrmstoothMarsh and WyrmstoothForest regional ambience. The exact WAV/XWM is absent; no substitute audio is supplied.', False),
        ('bendoonsse.esp', 0x04A1A3, 'known_source_unconsumed_package',
         'No typed PKID/ALPC or complete-payload FormID consumer in the selected source. Absence must be rechecked across the final enabled dependent plugin context; dynamic external lookups remain a limitation.', True),
    ]
    for object_id in range(0x801, 0x806):
        descriptors.append(('[longshou]uf6.esp', object_id, 'known_source_unplaced_furniture',
            'No typed NAME placement or complete-payload FormID consumer in the selected repaired source; zero attached VMAD in UF6. Absence must be rechecked across the final enabled dependent plugin context; dynamic external lookups remain a limitation.', True))
    descriptors.extend([
        ('forgottencity.esp',0x0E2673,'known_upstream_active_dialogue_motif_gap',
         'The complete original author SSE1.8 ZIP has the identical ESP and both BSAs, and lacks the exact motif WAV/XWM. INFO0C38B4 response5 uses this SNDR. Authored speech FUZ exists but is not a replacement. NOT_REPAIRED.',False),
        ('glenmoril.esm',0x00F5DF,'known_source_unreached_female_biped_branch',
         'Exact female biped model declaration is absent. Acceptance requires the final typed ARMA/skin/RACE/NPC chain to remain nonplayable and entirely male, with matching source payloads and template ancestors. No model alias or restoration is supplied; dynamic external lookups and gameplay are unproved.',False),
        ('glenmoril.esm',0x00C8CD,'known_engine_singlepass_material_source_stub',
         'Exact SinglePass1/noDNAM MATO source-model stub. Stock and matching1.5.97 reference-image EnsureLoaded evidence supports inline material data. Selected packed text was not directly decoded or executed. No NIF is restored or substituted; final typed MATO/STAT guards are mandatory.',False),
    ])
    for name, object_id, classification, limitation, unconsumed in descriptors:
        source = plugins[name]
        assert sha(source['path']) == source['sha256']
        h = plugin_header(source['path'])
        identity = name + '|' + f'{object_id:06x}'
        found = list(records(source['path'], {identity}, h['masters'], source['plugin']))
        assert len(found) == 1
        record = found[0]
        payload = raw_payload(source['path'], record['fid'])
        fields = record['fields']
        paths = []
        allowed_fields = []
        field_guards = []
        if record['sig'] in ('INFO', 'PACK'):
            vmad = next(v for t, v in fields if t == 'VMAD')
            scripts = vmad_scripts(vmad, record['sig'])
            assert len({n.lower() for n, _ in scripts}) == 1
            paths = ['scripts/' + scripts[0][0].lower() + '.pex']
            allowed_fields = sorted({f for _, f in scripts})
            field_guards.append({'tag': 'VMAD', 'sha256': hashlib.sha256(vmad).hexdigest(), 'bytes_hex': vmad.hex()})
        elif record['sig'] == 'SNDR':
            value = next(v for t, v in fields if t == 'ANAM')
            original = value.rstrip(b'\0').decode('utf-8')
            k = runtime_path(original, 'sound')
            paths = [k, k[:-4] + '.xwm']
            allowed_fields = ['ANAM sound descriptor']
            field_guards.append({'tag': 'ANAM', 'sha256': hashlib.sha256(value).hexdigest(), 'bytes_hex': value.hex()})
        elif record['sig'] in ('FURN','ARMA','MATO'):
            model_tag='MOD3' if record['sig']=='ARMA' else 'MODL'
            value = next(v for t, v in fields if t == model_tag)
            paths = ['meshes/' + value.rstrip(b'\0').decode('utf-8').replace('\\', '/').lower()]
            allowed_fields = [model_tag]
            field_guards.append({'tag': model_tag, 'sha256': hashlib.sha256(value).hexdigest(), 'bytes_hex': value.hex()})
        else:
            raise ValueError(record['sig'])
        cases.append({'id': classification + ':' + f'{object_id:06x}',
            'classification': classification, 'accepted_as': 'DOCUMENTED_SOURCE_LIMITATION_NOT_REPAIRED',
            'source_plugin': {'name': source['plugin'], 'path': source['path'], 'sha256': source['sha256'], 'masters': h['masters']},
            'winning_record_guard': {'plugin_name': source['plugin'], 'plugin_sha256': source['sha256'],
                'identity': identity, 'signature': record['sig'], 'flags': record['flags'],
                'raw_form_id': f'{record["fid"]:08X}', 'decompressed_payload_sha256': hashlib.sha256(payload).hexdigest(),
                'field_guards': field_guards},
            'allowed_missing_paths': paths, 'allowed_request_fields': allowed_fields,
            'allowed_resource_kind':'pex' if record['sig'] in ('INFO','PACK') else 'sound' if record['sig']=='SNDR' else 'model',
            'require_no_final_formid_consumers': unconsumed,
            'consumer_check': 'Require an actual-MO2 full-context xEdit BuildRef/ReferencedByCount audit. Its loaded plugin set and source SHA inventory must exactly match the bootstrap expectations; every enabled plugin must have a completed BuildRef marker. Each of these exact six records must have zero typed ReferencedBy entries. No raw-byte search can satisfy this requirement. Dynamic external lookups remain a limitation.' if unconsumed else None,
            'limitation': limitation, 'record_preserved': True, 'gameplay_verified': False,
            'evidence': [evidence(consumer_path)] + ([evidence(wyrm_path)] if name == 'wyrmstooth.esp' else [])})
    assert len(cases) == 11
    by_object = {x['winning_record_guard']['identity']: x for x in cases}
    def related_guard(source,record,tags=()):
        return {'plugin_name':source['plugin'],'plugin_sha256':source['sha256'],
            'identity':record['identity'],'signature':record['sig'],'flags':record['flags'],
            'raw_form_id':f'{record["fid"]:08X}','decompressed_payload_sha256':record['payload_sha256'],
            'field_guards':[{'tag':t,'sha256':hashlib.sha256(v).hexdigest(),'bytes_hex':v.hex()} for t,v in record['fields'] if t in tags]}
    fc=by_object['forgottencity.esp|0e2673'];source=plugins['forgottencity.esp'];h=plugin_header(source['path'])
    info=list(records(source['path'],{'forgottencity.esp|0c38b4'},h['masters'],source['plugin']))[0]
    guard=related_guard(source,info);trdts=[v for t,v in info['fields'] if t=='TRDT'];assert len(trdts)==6
    response=trdts[4];assert response[12]==5 and struct.unpack_from('<I',response,16)[0]==0x010E2673
    guard['field_guards']=[{'tag':'TRDT','occurrence':4,'expected_occurrences':6,
        'sha256':hashlib.sha256(response).hexdigest(),'bytes_hex':response.hex(),'typed_response_number':5,'typed_sound_raw_id':'010E2673'}]
    fc['related_record_guards']=[guard]
    author_path=BASE/'integration/research/forgotten_city_author_compare/author_compare.json'
    author=json.loads(author_path.read_text(encoding='utf-8'))
    assert author['status']=='AUTHOR_SSE18_EXACT_PACKAGE_CONFIRMS_UPSTREAM_MISSING_MOTIF_AUDIO'
    assert author['source_plugin']['sha256']==source['sha256'] and author['exact_audio_resources_to_import']==[]
    fc['author_package_guard']={'report':evidence(author_path),'zip_sha256':author['package']['sha256'],
        'source_plugin_sha256':source['sha256'],'expected_payloads':{x['identity']:x['author_payload_sha256'] for x in author['record_comparisons']}}
    fc['evidence']+=[evidence(author_path)]+[x['inventory_evidence'] for x in author['bsa_comparisons']]
    female=by_object['glenmoril.esm|00f5df'];material=by_object['glenmoril.esm|00c8cd'];source=plugins['glenmoril.esm'];h=plugin_header(source['path'])
    branch_path=OWN/'glen_female_branch_evidence.json';branch=json.loads(branch_path.read_text(encoding='utf-8'))
    actor_ids={x['identity'] for x in branch['source_actors']}
    related_ids=actor_ids|{'glenmoril.esm|00f5e1','glenmoril.esm|00f5dd','glenmoril.esm|011171','glenmoril.esm|011173','glenmoril.esm|00c8ce','glenmoril.esm|00c996'}
    related={r['identity']:r for r in records(source['path'],related_ids,h['masters'],source['plugin'])};assert set(related)==related_ids
    female['related_record_guards']=[related_guard(source,related[k],('ACBS','RNAM','TPLT','WNAM','DATA')) for k in sorted(related_ids-{'glenmoril.esm|00c8ce','glenmoril.esm|00c996'})]
    female['typed_rsrc_guard']={'target':'glenmoril.esm|00f5df','expected_direct_consumers':{
        'glenmoril.esm|00f5df':['glenmoril.esm|00f5e1'],
        'glenmoril.esm|00f5e1':['glenmoril.esm|00f5dd'],
        'glenmoril.esm|00f5dd':sorted(actor_ids|{'glenmoril.esm|00f5df','glenmoril.esm|011171','glenmoril.esm|00f5e1','glenmoril.esm|011173'})},
        'source_winner_plugin':'Glenmoril.esm','required_nodes':sorted(related_ids-{'glenmoril.esm|00c8ce','glenmoril.esm|00c996'}|{'glenmoril.esm|00f5df'})}
    female['female_branch_guard']={'armor':'glenmoril.esm|00f5e1','race':'glenmoril.esm|00f5dd','actors':sorted(actor_ids),
        'source_script_report':evidence(OWN/'glen_script_race_consumers.json'),'expected_source_script_count':928}
    templates={identity:[] for identity in actor_ids}
    for record in records(source['path'],masters=h['masters'],name=source['plugin'],signatures={'NPC_'}):
        for tag,value in record['fields']:
            if tag=='TPLT' and len(value)==4:
                raw=struct.unpack('<I',value)[0];identity='glenmoril.esm|'+f'{raw&0xffffff:06x}'
                if raw>>24==len(h['masters']) and identity in templates:
                    assert record['identity'] in actor_ids,('Additional source template descendant',record['identity'])
                    templates[identity].append(record['identity'])
    female['female_branch_guard']['expected_NPC_template_consumers']={k:sorted(v) for k,v in templates.items()}
    female['evidence']+=[evidence(branch_path),evidence(OWN/'new_feature_resource_gap_evidence.json'),evidence(OWN/'glen_script_race_consumers.json')]
    material['related_record_guards']=[related_guard(source,related[k],('DNAM',)) for k in ('glenmoril.esm|00c8ce','glenmoril.esm|00c996')]
    material['typed_rsrc_guard']={'target':'glenmoril.esm|00c8cd','expected_direct_consumers':{
        'glenmoril.esm|00c8cd':['glenmoril.esm|00c8ce','glenmoril.esm|00c996']},
        'source_winner_plugin':'Glenmoril.esm','required_nodes':['glenmoril.esm|00c8cd','glenmoril.esm|00c8ce','glenmoril.esm|00c996']}
    material['singlepass_material_guard']={'singlepass_data_offset':44,'singlepass_value':1,'DNAM_count':0,
        'semantic_report':evidence(OWN/'shaderbox_material_semantics_evidence.json'),
        'reference_disassembly':evidence(OWN/'material_ensure_loaded_reference_anno.json'),
        'image_comparison':evidence(OWN/'material_reference_image_comparison.json'),
        'stock_material_report':evidence(OWN/'shaderbox_stock_material_evidence.json'),
        'ensure_loaded_instruction_bytes':'83795000750f8379680074094883c1b8e90b000000c3',
        'selected_runtime_executed':False,'selected_packed_text_decoded':False}
    material['evidence']+=[x for k,x in material['singlepass_material_guard'].items() if isinstance(x,dict) and 'sha256' in x]
    # Every payload and binding from Wyrm's historical author files was exact.
    by_object = {x['winning_record_guard']['identity']: x for x in cases}
    for release in wyrm['author_release_comparisons']:
        for comparison in release['comparison']:
            identity = 'wyrmstooth.esp|' + comparison['form_id'][-6:].lower()
            if identity in by_object:
                assert comparison['same_exact_payload'] and comparison['same_flags']
                assert comparison['local_payload_sha256'] == by_object[identity]['winning_record_guard']['decompressed_payload_sha256']
    result = {'schema': 'skyrim.bounded_quest_resource_exceptions.v2',
        'status': 'EXACT_SOURCE_CONTRACTS_REQUIRE_FINAL_CONTEXT_VALIDATION',
        'scope': 'Eleven exact authored record declarations: nine original/author-proved gaps plus two conditionally classified Glen branches/stubs. No plugin record or asset is changed by this manifest.',
        'rules': ['A matching filename alone never grants an exception.',
            'Source and final winner plugin SHA, record namespace/signature/flags/raw ID, exact decompressed payload, typed field, and all missing alternative paths must match.',
            'Every requesting record for a missing path must match this contract; a new consumer requesting the same path is not covered.',
            'Known unconsumed records additionally require a SHA-context-bound full xEdit BuildRef/ReferencedBy audit with zero typed consumers.',
            'Present resources are checked normally and never classified as missing exceptions.',
            'Exceptions are reported visibly as documented source limitations, never repaired or complete-gameplay PASS.'],
        'case_count': len(cases), 'missing_alternative_path_count': sum(len(x['allowed_missing_paths']) for x in cases),
        'cases': cases}
    target = OWN / 'quest_resource_exceptions.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(target), 'sha256': sha(target), 'case_count': len(cases)}))


if __name__ == '__main__':
    main()
