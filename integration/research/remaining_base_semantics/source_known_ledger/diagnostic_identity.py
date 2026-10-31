"""Canonical identities and exact raw namespace-aware record fingerprints."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys
import zlib

sys.dont_write_bytecode = True
BASE = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(BASE / 'rootcause'))
from plugin_binary import subs


def file_sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()


def canonical_id(value, mapping):
    value = int(value, 16) if isinstance(value, str) else value
    light = value >> 24 == 0xFE
    prefix = value & (0xFFFFF000 if light else 0xFF000000)
    owner = mapping.get(prefix)
    if owner is None: return f'UNMAPPED:{value:08X}'
    return f'{owner.casefold()}|{value & (0xFFF if light else 0xFFFFFF):06X}'


def record_context(text, mapping, plugin):
    m = re.search(r'\[([A-Z0-9_]{4}):([0-9A-Fa-f]{8})\]', text)
    if not m: return None
    sig, value = m.groups()
    return sig, f'{plugin.casefold()}|000000' if sig == 'TES4' else canonical_id(value, mapping)


def field_path(text):
    return re.sub(r'\s*\\\s*', lambda _: '\\', text.strip()).casefold()


def message_identity(text, mapping):
    m = re.search(r'\[([0-9A-Fa-f]{8})\]\s*<Error: Could not be resolved>', text)
    if m: return 'missing-form:' + canonical_id(m[1], mapping)
    m = re.search(r'Tint layer index (\d+) not found.*?\[RACE:([0-9A-Fa-f]{8})\]', text)
    if m: return 'tint-index:' + m[1] + ':race=' + canonical_id(m[2], mapping)
    result = re.sub(r'\[([A-Z0-9_]{4}):([0-9A-Fa-f]{8})\]', lambda m: '[' + m[1] + ':' + canonical_id(m[2], mapping) + ']', text)
    result = re.sub(r'\[([0-9A-Fa-f]{8})\]', lambda m: '[' + canonical_id(m[1], mapping) + ']', result)
    return re.sub(r'\s+', ' ', result.strip()).casefold()


def key_for(plugin, signature, record, path, message):
    return '|'.join((plugin.casefold(), signature, record, field_path(path), message))


class PluginReader:
    def __init__(self, path):
        self.path = Path(path)
        self.name = self.path.name.casefold()
        self.masters = []
        self.by_key = None
        with self.path.open('rb') as f:
            h = f.read(24)
            assert h[:4] == b'TES4'
            self.header_flags = struct.unpack_from('<I', h, 8)[0]
            self.masters = [v.rstrip(b'\0').decode('utf-8', 'replace').casefold() for t, v in subs(f.read(struct.unpack_from('<I', h, 4)[0])) if t == 'MAST']

    def decode_id(self, value, signature):
        if signature == 'TES4': return self.name + '|000000'
        slot = value >> 24
        # 4.1.5f FixedFormID clamps any record-header self/out-of-range slot
        # to this file's self slot. This method is not used for payload links.
        owner = self.masters[slot] if slot < len(self.masters) else self.name
        return f'{owner}|{value & 0xFFFFFF:06X}'

    def at(self, offset):
        with self.path.open('rb') as f:
            f.seek(offset); h = f.read(24)
            sig = h[:4].decode('ascii'); size, flags, fid, vcs1, version, vcs2 = struct.unpack_from('<IIIIHH', h, 4)
            data = f.read(size)
        if flags & 0x40000:
            n = struct.unpack_from('<I', data)[0]; data = zlib.decompress(data[4:]); assert len(data) == n
        fields = subs(data)
        payload = {'signature': sig, 'flags_without_compression': flags & ~0x40000,
                   'masters': self.masters, 'namespace_self_plugin': self.name,
                   'VCS1': vcs1, 'form_version': version, 'VCS2': vcs2,
                   'ordered_subrecords': [(t, v.hex()) for t, v in fields]}
        sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return {'record': self.decode_id(fid, sig), 'signature': sig, 'offset': offset,
                'raw_form_id': f'{fid:08X}', 'record_payload_sha256': sha,
                'edid': next((v.rstrip(b'\0').decode('utf-8', 'replace') for t, v in fields if t == 'EDID'), ''),
                'flags': flags & ~0x40000, 'masters': self.masters}

    def index(self):
        if self.by_key is not None: return self.by_key
        self.by_key = {}
        with self.path.open('rb') as f:
            f.seek(0, 2); end = f.tell(); pos = 0
            while pos < end:
                f.seek(pos); h = f.read(24); sig = h[:4].decode('ascii'); size = struct.unpack_from('<I', h, 4)[0]
                if sig == 'GRUP': pos += 24; continue
                fid = struct.unpack_from('<I', h, 12)[0]
                self.by_key[(sig, self.decode_id(fid, sig))] = pos
                pos += 24 + size
            assert pos == end
        return self.by_key

    def get(self, signature, record):
        offset = self.index().get((signature, record))
        return self.at(offset) if offset is not None else None
