"""Static 1.5.97 image inspection; does not map/execute/attach to the game."""
import bisect
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
CACHE = OWN / 'author_source_cache'
sys.path.insert(0, str(CACHE / 'capstone5'))
import capstone


def address_library(path):
    data = Path(path).read_bytes()
    pos = 0
    def get(fmt):
        nonlocal pos
        result = struct.unpack_from('<' + fmt, data, pos)[0]
        pos += struct.calcsize('<' + fmt)
        return result
    assert get('I') == 1
    version = [get('I') for _ in range(4)]
    assert version == [1, 5, 97, 0]
    length = get('I'); name = data[pos:pos+length].decode(); pos += length
    pointer, count = get('I'), get('I')
    assert pointer == 8
    prev_id = prev_offset = 0
    result = {}
    for _ in range(count):
        kind = get('B'); lo, hi = kind & 15, kind >> 4
        def number(mode, previous):
            if mode == 0: return get('Q')
            if mode == 1: return previous + 1
            if mode == 2: return previous + get('B')
            if mode == 3: return previous - get('B')
            if mode == 4: return previous + get('H')
            if mode == 5: return previous - get('H')
            if mode == 6: return get('H')
            if mode == 7: return get('I')
            raise ValueError(mode)
        identity = number(lo, prev_id)
        offset = number(hi & 7, prev_offset // pointer if hi & 8 else prev_offset)
        if hi & 8: offset *= pointer
        result[identity] = offset
        prev_id, prev_offset = identity, offset
    assert pos == len(data)
    return result, {'version': version, 'image_name': name, 'address_count': count, 'exact_EOF': True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe');parser.add_argument('--output');args=parser.parse_args()
    address_path = BASE / 'UnifiedSkyrim/mods/T4172 Address Library for SKSE Plugins/SKSE/Plugins/version-1-5-97-0.bin'
    executable = Path(args.exe) if args.exe else BASE / 'UnifiedSkyrim/Game/SkyrimSE.exe'
    mapping, library = address_library(address_path)
    data = executable.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    assert data[pe:pe+4] == b'PE\0\0'
    machine, nsections = struct.unpack_from('<HH', data, pe+4)
    assert machine == 0x8664
    opt_size = struct.unpack_from('<H', data, pe+20)[0]
    opt = pe + 24
    assert struct.unpack_from('<H', data, opt)[0] == 0x20b
    imagebase = struct.unpack_from('<Q', data, opt+24)[0]
    sections = []
    for n in range(nsections):
        p = opt + opt_size + n*40
        name = data[p:p+8].rstrip(b'\0').decode()
        vsize, rva, raw_size, raw = struct.unpack_from('<IIII', data, p+8)
        sections.append((rva, rva + max(vsize, raw_size), raw, name))
    def fileoff(rva):
        for start, end, offset, _ in sections:
            if start <= rva < end: return offset + rva - start
        raise ValueError(hex(rva))
    exception_rva, exception_size = struct.unpack_from('<II', data, opt+112+3*8)
    begin = fileoff(exception_rva)
    functions = [struct.unpack_from('<III', data, p) for p in range(begin, begin+exception_size, 12)]
    starts = [r[0] for r in functions]
    disassembler = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    def function(rva):
        i = bisect.bisect_right(starts, rva) - 1
        leaf = not (i >= 0 and functions[i][0] <= rva < functions[i][1])
        if leaf:
            start, end, unwind = rva, rva+128, 0
        else:
            start, end, unwind = functions[i]
        code = data[fileoff(start):fileoff(start)+end-start]
        assembly = []
        for ins in disassembler.disasm(code, imagebase+start):
            assembly.append({'rva': f'{ins.address-imagebase:08X}', 'bytes': ins.bytes.hex(), 'instruction': ins.mnemonic + ' ' + ins.op_str})
            if leaf and ins.mnemonic == 'ret':break
        return {'start_rva': f'{start:08X}', 'end_rva': f'{end:08X}', 'unwind_rva': f'{unwind:08X}',
                'sha256': hashlib.sha256(code).hexdigest(), 'instructions': assembly,'no_unwind_leaf_or_thunk':leaf}
    tables = []
    for identity in (236434, 236435, 236436):
        rva = mapping[identity]
        pointers = list(struct.unpack_from('<'+'Q'*10, data, fileoff(rva)))
        tables.append({'address_library_id': identity, 'rva': f'{rva:08X}', 'first10_vfunc_rvas': [f'{p-imagebase:08X}' for p in pointers]})
    # Third table is BSMaterialObject subobject; slot1 is EnsureLoaded per primary CommonLib headers.
    material_table = mapping[236436]
    ensure_loaded = struct.unpack_from('<Q', data, fileoff(material_table)+8)[0] - imagebase
    body = function(ensure_loaded)
    interpretable = bool(body['instructions'])
    helpers=[]
    for instruction in body['instructions']:
        mnemonic,_,operand=instruction['instruction'].partition(' ')
        if mnemonic=='jmp' and operand.startswith('0x'):
            target=int(operand,16)-imagebase
            helpers.append(function(target))
    output = {'status': 'STATIC_FUNCTION_BYTES_NEED_REVIEW_NOT_RUNTIME_SEMANTICS_PROOF' if interpretable else 'STATIC_IMAGE_TARGET_NOT_ANALYZABLE_NO_SEMANTICS_PROOF',
        'exe': {'path': str(executable), 'sha256': hashlib.sha256(data).hexdigest(), 'image_base': hex(imagebase)},
        'address_library': {'path': str(address_path), 'sha256': hashlib.sha256(address_path.read_bytes()).hexdigest(), **library},
        'primary_vtable_declaration': 'CommonLibSSE-NG VTABLE_BGSMaterialObject SE IDs236434/236435/236436, BSMaterialObject EnsureLoaded virtual slot1.',
        'tables': tables, 'ensure_loaded': body, 'direct_tail_helpers': helpers,
        'model_path_runtime_ignored_proved': False,
        'limits': 'Disassembly is static image data, not a game launch. Reverse-engineered symbol identities rely on the pinned primary CommonLib declarations and exact matching1.5.97 address library.'}
    path = Path(args.output).resolve() if args.output else OWN / 'material_ensure_loaded_disassembly.json'
    assert path.is_relative_to(OWN)
    path.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(path), 'tables': tables, 'ensure_loaded': body}, indent=2)[:21000])


if __name__ == '__main__':
    main()
