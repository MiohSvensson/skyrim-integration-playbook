"""Close missing generated mesh resources only from exact author assets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
COLLECTION = BASE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(BASE / 'rootcause'))
sys.path.insert(0, str(BASE / 'integration/research/synthesis_final'))
from nif_resource_inventory import inventory
from bsarch_readonly import extract_files
from synthesis_arma_diff import source_key
import vfs_common as vfs

LAYER = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets'
SOURCE_ROOT = COLLECTION / 'Anno/iniRePather-Skyrim/mods/PGPatcher_Output'
SOURCE_DIR = HERE / 'generated_mesh_sources'


def pin(path):
    path = Path(path).resolve(strict=True)
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest, 'bytes': path.stat().st_size}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True)
    parser.add_argument('--arma-delta', required=True)
    parser.add_argument('--input-models', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assert vfs.injected(), 'Actual usvfs injection required'
    replay_path = Path(args.replay).resolve(strict=True)
    replay = json.loads(replay_path.read_text('utf-8'))
    candidate = Path(replay['final_plugin_candidate']['path']).resolve(strict=True)
    assert vfs.digest(candidate) == replay['final_plugin_candidate']['sha256']
    delta_path = Path(args.arma_delta).resolve(strict=True)
    armor_delta = json.loads(delta_path.read_text('utf-8'))
    assert armor_delta['status'] == 'ARMA_DELTA_READY_FOR_SCOPED_RUNTIME_AUDIT'
    assert armor_delta['candidate']['sha256'] == replay['final_plugin_candidate']['sha256']
    assert armor_delta['replay_result_sha256'] == vfs.digest(replay_path)
    affected = set(armor_delta['affected_source_keys'])
    masters, records = __import__('plugin_binary').read(candidate)
    records = [record for record in records if record['sig'] == 'ARMA' and source_key(masters, record) in affected]
    assert {source_key(masters, record) for record in records} == affected
    mapping = []
    mapped = set()
    sources = {}
    source_dir = SOURCE_DIR

    def source_for(path):
        if path in sources:
            return sources[path]
        loose = SOURCE_ROOT / path
        if path == 'meshes/dr aris tag/dr_aris_armor.nif' and (COLLECTION / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2/meshes/dr aris tag/dr_aris_armor_0.nif').is_file():
            result = (COLLECTION / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2/meshes/dr aris tag/dr_aris_armor_0.nif',
                      'Derived default base alias from the exact author weight-0 mesh; weight-1 is separately present')
        elif (path.startswith('meshes/dr aris tag/') or path.startswith('textures/dr aris tag/')) and (COLLECTION / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2' / path).is_file():
            result = (COLLECTION / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2' / path,
                      'Exact Adventurer\'s Guild author asset')
        elif loose.is_file():
            result = (loose, 'Exact author PGPatcher_Output asset')
        elif path.startswith('textures/pbr/') and (COLLECTION / 'Anno/iniRePather-Skyrim/mods/原版装备材质替换-Faultier\'s PBR conversion of Xavbio\'s armors - vanilla res' / path).is_file():
            result = (COLLECTION / 'Anno/iniRePather-Skyrim/mods/原版装备材质替换-Faultier\'s PBR conversion of Xavbio\'s armors - vanilla res' / path,
                      'Exact Faultier PBR material source')
        else:
            with sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True) as db:
                rows = db.execute('''select distinct e.sha256,a.path,a.sha256 archive_sha256,s.source_kind from bsa_entries e
                    join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=a.id
                    where e.path_key=? order by a.id''', (path,)).fetchall()
            if not rows:
                raise ValueError('Missing runtime and source asset: ' + path)
            if path.startswith('textures/armor/darkcrusaderreforged/kingcrusaderarmor/'):
                rows = [row for row in rows if Path(row[1]).name == 'DCR_KingCrusaderMegaPack_SSE - Textures.bsa']
            baseline = [row for row in rows if 'TuLED' in Path(row[1]).parts]
            if baseline:
                rows = baseline
            if path == 'textures/cubemaps/blacksky_e.dds':
                rows = [row for row in rows if Path(row[1]).name == 'LegacyoftheDragonborn - Textures.bsa']
            stock = [row for row in rows if row[3] == 'stock Data'
                     and (BASE / 'repairs/consistent_stock/Data' / Path(row[1]).name).is_file()
                     and vfs.digest(BASE / 'repairs/consistent_stock/Data' / Path(row[1]).name) == row[2]]
            if stock:
                rows = stock
            if len({row[0] for row in rows}) != 1:
                raise ValueError('Ambiguous archive source hashes: ' + path)
            digest, archive, archive_sha, source_kind = rows[0]
            if vfs.digest(archive) != archive_sha:
                raise ValueError('Archive hash changed: ' + archive)
            blob = extract_files(archive, {path: digest})[path]
            if shutil.disk_usage(BASE).free < 32 * 1024**3 + len(blob) + 4096:
                raise RuntimeError('Disk reserve would be crossed')
            extracted = source_dir / path
            extracted.parent.mkdir(parents=True, exist_ok=True)
            if not extracted.exists():
                with extracted.open('xb') as stream:
                    stream.write(blob)
            elif vfs.digest(extracted) != digest:
                raise ValueError('Extracted source differs from archive hash: ' + path)
            result = (extracted, 'Exact archive-backed author asset: ' + archive)
        sources[path] = result
        return result

    from synthesis_source_models import SourceModels, origin
    from synthesis_input_models import load_verified
    input_fields, input_report = load_verified(args.input_models, delta_path, vfs.digest)
    source_models = SourceModels(None, None, input_fields=input_fields)
    missing = []
    seen = set()
    source_blockers = []
    inherited_source_gaps = []
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Output must stay in vfs_validation')
    for record in records:
        source_fields = source_models.fields_for(masters, record)
        for tag, value in record['fields']:
            if tag not in ('MOD2', 'MOD3', 'MOD4', 'MOD5') or not value:
                continue
            path = vfs.asset_key(value.rstrip(b'\0').decode('utf-8'), kind='model')
            if not path:
                raise ValueError('Unsupported ARMA model path')
            if path in seen:
                continue
            seen.add(path)
            try:
                identity = vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / path)
                missing.append({'path': path, 'runtime_file_id': identity})
                continue
            except OSError as exc:
                if getattr(exc, 'winerror', None) not in (2, 3):
                    raise
            try:
                source, basis = source_for(path)
            except ValueError as exc:
                if origin(source_fields, tag, value) == 'inherited_unchanged':
                    inherited_source_gaps.append({'path': path, 'source_key': source_key(masters, record), 'field': tag,
                                                  'source_plugin': masters[record['fid'] >> 24],
                                                  'disposition': 'INHERITED_UNCHANGED_SOURCE_GAP_RETAINED_NO_ALIAS',
                                                  'scope': 'Not a new Synthesis dependency; final full resource disposition remains required'})
                    continue
                source_blockers.append({'path': path, 'source_key': source_key(masters, record), 'field': tag, 'error': str(exc)})
                continue
            parsed = inventory(source)
            if not any('textures' in block for block in parsed['blocks']):
                raise ValueError('Mesh has no typed texture set: ' + str(source))
            missing.append({'path': path, 'source': pin(source), 'basis': basis, 'mesh_sha256': parsed['sha256']})
            if path not in mapped:
                mapped.add(path)
                mapping.append({'source': pin(source), 'destination': str(LAYER / path), 'basis': basis})
            for block in parsed['blocks']:
                for texture in block.get('textures', []):
                    if not texture:
                        continue
                    texture_path = vfs.asset_key(texture, kind='texture')
                    if not texture_path:
                        raise ValueError('Unsupported texture path: ' + texture)
                    if texture_path in seen:
                        continue
                    seen.add(texture_path)
                    try:
                        identity = vfs.file_identity(vfs.DEFAULT_TARGET / 'Game/Data' / texture_path)
                        missing.append({'path': texture_path, 'runtime_file_id': identity})
                        continue
                    except OSError as exc:
                        if getattr(exc, 'winerror', None) not in (2, 3):
                            raise
                    try:
                        texture_source, basis = source_for(texture_path)
                    except ValueError as exc:
                        source_blockers.append({'path': texture_path, 'parent_mesh': path, 'error': str(exc)})
                        continue
                    if texture_path not in mapped:
                        mapped.add(texture_path)
                        mapping.append({'source': pin(texture_source), 'destination': str(LAYER / texture_path), 'basis': basis})
                    missing.append({'path': texture_path, 'source': pin(texture_source), 'basis': basis})
    if source_blockers:
        report = {'schema': 'skyrim.generated_mesh_source_blocker.v1', 'status': 'GENERATED_SOURCE_CLOSURE_BLOCKED',
                  'candidate': pin(candidate), 'arma_delta': pin(delta_path), 'affected_record_count': len(affected),
                  'source_blockers': source_blockers, 'resolved_resource_count': len(mapping),
                  'private_resource_mapping_not_approved': mapping, 'original_packs_modified': False, 'game_launched': False,
                  'next': 'Resolve every listed exact-source gap or prove a bounded unused-source disposition before installation'}
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        raise ValueError('Generated source closure is blocked; see ' + str(output))
    report = {'schema': 'skyrim.generated_mesh_audit.v1', 'status': 'READY_FOR_PRIVATE_RESOURCE_INSTALL',
              'candidate': pin(candidate), 'arma_delta': pin(delta_path),
              'input_models': pin(Path(args.input_models).resolve(strict=True)),
              'affected_record_count': len(affected),
              'missing_model_count': sum(1 for row in missing if row['path'].startswith('meshes/') and 'source' in row),
              'resource_count': len(mapping), 'resources': missing,
              'inherited_source_gaps': inherited_source_gaps,
              'private_resource_mapping': mapping,
              'basis': 'Exact author/stock assets for repaired paths; source-identical missing paths are retained separately, without gender or weight substitution',
              'original_packs_modified': False,
              'next': 'Install only this exact private resource set into ZZ83, then repeat native Synthesis model closure; inherited gaps still need final disposition'}
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'missing_models': report['missing_model_count'],
                      'private_files': len(mapping), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
