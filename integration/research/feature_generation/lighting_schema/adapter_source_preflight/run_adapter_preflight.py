"""Resumable read-only closure of the frozen adapter's schema_snapshot.

Only private frozen input bytes are read. Every artifact stays beside this
script. No recipe, unit-normal quality gate, PG, native helper, save or GUI.
"""
import ast
import collections
import contextlib
import datetime
import hashlib
import importlib
import io
import json
import logging
import math
import os
from pathlib import Path
import struct
import sys
import time
import traceback
sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parent.parent
DB = BASE.parents[2]
ADAPTER_PATH = BASE / 'pg_nif_lighting_validate.py'
SCHEMA_PATH = OWN.parent / 'lighting_schema.py'
SOURCE_PATH = BASE / 'pg_runs/nif_cpu_preflight_002/source_reaudit_ec513533833e/result.json'
EXCLUSIONS_PATH = BASE / 'PG_source_exclusion_review_107.json'
PRIVATE_BYTES = (BASE / 'pg_runs/nif_cpu_preflight_002/nif_inputs/bytes').resolve()
ADAPTER_SHA = '1ada7041ead76321e1ae12327b4fb87b094a7c71bb43c78bd8763e1c2c068297'
SCHEMA_SHA = 'dc6c4d668395e7c59c61f53720f0fc6e71fdbad52432c2bb75902e126873b7b1'
ARRAYS = ('normals', 'tangents', 'bitangents', 'normal_encoding', 'tangent_encoding', 'bitangent_encoding', 'colors')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')

def atomic_json(path, value):
    path = Path(path).resolve()
    assert path.is_relative_to(OWN), 'Output escaped owned directory'
    temp = path.with_name(path.name + '.partial')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    os.replace(temp, path)

def pinned_import_files():
    files = {}
    modules = {}
    for name, module in sorted(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        path = Path(filename).resolve()
        if not path.is_file():
            continue
        # Pin all imported local/author code plus the exact Python stdlib and
        # extension modules used by this process. No blocked helper is read.
        if path == Path(__file__).resolve():
            continue
        files[str(path)] = sha(path)
        modules[name] = str(path)
    dll = Path(importlib.import_module('pyn.niflydll').nifly._name).resolve()
    assert dll.is_relative_to(BASE / 'primary_sources/PyNifly'), 'Unexpected native reader DLL provider'
    files[str(dll)] = sha(dll)
    files[str(Path(sys.executable).resolve())] = sha(sys.executable)
    return files, modules, str(dll)

def watched_evidence(import_files):
    files = dict(import_files)
    # Include potential lazy author imports as well as modules already loaded.
    # These are exact official parser trees, not any native helper directory.
    for root in (BASE / 'primary_sources/NiftoolsAddon/io_scene_niftools/dependencies/nifgen',
                 BASE / 'primary_sources/PyNifly/addon/io_scene_nifly/pyn'):
        for path in root.rglob('*.py'):
            files[str(path.resolve())] = sha(path)
    for path in (ADAPTER_PATH, SCHEMA_PATH, SOURCE_PATH, EXCLUSIONS_PATH, Path(__file__).resolve(),
                 BASE / 'PG_serializer_derivation_proof.json', BASE / 'primary_sources/NiftoolsAddon/manifest.json',
                 OWN.parent / 'delivery.json', OWN.parent / 'full_source_preflight/shared_pointer_path_representation.json'):
        files[str(path.resolve())] = sha(path)
    proof = json.loads((BASE / 'PG_serializer_derivation_proof.json').read_text(encoding='utf8'))
    for row in proof['files']:
        path = Path(row['path']).resolve()
        assert sha(path) == row['sha256'], 'Pinned serializer evidence changed: ' + str(path)
        files[str(path)] = row['sha256']
    addon = json.loads((BASE / 'primary_sources/NiftoolsAddon/manifest.json').read_text(encoding='utf8'))
    # The zip is provenance, not loaded code. Find the already downloaded exact
    # author release archive without reading any unrelated helper/executable.
    addon_zips = []
    for root in (BASE / 'primary_sources', BASE / 'primary_sources/NiftoolsAddon'):
        for path in root.glob('*.zip'):
            if (root.name == 'NiftoolsAddon' or 'niftool' in path.name.lower()) and sha(path) == addon['zip_sha256']:
                addon_zips.append(str(path.resolve()))
                files[str(path.resolve())] = addon['zip_sha256']
    assert addon_zips, 'Exact official NifTools provenance ZIP not found'
    binary_manifest_path = BASE / 'primary_sources/PyNifly/binary_manifest.json'
    binary_manifest = json.loads(binary_manifest_path.read_text(encoding='utf8'))
    binary_zip = BASE / 'primary_sources/PyNifly/io_scene_nifly.zip'
    assert sha(binary_zip) == binary_manifest['asset_sha256']
    files[str(binary_manifest_path.resolve())] = sha(binary_manifest_path)
    files[str(binary_zip.resolve())] = binary_manifest['asset_sha256']
    return files, addon_zips

def assert_no_drift(files):
    changed = []
    for filename, expected in files.items():
        try:
            actual = sha(filename)
        except Exception as error:
            actual = repr(error)
        if actual != expected:
            changed.append({'path': filename, 'expected_sha256': expected, 'actual': actual})
    if changed:
        atomic_json(OWN / 'DRIFT_STOP.json', {'status': 'STOP_PINNED_IMPORT_OR_EVIDENCE_DRIFT', 'changed': changed})
        raise RuntimeError('Pinned imports/evidence drift; stopped: ' + repr(changed[:3]))

def compare_identity(actual, reference):
    issues = []
    for field in ('sha256', 'stream'):
        if actual[field] != reference[field]:
            issues.append({'kind': 'SOURCE_IDENTITY_DISAGREEMENT', 'field': field, 'actual': actual[field], 'reference': reference[field]})
    if actual['block_count'] != len(reference['raw']['blocks']):
        issues.append({'kind': 'BLOCK_COUNT_DISAGREEMENT'})
    if len(actual['shapes']) != len(reference['shapes']):
        issues.append({'kind': 'SHAPE_COUNT_DISAGREEMENT'})
    actual_by_pathlist = collections.defaultdict(list)
    for shape in actual['shapes']:
        actual_by_pathlist[tuple(shape['paths'])].append(shape)
    paired = []
    for expected in reference['shapes']:
        node = reference['nodes'].get(expected['key'])
        if node is None:
            issues.append({'kind': 'REFERENCE_NODE_MISSING', 'key': expected['key']})
            continue
        paths = node['paths']
        if expected['key'] != ';'.join(paths):
            issues.append({'kind': 'UNKNOWN_REFERENCE_KEY_REPRESENTATION', 'key': expected['key'], 'paths': paths})
            continue
        matches = actual_by_pathlist.get(tuple(paths), [])
        if len(matches) != 1:
            issues.append({'kind': 'PATH_LIST_NOT_ONE_TO_ONE', 'expected_paths': paths, 'actual_block_ids': [shape['block_id'] for shape in matches]})
            continue
        shape = matches[0]
        paired.append(shape['block_id'])
        for field, expected_field in [('name', 'name'), ('block_type', 'block_type'), ('vertex_count', 'vertices')]:
            if shape[field] != expected[expected_field]:
                issues.append({'kind': 'SHAPE_IDENTITY_OR_COUNT_DISAGREEMENT', 'key': expected['key'], 'field': field, 'actual': shape[field], 'reference': expected[expected_field]})
    if collections.Counter(paired) != collections.Counter(shape['block_id'] for shape in actual['shapes']):
        issues.append({'kind': 'FULL_SHAPE_BLOCK_PAIRING_DISAGREEMENT'})
    return issues

def summarize_snapshot(actual):
    compact = {key: value for key, value in actual.items() if key != 'shapes'}
    compact['shapes'] = []
    for shape in actual['shapes']:
        one = {key: value for key, value in shape.items() if key not in ARRAYS}
        one['lighting_arrays'] = {key: {'count': len(shape[key]), 'sha256': hashlib.sha256(canonical(shape[key])).hexdigest()} for key in ARRAYS}
        # Retain the complete supplemental bits/slots, not only their hashes.
        # Detect a gap in supplementary finite checking separately, without
        # changing the frozen adapter or granting an allowance.
        compact['shapes'].append(one)
    return compact

def main():
    started = time.monotonic()
    assert sha(ADAPTER_PATH) == ADAPTER_SHA and sha(SCHEMA_PATH) == SCHEMA_SHA
    sys.path.insert(0, str(BASE))
    adapter = importlib.import_module('pg_nif_lighting_validate')
    assert sha(ADAPTER_PATH) == ADAPTER_SHA and sha(SCHEMA_PATH) == SCHEMA_SHA
    assert Path(adapter.__file__).resolve() == ADAPTER_PATH.resolve()
    source = json.loads(SOURCE_PATH.read_text(encoding='utf8'))
    exclusions = json.loads(EXCLUSIONS_PATH.read_text(encoding='utf8'))
    assert sha(SOURCE_PATH) == exclusions['source_proof_sha256']
    excluded = {row['path_key']: row for row in exclusions['proposed_exclusions']}
    assert len(source['entries']) == 3842 and len(excluded) == 107
    for key, row in excluded.items():
        assert source['entries'][key]['sha256'] == row['source_sha256'], 'Exact exclusion mismatch ' + key
    selected = {key: row for key, row in source['entries'].items() if key not in excluded}
    assert len(selected) == 3735
    imported_files, modules, dll = pinned_import_files()
    files, addon_zips = watched_evidence(imported_files)
    source_code = ADAPTER_PATH.read_text(encoding='utf8')
    function = next(node for node in ast.parse(source_code).body if isinstance(node, ast.FunctionDef) and node.name == 'schema_snapshot')
    receipt = {'status': 'FROZEN_READ_ONLY_SCHEMA_ADAPTER_SOURCE_CPU_PREFLIGHT', 'expected_paths': len(selected), 'excluded_paths': len(excluded),
               'adapter': str(ADAPTER_PATH), 'adapter_sha256': ADAPTER_SHA, 'schema_sha256': SCHEMA_SHA,
               'schema_snapshot_exact_source_sha256': hashlib.sha256(ast.get_source_segment(source_code, function).encode('utf8')).hexdigest(),
               'watched_files_sha256': files, 'imported_modules': modules, 'author_PyNifly_DLL_loaded_by_adapter_import': dll,
               'author_NifTools_zip_paths': addon_zips, 'python': sys.version, 'python_executable': sys.executable,
               'source_selection_sha256': hashlib.sha256(canonical({key: row['sha256'] for key, row in selected.items()})).hexdigest(),
               'write_directory': str(OWN), 'unit_normal_quality_predicate_applied': False, 'PG_GUI_or_game_launched': False,
               'blocked_native_helper_used': False}
    receipt_path = OWN / 'receipt.json'
    if receipt_path.exists():
        old = json.loads(receipt_path.read_text(encoding='utf8'))
        assert old == receipt, 'Resume receipt differs; preserve existing evidence and stop'
    else:
        atomic_json(receipt_path, receipt)
    assert_no_drift(files)
    rows_dir = OWN / 'rows'
    rows_dir.mkdir(exist_ok=True)
    counts = collections.Counter()
    failures = []
    resumed = 0
    for ordinal, (key, source_row) in enumerate(selected.items(), 1):
        filename = rows_dir / (str(ordinal).zfill(4) + '_' + source_row['sha256'] + '.json')
        if filename.exists():
            row = json.loads(filename.read_text(encoding='utf8'))
            assert row['path_key'] == key and row['source_sha256'] == source_row['sha256'] and row['receipt_sha256'] == sha(receipt_path), 'Resume row identity changed'
            resumed += 1
        else:
            row = {'ordinal': ordinal, 'path_key': key, 'source_sha256': source_row['sha256'], 'input': source_row['snapshot'],
                   'typed_reference': source_row['typed_snapshot'], 'receipt_sha256': sha(receipt_path), 'issues': []}
            log = io.StringIO()
            handler = logging.StreamHandler(log)
            handler.setLevel(logging.WARNING)
            logging.getLogger().addHandler(handler)
            printed = io.StringIO()
            try:
                assert sha(ADAPTER_PATH) == ADAPTER_SHA and sha(SCHEMA_PATH) == SCHEMA_SHA, 'Core adapter/schema drift'
                path = Path(source_row['snapshot']).resolve()
                assert path.is_relative_to(PRIVATE_BYTES)
                before = path.stat()
                assert before.st_nlink == 1, 'Frozen input is not a private single-link copy'
                reference_path = Path(source_row['typed_snapshot'])
                assert sha(reference_path) == source_row['typed_snapshot_sha256']
                reference = json.loads(reference_path.read_text(encoding='utf8'))
                with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
                    actual = adapter.schema_snapshot(path)
                after = path.stat()
                assert (before.st_nlink, before.st_size, before.st_mtime_ns) == (after.st_nlink, after.st_size, after.st_mtime_ns)
                assert sha(path) == source_row['sha256'] == actual['sha256'], 'Input SHA drift'
                row['issues'].extend(compare_identity(actual, reference))
                for shape in actual['shapes']:
                    extra = shape['supplemental_vertex_payload']
                    for field in ('eye_data', 'dynamic_w'):
                        for index, bits in enumerate(extra.get(field, [])):
                            if not math.isfinite(struct.unpack('<f', bytes.fromhex(bits))[0]):
                                row['issues'].append({'kind': 'NONFINITE_SUPPLEMENTAL_STORED_FLOAT', 'shape_block_id': shape['block_id'], 'paths': shape['paths'], 'field': field, 'vertex': index, 'float32_bits': bits})
                row['snapshot_sha256'] = hashlib.sha256(canonical(actual)).hexdigest()
                row['snapshot_hash_definition'] = 'Sorted-key compact UTF8 JSON, allow_nan=False, full returned adapter schema_snapshot object'
                row['compact_snapshot'] = summarize_snapshot(actual)
                row['source_private_link_count'] = before.st_nlink
            except Exception as error:
                row['issues'].append({'kind': 'ADAPTER_SCHEMA_LAYOUT_OR_INPUT_EXCEPTION', 'exception_type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
            finally:
                logging.getLogger().removeHandler(handler)
                handler.close()
            diagnostics = log.getvalue() + printed.getvalue()
            if diagnostics:
                row['issues'].append({'kind': 'PARSER_DIAGNOSTIC_OR_OUTPUT', 'messages': diagnostics})
            row['status'] = 'STRICT_ADAPTER_SOURCE_SCHEMA_IDENTITY_PASS' if not row['issues'] else 'STOP_SOURCE_SCHEMA_ADAPTER_REVIEW'
            atomic_json(filename, row)
        counts['attempted'] += 1
        if row['issues']:
            counts['failed'] += 1
            failures.append({'path_key': key, 'source_sha256': source_row['sha256'], 'row': str(filename), 'issues': row['issues']})
        else:
            counts['passed'] += 1
        if 'compact_snapshot' in row:
            compact = row['compact_snapshot']
            counts['stream_' + str(compact['stream'])] += 1
            counts['shapes'] += compact['shape_count']
            counts['vertices'] += sum(shape['vertex_count'] for shape in compact['shapes'])
            for shape in compact['shapes']:
                counts['shape_type_' + shape['block_type']] += 1
                counts['with_stored_texture_slots'] += shape['stored_texture_slots'] is not None
                counts['with_eye_data'] += 'eye_data' in shape['supplemental_vertex_payload']
                counts['with_dynamic_w'] += 'dynamic_w' in shape['supplemental_vertex_payload']
                counts['with_unused_w'] += 'unused_w' in shape['supplemental_vertex_payload']
                counts['with_normal_padding'] += 'normal_padding' in shape['supplemental_vertex_payload']
        if ordinal % 50 == 0 or ordinal == len(selected):
            assert_no_drift(files)
            progress = {'attempted': ordinal, 'expected': len(selected), 'passed': counts['passed'], 'failed': counts['failed'], 'resumed_rows': resumed,
                        'elapsed_seconds_this_process': round(time.monotonic() - started, 3), 'last_path_key': key}
            atomic_json(OWN / 'progress.json', progress)
            print(json.dumps(progress), flush=True)
    assert_no_drift(files)
    atomic_json(OWN / 'failures.json', failures)
    summary = {'status': 'ALL_3735_STRICT_COMPLETE_ADAPTER_SOURCE_CPU_PASS' if not failures else 'ALL_3735_ATTEMPTED_ADAPTER_SOURCE_GAPS_REVIEW',
               'counts': dict(counts), 'failure_paths': len(failures), 'receipt': str(receipt_path), 'receipt_sha256': sha(receipt_path),
               'elapsed_seconds_this_process': round(time.monotonic() - started, 3), 'resumed_rows': resumed,
               'completed_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'all_watched_import_and_author_evidence_sha_rechecked': True,
               'runtime_or_profile_proof': False, 'sources_modified': False, 'normal_unit_quality_test_applied': False,
               'limits': ['Strict CPU source parsing/finite/padding/material-slot and CAPI identity/count/path closure only.',
                          'No profile/VFS/runtime/rendering or actual PG output is proven.',
                          'Existing source values and all107 exact exclusions remain untouched. Source normal unit quality is not graded.']}
    atomic_json(OWN / 'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == '__main__':
    main()
