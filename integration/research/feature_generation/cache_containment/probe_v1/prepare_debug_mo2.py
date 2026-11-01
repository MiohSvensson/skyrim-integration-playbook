"""Prepare a private debug MO2 executable/config without changing the original."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[4]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def copy(source, destination):
    data = source.read_bytes()
    with destination.open('xb') as stream:
        stream.write(data)
    assert sha(destination) == sha(source)


def main():
    source_dir = BASE / 'UnifiedSkyrim/MO2'
    original_config = source_dir / 'ModOrganizer.ini'
    original_hash = sha(original_config)
    debug_dir = HERE / 'mo2_debug_full'
    debug_dir.mkdir(exist_ok=False)
    for source in source_dir.rglob('*'):
        if source.is_dir() and source.name in {'logs', 'crashDumps'}:
            continue
        relative = source.relative_to(source_dir)
        destination = debug_dir / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        if source.name == 'ModOrganizer.ini' or source.suffix in {'.log', '.dmp', '.pdb'}:
            continue
        if source.lstat().st_file_attributes & 0x400:
            raise ValueError('Reparse tool input: ' + str(source))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.hardlink_to(source)
    (debug_dir / 'logs').mkdir(exist_ok=True)
    (debug_dir / 'crashDumps').mkdir(exist_ok=True)
    text = original_config.read_text('utf-8-sig')
    assert 'log_level=1' in text
    debug_config = debug_dir / 'ModOrganizer.ini'
    debug_config.write_text(text.replace('log_level=1', 'log_level=0'), encoding='utf-8', newline='')
    assert sha(original_config) == original_hash
    report = {'schema': 'skyrim.pg_cache_probe.debug_mo2.v1', 'status': 'PRIVATE_DEBUG_MO2_READY',
              'original_config': str(original_config), 'original_config_sha256': original_hash,
              'debug_config': str(debug_dir / 'ModOrganizer.ini'), 'debug_config_sha256': sha(debug_dir / 'ModOrganizer.ini'),
              'debug_exe_sha256': sha(debug_dir / 'ModOrganizer.exe'), 'source_exe_sha256': sha(source_dir / 'ModOrganizer.exe'),
              'debug_log_level': 0, 'original_config_unchanged': True,
              'dependencies': 'Private full MO2 tool tree with read-only linked binaries and an independent debug INI; original config is not modified',
              'game_launched': False, 'pg_launched': False}
    (HERE / 'debug_mo2_manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
