"""Read-only bounded representation proof and full-source descriptor inventory.

Keeps dispatched source-run reports unchanged. Uses only the metadata recorded
by that run and the nine supplemental snapshots; never reparses all sources.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parent.parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name, value):
    (OWN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')

def main():
    entries = [json.loads(line) for line in (OWN / 'entries.jsonl').read_text(encoding='utf8').splitlines()]
    supplement = json.loads((OWN / 'source_lighting_nonfinite.json').read_text(encoding='utf8'))
    supplemental = {row['path_key']: row for row in supplement['rows']}
    canonical_cases = []
    source_counter = collections.Counter()
    special_flags = {'UV2_0x4': [], 'LAND_0x80': [], 'EYEDATA_0x100': []}
    flags_counter = collections.Counter()
    numeric_rows = []
    unresolved = []
    for row in entries:
        compact = row.get('compact_snapshot')
        if compact is None:
            sub = supplemental[row['path_key']]
            compact = {**sub['snapshot_metadata'], 'shapes': sub['compact_shapes']}
        source_counter['files'] += 1
        source_counter['stream_' + str(compact['stream'])] += 1
        source_counter['shapes'] += compact['shape_count']
        source_counter['blocks'] += compact['block_count']
        for shape in compact['shapes']:
            source_counter['vertices'] += shape['vertex_count']
            source_counter['shape_type_' + shape['block_type']] += 1
            desc = shape['descriptor']
            if desc is None:
                continue
            flags = (desc['value'] >> 44) & 0xFFFF
            assert flags == shape['layout_flags']['vertex_attributes']
            flags_counter[str(flags)] += 1
            for label, mask in [('UV2_0x4', 4), ('LAND_0x80', 128), ('EYEDATA_0x100', 256)]:
                if flags & mask:
                    special_flags[label].append({'path_key': row['path_key'], 'source_sha256': row['source_sha256'], 'stream': compact['stream'], 'shape': {key: shape[key] for key in ('block_id', 'block_type', 'name', 'source_shader_block_id', 'paths', 'vertex_count')}, 'flags': flags, 'descriptor': desc})
        if row['path_key'] in supplemental and supplemental[row['path_key']]['nonfinite']:
            sub = supplemental[row['path_key']]
            groups = collections.defaultdict(list)
            for issue in sub['nonfinite']:
                parts = issue['typed_path'].split('/')
                groups[(issue['shape']['block_id'], parts[2], issue['float32_bits'])].append(issue)
            numeric_rows.append({'path_key': row['path_key'], 'source_sha256': row['source_sha256'], 'stream': compact['stream'], 'nonfinite_scalar_components': sub['nonfinite_count'],
                'groups': [{'shape_block_id': block, 'array': array, 'float32_bits': bits, 'scalar_components': len(issues), 'vertices': sorted({int(issue['typed_path'].split('/')[3]) for issue in issues}), 'shape': issues[0]['shape']} for (block, array, bits), issues in groups.items()], 'source_repaired': False})
        for issue in row['issues']:
            if issue['kind'] == 'SCHEMA_LAYOUT_OR_INPUT_EXCEPTION':
                sub = supplemental.get(row['path_key'])
                if not (sub and sub['schema_returned'] and sub['nonfinite'] and issue.get('exception_type') == 'ValueError' and issue.get('message') == 'Out of range float values are not JSON compliant: nan'):
                    unresolved.append({'path_key': row['path_key'], 'issue': issue})
            elif issue['kind'] not in ('CHILD_PATH_NOT_UNIQUE_OR_MISSING', 'ONE_TO_ONE_SHAPE_PAIRING_DISAGREEMENT'):
                unresolved.append({'path_key': row['path_key'], 'issue': issue})
        if row.get('parser_diagnostics'):
            unresolved.append({'path_key': row['path_key'], 'issue': {'kind': 'UNRESOLVED_PARSER_DIAGNOSTIC', 'messages': row['parser_diagnostics']}})
        if any(issue['kind'] == 'CHILD_PATH_NOT_UNIQUE_OR_MISSING' for issue in row['issues']):
            reference = json.loads(Path(row['typed_reference']).read_text(encoding='utf8'))
            proof = {'path_key': row['path_key'], 'source_sha256': row['source_sha256'], 'reference': row['typed_reference'], 'matches': [], 'issues': []}
            paired = []
            for expected in reference['shapes']:
                expected_paths = reference['nodes'][expected['key']]['paths']
                assert expected['key'] == ';'.join(expected_paths), 'Reference canonical key is not exact known path-list join'
                matches = [shape for shape in compact['shapes'] if shape['paths'] == expected_paths]
                if len(matches) != 1:
                    proof['issues'].append({'kind': 'PATH_LIST_PAIR_NOT_UNIQUE', 'expected_key': expected['key'], 'expected_paths': expected_paths, 'actual_block_ids': [shape['block_id'] for shape in matches]})
                    continue
                actual = matches[0]
                for actual_key, expected_key in [('name', 'name'), ('block_type', 'block_type'), ('vertex_count', 'vertices')]:
                    if actual[actual_key] != expected[expected_key]:
                        proof['issues'].append({'kind': 'PAIRED_SHAPE_FIELD_DISAGREEMENT', 'field': actual_key, 'expected_key': expected['key'], 'actual': actual[actual_key], 'expected': expected[expected_key]})
                paired.append(actual['block_id'])
                proof['matches'].append({'reference_key': expected['key'], 'reference_paths': expected_paths, 'actual_paths': actual['paths'], 'actual_block_id': actual['block_id'], 'source_shader_block_id': actual['source_shader_block_id'], 'name': actual['name'], 'vertex_count': actual['vertex_count'], 'shared_pointer': len(expected_paths) > 1})
            if collections.Counter(paired) != collections.Counter(shape['block_id'] for shape in compact['shapes']):
                proof['issues'].append({'kind': 'ONE_TO_ONE_BLOCK_PAIRING_NOT_PROVEN'})
            proof['status'] = 'EXACT_CANONICAL_PATH_LIST_REPRESENTATION_EQUIVALENCE_PASS' if not proof['issues'] else 'STOP_PATH_REVIEW'
            canonical_cases.append(proof)
            if proof['issues']:
                unresolved.append({'path_key': row['path_key'], 'issue': {'kind': 'UNRESOLVED_SHARED_POINTER_PATH_PAIRING', 'details': proof['issues']}})
    assert source_counter['files'] == 3741
    flag_summary = {label: {'shape_count': len(rows), 'file_count': len({row['path_key'] for row in rows}), 'dynamic_shape_count': sum(row['shape']['block_type'] == 'BSDynamicTriShape' for row in rows)} for label, rows in special_flags.items()}
    save('source_descriptor_special_flags.json', {'status': 'SOURCE_ALL_3741_DESCRIPTOR_FLAGS_INVENTORIED', 'source_counts': dict(source_counter), 'flag_histogram': dict(flags_counter), 'special_flag_summary': flag_summary, 'special_flags': special_flags,
        'eye_data_arrays_in_frozen_snapshot': False, 'UV2_semantic_array_in_frozen_snapshot': False,
        'limits': ['This reports flags only; it does not prove or permit eyeData/UV2 byte changes.', 'UV2 has no frozen BSVertexData array schema and requires STOP or explicit new complete schema evidence.', 'Parent adapter must separately snapshot and compare eyeData; dynamic derived changes require exact pinned CalcDynamicData proof.']})
    reader = BASE / 'pg_nif_reader.py'
    save('shared_pointer_path_representation.json', {'status': 'ALL_CANONICAL_PATH_LIST_CASES_PROVEN' if all(not case['issues'] for case in canonical_cases) else 'STOP_PATH_REVIEW', 'cases': canonical_cases,
        'reference_reader': str(reader), 'reference_reader_sha256': sha(reader), 'reference_expression': "keys={i:';'.join(paths[i]) for i in by_id}",
        'original_source_run_changed': False, 'source_models_modified': False})
    save('source_numeric_summary.json', {'status': 'SIX_ADDITIONAL_SOURCE_LIGHTING_NAN_PATHS_NOT_REPAIRED', 'paths': numeric_rows, 'nonfinite_paths': len(numeric_rows),
        'full_typed_details': str(OWN / 'source_lighting_nonfinite.json'), 'full_typed_details_sha256': sha(OWN / 'source_lighting_nonfinite.json'), 'source_repaired': False})
    final = {'status': 'ALL_3741_SCHEMA_IDENTITY_PROVEN_SIX_SOURCE_NUMERIC_LIMITATIONS_REQUIRE_DECISION' if not unresolved else 'STOP_UNRESOLVED_SCHEMA_OR_IDENTITY_REVIEW', 'source_counts': dict(source_counter), 'schema_returned_paths': 3741,
        'source_sha_count_block_and_exact_path_list_disagreements_after_proven_representation_translation': len(unresolved), 'unresolved': unresolved,
        'parser_diagnostic_paths': 0, 'new_source_lighting_nonfinite_paths': len(numeric_rows), 'canonical_shared_path_cases_proven': len(canonical_cases),
        'special_flag_summary': flag_summary, 'frozen_module_sha256': sha(OWN.parent / 'lighting_schema.py'), 'postprocessor_sha256': sha(__file__),
        'original_full_run_and_frozen_module_unchanged': True, 'source_models_modified': False,
        'limits': ['Six source tangent NaN paths are not approved for PG/output; this report does not silently exclude or repair them.', 'Original strict preflight reports retain all nine raw reviews. Three path-key representation cases are resolved only by exact one-to-one block/path-list proof in the separate evidence.', 'No normal unit-quality predicate was applied to source; actual output and selected recipe verification remain required.']}
    assert final['frozen_module_sha256'] == 'dc6c4d668395e7c59c61f53720f0fc6e71fdbad52432c2bb75902e126873b7b1'
    assert not json.loads((OWN / 'diagnostics.json').read_text(encoding='utf8'))
    save('final_source_review.json', final)
    print(json.dumps(final, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
