"""Read-only exact-source preflight and independently parsed Glen patch check.

Does not construct a plugin or call xEdit. The typed fresh-reload marker is
required before reporting the combined static verification level.
"""
import argparse
import copy
import hashlib
import json
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parent / 'navmesh_patch'))
from verify_candidate import Plugin, navi_model, NAVI, fields
sys.path.insert(0, str(OUT.parent / 'forgotten_city_navigation'))
from analyze_navigation import View
from analyze import parent_cell, component

PATCH = 'database glenmoril navigation compatibility.esp'
WORLD = 'skyrim.esm|00003C'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def uses_path(model, key):
    value = model['precomputed']
    return value is not None and (any(key in path for path in value['paths']) or
                                any(row['navmesh'] == key for row in value['roadmarkers']))


def header_equal(actual, desired, context):
    for key in ('flags', 'vcs1', 'form_version', 'vcs2'):
        assert actual[key] == desired[key], f'{context}: header {key} changed'


def door_sort(doors):
    return sorted(doors, key=lambda door: (door['triangle'], door['door'], door['crc']))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--vanilla')
    parser.add_argument('--glen')
    parser.add_argument('--ak')
    parser.add_argument('--ancientland')
    parser.add_argument('--redbag')
    parser.add_argument('--candidate')
    parser.add_argument('--navi-winning')
    parser.add_argument('--typed-log')
    parser.add_argument('--output', default=str(OUT / 'source_preflight.json'))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    assert output.is_relative_to(OUT), 'Report must remain under this research directory'
    plan = json.loads((OUT / 'comparison.json').read_text(encoding='utf-8'))
    override = {'vanilla': args.vanilla, 'Glen': args.glen, 'AK': args.ak,
                'AncientLand': args.ancientland, 'RedBag': args.redbag}
    plugins = {}
    for key, reviewed in plan['sources'].items():
        path = Path(override[key] or reviewed['path'])
        assert sha(path) == reviewed['sha256'], f'{key}: file differs from reviewed source'
        plugins[key] = Plugin(path)
    navis = {key: navi_model(plugin, plugin.get(NAVI, 'NAVI')) for key, plugin in plugins.items()}
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'status': 'SOURCE_PREFLIGHT_PASS',
              'sources': {key: {'path': str(value.path), 'sha256': sha(value.path)}
                          for key, value in plugins.items()}, 'cases': []}
    expected_views = {}
    for case in plan['cases']:
        identity = case['identity']
        base = View(plugins[case['selected_base']], identity)
        source = View(plugins['Glen'], identity)
        assert base.model == case['base_geometry'], 'Reviewed base geometry differs'
        assert parent_cell(base.plugin, base.record) == case['base_parent_cell']
        expected_triangles = [list(row) for row in base.triangles]
        for mapping in case['mappings']:
            old, new = mapping['source_triangle'], mapping['base_triangle']
            matches = [i for i, triangle in enumerate(base.triangles)
                       if base.face_key(triangle) == source.face_key(source.triangles[old])]
            assert matches == [new], 'Exact unique door face mapping changed'
            assert base.winding_key(base.triangles[new]) == source.winding_key(source.triangles[old]), 'Door face winding differs'
            assert not base.triangles[new][6] & (8 | 512 | 1024)
            expected_triangles[new][6] |= 1024
            proof = component(base, new)
            assert not proof['errors'] and proof['water_triangles'] == 0
            reviewed = mapping['connected_component']
            for item in ('component_size', 'total_triangles', 'external_port_count', 'existing_door_exits', 'external_neighbors'):
                assert proof[item] == reviewed[item], f'Component proof changed: {item}'
        expected = copy.deepcopy(base.model)
        expected['triangles_sha256'] = hashlib.sha256(b''.join(struct.pack('<hhh hhh HH', *row) for row in expected_triangles)).hexdigest()
        assert expected['triangles_sha256'] == case['expected_triangles_sha256']
        expected['doors'] = case['expected_door_triangles']
        expected_views[identity] = (base, expected_triangles, expected)
        report['cases'].append({'id': identity, 'base': case['selected_base_plugin'],
                                'mapping': [{'source_triangle': row['source_triangle'], 'base_triangle': row['base_triangle'],
                                             'door': row['authored_door']['door']} for row in case['mappings']]})
    if args.candidate:
        assert args.navi_winning, '--navi-winning must witness the builder-logged prior final NAVI source'
        candidate = Plugin(args.candidate)
        assert candidate.name == PATCH, 'Unexpected candidate filename'
        assert candidate.header_flags & 0x200, 'ESL flag absent'
        assert {'skyrim.esm', 'glenmoril.esm', 'akskyrimunderground.esm', 'ancientland2.esp', "redbag's falkreath.esp"}.issubset(candidate.masters)
        desired_ids = [('NAVM', row['identity']) for row in plan['cases']]
        desired_ids += [('CELL', row['base_parent_cell']) for row in plan['cases']]
        desired_ids += [('WRLD', WORLD), ('NAVI', NAVI)]
        records = [record for record in candidate.records if record['signature'] != 'TES4']
        assert sorted((r['signature'], r['id']) for r in records) == sorted(desired_ids), 'Unexpected extra/new/missing records'
        for case in plan['cases']:
            identity = case['identity']
            actual = View(candidate, identity)
            base, triangles, desired = expected_views[identity]
            actual_model = copy.deepcopy(actual.model)
            actual_model['doors'] = door_sort(actual_model['doors'])
            desired = copy.deepcopy(desired)
            desired['doors'] = door_sort(desired['doors'])
            assert actual_model == desired, f'{identity}: unplanned NVNM change'
            assert actual.triangles == triangles, f'{identity}: exact triangle tuple mismatch'
            assert actual.vertices == base.vertices, f'{identity}: base vertex bytes changed'
            header_equal(actual.record, base.record, identity)
            # NAVM source contains NVNM only today; fail closed if additional fields appear.
            old_fields = fields(base.plugin.payload(base.record))
            new_fields = fields(candidate.payload(actual.record))
            assert [(sig, data) for sig, data in old_fields if sig != 'NVNM'] == [(sig, data) for sig, data in new_fields if sig != 'NVNM'], 'Unexpected non-NVNM payload field'
            assert parent_cell(candidate, actual.record) == case['base_parent_cell'], 'NAVM parent group changed'
        witness = Plugin(args.navi_winning)
        assert witness.path != candidate.path and witness.name != PATCH, 'Candidate cannot witness itself'
        original_record = witness.get(NAVI, 'NAVI')
        original = navi_model(witness, original_record)
        desired = copy.deepcopy(original)
        for case in plan['cases']:
            identity = case['identity']
            assert not uses_path(original, identity), 'Final NVPP references target; requires new review'
            assert identity not in original['deleted_navmeshes'], 'Final NVSI deletes target'
            info = copy.deepcopy(navis[case['selected_base']]['infos'][identity])
            source_info = navis['Glen']['infos'][identity]
            for mapping in case['mappings']:
                authored = mapping['authored_door']
                matches = [row for row in source_info['doors'] if row['door'] == authored['door']]
                assert len(matches) == 1 and matches[0]['crc'] == authored['crc']
                assert not any(row['door'] == authored['door'] for row in info['doors'])
                info['doors'].append(copy.deepcopy(matches[0]))
            desired['infos'][identity] = info
        actual_record = candidate.get(NAVI, 'NAVI')
        actual = navi_model(candidate, actual_record)
        # NVMI is a keyed table; door arrays are sorted arrays in the xEdit definition.
        for value in (desired, actual):
            for info in value['infos'].values():
                info['doors'].sort(key=lambda row: (row['door'], row['crc']))
        assert actual == desired, 'NAVI differs outside the three exact selected NVMI door arrays'
        header_equal(actual_record, original_record, 'NAVI')
        report.update(status='BINARY_PASS_TYPED_RELOAD_REQUIRED', candidate={
            'path': str(candidate.path), 'sha256': sha(candidate.path), 'records': records,
            'NAVI_source': str(witness.path), 'NAVI_source_sha256': sha(witness.path),
            'NAVM_geometry_preserved': True, 'NAVI_other_fields_preserved': True,
            'own_records': 0, 'new_door_links': 4,
            'CELL_WRLD_payload_validation': 'Requires the typed fresh reload, canonical FormID resolution, and all eight Check diagnostics in its log.'})
        if args.typed_log:
            log = Path(args.typed_log)
            text = log.read_text(encoding='utf-8-sig', errors='replace')
            assert 'GLEN_NAV_RELOAD_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0' in text
            assert 'BOUNDED_NAVM_STOP:' not in text
            assert f'GLEN_NAV_NAVI_SOURCE|{witness.path.name}' in text
            for row in plan['cases']:
                assert f"GLEN_NAV_CELL_SOURCE|{row['base_parent_cell'].split('|')[1]}|" in text
            assert 'GLEN_NAV_WRLD_SOURCE|' in text
            report['status'] = 'STATIC_BINARY_AND_TYPED_RELOAD_PASS'
            report['typed_log'] = {'path': str(log.resolve()), 'sha256': sha(log)}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'report': str(output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
