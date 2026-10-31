"""Read-only binary after-check of a future xEdit-generated bounded NAVM patch.

Main header: 4.1.5f wbImplementation.pas:1022-1044.
NVNM layout: 4.1.5f wbDefinitionsTES5.pas:8015-8136.
This verifier never generates/edits plugin data. A full typed xEdit reload is
also required to confirm every CELL field and the final loaded override chain.
"""
import argparse
import hashlib
import json
import struct
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
TARGET = 'skyrim.esm|016F5D'
CELL = 'skyrim.esm|016D72'
NAVI = 'skyrim.esm|012FB4'
HEADER = struct.Struct('<4sIIIIHH')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fields(data):
    result = []
    pos = 0
    extended = None
    while pos < len(data):
        assert pos + 6 <= len(data), 'Truncated subrecord header'
        tag, size = struct.unpack_from('<4sH', data, pos)
        pos += 6
        if tag == b'XXXX':
            assert size == 4
            extended = struct.unpack_from('<I', data, pos)[0]
            pos += size
            continue
        if extended is not None:
            size, extended = extended, None
        value = data[pos:pos+size]
        assert len(value) == size, 'Truncated subrecord payload'
        result.append((tag.decode('ascii'), value))
        pos += size
    assert pos == len(data) and extended is None
    return result


class Plugin:
    def __init__(self, path):
        self.path = Path(path).resolve(strict=True)
        self.name = self.path.name.lower()
        self.records = []
        self.masters = []
        with self.path.open('rb') as stream:
            header = stream.read(24)
            values = HEADER.unpack(header)
            assert values[0] == b'TES4'
            self.header_flags = values[2]
            self.masters = [value.rstrip(b'\0').decode('utf-8').lower()
                            for tag, value in fields(stream.read(values[1])) if tag == 'MAST']
            stream.seek(0, 2)
            end = stream.tell()
            self._walk(stream, 0, end)

    def identity(self, fid):
        if fid == 0:
            return 'NULL'
        index = fid >> 24
        assert index <= len(self.masters), f'Out-of-range raw master index: {fid:08X}'
        owner = self.masters[index] if index < len(self.masters) else self.name
        return f'{owner}|{fid & 0xFFFFFF:06X}'

    def _walk(self, stream, start, end):
        pos = start
        while pos < end:
            stream.seek(pos)
            data = stream.read(24)
            assert len(data) == 24
            if data[:4] == b'GRUP':
                size = struct.unpack_from('<I', data, 4)[0]
                assert size >= 24 and pos + size <= end
                self._walk(stream, pos+24, pos+size)
            else:
                tag, size, flags, fid, vcs1, version, vcs2 = HEADER.unpack(data)
                assert pos + 24 + size <= end
                # Unrelated source records can contain legacy out-of-range
                # self indices. Do not normalize them or let them block the
                # bounded NAVM lookup. Candidate identities are checked by the
                # exact allowed-record set below; NVNM references stay strict.
                try:
                    identity = self.identity(fid)
                except AssertionError:
                    identity = f'UNMAPPED|{fid:08X}'
                self.records.append({'signature': tag.decode('ascii'), 'id': identity,
                                     'offset': pos, 'size': size, 'flags': flags,
                                     'vcs1': vcs1, 'form_version': version, 'vcs2': vcs2})
                size += 24
            pos += size
        assert pos == end

    def get(self, identity, signature):
        result = [r for r in self.records if r['id'] == identity and r['signature'] == signature]
        assert len(result) == 1, (self.path, identity, signature, len(result))
        return result[0]

    def payload(self, record):
        with self.path.open('rb') as stream:
            stream.seek(record['offset']+24)
            data = stream.read(record['size'])
        if record['flags'] & 0x40000:
            expected = struct.unpack_from('<I', data)[0]
            data = zlib.decompress(data[4:])
            assert len(data) == expected
        return data


def geometry(plugin, record):
    subrecords = fields(plugin.payload(record))
    assert [tag for tag, value in subrecords] == ['NVNM'], 'Unexpected NAVM fields'
    data = subrecords[0][1]
    pos = 0

    def read(fmt):
        nonlocal pos
        values = struct.unpack_from('<'+fmt, data, pos)
        pos += struct.calcsize('<'+fmt)
        return values[0] if len(values) == 1 else values

    def take(n):
        nonlocal pos
        value = data[pos:pos+n]
        assert len(value) == n
        pos += n
        return value

    version = read('I')
    assert version == 12
    crc, world, cell = read('III')
    pathing = {'crc': crc, 'world': plugin.identity(world),
               'cell_or_coords': plugin.identity(cell) if world == 0 else list(struct.unpack('<hh', struct.pack('<I', cell)))}
    vertex_count = read('I')
    vertices = take(vertex_count*12)
    triangle_count = read('I')
    triangle_bytes = take(triangle_count*16)
    triangles = [list(struct.unpack_from('<hhh hhh HH', triangle_bytes, i*16)) for i in range(triangle_count)]
    edge_count = read('I')
    edges = []
    for _ in range(edge_count):
        typ, ref, triangle = read('IIh')
        edges.append({'type':typ,'navmesh':plugin.identity(ref),'triangle':triangle})
    door_count = read('I')
    doors = []
    for _ in range(door_count):
        triangle, crc, ref = read('hII')
        doors.append({'triangle':triangle,'crc':crc,'door':plugin.identity(ref)})
    cover_count = read('I')
    cover = take(cover_count*2)
    grid = take(len(data)-pos)
    result = {'version':version,'pathing':pathing,'vertex_count':vertex_count,
              'vertices_sha256':sha(vertices),'triangle_count':triangle_count,
              'triangles_sha256':sha(triangle_bytes),'edges':edges,'doors':doors,
              'cover_count':cover_count,'cover_sha256':sha(cover),'grid_bytes':len(grid),'grid_sha256':sha(grid)}
    return result, triangles


def nvmi_model(plugin, data):
    pos = 0

    def read(fmt):
        nonlocal pos
        value = struct.unpack_from('<'+fmt, data, pos)
        pos += struct.calcsize('<'+fmt)
        return value[0] if len(value) == 1 else value

    navmesh = plugin.identity(read('I'))
    category = read('I')
    # Preserve exact three float encodings and four preferred-merge bytes.
    xyz_merge = data[pos:pos+16].hex()
    pos += 16
    edges = [plugin.identity(read('I')) for _ in range(read('I'))]
    preferred = [plugin.identity(read('I')) for _ in range(read('I'))]
    doors = []
    for _ in range(read('I')):
        crc, ref = read('II')
        doors.append({'crc':crc,'door':plugin.identity(ref)})
    is_island = read('B')
    assert is_island in (0,1)
    island_start = pos
    if is_island:
        pos += 24  # exact six bbox floats, then typed triangle/vertex arrays
        triangle_count = read('I')
        pos += triangle_count*6
        vertex_count = read('I')
        pos += vertex_count*12
    island_hex = data[island_start:pos].hex()
    crc, world, cell = read('III')
    assert pos == len(data), 'Unexpected NVMI layout/tail'
    return {'navmesh':navmesh,'category':category,'xyz_preferred_merge_hex':xyz_merge,
            'edges':sorted(edges),'preferred_edges':sorted(preferred),
            'doors':sorted(doors,key=lambda d:(d['door'],d['crc'])),
            'is_island':is_island,'island_hex':island_hex,
            'pathing':{'crc':crc,'world':plugin.identity(world),
                'cell_or_coords':plugin.identity(cell) if world == 0 else list(struct.unpack('<hh',struct.pack('<I',cell)))}}


def nvpp_model(plugin, data):
    pos = 0

    def read():
        nonlocal pos
        value = struct.unpack_from('<I',data,pos)[0]
        pos += 4
        return value

    paths = []
    for _ in range(read()):
        paths.append([plugin.identity(read()) for _ in range(read())])
    roads = []
    for _ in range(read()):
        roads.append({'navmesh':plugin.identity(read()),'index':read()})
    assert pos == len(data), 'Unexpected NVPP layout/tail'
    return {'paths':paths,'roadmarkers':sorted(roads,key=lambda d:(d['navmesh'],d['index']))}


def navi_model(plugin, record):
    result = {'infos':{},'precomputed':None,'deleted_navmeshes':[],'scalar_fields':[]}
    for tag,data in fields(plugin.payload(record)):
        if tag == 'NVMI':
            info = nvmi_model(plugin,data)
            assert info['navmesh'] not in result['infos'], 'Duplicate NVMI key'
            result['infos'][info['navmesh']] = info
        elif tag == 'NVPP':
            assert result['precomputed'] is None
            result['precomputed'] = nvpp_model(plugin,data)
        elif tag == 'NVSI':
            assert len(data)%4 == 0
            result['deleted_navmeshes'].extend(plugin.identity(struct.unpack_from('<I',data,i)[0]) for i in range(0,len(data),4))
        elif tag in ('NVER','EDID'):
            result['scalar_fields'].append((tag,data.hex()))
        else:
            raise AssertionError(f'Unreviewed NAVI subrecord: {tag}')
    result['deleted_navmeshes'].sort()
    return result


def target_in_precomputed(model):
    precomputed = model['precomputed']
    if precomputed is None:
        return False
    return any(TARGET in path for path in precomputed['paths']) or any(x['navmesh'] == TARGET for x in precomputed['roadmarkers'])


def known_evidence(kind):
    rows = json.loads((BASE.parent/'plugin_integration/navmesh_comparison.json').read_text(encoding='utf-8'))['records']['Skyrim.esm|016F5D']
    pack, plugin = {'vanilla':('TuLED','Skyrim.esm'),'glen':('Anno','Glenmoril.esm'),
                    'ak':('TuLED','AKSkyrimUnderground.esm')}[kind]
    return next(row for row in rows if row['pack'] == pack and row['plugin'] == plugin)


def audit_sources(paths):
    result = {}
    for kind, path in paths.items():
        plugin = Plugin(path)
        record = plugin.get(TARGET, 'NAVM')
        model, triangles = geometry(plugin, record)
        evidence = known_evidence(kind)
        expected = {key:value for key,value in evidence['nvnm'].items() if key != 'changed_triangles_against_vanilla'}
        assert model == expected, f'{kind} source NAVM differs from reviewed evidence'
        assert record['flags'] == evidence['flags']
        navi = navi_model(plugin,plugin.get(NAVI,'NAVI'))
        audit = json.loads((BASE/'navi_source_audit.json').read_text(encoding='utf-8'))
        pinned = next(row for row in audit if Path(row['file']).name.lower() == plugin.name)
        assert len(pinned['entries']) == 1
        original = Plugin(pinned['file'])
        pinned_info = nvmi_model(original,bytes.fromhex(pinned['entries'][0]['raw_NVMI_hex']))
        assert navi['infos'][TARGET] == pinned_info, f'{kind} NVMI source changed from reviewed evidence'
        assert not target_in_precomputed(navi), f'{kind} NVPP now uses target NAVM'
        result[kind] = (plugin, record, model, triangles)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vanilla', required=True)
    parser.add_argument('--glen', required=True)
    parser.add_argument('--ak', required=True)
    parser.add_argument('--candidate')
    parser.add_argument('--typed-log')
    parser.add_argument('--navi-winning', help='Actual final source NAVI winner, as logged by the typed draft')
    parser.add_argument('--output', default=str(BASE/'source_preflight.json'))
    args = parser.parse_args()
    out = Path(args.output).resolve()
    assert out.is_relative_to(BASE.resolve()), 'Output must remain in navmesh_patch'
    sources = audit_sources({'vanilla':args.vanilla,'glen':args.glen,'ak':args.ak})
    report = {'utc':datetime.now(timezone.utc).isoformat(), 'status':'SOURCE_PREFLIGHT_PASS',
              'source_files':{kind:{'path':str(value[0].path),'navm_record':value[1],
                  'navm_payload_sha256':sha(value[0].payload(value[1]))} for kind,value in sources.items()}}
    if args.candidate:
        assert args.navi_winning, '--navi-winning is required for candidate verification'
        candidate = Plugin(args.candidate)
        assert candidate.header_flags & 0x200, 'Candidate lacks ESL flag'
        assert {'skyrim.esm','glenmoril.esm','akskyrimunderground.esm'}.issubset(candidate.masters)
        non_header = [r for r in candidate.records if r['signature'] != 'TES4']
        assert sorted((r['signature'],r['id']) for r in non_header) == sorted([('NAVM',TARGET),('CELL',CELL),('NAVI',NAVI)]), 'Unexpected extra or own records'
        rec = candidate.get(TARGET,'NAVM')
        model, triangles = geometry(candidate,rec)
        ak_model, ak_triangles = sources['ak'][2:]
        expected_triangles = [list(t) for t in ak_triangles]
        expected_triangles[502][6] = sources['glen'][3][502][6]
        assert expected_triangles[502][6] == 3072
        assert triangles == expected_triangles, 'Candidate has unexpected triangle changes'
        expected = dict(ak_model)
        expected['triangles_sha256'] = sha(b''.join(struct.pack('<hhh hhh HH',*t) for t in expected_triangles))
        expected['doors'] = sorted(ak_model['doors'] + [d for d in sources['glen'][2]['doors'] if d['triangle'] == 502],key=lambda d:(d['triangle'],d['door']))
        assert model == expected, 'Candidate has unexpected pathing/geometry/door/grid changes'
        for key in ('flags','vcs1','form_version','vcs2'):
            assert rec[key] == sources['ak'][1][key], f'Unexpected NAVM header change: {key}'
        winning_navi = Plugin(args.navi_winning)
        winning_record = winning_navi.get(NAVI,'NAVI')
        original_navi = navi_model(winning_navi,winning_record)
        assert not target_in_precomputed(original_navi), 'Final NVPP uses target NAVM'
        assert TARGET not in original_navi['deleted_navmeshes'], 'Final NAVI marks target deleted'
        ak_navi = navi_model(sources['ak'][0],sources['ak'][0].get(NAVI,'NAVI'))
        glen_navi = navi_model(sources['glen'][0],sources['glen'][0].get(NAVI,'NAVI'))
        expected_info = dict(ak_navi['infos'][TARGET])
        expected_info['doors'] = sorted(ak_navi['infos'][TARGET]['doors']+
            [door for door in glen_navi['infos'][TARGET]['doors'] if door['door'] == 'glenmoril.esm|0122F4'],key=lambda d:(d['door'],d['crc']))
        if TARGET in original_navi['infos']:
            assert original_navi['infos'][TARGET] == ak_navi['infos'][TARGET], 'Final source target NVMI is not reviewed AK content'
        expected_navi = dict(original_navi)
        expected_navi['infos'] = dict(original_navi['infos'])
        expected_navi['infos'][TARGET] = expected_info
        candidate_navi_record = candidate.get(NAVI,'NAVI')
        actual_navi = navi_model(candidate,candidate_navi_record)
        assert actual_navi == expected_navi, 'Unexpected NAVI/NVMI/NVPP/NVSI change'
        for key in ('flags','vcs1','form_version','vcs2'):
            assert candidate_navi_record[key] == winning_record[key], f'Unexpected NAVI header change: {key}'
        report['candidate'] = {'path':str(candidate.path),'sha256':sha(candidate.path.read_bytes()),
                               'masters':candidate.masters,'records':non_header,'nvnm':model,
                               'navi_source':str(winning_navi.path),'navi_target':actual_navi['infos'][TARGET],
                               'navi_other_entry_count':len(actual_navi['infos'])-1,
                               'navi_all_unchanged_other_content_verified':True}
        report['status'] = 'BINARY_PASS_TYPED_RELOAD_REQUIRED'
        if args.typed_log:
            log = Path(args.typed_log)
            text = log.read_text(encoding='utf-8-sig',errors='replace')
            assert 'BOUNDED_NAVM_RELOAD_TYPED_PASS|' in text
            assert 'BOUNDED_NAVM_STOP:' not in text
            report['typed_reload_log'] = {'path':str(log.resolve()),'sha256':sha(log.read_bytes())}
            report['status'] = 'STATIC_BINARY_AND_TYPED_RELOAD_PASS'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'report':str(out)},ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
