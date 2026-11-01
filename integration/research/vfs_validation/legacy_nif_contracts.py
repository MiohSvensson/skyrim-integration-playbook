"""Exact two-file source-format inventory; never a general BS82 allowance.

The full typed CPU-reader snapshots and raw block tables are immutable evidence.
Actual VFS bytes and their logical BSA winner must match before this inventory is
used. Four texture dependencies are still mandatory graph edges. Source stream82
is retained; no SSE conversion or native game compatibility is claimed.
"""
import hashlib
import json
from pathlib import Path
import struct

from vfs_common import BASE, digest, key

CONTRACT = BASE / 'integration/research/feature_generation/moonstar_conversion/effective_bs82_contract.json'
CONTRACT_SHA = '0fa0b6f710fbf777af3eb3f1095c67649eb9295633e5fe63730480d3394d23a8'
ASSETS = {
    'meshes/mwl/wg_0.nif': '3182b43fd2f42132907f22743d43fac5588f9bfcdbfb20bf556cefa26bddb0ed',
    'meshes/mwl/wg_1.nif': '9cdb6d3d6b8b34b85ff08720ed1e31a56d2ca0b2afa39f87c1655bf85d0c3f27',
}
TEXTURES = {'textures/cubemaps/bronze_e.dds', 'textures/mwl/wraithguard.dds',
            'textures/mwl/wraithguard_m.dds', 'textures/mwl/wraithguard_n.dds'}
BLOCK_TYPES = {'NiNode': 40, 'NiTriShape': 1, 'NiTriShapeData': 1,
               'BSDismemberSkinInstance': 1, 'NiSkinData': 1, 'NiSkinPartition': 1,
               'BSLightingShaderProperty': 1, 'BSShaderTextureSet': 1}
ARCHIVE_SHA = 'fd3f9014c35f92a5af131436774e36a79ebdc027e00cbe71f9e8aec98fc6fc05'


def need(condition, reason):
    if not condition:
        raise ValueError('Bounded legacy NIF contract: ' + reason)


class LegacyNifContracts:
    def __init__(self):
        need(digest(CONTRACT) == CONTRACT_SHA, 'contract changed')
        self.contract = json.loads(CONTRACT.read_text('utf-8'))
        c = self.contract
        need(c['status'] == 'EXACT_TWO_EFFECTIVE_ORIGINAL_BS82_FORMAT_EXCEPTIONS_NOT_REPAIRED'
             and c['game_started'] is False, 'unexpected source-proof status')
        self.evidence = {}
        self.pin(CONTRACT, CONTRACT_SHA)
        self.pin(c['parser_script'], c['parser_script_sha256'])
        self.pin(c['comparison_script'], c['comparison_script_sha256'])
        reader = BASE / 'integration/research/feature_generation/primary_sources/PyNifly'
        self.pin(reader / 'addon/io_scene_nifly/NiflyDLL.dll', c['reader_dll_sha256'])
        self.pin(reader / 'io_scene_nifly.zip', c['reader_release']['asset_sha256'])
        need(c['reader_release']['GitHub_digest'] == 'sha256:' + c['reader_release']['asset_sha256'],
             'release asset digest mismatch')
        self.entries = {key(r['path_key']): r for r in c['entries']}
        need(len(c['entries']) == 2 and set(self.entries) == set(ASSETS), 'source-proof path set broadened')
        for path, row in self.entries.items():
            need(row['sha256'] == ASSETS[path] and row['stream'] == 82 and
                 row['native_runtime_verified'] is False, 'asset SHA/format/native claim changed')
            table = row['block_table']
            need(table['version'] == 0x14020007 and table['endian'] == 1 and table['user'] == 12 and
                 table['stream'] == 82 and table['EOF_exact'] is True and table['roots'] == [0] and
                 table['groups'] == [] and table['block_types'] == BLOCK_TYPES and len(table['blocks']) == 47,
                 'unproved block schema')
            need(row['BODYTRI_refs'] == row['behavior_refs'] == row['controller_refs'] == [] and
                 row['extra_data_count'] == 0, 'unproved additional external reference class')
            need({key(r['path']) for r in row['external_refs']} == TEXTURES and
                 len(row['external_refs']) == 4 and
                 all(r['kind'] == 'texture' and r['via'] == 'BSShaderTextureSet' for r in row['external_refs']),
                 'external dependency proof changed')
            need(row['geometry'] == {'shapes': 1, 'nodes': 41, 'vertices': 3056,
                                     'triangles': 4224, 'bones': 39, 'partitions': 3},
                 'geometry proof changed')
            self.pin(row['parsed_copy'], ASSETS[path])
            self.pin(row['typed_snapshot'], row['typed_snapshot_sha256'])
            snapshot = json.loads(Path(row['typed_snapshot']).read_text('utf-8'))
            need(snapshot['sha256'] == ASSETS[path] and snapshot['nifly_classification'] == 'FO3' and
                 len(snapshot['nodes']) == 41 and len(snapshot['shapes']) == 1,
                 'typed snapshot does not bind this source image')

    def pin(self, path, expected):
        path = Path(path).resolve(strict=True)
        need(path.is_relative_to((BASE / 'integration/research').resolve()), 'evidence escaped research')
        need(digest(path) == expected, 'evidence changed: ' + str(path))
        self.evidence[str(path)] = {'path': str(path), 'sha256': expected}

    def metadata(self):
        return {'status': self.contract['status'], 'contract': {'path': str(CONTRACT), 'sha256': CONTRACT_SHA},
                'assets': [{'path_key': k, 'sha256': ASSETS[k]} for k in sorted(ASSETS)],
                'evidence': sorted(self.evidence.values(), key=lambda r: r['path']),
                'limits': 'Two exact original stream82 assets have complete static author-library CPU parse and external-resource proof; no native runtime, render, or SSE100-conversion claim.'}

    def inventory(self, path_key, data, location):
        path_key = key(path_key)
        if path_key not in ASSETS:
            return None
        need(hashlib.sha256(data).hexdigest() == ASSETS[path_key], 'actual winning asset SHA differs')
        row = self.entries[path_key]
        expected = row['provider']
        need(location['kind'] == 'bsa' and key(location['archive']) == 'moonandstar_mas.bsa' and
             location['archive_sha256'] == ARCHIVE_SHA and location['sha256'] == ASSETS[path_key] and
             key(location['entry']) == path_key and location['provider'] == expected['provider'] and
             Path(location['archive_physical']).resolve() == Path(expected['archive_physical']).resolve(),
             'actual logical archive/provider winner differs')
        need(len(data) == row['bytes'], 'actual asset length differs')
        table = row['block_table']
        blocks = []
        for index, r in enumerate(table['blocks']):
            start, length = r['offset'], r['size']
            need(r['index'] == index and start >= 0 and start + length <= len(data), 'block boundary differs')
            block = data[start:start+length]
            need(hashlib.sha256(block).hexdigest() == r['sha256'], 'block payload differs')
            b = {'index': index, 'type': r['type'], 'offset': start, 'bytes': length}
            if r['type'] == 'BSShaderTextureSet':
                count = struct.unpack_from('<I', block, 0)[0]
                textures = []
                pos = 4
                for _ in range(count):
                    n = struct.unpack_from('<I', block, pos)[0]
                    pos += 4
                    need(pos + n <= len(block), 'texture field exceeds block')
                    textures.append(block[pos:pos+n].rstrip(b'\0').decode('utf-8', errors='strict'))
                    pos += n
                need(pos == len(block), 'unconsumed texture block bytes')
                need({key(v) for v in textures if v} == TEXTURES, 'actual typed texture set differs')
                b['textures'] = textures
            blocks.append(b)
        return {'user_version': 12, 'bs_version': 82, 'strings': table['strings'], 'blocks': blocks,
                'bounded_format_contract_sha256': CONTRACT_SHA,
                'native_runtime_verified': False, 'source_format_retained': True}
