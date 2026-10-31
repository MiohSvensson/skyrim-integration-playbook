"""Check real source guards and adversarial matching; no fake xEdit evidence."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
VFS = BASE / 'integration/research/vfs_validation'
sys.path.insert(0, str(VFS))
from bounded_quest_exceptions import BoundedQuestExceptions
from quest_resource_seeds import records, plugin_header


def main():
    manifest_path = OWN / 'quest_resource_exceptions.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    expected = {}
    identities = {}
    guard_identities={}
    for case in manifest['cases']:
        p = case['source_plugin']
        h = plugin_header(p['path'])
        expected[p['name'].lower()] = {'name': p['name'], 'sha256': p['sha256'], 'physical_path': p['path'],'masters':h['masters']}
        guard_identities.setdefault(p['name'].lower(),set()).update(x['identity'] for x in [case['winning_record_guard']]+case.get('related_record_guards',[]))
    for name,plugin in expected.items():
        for record in records(plugin['physical_path'],guard_identities[name],plugin['masters'],plugin['name']):identities[record['identity']]=(plugin,record)
    contract = BoundedQuestExceptions(manifest_path, list(expected.values()), identities,target=BASE/'UnifiedSkyrim')
    # Real source hashes and payloads match, but the six unused cases cannot
    # become exceptions without the independently produced xEdit typed result.
    assert len(contract.valid) == 3
    assert all(x.startswith('known_upstream_active_') for x in contract.valid)
    assert any(e['kind'] == 'bounded_exception_typed_consumer_gate_failed' for e in contract.errors)
    assert sum(e['kind'] == 'bounded_exception_record_guard_failed' for e in contract.errors) == 8
    cases = {x['winning_record_guard']['identity']: x for x in manifest['cases']}
    def request(case):
        guard = case['winning_record_guard']
        return {'path_key': case['allowed_missing_paths'][0], 'kind':case['allowed_resource_kind'],'requested_by': [
            {'plugin': guard['plugin_name'], 'record': guard['identity'], 'signature': guard['signature'], 'field': f}
            for f in case['allowed_request_fields']]}
    positive = []
    for case in contract.valid.values():
        resource = request(case)
        assert contract.match_missing(resource, case['allowed_missing_paths'])
        positive.append(case['id'])
        invalid = copy.deepcopy(resource)
        invalid['requested_by'].append({**invalid['requested_by'][0], 'record': 'wyrmstooth.esp|000800'})
        assert contract.match_missing(invalid, case['allowed_missing_paths']) is None
        invalid = copy.deepcopy(resource)
        invalid['requested_by'][0]['field'] += ' different binding'
        assert contract.match_missing(invalid, case['allowed_missing_paths']) is None
        assert contract.match_missing(resource, case['allowed_missing_paths'] + ['sound/other.wav']) is None
        invalid=copy.deepcopy(resource);invalid['path_key']='sound/a_different_file.wav'
        assert contract.match_missing(invalid,case['allowed_missing_paths']) is None
        invalid=copy.deepcopy(resource);invalid['kind']='a_different_kind'
        assert contract.match_missing(invalid,case['allowed_missing_paths']) is None
    for case in manifest['cases']:
        if case['require_no_final_formid_consumers'] or case.get('typed_rsrc_guard'):
            assert contract.match_missing(request(case), case['allowed_missing_paths']) is None
    tampered=copy.deepcopy(identities);info=tampered['forgottencity.esp|0c38b4'][1]
    for n,(tag,value) in enumerate(info['fields']):
        if tag=='TRDT' and value[12]==5:
            wrong=bytearray(value);wrong[16]^=1;info['fields'][n]=(tag,bytes(wrong));break
    bad=BoundedQuestExceptions(manifest_path,list(expected.values()),tampered,target=BASE/'UnifiedSkyrim')
    assert 'known_upstream_active_dialogue_motif_gap:0e2673' not in bad.valid
    material=next(x for x in manifest['cases'] if x.get('singlepass_material_guard'))
    material_record=identities[material['winning_record_guard']['identity']][1]
    contract.material_guard(material,material_record)
    invalid_material=copy.deepcopy(material_record)
    for n,(tag,value) in enumerate(invalid_material['fields']):
        if tag=='DATA':
            wrong=bytearray(value);wrong[44:48]=bytes(4);invalid_material['fields'][n]=(tag,bytes(wrong));break
    rejected=False
    try:contract.material_guard(material,invalid_material)
    except AssertionError:rejected=True
    assert rejected
    for name in ('bounded_quest_exceptions.py', 'quest_resource_seeds.py', 'prepare_vfs_expectations.py', 'probe_resource_graph.py', 'probe_vfs_full.py'):
        ast.parse((VFS / name).read_text(encoding='utf-8'), filename=name)
    result = {'status': 'SOURCE_GUARDS_AND_NEGATIVE_MATCHING_VERIFIED_TYPED_FINAL_GATE_PENDING',
        'real_author_gap_guard_cases_validated': positive,
        'unused_or_branch_cases_rejected_without_real_typed_xedit': 8,
        'new_consumer_different_field_kind_path_or_alternative_rejected': True,
        'FC_related_INFO_response_sound_tamper_rejected':True,
        'actual_material_reference_images_headers_stock_and_inline_fields_checked':True,
        'changed_singlepass_field_rejected':True,
        'syntax_checked_tools': 5,
        'scope': 'This test never fabricates an xEdit result. It does not claim the final loaded profile has passed the typed consumer gate or VFS.'}
    (OWN / 'bounded_contract_verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
