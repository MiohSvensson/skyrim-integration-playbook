"""Inventory exact sources for inherited missing ARMA models without installing."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BASE / 'rootcause'))
from nif_resource_inventory import inventory
import vfs_common as vfs

SOURCE_DIR = HERE / 'inherited_mesh_sources'
LAYER = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets'


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': vfs.digest(path), 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validation', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual MO2 VFS injection required'
    validation_path = Path(args.validation).resolve(strict=True)
    validation = json.loads(validation_path.read_text('utf-8'))
    assert validation['status'] == 'SYNTHESIS_INSTALLED_SCOPED_STATIC_PASS_PENDING_ACCEPTANCE'
    paths = sorted({row['path'] for row in validation['inherited_missing_references']})
    from mesh_sources import SourceResolver
    resolver = SourceResolver(SOURCE_DIR, strict=True)
    archive_rows = resolver.archive_rows
    source_for = resolver.source_for

    resolved = []
    blockers = []
    for index, path in enumerate(paths):
        if index % 50 == 0:
            print(json.dumps({'progress': index + 1, 'total': len(paths), 'path': path}), flush=True)
        try:
            vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / path)
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (2, 3):
                raise
            try:
                source, basis = source_for(path)
                parsed = inventory(source)
                if not any(block.get('textures') for block in parsed['blocks']):
                    raise ValueError('Mesh has no typed texture set: ' + str(source))
                resolved.append({'path': path, 'source': pin(source), 'basis': basis, 'mesh_sha256': parsed['sha256'],
                                 'destination': str(LAYER / path), 'typed_texture_sets': True})
            except (ValueError, OSError) as exc:
                blockers.append({'path': path, 'error': str(exc),
                                 'archive_alternatives': [{'archive': row[1], 'entry_sha256': row[0], 'archive_sha256': row[2], 'source_kind': row[3]}
                                                         for row in archive_rows(path)]})
        else:
            raise ValueError('Inherited report is stale; runtime path now exists: ' + path)
    report = {'schema': 'skyrim.inherited_mesh_source_audit.v1',
              'status': 'INHERITED_SOURCE_REVIEW_REQUIRED' if blockers else 'INHERITED_EXACT_SOURCE_SET_READY',
              'validation_report': pin(validation_path), 'candidate_sha256': validation['candidate']['sha256'],
              'inherited_mesh_count': len(paths), 'resolved_mesh_count': len(resolved), 'blocker_count': len(blockers),
              'resolved_meshes': resolved, 'blockers': blockers,
              'installation_performed': False, 'original_packs_modified': False, 'game_launched': False,
              'next': 'Review ambiguous and missing sources before any bulk installation; every resolved mesh still needs final material/resource closure'}
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Output must stay in vfs_validation')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'inherited_meshes': len(paths), 'resolved': len(resolved),
                      'blockers': len(blockers), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
