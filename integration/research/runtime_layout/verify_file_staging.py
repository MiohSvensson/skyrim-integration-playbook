"""Synthetic NTFS proof, confined to this report's own fixture directory."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from safe_files import assert_private, detach_for_write, digest, stage_private, stage_shared

BASE = Path(__file__).resolve().parent


def main():
    fixture = BASE / 'fixtures' / uuid.uuid4().hex
    fixture.mkdir(parents=True)
    original = fixture / 'source/meshes/probe.nif'
    original.parent.mkdir(parents=True)
    original.write_bytes(b'FIXTURE_ONLY_NO_GAME_RESOURCE\n'*31)
    source_hash = digest(original)
    linked = fixture / 'view/meshes/probe.nif'
    stage_shared(original, linked, fixture)
    shared_identity = os.path.samefile(original, linked)
    refused_shared_write = False
    try:
        assert_private(linked, fixture)
    except RuntimeError:
        refused_shared_write = True
    detached = detach_for_write(linked, fixture)
    assert_private(linked, fixture).write_bytes(b'PRIVATE_GENERATED_RESULT')
    source_unchanged = digest(original) == source_hash
    identity_separated = not os.path.samefile(original, linked)
    plugin = fixture / 'view/example.esp'
    stage_private(original, plugin, fixture)
    private_plugin = not os.path.samefile(original, plugin) and os.stat(plugin).st_nlink == 1
    escaped_refused = False
    try:
        stage_private(original, fixture.parent / 'outside-probe.ini', fixture)
    except ValueError:
        escaped_refused = True
    # Demonstrate shared-write behavior only on separate synthetic objects.
    risk_source = fixture / 'risk-source.dds'
    risk_source.write_bytes(b'original fixture bytes')
    risk_link = fixture / 'risk-link.dds'
    stage_shared(risk_source, risk_link, fixture)
    risk_link.write_bytes(b'shared fixture write')
    shared_writes_reach_source = risk_source.read_bytes() == b'shared fixture write'
    checks = {'initial_hardlink_identity': shared_identity,
              'private_guard_refused_link': refused_shared_write,
              'detach_performed': detached['detached'],
              'source_unchanged_after_private_edit': source_unchanged,
              'file_identity_separated_after_detach': identity_separated,
              'plugin_copy_is_independent': private_plugin,
              'outside_destination_refused': escaped_refused,
              'uncontrolled_shared_write_reaches_source': shared_writes_reach_source}
    assert all(checks.values()), checks
    result = {'utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS',
              'fixture': str(fixture), 'checks': checks,
              'scope': 'Only synthetic files under runtime_layout/fixtures. No source pack link, content or attributes changed. This is not a third-party process sandbox.'}
    (BASE/'file_staging_validation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
