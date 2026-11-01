"""Load and verify the native input-model context for both resource audits."""
import json
from pathlib import Path


def load_verified(path, delta_path, digest):
    path = Path(path).resolve(strict=True)
    delta_path = Path(delta_path).resolve(strict=True)
    delta = json.loads(delta_path.read_text('utf-8'))
    report = json.loads(path.read_text('utf-8'))
    assert report['schema'] == 'skyrim.synthesis.input_models.v1'
    assert report['status'] == 'INPUT_MODEL_CONTEXT_VERIFIED'
    assert report['candidate_sha256'] == delta['candidate']['sha256']
    assert report['arma_delta_sha256'] == digest(delta_path)
    assert report['source_key_count'] == len(delta['affected_source_keys'])
    assert report['synthesis_not_loaded'] and not report['game_launched']
    for filename, pinned in [('result.json', report['native_result_sha256']),
                             ('logs/xedit.log', report['native_log_sha256']),
                             ('prepared.json', report['native_prepared_sha256']),
                             ('input_inventory.json', report['input_inventory_sha256'])]:
        assert digest(Path(report['native_task']) / filename) == pinned, 'Input model evidence changed: ' + filename
    fields = {key: {tag: value.encode('utf-8') for tag, value in row.items()}
              for key, row in report['source_fields'].items()}
    assert set(fields) == set(delta['affected_source_keys'])
    assert all(set(row) == {'MOD2', 'MOD3', 'MOD4', 'MOD5'} for row in fields.values())
    return fields, report
