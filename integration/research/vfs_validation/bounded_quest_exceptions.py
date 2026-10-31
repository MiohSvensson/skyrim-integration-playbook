"""Exact source-gap contracts. Only xEdit typed references prove static nonuse."""
import collections
import hashlib
import json
from pathlib import Path
import struct


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def provenance(path):
    return {'path': str(Path(path).resolve()), 'sha256': digest(path)}


def validate_xedit_result(path, expected_plugins, script):
    """Accept only actual-MO2, full-context, immutable producer evidence."""
    path = Path(path).resolve()
    result = json.loads(path.read_text(encoding='utf-8'))
    assert result['status'] == 'PASS' and result['usvfs'] is True
    assert result['return_code'] == 0 and result['marker_seen'] is True
    assert result['pass_marker'] == 'QEX_PASS' and result['changed_input_plugins'] == []
    task = path.parent
    prepared_path = task / 'prepared.json'
    prepared = json.loads(prepared_path.read_text(encoding='utf-8'))
    assert prepared['pass_marker'] == 'QEX_PASS'
    assert prepared.get('candidate') in (None,'') and not prepared.get('patch_name')
    assert prepared['script_sha256'] == digest(script) == digest(prepared['script'])
    inventory_path = task / 'input_inventory.json'
    inventory = json.loads(inventory_path.read_text(encoding='utf-8'))
    expected = {x['name'].lower(): x['sha256'] for x in expected_plugins}
    actual = {x['name'].lower(): x['sha256'] for x in inventory['plugins'] if not x['name'].lower().endswith('.exe')}
    assert actual == expected, 'xEdit inventory SHA set is not the final enabled expectation context'
    log = task / 'logs/xedit.log'
    assert result['log_sha256'] == digest(log)
    messages = [];resource_messages=[]
    for line in log.read_text(encoding='utf-8-sig', errors='strict').splitlines():
        if 'QEX_' in line:
            messages.append(line[line.index('QEX_'):].split('\t'))
        if 'RSRC_' in line:
            resource_messages.append(line[line.index('RSRC_'):].split('\t'))
    files = [r[1].lower() for r in messages if r[0] == 'QEX_FILE']
    built = [r[1].lower() for r in messages if r[0] == 'QEX_BUILDREF']
    assert len(files) == len(set(files)) == len(expected) and set(files) == set(expected)
    assert len(built) == len(set(built)) == len(expected) and set(built) == set(expected)
    assert not any(r[0] in ('QEX_REF', 'QEX_ERROR', 'QEX_FAIL') for r in messages)
    complete = [r for r in messages if r[0] == 'QEX_COMPLETE']
    assert len(complete) == 1 and list(map(int, complete[0][1:])) == [len(expected), len(expected), 6, 0]
    assert sum(r[0] == 'QEX_PASS' for r in messages) == 1
    targets = {}
    for row in messages:
        if row[0] != 'QEX_TARGET':
            continue
        _, plugin, objid, sig, count, winner = row
        identity = plugin.lower() + '|' + objid.lower()
        assert identity not in targets and int(count) == 0
        assert winner.lower() == plugin.lower()
        targets[identity] = {'identity': identity, 'signature': sig, 'typed_referenced_by_count': 0,
                             'winning_record_plugin': winner}
    required = {'bendoonsse.esp|04a1a3'} | {'[longshou]uf6.esp|' + f'{n:06x}' for n in range(0x801, 0x806)}
    assert set(targets) == required
    resource_targets={};resource_nodes={};resource_edges={};resource_errors=[]
    for row in resource_messages:
        if row[0]=='RSRC_TARGET':
            _,name,object_id,signature=row
            identity=name.lower()+'|'+object_id.lower();assert identity not in resource_targets
            resource_targets[identity]=signature
        elif row[0]=='RSRC_NODE':
            assert len(row)>=7,('Malformed RSRC_NODE',row)
            _,depth,identity,signature,winner,edid,count,*rest=row
            node={'identity':identity.lower(),'signature':signature,'winning_record_plugin':winner,
                'edid':edid,'typed_referenced_by_count':int(count)}
            if identity.lower() in resource_nodes:assert resource_nodes[identity.lower()]==node
            resource_nodes[identity.lower()]=node
        elif row[0]=='RSRC_EDGE':
            assert len(row)>=6,('Malformed RSRC_EDGE',row)
            _,origin,consumer,signature,provider,*label=row
            edge={'from':origin.lower(),'to':consumer.lower(),'signature':signature,'reference_record_plugin':provider}
            resource_edges[(origin.lower(),consumer.lower(),provider.lower())]=edge
        elif row[0]=='RSRC_ERROR':resource_errors.append(row)
    appendix_complete=sum(r[0]=='RSRC_APPENDIX_COMPLETE' for r in resource_messages)==1
    return {'status': 'FULL_CONTEXT_TYPED_XEDIT_ZERO_CONSUMERS', 'plugin_count': len(expected),
            'targets': targets, 'provenance': [provenance(path), provenance(prepared_path),
                provenance(inventory_path), provenance(log), provenance(script)],
            'resource_appendix':{'complete':appendix_complete,'targets':resource_targets,'nodes':resource_nodes,
                'edges':list(resource_edges.values()),'errors':resource_errors}}


class BoundedQuestExceptions:
    def __init__(self, manifest_path, expected_plugins, identities, xedit_result=None, target=None):
        self.path = Path(manifest_path).resolve()
        self.manifest = json.loads(self.path.read_text(encoding='utf-8'))
        assert self.manifest['schema'] == 'skyrim.bounded_quest_resource_exceptions.v2'
        assert self.manifest['case_count'] == len(self.manifest['cases']) == 11
        self.provenance = provenance(self.path)
        self.active = {x['name'].lower(): x for x in expected_plugins}
        self.records = identities
        self.errors = []
        self.valid = {}
        self.inactive = []
        self.typed = None
        self.evidence = {}
        self.target=Path(target).resolve() if target else None
        needed = any((x['require_no_final_formid_consumers'] or x.get('typed_rsrc_guard')) and x['source_plugin']['name'].lower() in self.active for x in self.manifest['cases'])
        if needed:
            try:
                assert xedit_result, 'A SHA-context-bound xEdit typed reference result is required'
                self.typed = validate_xedit_result(xedit_result, expected_plugins, self.path.parent / 'BoundedQuestConsumerAudit.pas')
            except Exception as ex:
                self.errors.append({'kind': 'bounded_exception_typed_consumer_gate_failed', 'error': repr(ex)})
        hashed = {}
        def actual_sha(path):
            if path not in hashed:
                hashed[path] = digest(path)
            return hashed[path]
        self.actual_sha=actual_sha
        for case in self.manifest['cases']:
            guard = case['winning_record_guard']
            name = case['source_plugin']['name'].lower()
            if name not in self.active:
                self.inactive.append(case['id'])
                continue
            try:
                assert self.active[name]['sha256'] == guard['plugin_sha256'] == case['source_plugin']['sha256']
                assert actual_sha(case['source_plugin']['path']) == guard['plugin_sha256']
                record=self.record_guard(guard)
                for related in case.get('related_record_guards',[]):self.record_guard(related)
                for ev in case['evidence']:
                    self.evidence_guard(ev)
                if case['require_no_final_formid_consumers']:
                    assert self.typed is not None and guard['identity'] in self.typed['targets']
                    assert self.typed['targets'][guard['identity']]['signature'] == guard['signature']
                if case.get('typed_rsrc_guard'):self.rsrc_guard(case)
                if case.get('female_branch_guard'):self.female_branch_guard(case)
                if case.get('singlepass_material_guard'):self.material_guard(case,record)
                if case.get('author_package_guard'):self.author_package_guard(case)
                self.valid[case['id']] = case
            except Exception as ex:
                self.errors.append({'kind': 'bounded_exception_record_guard_failed', 'case_id': case['id'], 'error': repr(ex)})

    def evidence_guard(self,ev):
        assert self.actual_sha(ev['path'])==ev['sha256'],('Evidence changed',ev['path'])
        self.evidence[ev['path']]=ev

    def record_guard(self,guard):
        assert self.active[guard['plugin_name'].lower()]['sha256']==guard['plugin_sha256']
        winner,record=self.records[guard['identity']]
        assert winner['name'].lower()==guard['plugin_name'].lower(),('Unexpected final record winner',guard['identity'],winner['name'])
        assert self.active[winner['name'].lower()]['sha256']==guard['plugin_sha256']
        assert record['sig']==guard['signature'] and record['flags']==guard['flags']
        assert f'{record["fid"]:08X}'==guard['raw_form_id']
        assert record['payload_sha256']==guard['decompressed_payload_sha256']
        for field in guard['field_guards']:
            values=[v for t,v in record['fields'] if t==field['tag']]
            if 'occurrence' in field:
                assert len(values)==field['expected_occurrences'];value=values[field['occurrence']]
            else:
                assert len(values)==1;value=values[0]
            assert hashlib.sha256(value).hexdigest()==field['sha256'] and value.hex()==field['bytes_hex']
            if 'typed_response_number' in field:
                assert field['tag']=='TRDT' and value[12]==field['typed_response_number']
                assert f'{struct.unpack_from("<I",value,16)[0]:08X}'==field['typed_sound_raw_id']
        return record

    def rsrc_guard(self,case):
        assert self.typed is not None,'A real final-context typed resource appendix is required'
        audit=self.typed['resource_appendix'];guard=case['typed_rsrc_guard']
        assert audit['complete'] and not audit['errors']
        target=guard['target'];assert audit['targets'][target]==case['winning_record_guard']['signature']
        for identity in guard['required_nodes']:
            node=audit['nodes'][identity]
            assert node['winning_record_plugin'].lower()==guard['source_winner_plugin'].lower()
            assert node['signature']==self.records[identity][1]['sig']
        for identity,expected in guard['expected_direct_consumers'].items():
            edges=[e for e in audit['edges'] if e['from']==identity]
            assert len(edges)==audit['nodes'][identity]['typed_referenced_by_count']
            assert {e['to'] for e in edges}==set(expected),('New or missing typed consumer',identity,edges)
            assert len(edges)==len(expected),'Duplicate or extra override consumer requires review'
            for edge in edges:
                assert edge['reference_record_plugin'].lower()==guard['source_winner_plugin'].lower()
                assert edge['signature']==self.records[edge['to']][1]['sig']

    def female_branch_guard(self,case):
        guard=case['female_branch_guard'];main=case['winning_record_guard'];owner=main['plugin_name'].lower()
        own_index=len(self.active[owner]['masters'])
        def raw_id(identity):return (own_index<<24)|int(identity.split('|')[1],16)
        def fields(identity,tag):return [v for t,v in self.records[identity][1]['fields'] if t==tag]
        def one(identity,tag):
            values=fields(identity,tag);assert len(values)==1;return values[0]
        armor,race=guard['armor'],guard['race']
        assert self.records[armor][1]['flags']&0x4,'Skin armor must remain NonPlayable'
        assert struct.unpack('<I',one(race,'WNAM'))[0]==raw_id(armor)
        assert struct.unpack('<I',one(armor,'RNAM'))[0]==raw_id(race)
        assert fields(armor,'MODL')==[struct.pack('<I',raw_id(main['identity']))]
        assert not struct.unpack_from('<I',one(race,'DATA'),32)[0]&1,'Race must remain nonplayable'
        assert struct.unpack('<I',one(main['identity'],'RNAM'))[0]==raw_id(race)
        assert fields(main['identity'],'MODL')==[],'Additional races are outside this bounded branch'
        actors=set(guard['actors'])
        typed_edges=self.typed['resource_appendix']['edges']
        for ancestor,expected in guard['expected_NPC_template_consumers'].items():
            edges=[e for e in typed_edges if e['from']==ancestor and e['signature']=='NPC_']
            assert len(edges)==len(expected) and {e['to'] for e in edges}==set(expected),('New NPC template/VMAD consumer',ancestor,edges)
            assert all(e['reference_record_plugin'].lower()==owner for e in edges)
        for identity in actors:
            assert self.records[identity][1]['sig']=='NPC_'
            assert struct.unpack('<I',one(identity,'RNAM'))[0]==raw_id(race)
            assert not struct.unpack_from('<I',one(identity,'ACBS'))[0]&1,'Female consumer found'
            templates=fields(identity,'TPLT')
            if templates:
                assert len(templates)==1
                raw=struct.unpack('<I',templates[0])[0]
                if raw:
                    assert raw>>24==own_index
                    template=owner+'|'+f'{raw&0xffffff:06x}'
                    assert template in actors
                    assert not struct.unpack_from('<I',one(template,'ACBS'))[0]&1
        report=guard['source_script_report'];self.evidence_guard(report)
        source=json.loads(Path(report['path']).read_text(encoding='utf-8'))
        assert source['source_count']==guard['expected_source_script_count'] and source['hits']==[]
        self.evidence_guard({'path':source['archive'],'sha256':source['archive_sha256']})

    def material_guard(self,case,record):
        guard=case['singlepass_material_guard']
        data=[v for t,v in record['fields'] if t=='DATA'];assert len(data)==1 and len(data[0])>=48
        assert struct.unpack_from('<I',data[0],guard['singlepass_data_offset'])[0]==guard['singlepass_value']==1
        assert sum(t=='DNAM' for t,v in record['fields'])==guard['DNAM_count']==0
        assert guard['selected_runtime_executed'] is False and guard['selected_packed_text_decoded'] is False
        for name in ('semantic_report','reference_disassembly','image_comparison','stock_material_report'):self.evidence_guard(guard[name])
        semantic=json.loads(Path(guard['semantic_report']['path']).read_text(encoding='utf-8'))
        for source in semantic['primary_headers']:self.evidence_guard(source)
        reference=json.loads(Path(guard['reference_disassembly']['path']).read_text(encoding='utf-8'))
        comparison=json.loads(Path(guard['image_comparison']['path']).read_text(encoding='utf-8'))
        assert self.target is not None
        assert Path(comparison['selected']['path']).resolve()==self.target/'Game/SkyrimSE.exe'
        self.evidence_guard(comparison['selected']);self.evidence_guard(comparison['reference'])
        assert reference['exe']['sha256']==comparison['reference']['sha256']
        assert reference['ensure_loaded']['start_rva']=='002C6370'
        assert ''.join(i['bytes'] for i in reference['ensure_loaded']['instructions'])==guard['ensure_loaded_instruction_bytes']
        assert reference['address_library']['version']==[1,5,97,0] and reference['address_library']['exact_EOF']
        self.evidence_guard(reference['address_library'])
        sections=comparison['sections'];assert len(sections)==10
        assert {s['section'] for s in sections if not s['byte_identical']}=={'.text:0x1000'}
        assert all(s['same_size'] for s in sections)
        stock=json.loads(Path(guard['stock_material_report']['path']).read_text(encoding='utf-8'))
        assert stock['count']==16 and len(stock['same_missing_model_declarations'])==16
        self.evidence_guard({'path':stock['stock_path'],'sha256':stock['stock_sha256']})

    def author_package_guard(self,case):
        guard=case['author_package_guard'];self.evidence_guard(guard['report'])
        report=json.loads(Path(guard['report']['path']).read_text(encoding='utf-8'))
        assert report['schema']=='skyrim.forgotten_city_author_compare.v1'
        assert report['status']=='AUTHOR_SSE18_EXACT_PACKAGE_CONFIRMS_UPSTREAM_MISSING_MOTIF_AUDIO'
        assert report['package']['sha256']==guard['zip_sha256']
        self.evidence_guard(report['package']);self.evidence_guard(report['author_plugin'])
        assert report['whole_author_and_selected_plugin_sha_equal']
        assert report['source_plugin']['sha256']==guard['source_plugin_sha256']
        assert report['exact_audio_resources_to_import']==[] and report['zip_member_count']==3
        assert {r['identity']:r['author_payload_sha256'] for r in report['record_comparisons']}==guard['expected_payloads']
        for row in report['record_comparisons']:
            assert row['byte_identical_decompressed_payload'] and row['author_payload_sha256']==row['selected_payload_sha256']
        assert sorted(r['directly_enumerated_members'] for r in report['bsa_comparisons'])==[90,1934]
        for archive in report['bsa_comparisons']:
            self.evidence_guard(archive['byte_identical_existing_local_archive']);self.evidence_guard(archive['inventory_evidence'])
            assert archive['entire_name_set_equals_previously_full_hash_verified_inventory']
            assert set(archive['exact_missing_target_presence'])==set(case['allowed_missing_paths'])
            assert not any(archive['exact_missing_target_presence'].values())

    def match_missing(self, resource, alternatives):
        """All requesters and the complete alternative set must be covered."""
        for case in self.valid.values():
            if resource['path_key'] not in case['allowed_missing_paths'] or resource.get('kind')!=case['allowed_resource_kind']:
                continue
            if set(alternatives) != set(case['allowed_missing_paths']):
                continue
            guard = case['winning_record_guard']
            requests = resource['requested_by']
            if not requests:
                continue
            if not all(r.get('plugin', '').lower() == guard['plugin_name'].lower()
                       and r.get('record') == guard['identity']
                       and r.get('signature') == guard['signature']
                       and r.get('field') in case['allowed_request_fields'] for r in requests):
                continue
            if set(r['field'] for r in requests) != set(case['allowed_request_fields']):
                continue
            return {'case_id': case['id'], 'classification': case['classification'],
                    'accepted_as': case['accepted_as'], 'path_key': resource['path_key'],
                    'alternatives': alternatives, 'requested_by': requests,
                    'source_plugin_sha256': guard['plugin_sha256'],
                    'record_payload_sha256': guard['decompressed_payload_sha256'],
                    'author_package_sha256':case.get('author_package_guard',{}).get('zip_sha256'),
                    'bounded_guard_categories':[k for k in ('typed_rsrc_guard','female_branch_guard','singlepass_material_guard','author_package_guard') if k in case],
                    'limitation': case['limitation'], 'gameplay_verified': False}
        return None

    def audit(self):
        return {'manifest': self.provenance, 'valid_case_ids': sorted(self.valid),
                'inactive_case_ids': self.inactive, 'typed_xedit_consumers': self.typed,
                'evidence': list(self.evidence.values()), 'errors': self.errors}
