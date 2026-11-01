"""Audit the exact author Hoth cloak weight-1 mesh and its runtime dependencies."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BASE / 'rootcause'))
from nif_resource_inventory import inventory
from bsarch_readonly import extract_files
import vfs_common as vfs

SOURCE = BASE.parent / 'Anno/iniRePather-Skyrim/mods/PGPatcher_Output/meshes/armor/hotharmor/hothwcloak_1.nif'
DESTINATION = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets/meshes/armor/hotharmor/hothwcloak_1.nif'


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest, 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual usvfs injection required'
    assert not DESTINATION.exists(), 'Review an existing cloak mesh instead of overwriting it'
    report = inventory(SOURCE)
    dependencies = []
    extracted = []
    seen = set()
    source_dir = HERE / 'hoth_cloak_sources'
    for block in report['blocks']:
        for texture in block.get('textures', []):
            if texture:
                path = vfs.asset_key(texture, kind='texture')
                assert path, texture
                if path in seen:
                    continue
                seen.add(path)
                try:
                    identity = vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / path)
                    dependencies.append({'path': path, 'file_id': identity})
                    continue
                except OSError as exc:
                    if getattr(exc, 'winerror', None) not in (2, 3):
                        raise
                with sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True) as db:
                    row = db.execute('''select e.sha256,a.path,a.sha256 archive_sha256 from bsa_entries e
                        join bsa_archives a on a.id=e.archive_id where e.path_key=? and a.path like '%HothFollower.bsa'
                        order by a.id limit 1''', (path,)).fetchone()
                if not row:
                    raise ValueError('Dependency absent from runtime and author archive: ' + path)
                digest, archive, archive_sha = row
                if vfs.digest(archive) != archive_sha:
                    raise ValueError('Author archive changed: ' + archive)
                source_dir.mkdir(exist_ok=True)
                blob = extract_files(archive, {path: digest})[path]
                if shutil.disk_usage(BASE).free < 32 * 1024**3 + len(blob) + 4096:
                    raise RuntimeError('Disk reserve would be crossed')
                extracted_path = source_dir / path
                extracted_path.parent.mkdir(parents=True, exist_ok=True)
                if not extracted_path.exists():
                    with extracted_path.open('xb') as stream:
                        stream.write(blob)
                elif vfs.digest(extracted_path) != digest:
                    raise ValueError('Extracted dependency differs from its archive hash: ' + path)
                extracted.append({'source': pin(extracted_path),
                                  'destination': str(BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets' / path),
                                  'basis': 'Exact author HothFollower.bsa member, verified against indexed SHA256'})
                dependencies.append({'path': path, 'source': 'HothFollower.bsa', 'sha256': digest, 'archive_sha256': archive_sha})
    report = {'schema': 'skyrim.hoth_cloak_resource_audit.v1', 'status': 'READY_FOR_PRIVATE_RESOURCE_INSTALL',
              'source_mesh': pin(SOURCE), 'runtime_dependencies': dependencies,
              'basis': 'Exact author PGPatcher_Output weight-1 mesh; no alias or invented asset',
              'private_resource_mapping': [{'source': pin(SOURCE), 'destination': str(DESTINATION),
                                            'basis': 'Exact author mesh for the generated weight-1 ARMA reference'}],
              'original_packs_modified': False, 'mesh_or_controls_modified': False,
              'next': 'Install the exact private mesh into the active ZZ83 layer and verify its actual MO2 VFS identity and hash'}
    report['private_resource_mapping'].extend(extracted)
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Output must stay in vfs_validation')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
