"""Supplemental strict numeric locations in source lighting, without repairs.

Run after the main full-source pass. Only exception paths are re-read. Unknown
schema errors remain errors; this does not replace or relax the frozen reader.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
sys.path.insert(0, str(OWN.parent))
import lighting_schema as schema

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def bad_values(value, path=''):
    result = []
    if isinstance(value, float) and not math.isfinite(value):
        result.append({'typed_path': path, 'float32_bits': struct.pack('<f', value).hex(), 'kind': 'NaN' if math.isnan(value) else 'PositiveInfinity' if value > 0 else 'NegativeInfinity'})
    elif isinstance(value, dict):
        for key, child in value.items():
            result.extend(bad_values(child, path + '/' + str(key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            result.extend(bad_values(child, path + '/' + str(index)))
    return result

def report_representation(value):
    """Encode observed nonfinite fields explicitly; never change parsed values.

    This is a report/hash format only and grants no source/output allowance.
    """
    if isinstance(value, float) and not math.isfinite(value):
        return {'observed_nonfinite_float32_bits': struct.pack('<f', value).hex()}
    if isinstance(value, dict):
        return {key: report_representation(child) for key, child in value.items()}
    if isinstance(value, list):
        return [report_representation(child) for child in value]
    return value

def report_hash(value):
    return hashlib.sha256(json.dumps(report_representation(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')).hexdigest()

def main():
    results = []
    for line in (OWN / 'entries.jsonl').read_text(encoding='utf8').splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not row['issues']:
            continue
        one = {'path_key': row['path_key'], 'source_sha256': row['source_sha256'], 'input': row['input'], 'nonfinite': []}
        try:
            snapshot = schema.snapshot(row['input'])
            assert snapshot['sha256'] == row['source_sha256']
            one['schema_returned'] = True
            one['snapshot_metadata'] = {key: snapshot[key] for key in ('sha256', 'stream', 'block_count', 'shape_count')}
            one['tagged_report_snapshot_sha256'] = report_hash(snapshot)
            one['tagged_report_hash_definition'] = 'Canonical compact sorted-key UTF8 JSON; observed nonfinite float values are tagged by exact float32 bits. This reporting format does not validate or repair nonfinite source fields.'
            arrays = ('normals', 'tangents', 'bitangents', 'normal_encoding', 'tangent_encoding', 'bitangent_encoding', 'colors')
            one['compact_shapes'] = []
            for index, shape in enumerate(snapshot['shapes']):
                compact = {key: value for key, value in shape.items() if key not in arrays}
                compact['lighting_arrays'] = {key: {'count': len(shape[key]), 'tagged_report_sha256': report_hash(shape[key])} for key in arrays}
                one['compact_shapes'].append(compact)
                for found in bad_values(shape, 'shapes/' + str(index)):
                    found['shape'] = {key: shape[key] for key in ('block_id', 'block_type', 'name', 'source_shader_block_id', 'paths', 'vertex_count', 'descriptor')}
                    one['nonfinite'].append(found)
            one['nonfinite_count'] = len(one['nonfinite'])
            one['source_repaired'] = False
        except Exception as error:
            one['schema_returned'] = False
            one['exception'] = {'type': type(error).__name__, 'message': str(error)}
        results.append(one)
    report = {'status': 'SOURCE_LIGHTING_NUMERIC_REVIEW_NO_REPAIRS', 'rows': results, 'nonfinite_paths': sum(bool(x['nonfinite']) for x in results), 'source_models_modified': False,
              'frozen_module_sha256': sha(OWN.parent / 'lighting_schema.py'), 'script_sha256': sha(__file__),
              'limits': ['This exposes source defects without repairing, suppressing, or permitting them in PG output.', 'No unit-normal quality predicate is used. Nonfinite values are reported by exact typed field and raw float32 encoding.']}
    (OWN / 'source_lighting_nonfinite.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({'nonfinite_paths': report['nonfinite_paths'], 'rows': [{k: v for k, v in r.items() if k in ('path_key', 'source_sha256', 'schema_returned', 'nonfinite_count', 'exception')} for r in results]}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
