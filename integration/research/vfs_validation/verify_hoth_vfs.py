"""Verify the installed cloak and its material through the actual MO2 VFS."""
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
    assert vfs.injected(), 'Actual usvfs injection required'
    installed_path = Path(args.installed).resolve(strict=True)
    receipt = json.loads(installed_path.read_text('utf-8'))
    assert receipt['status'] == 'INSTALLED_PENDING_ACTUAL_VFS' and receipt['accepted'] is False
    manifest_path = Path(receipt['manifest']['path']).resolve(strict=True)
    assert vfs.digest(manifest_path) == receipt['manifest']['sha256']
    manifest = json.loads(manifest_path.read_text('utf-8'))
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
        rows.append({'path': relative.as_posix(), 'runtime_file_id': runtime_id,
                     'installed_file_id': installed_id, 'sha256': sha, 'bytes': file['bytes']})
    mesh = layer / 'meshes/armor/hotharmor/hothwcloak_1.nif'
    assert vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data/meshes/armor/hotharmor/hothwcloak_1.nif') == vfs.file_identity(mesh)
    assert vfs.digest(mesh) == manifest['source_mesh']['sha256']
    for row in manifest['runtime_dependencies']:
        vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / row['path'])
    report = {'schema': 'skyrim.hoth_cloak_vfs_proof.v1', 'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_HOTH_CLOAK_RUNTIME_RESOURCES', 'usvfs': True, 'resources': rows,
              'mesh_sha256': vfs.digest(mesh), 'controls_unchanged': True,
              'original_packs_modified': False, 'game_launched': False,
              'scope': 'Exact cloak mesh and all material dependencies; not a full resource or in-game proof'}
    output = Path(args.output).resolve()
    vfs.safe_output(output)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    accepted = {'schema': 'skyrim.hoth_cloak_acceptance.v1', 'status': 'HOTH_CLOAK_RESOURCE_VERIFIED',
                'accepted': True, 'proof': {'path': str(output), 'sha256': vfs.digest(output)},
                'resources': rows, 'scope': report['scope']}
    with (installed_path.parent / 'accepted.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(accepted, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
