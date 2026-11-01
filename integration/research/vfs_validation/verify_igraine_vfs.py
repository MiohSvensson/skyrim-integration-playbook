"""Verify the two installed Igraine resources through the actual MO2 VFS."""
import argparse
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import vfs_common as vfs
from nif_resource_inventory import inventory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('installed')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not vfs.injected():
        raise RuntimeError('Actual usvfs injection required')
    installed_path = Path(args.installed).resolve(strict=True)
    if not installed_path.is_relative_to(HERE):
        raise ValueError('Igraine installation receipt must be inside its research directory')
    receipt = json.loads(installed_path.read_text('utf-8'))
    if receipt.get('status') != 'INSTALLED_PENDING_ACTUAL_VFS' or receipt.get('accepted') is not False:
        raise ValueError('Pending private Igraine installation required')
    manifest_path = Path(receipt['manifest']['path']).resolve(strict=True)
    if vfs.digest(manifest_path) != receipt['manifest']['sha256']:
        raise ValueError('Audited manifest changed')
    manifest = json.loads(manifest_path.read_text('utf-8'))
    for profile, digest in receipt['controls'].items():
        if vfs.digest(vfs.DEFAULT_TARGET / profile) != digest:
            raise ValueError('Profile control changed: ' + profile)
    layer = vfs.DEFAULT_TARGET / 'mods/ZZ83 Verified generated item and quest assets'
    rows = []
    for file in receipt['files']:
        destination = Path(file['path']).resolve(strict=True)
        relative = destination.relative_to(layer)
        if relative.as_posix() not in {'textures/SC/4_Ports/21_Order1886/Igraine/Knight/Hands_F_m.dds',
                                       'textures/SC/4_Ports/21_Order1886/Igraine/Knight/quicksilver_e.dds'}:
            raise ValueError('Unexpected installed resource')
        runtime = vfs.DEFAULT_TARGET / 'Game/Data' / relative
        runtime_id = vfs.file_identity(runtime)
        installed_id = vfs.file_identity(destination)
        runtime_sha = vfs.digest(runtime)
        if runtime_id != installed_id or runtime_sha != file['sha256'] or vfs.digest(destination) != file['sha256']:
            raise ValueError('VFS winner is not the exact private resource: ' + str(relative))
        if destination.stat().st_nlink != 1:
            raise ValueError('Installed resource is not a private file')
        runtime_bytes = len(runtime.read_bytes())
        if runtime_bytes != file['bytes']:
            raise ValueError('VFS resource length differs from the installed file')
        rows.append({'relative_path': relative.as_posix(), 'runtime_path': str(runtime),
                     'runtime_file_id': runtime_id, 'installed_file_id': installed_id,
                     'sha256': runtime_sha, 'bytes': runtime_bytes})
    mesh = Path(manifest['runtime_morph']['path']).resolve(strict=True)
    mesh_relative = mesh.relative_to(layer)
    runtime_mesh = vfs.DEFAULT_TARGET / 'Game/Data' / mesh_relative
    if vfs.file_identity(runtime_mesh) != vfs.file_identity(mesh) or vfs.digest(runtime_mesh) != manifest['runtime_morph']['sha256']:
        raise ValueError('Runtime hand mesh changed')
    slots = [row['textures'] for row in inventory(runtime_mesh)['blocks'] if 'textures' in row]
    if slots != [manifest['texture_slots']]:
        raise ValueError('Runtime hand material texture slots changed')
    report = {'schema': 'skyrim.igraine_vfs_proof.v1', 'utc': datetime.now(timezone.utc).isoformat(),
              'status': 'PASS_TWO_IGRAINE_RUNTIME_RESOURCES', 'usvfs': True,
              'installation_receipt': {'path': str(installed_path), 'sha256': vfs.digest(installed_path)},
              'resources': rows, 'mesh_sha256': vfs.digest(runtime_mesh), 'texture_slots': slots[0],
              'controls_unchanged': True, 'original_packs_modified': False, 'game_launched': False,
              'scope': 'Targeted two-resource closure only; not a full resource graph or in-game proof'}
    output = Path(args.output).resolve()
    vfs.safe_output(output)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    accepted = {'schema': 'skyrim.igraine_material_acceptance.v1', 'status': 'IGRAINE_RESOURCE_REPAIR_VERIFIED',
                'accepted': True, 'proof': {'path': str(output), 'sha256': vfs.digest(output)},
                'resources': rows, 'scope': report['scope']}
    accepted_path = installed_path.parent / 'accepted.json'
    with accepted_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(accepted, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
