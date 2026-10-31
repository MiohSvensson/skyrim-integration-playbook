"""Read frozen private source copies only; the frozen lighting reader is unchanged.

Run sequentially so parser diagnostics remain attributable to each exact file.
All output is beneath this script's own directory. No recipe/unit-quality test
is applied to pre-existing lighting; this is schema/identity coverage only.
"""
import collections
import contextlib
import datetime
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import time
import traceback
sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
LIGHTING = OWN.parent
BASE = LIGHTING.parent
sys.path.insert(0, str(LIGHTING))
import lighting_schema as schema

FROZEN_MODULE_SHA = 'dc6c4d668395e7c59c61f53720f0fc6e71fdbad52432c2bb75902e126873b7b1'
SOURCE = BASE / 'pg_runs/nif_cpu_preflight_002/source_reaudit_ec513533833e/result.json'
EXCLUSIONS = BASE / 'PG_source_exclusion_review.json'
PRIVATE_BYTES = (BASE / 'pg_runs/nif_cpu_preflight_002/nif_inputs/bytes').resolve()
ARRAY_FIELDS = ('normals', 'tangents', 'bitangents', 'normal_encoding', 'tangent_encoding', 'bitangent_encoding', 'colors')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')

def json_write(name, value):
    (OWN / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')

def compare_identity(actual, reference):
    issues = []
    if actual['sha256'] != reference['sha256']:
        issues.append({'kind': 'SOURCE_SHA_DISAGREEMENT', 'actual': actual['sha256'], 'reference': reference['sha256']})
    if actual['stream'] != reference['stream']:
        issues.append({'kind': 'STREAM_DISAGREEMENT', 'actual': actual['stream'], 'reference': reference['stream']})
    if actual['block_count'] != len(reference['raw']['blocks']):
        issues.append({'kind': 'BLOCK_COUNT_DISAGREEMENT', 'actual': actual['block_count'], 'reference': len(reference['raw']['blocks'])})
    if actual['shape_count'] != len(reference['shapes']):
        issues.append({'kind': 'SHAPE_COUNT_DISAGREEMENT', 'actual': actual['shape_count'], 'reference': len(reference['shapes'])})
    actual_paths = collections.defaultdict(list)
    for shape in actual['shapes']:
        if not shape['paths']:
            issues.append({'kind': 'SHAPE_HAS_NO_SCENE_PATH', 'block_id': shape['block_id'], 'name': shape['name']})
        for path in shape['paths']:
            actual_paths[path].append(shape)
    paired_block_ids = []
    for ref in reference['shapes']:
        path = ref['key']
        candidates = actual_paths.get(path, [])
        if len(candidates) != 1:
            issues.append({'kind': 'CHILD_PATH_NOT_UNIQUE_OR_MISSING', 'path': path, 'reference': {'name': ref['name'], 'block_type': ref['block_type'], 'vertices': ref['vertices']}, 'actual_block_ids': [v['block_id'] for v in candidates]})
            continue
        found = candidates[0]
        paired_block_ids.append(found['block_id'])
        for field, ref_field in [('name', 'name'), ('block_type', 'block_type'), ('vertex_count', 'vertices')]:
            if found[field] != ref[ref_field]:
                issues.append({'kind': 'SHAPE_IDENTITY_OR_COUNT_DISAGREEMENT', 'path': path, 'field': field, 'actual': found[field], 'reference': ref[ref_field], 'block_id': found['block_id']})
        ref_node = reference.get('nodes', {}).get(path)
        expected_paths = ref_node.get('paths') if ref_node is not None else None
        if expected_paths is None:
            issues.append({'kind': 'REFERENCE_NODE_PATHS_UNAVAILABLE', 'path': path})
        elif found['paths'] != expected_paths:
            issues.append({'kind': 'SHARED_POINTER_CHILD_PATH_DISAGREEMENT', 'reference_key': path, 'block_id': found['block_id'], 'actual_paths': found['paths'], 'reference_paths': expected_paths})
    expected_paired_ids = [shape['block_id'] for shape in actual['shapes']]
    if collections.Counter(paired_block_ids) != collections.Counter(expected_paired_ids):
        issues.append({'kind': 'ONE_TO_ONE_SHAPE_PAIRING_DISAGREEMENT', 'paired_block_ids': paired_block_ids, 'actual_block_ids': expected_paired_ids})
    return issues

def compact_snapshot(actual):
    output = {k: v for k, v in actual.items() if k != 'shapes'}
    output['shapes'] = []
    for shape in actual['shapes']:
        one = {k: v for k, v in shape.items() if k not in ARRAY_FIELDS}
        one['lighting_arrays'] = {k: {'count': len(shape[k]), 'sha256': hashlib.sha256(encoded(shape[k])).hexdigest()} for k in ARRAY_FIELDS}
        output['shapes'].append(one)
    return output

def main():
    started = time.monotonic()
    module = LIGHTING / 'lighting_schema.py'
    assert sha(module) == FROZEN_MODULE_SHA, 'Frozen lighting module changed; stop before processing'
    source_bytes = SOURCE.read_bytes()
    source = json.loads(source_bytes)
    exclusions = json.loads(EXCLUSIONS.read_text(encoding='utf8'))
    assert hashlib.sha256(source_bytes).hexdigest() == exclusions['source_proof_sha256'], 'Exclusion proof/source mismatch'
    entries = source['entries']
    excluded = {row['path_key']: row for row in exclusions['proposed_exclusions']}
    assert len(entries) == 3842 and len(excluded) == 101
    for key, row in excluded.items():
        assert key in entries and entries[key]['sha256'] == row['source_sha256'], 'Exact exclusion path/SHA mismatch: ' + key
    selected = {k: v for k, v in entries.items() if k not in excluded}
    assert len(selected) == 3741
    excluded_rows = [{'path_key': k, 'sha256': v['source_sha256'], 'reason': v['reason'], 'source_repaired': False} for k, v in excluded.items()]
    json_write('excluded.json', excluded_rows)
    failures = []
    counts = collections.Counter()
    diagnostics = []
    basenode_cases = []
    for key, row in selected.items():
        ref = json.loads(Path(row['typed_snapshot']).read_text(encoding='utf8'))
        if ref['raw']['block_types'].get('BSBlastNode', 0):
            basenode_cases.append({'path_key': key, 'source_sha256': row['sha256'], 'BSBlastNode_count': ref['raw']['block_types']['BSBlastNode']})
    json_write('BSBlastNode_cases.json', basenode_cases)
    progress_path = OWN / 'progress.json'
    with (OWN / 'entries.jsonl').open('w', encoding='utf8') as stream:
        for ordinal, (key, row) in enumerate(selected.items(), 1):
            result = {'ordinal': ordinal, 'path_key': key, 'source_sha256': row['sha256'], 'input': row['snapshot'], 'typed_reference': row['typed_snapshot'], 'issues': []}
            log_buffer = io.StringIO()
            handler = logging.StreamHandler(log_buffer)
            logging.getLogger().addHandler(handler)
            std_buffer = io.StringIO()
            try:
                path = Path(row['snapshot']).resolve()
                assert path.is_relative_to(PRIVATE_BYTES), 'Input is outside frozen private copy directory'
                before = path.stat()
                assert before.st_nlink == 1, f'Frozen source is not a private single-link copy: {before.st_nlink}'
                typed_path = Path(row['typed_snapshot'])
                if sha(typed_path) != row['typed_snapshot_sha256']:
                    raise AssertionError('Typed reference SHA changed')
                reference = json.loads(typed_path.read_text(encoding='utf8'))
                with contextlib.redirect_stderr(std_buffer), contextlib.redirect_stdout(std_buffer):
                    actual = schema.snapshot(path)
                after = path.stat()
                assert (before.st_size, before.st_mtime_ns, before.st_nlink) == (after.st_size, after.st_mtime_ns, after.st_nlink), 'Source changed during read'
                if actual['sha256'] != row['sha256']:
                    result['issues'].append({'kind': 'FROZEN_INPUT_SHA_CHANGED', 'actual': actual['sha256']})
                result['issues'].extend(compare_identity(actual, reference))
                result['full_snapshot_canonical_json_sha256'] = hashlib.sha256(encoded(actual)).hexdigest()
                result['full_snapshot_hash_definition'] = 'json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(comma,colon),allow_nan=False), UTF8'
                result['compact_snapshot'] = compact_snapshot(actual)
                result['source_private_link_count'] = before.st_nlink
                counts['shapes'] += actual['shape_count']
                counts['vertices'] += sum(s['vertex_count'] for s in actual['shapes'])
                counts['blocks'] += actual['block_count']
                counts['stream_' + str(actual['stream'])] += 1
                for shape in actual['shapes']:
                    counts['shape_type_' + shape['block_type']] += 1
            except Exception as error:
                result['issues'].append({'kind': 'SCHEMA_LAYOUT_OR_INPUT_EXCEPTION', 'exception_type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
            finally:
                logging.getLogger().removeHandler(handler)
                handler.close()
            log_text = log_buffer.getvalue() + std_buffer.getvalue()
            if log_text:
                result['parser_diagnostics'] = log_text
                diagnostics.append({'path_key': key, 'messages': log_text})
            result['status'] = 'LIGHTING_SCHEMA_IDENTITY_PASS' if not result['issues'] else 'STOP_SCHEMA_OR_IDENTITY_REVIEW'
            if result['issues']:
                failures.append({'path_key': key, 'source_sha256': row['sha256'], 'issues': result['issues']})
                counts['failed'] += 1
            else:
                counts['passed'] += 1
            counts['attempted'] += 1
            stream.write(json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n')
            stream.flush()
            if ordinal % 25 == 0 or ordinal == len(selected):
                progress = {'attempted': ordinal, 'expected': len(selected), 'passed': counts['passed'], 'failed': counts['failed'], 'elapsed_seconds': round(time.monotonic() - started, 3), 'last_path_key': key}
                progress_path.write_text(json.dumps(progress, indent=2) + '\n', encoding='utf8')
                print(json.dumps(progress), flush=True)
    assert sha(module) == FROZEN_MODULE_SHA, 'Frozen module changed during audit'
    json_write('failures.json', failures)
    json_write('diagnostics.json', diagnostics)
    summary = {
        'status': 'ALL_3741_LIGHTING_SCHEMA_IDENTITY_PASS' if not failures else 'ALL_3741_ATTEMPTED_SCHEMA_OR_IDENTITY_REVIEW_REQUIRED',
        'expected_formal_candidates': len(selected), 'excluded_paths': len(excluded), 'source_total_paths': len(entries),
        'counts': dict(counts), 'failures': len(failures), 'parser_diagnostics_paths': len(diagnostics),
        'BSBlastNode_paths': len(basenode_cases),
        'module': str(module), 'module_sha256': sha(module), 'runner_sha256': sha(__file__),
        'source_proof': str(SOURCE), 'source_proof_sha256': hashlib.sha256(source_bytes).hexdigest(),
        'exclusion_contract': str(EXCLUSIONS), 'exclusion_contract_sha256': sha(EXCLUSIONS),
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'geometry_or_lighting_quality_claimed': False, 'source_models_modified': False,
        'native_helper_used': False, 'GUI_game_MO2_or_PG_launched': False,
        'limits': ['This tests complete schema field access and exact source identity/count/child-path agreement only; source normal unit lengths are not graded.',
                   'The 101 exact source exclusions remain unmodified and unrepaired. No relaxed parser was used for included inputs.',
                   'Names are metadata only. Pairing uses exact real child paths and one-to-one actual shape block identity, preserving duplicates.',
                   'No author recipe or final PG output is tested by this source-only preflight.']}
    json_write('summary.json', summary)
    print(json.dumps({k: summary[k] for k in ('status', 'counts', 'failures', 'elapsed_seconds')}, indent=2), flush=True)

if __name__ == '__main__':
    main()
