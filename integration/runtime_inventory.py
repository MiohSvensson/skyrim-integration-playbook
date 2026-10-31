"""Independent physical resolution of the planned MO2 view, before VFS probing."""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

from materialize import BASE, TARGET, key, lp, utc

PROFILE = TARGET/'profiles/Unified Skyrim'
ROOT_CACHE = {'signature': None, 'files': {}}


def active_mods():
    return [(line[1:], TARGET/'mods'/line[1:]) for line in (PROFILE/'modlist.txt').read_text(encoding='utf-8-sig').splitlines() if line.startswith('+')]


def resolve(relative, mods=None):
    mods = active_mods() if mods is None else mods
    if '/' not in str(relative) and '\\' not in str(relative):
        signature = tuple(str(folder) for _, folder in mods)
        if ROOT_CACHE['signature'] != signature:
            files = {}
            for name, folder in mods+[('Game/Data', TARGET/'Game/Data')]:
                if not folder.is_dir():
                    continue
                with os.scandir(lp(folder)) as entries:
                    for entry in entries:
                        if entry.is_file(follow_symlinks=False):
                            files.setdefault(key(entry.name), (name, folder/entry.name))
            ROOT_CACHE.update(signature=signature, files=files)
        return ROOT_CACHE['files'].get(key(relative), (None, None))
    for name, folder in mods:
        candidate = folder/relative
        if os.path.isfile(lp(candidate)):
            return name, candidate
    candidate = TARGET/'Game/Data'/relative
    return ('Game/Data', candidate) if os.path.isfile(lp(candidate)) else (None, None)


def header(path):
    with open(lp(path), 'rb') as stream:
        raw = stream.read(24)
        if raw[:4] != b'TES4':
            raise ValueError(f'Not a TES4 plugin: {path}')
        length, flags = struct.unpack_from('<II', raw, 4)
        payload = stream.read(length)
        stream.seek(0)
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    pos = 0
    masters = []
    version = None
    while pos < len(payload):
        tag = payload[pos:pos+4]
        size = struct.unpack_from('<H', payload, pos+4)[0]
        pos += 6
        data = payload[pos:pos+size]
        if tag == b'MAST':
            masters.append(data.rstrip(b'\0').decode('utf-8'))
        if tag == b'HEDR':
            version = struct.unpack_from('<f', data)[0]
        pos += size
    return {'masters': masters, 'flags': flags, 'version': version, 'sha256': digest,
            'is_light': bool(flags & 0x200) or path.suffix.casefold() == '.esl',
            'is_master': bool(flags & 1) or path.suffix.casefold() in ('.esm', '.esl')}


def plugin_names(mods=None):
    result = []
    seen = set()
    def add(name):
        if key(name) not in seen:
            seen.add(key(name))
            result.append(name)
    for name in ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm']:
        add(name)
    ccc = TARGET/'Game/Skyrim.ccc'
    if ccc.exists():
        for name in ccc.read_text(encoding='utf-8-sig').splitlines():
            if name.strip() and not name.startswith('#') and resolve(name.strip(), mods)[1] is not None:
                add(name.strip())
    for line in (PROFILE/'plugins.txt').read_text(encoding='utf-8-sig').splitlines():
        if line.startswith('*'):
            add(line[1:])
    return result


def inventory():
    mods = active_mods()
    result = {'utc': utc(), 'profile': str(PROFILE), 'active_mods': len(mods),
              'missing_mod_dirs': [name for name, folder in mods if not folder.is_dir()],
              'plugins': [], 'missing_plugins': [], 'missing_masters': [], 'dlls': [], 'non_x64_runtime_dlls': []}
    names = plugin_names(mods)
    enabled = {key(n) for n in names}
    for name in names:
        provider, file = resolve(name, mods)
        if file is None:
            result['missing_plugins'].append(name)
            continue
        row = {'name': name, 'provider': provider, 'path': str(file), **header(file)}
        result['plugins'].append(row)
        for master in row['masters']:
            if key(master) not in enabled:
                result['missing_masters'].append({'plugin': name, 'master': master})
    dll_paths = {}
    for name, folder in mods+[('Game/Data', TARGET/'Game/Data')]:
        directory = folder/'SKSE/Plugins'
        if not directory.is_dir():
            continue
        for file in directory.iterdir():
            if file.is_file() and file.suffix.casefold() == '.dll':
                dll_paths.setdefault(key(file.name), (name, file))
    for name, (provider, file) in sorted(dll_paths.items()):
        with open(lp(file), 'rb') as stream:
            blob = stream.read()
        offset = struct.unpack_from('<I', blob, 0x3c)[0]
        assert blob[offset:offset+4] == b'PE\0\0', file
        machine = struct.unpack_from('<H', blob, offset+4)[0]
        row = {'name': file.name, 'provider': provider, 'path': str(file),
               'machine': hex(machine), 'sha256': hashlib.sha256(blob).hexdigest()}
        result['dlls'].append(row)
        if machine != 0x8664:
            result['non_x64_runtime_dlls'].append(row)
    result['slots'] = {'full': sum(not p['is_light'] for p in result['plugins']),
                       'light': sum(p['is_light'] for p in result['plugins'])}
    result['within_slot_limits'] = result['slots']['full'] <= 254 and result['slots']['light'] <= 4096
    ccc = TARGET/'Game/Skyrim.ccc'
    result['absent_optional_ccc_entries'] = [name.strip() for name in ccc.read_text(encoding='utf-8-sig').splitlines()
        if name.strip() and not name.startswith('#') and resolve(name.strip(), mods)[1] is None] if ccc.exists() else []
    return result


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    result = inventory()
    output = BASE/'integration/physical_runtime_inventory.json'
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('plugins', 'dlls')}, ensure_ascii=False, indent=2))
