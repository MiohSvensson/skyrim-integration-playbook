"""Stage a completed replay in an isolated profile without deploying it."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import uuid

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(BASE / 'integration'))
import materialize as mat
import runtime_inventory as runtime
from mo2_controls import canonical_modlist

PROFILE = 'Synthesis Diagnostic'
LAYER = 'ZZ89 Synthesis candidate'
PATCH = 'Synthesis - Patch.esp'
SIDECAR = 'skse/plugins/experience/races/generatedexperiencepatch.ini'
CONTROL_FILES = ['modlist.txt', 'plugins.txt', 'loadorder.txt', 'Skyrim.ini', 'SkyrimCustom.ini',
                 'skyrimprefs.ini', 'initweaks.ini', 'archives.txt', 'settings.ini']


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': mat.sha(path), 'size_bytes': path.stat().st_size}


def append(blob, row, first=False):
    bom = b'\xef\xbb\xbf' if blob.startswith(b'\xef\xbb\xbf') else b''
    rows = blob[len(bom):].splitlines(keepends=True)
    eol = next((b'\r\n' if line.endswith(b'\r\n') else line[-1:] for line in rows if line.endswith((b'\r', b'\n'))), b'\r\n')
    if rows and not rows[-1].endswith((b'\r', b'\n')):
        rows[-1] += eol
    if first:
        index = 0
        while index < len(rows) and rows[index].startswith(b'#'):
            index += 1
        rows.insert(index, row + eol)
    else:
        rows.append(row + eol)
    return bom + b''.join(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--replay', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    replay_path = Path(args.replay).resolve(strict=True)
    if not replay_path.is_relative_to(HERE / 'runs'):
        raise ValueError('Replay result must be in synthesis_final/runs')
    replay = json.loads(replay_path.read_text('utf-8'))
    if replay.get('status') != 'REPLAY_COMPLETED_OUTPUT_NOT_DEPLOYED_NEEDS_SEMANTIC_AND_XEDIT_VALIDATION':
        raise ValueError('A completed six-stage replay is required')
    if len(replay.get('stages', [])) != 6 or any(row.get('return_code') != 0 for row in replay['stages']):
        raise ValueError('Every official stage must succeed')
    candidate = Path(replay['final_plugin_candidate']['path']).resolve(strict=True)
    if candidate.name != PATCH or mat.sha(candidate) != replay['final_plugin_candidate']['sha256']:
        raise ValueError('Final plugin does not match the replay')
    if not replay.get('private_sidecar_restored') or not replay.get('generated_sidecar'):
        raise ValueError('Sidecar capture and restoration proof is incomplete')
    sidecar = Path(replay['generated_sidecar']['path']).resolve(strict=True)
    if mat.sha(sidecar) != replay['generated_sidecar']['sha256'] or not 0 < sidecar.stat().st_size <= 1024 * 1024:
        raise ValueError('Captured sidecar differs from its proof')
    prepared_path = replay_path.parent / 'prepared.json'
    prepared = json.loads(prepared_path.read_text('utf-8'))
    original_sidecar = Path(prepared['private_sidecar']['path']).resolve(strict=True)
    if mat.sha(original_sidecar) != replay['original_sidecar_sha256']:
        raise ValueError('Original sidecar was not restored exactly')
    original = mat.TARGET / 'profiles/Unified Build'
    profile = mat.TARGET / 'profiles' / PROFILE
    layer = mat.TARGET / 'mods' / LAYER
    if profile.exists() or layer.exists():
        raise FileExistsError('Synthesis diagnostic profile/layer must be fresh')
    folder = Path(args.output).resolve()
    mat.within(folder, HERE)
    if folder.exists():
        raise FileExistsError('Use a fresh diagnostic preparation directory')
    before = {name: pin(original / name) for name in CONTROL_FILES}
    previous = runtime.PROFILE
    runtime.PROFILE = original
    try:
        inventory = runtime.inventory()
    finally:
        runtime.PROFILE = previous
    if inventory['missing_plugins'] or inventory['missing_masters'] or not inventory['within_slot_limits']:
        raise ValueError('Original Build is not closed')
    modlist = canonical_modlist((original / 'modlist.txt').read_bytes())
    original_names = {mat.key(line[1:]) for line in modlist.decode('utf-8-sig').splitlines() if line.startswith(('+', '-'))}
    additional = []
    for entry in sorted((mat.TARGET / 'mods').iterdir(), key=lambda p: mat.key(p.name)):
        if not entry.is_dir():
            continue
        if getattr(entry.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse mod directory needs review: ' + str(entry))
        if mat.key(entry.name) not in original_names and mat.key(entry.name) != mat.key(LAYER):
            additional.append(entry.name)
    for name in additional:
        modlist = append(modlist, ('-' + name).encode(), first=True)
    controls = {
        'modlist.txt': append(modlist, ('+' + LAYER).encode(), first=True),
        'plugins.txt': append((original / 'plugins.txt').read_bytes(), ('*' + PATCH).encode()),
        'loadorder.txt': append((original / 'loadorder.txt').read_bytes(), PATCH.encode()),
    }
    sources = {}
    for name in CONTROL_FILES:
        destination = folder / 'profile' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(controls.get(name, (original / name).read_bytes()))
        sources[str(destination)] = f'profiles/{PROFILE}/{name}'
    snapshot = folder / 'mod' / PATCH
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(candidate.read_bytes())
    sources[str(snapshot)] = f'mods/{LAYER}/{PATCH}'
    side_snapshot = folder / 'mod' / SIDECAR
    side_snapshot.parent.mkdir(parents=True, exist_ok=True)
    side_snapshot.write_bytes(sidecar.read_bytes())
    sources[str(side_snapshot)] = f'mods/{LAYER}/{SIDECAR}'
    mappings = [{'source': source, 'destination': destination, 'storage': 'private',
                 'bytes': Path(source).stat().st_size} for source, destination in sources.items()]
    if shutil.disk_usage(BASE).free < mat.RESERVE + sum(row['bytes'] for row in mappings) + len(mappings) * 4096:
        raise RuntimeError('Disk reserve would be crossed')
    mat.assert_owned_tree()
    unit = 'synthesis_diagnostic_' + uuid.uuid4().hex
    c = mat.connect()
    copied = []
    try:
        mat.add_file_mapping(c, unit, mappings, 'Candidate-only Synthesis plugin and Experience sidecar; not a production installation')
        for row in mappings:
            target = mat.guard_destination(mat.TARGET / row['destination'])
            if target.exists():
                raise FileExistsError('Diagnostic destination unexpectedly exists: ' + str(target))
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = mat.make_private(row['source'], target, Path(row['source']).stat())
            if digest != mat.sha(row['source']):
                raise RuntimeError('Private diagnostic copy mismatch')
            c.execute("update files set status='materialized',sha256=? where unit_id=? and dest_key=?",
                      (digest, unit, mat.key(row['destination'])))
            c.commit()
            copied.append(pin(target))
        for name, row in before.items():
            if mat.sha(original / name) != row['sha256']:
                raise RuntimeError('Production Build control changed: ' + name)
        receipt = {'schema': 'skyrim.synthesis_diagnostic.v1', 'utc': mat.utc(),
                   'status': 'DIAGNOSTIC_PROFILE_READY_NOT_PRODUCTION_INSTALLATION', 'unit': unit,
                   'profile': str(profile), 'source_profile': str(original),
                   'candidate': pin(layer / PATCH), 'sidecar': pin(layer / SIDECAR),
                   'replay_result': pin(replay_path), 'original_control_pins': list(before.values()),
                   'copied_files': copied, 'expected_profile_plugins': len(inventory['plugins']) + 1,
                   'expected_native_entries': len(inventory['plugins']) + 2,
                   'production_profiles_modified': False, 'game_launched': False,
                   'next': 'Run read-only native record and resource checks. Installation and acceptance remain separate.'}
        (folder / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'status': receipt['status'], 'profile': str(profile), 'receipt': str(folder / 'receipt.json'),
                          'expected_native_entries': receipt['expected_native_entries']}, indent=2))
    except BaseException:
        for row in mappings:
            target = mat.guard_destination(mat.TARGET / row['destination'])
            if target.exists():
                target.unlink()
        c.execute('delete from files where unit_id=?', (unit,))
        c.execute('delete from units where id=?', (unit,))
        c.commit()
        raise
    finally:
        c.close()


if __name__ == '__main__':
    main()
