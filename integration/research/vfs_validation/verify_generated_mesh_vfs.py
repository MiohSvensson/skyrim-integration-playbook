"""Verify the exact 23-file supplement and inherited-gap boundary through MO2."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vfs_common as vfs
from nif_resource_inventory import inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('installed')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual usvfs injection is required'
    installed_path = Path(args.installed).resolve(strict=True)
    receipt = json.loads(installed_path.read_text('utf-8'))
    assert receipt['status'] == 'INSTALLED_PENDING_ACTUAL_VFS' and receipt['accepted'] is False
    assert receipt['unit'] == 'generated_mesh_resources_v1'
    manifest_path = Path(receipt['manifest']['path']).resolve(strict=True)
    assert vfs.digest(manifest_path) == receipt['manifest']['sha256']
    manifest = json.loads(manifest_path.read_text('utf-8'))
    input_path = Path(manifest['input_models']['path']).resolve(strict=True)
    assert vfs.digest(input_path) == manifest['input_models']['sha256']
    inputs = json.loads(input_path.read_text('utf-8'))
    assert inputs['candidate_sha256'] == manifest['candidate']['sha256']
    assert len(receipt['files']) == manifest['resource_count'] == 23
    layer = vfs.DEFAULT_TARGET / 'mods/ZZ83 Verified generated item and quest assets'
    for profile, digest in receipt['controls'].items():
        assert vfs.digest(vfs.DEFAULT_TARGET / profile) == digest, profile
    rows = []
    for file in receipt['files']:
        destination = Path(file['path']).resolve(strict=True)
        relative = destination.relative_to(layer)
        runtime = vfs.DEFAULT_TARGET / 'Game/Data' / relative
        runtime_id = vfs.file_identity(runtime)
        installed_id = vfs.file_identity(destination)
        sha = vfs.digest(runtime)
        assert runtime_id == installed_id and sha == file['sha256'] == vfs.digest(destination)
        assert destination.stat().st_nlink == 1 and len(runtime.read_bytes()) == file['bytes']
        if relative.suffix.casefold() == '.nif':
            parsed = inventory(runtime)
            assert any(block.get('textures') for block in parsed['blocks'])
            for block in parsed['blocks']:
                for texture in block.get('textures', []):
                    if texture:
                        path = vfs.asset_key(texture, kind='texture')
                        assert path
                        vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / path)
        rows.append({'path': relative.as_posix(), 'runtime_file_id': runtime_id,
                     'installed_file_id': installed_id, 'sha256': sha, 'bytes': file['bytes']})
    for row in manifest['resources']:
        if 'runtime_file_id' in row:
            assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / row['path']) == row['runtime_file_id']
    for gap in manifest['inherited_source_gaps']:
        assert gap['disposition'] == 'INHERITED_UNCHANGED_SOURCE_GAP_RETAINED_NO_ALIAS'
        original = inputs['source_fields'][gap['source_key']][gap['field']]
        assert vfs.asset_key(original, kind='model') == gap['path']
        try:
            vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / gap['path'])
        except OSError as exc:
            assert getattr(exc, 'winerror', None) in (2, 3)
        else:
            raise AssertionError('An unreviewed replacement appeared for the inherited gap')
    report = {'schema': 'skyrim.generated_mesh_vfs_proof.v1', 'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_GENERATED_MESH_RUNTIME_RESOURCES', 'usvfs': True, 'resources': rows,
              'input_models_sha256': vfs.digest(input_path), 'inherited_source_gaps': manifest['inherited_source_gaps'],
              'controls_unchanged': True, 'original_packs_modified': False, 'game_launched': False,
              'scope': 'Exact 23 files, eight mesh material closures and retained inherited-gap proof; not final all-resource or in-game acceptance'}
    output = Path(args.output).resolve()
    vfs.safe_output(output)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    accepted = {'schema': 'skyrim.generated_mesh_acceptance.v1', 'status': 'GENERATED_MESH_RESOURCES_VERIFIED',
                'accepted': True, 'proof': {'path': str(output), 'sha256': vfs.digest(output)},
                'resources': rows, 'inherited_source_gaps': manifest['inherited_source_gaps'],
                'scope': report['scope']}
    with (installed_path.parent / 'accepted.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(accepted, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'resources': len(rows), 'proof': str(output)}, indent=2))


if __name__ == '__main__':
    main()
