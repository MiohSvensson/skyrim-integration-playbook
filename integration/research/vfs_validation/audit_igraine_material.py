"""Audit the authored Igraine hand material without changing meshes or controls."""
import argparse
import ctypes
import hashlib
import importlib
import json
from pathlib import Path
import sys
import types
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
COLLECTION = BASE.parent
sys.path.insert(0, str(HERE))
from nif_resource_inventory import inventory

AUTHOR = COLLECTION / 'Anno/iniRePather-Skyrim/mods/【服装】 贵族小裙子 SC - Order1886 - Igraine'
PRESET = AUTHOR / 'CalienteTools/BodySlide/SliderSets/Igraine Knight CBBE 3BA.osp'
SOURCE = AUTHOR / 'CalienteTools/BodySlide/ShapeData/Igraine Knight CBBE 3BA/HandsF.nif'
MORPH = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets/meshes/sc/4_ports/21_order1886/igraine/knight/handsf_0.nif'
MASK = AUTHOR / 'textures/SC/4_Ports/21_Order1886/Igraine/Knight/Hands_F_m.dds'
CUBEMAP = COLLECTION / 'Anno/iniRePather-Skyrim/mods/头环材质替换-JS Vanilla Circlets/textures/johnskyrim/vanillacirclets/cubes/quicksilver_e.dds'
NIFLY = BASE / 'integration/research/feature_generation/primary_sources/PyNifly/addon/io_scene_nifly'
TARGET_LAYER = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets'
MASK_DEST = TARGET_LAYER / 'textures/SC/4_Ports/21_Order1886/Igraine/Knight/Hands_F_m.dds'
CUBE_DEST = TARGET_LAYER / 'textures/SC/4_Ports/21_Order1886/Igraine/Knight/quicksilver_e.dds'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def pin(path):
    path = path.resolve(strict=True)
    return {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}


def shader_reader():
    package = types.ModuleType('io_scene_nifly')
    package.__path__ = [str(NIFLY)]
    sys.modules['io_scene_nifly'] = package
    pyn = types.ModuleType('io_scene_nifly.pyn')
    pyn.__path__ = [str(NIFLY / 'pyn')]
    sys.modules['io_scene_nifly.pyn'] = pyn
    defs = importlib.import_module('io_scene_nifly.pyn.nifdefs')
    lib = ctypes.CDLL(str(NIFLY / 'NiflyDLL.dll'))
    lib.load.argtypes = [ctypes.c_char_p]
    lib.load.restype = ctypes.c_void_p
    lib.getShapes.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.getShapes.restype = ctypes.c_int
    lib.getBlockID.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.getBlockID.restype = ctypes.c_int
    lib.getBlock.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
    lib.getBlock.restype = ctypes.c_int
    lib.destroy.argtypes = [ctypes.c_void_p]

    def read(path):
        nif = lib.load(str(path.resolve()).encode('utf-8'))
        assert nif
        try:
            count = lib.getShapes(nif, None, 0, 0)
            shapes = (ctypes.c_void_p * count)()
            assert count == 1 and lib.getShapes(nif, shapes, count, 0) == count
            shape = defs.NiShapeBuf()
            shape.bufType = defs.PynBufferTypes.NiShapeBufType
            shape_id = lib.getBlockID(nif, shapes[0])
            assert lib.getBlock(nif, shape_id, ctypes.byref(shape)) == 0
            shader = defs.NiShaderBuf()
            shader.bufType = defs.PynBufferTypes.NiShaderBufType
            assert lib.getBlock(nif, shape.shaderPropertyID, ctypes.byref(shader)) == 0
            return {'shape_count': count, 'shader_type': int(shader.Shader_Type),
                    'shader_flags_1': hex(shader.Shader_Flags_1), 'shader_flags_2': hex(shader.Shader_Flags_2),
                    'environment_mapping': bool(shader.Shader_Flags_1 & (1 << 7)),
                    'environment_map_scale': shader.Env_Map_Scale}
        finally:
            lib.destroy(nif)
    return read


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    source = inventory(SOURCE)
    morph = inventory(MORPH)
    source_slots = [row['textures'] for row in source['blocks'] if 'textures' in row]
    morph_slots = [row['textures'] for row in morph['blocks'] if 'textures' in row]
    assert source_slots == morph_slots and len(source_slots) == 1
    slots = source_slots[0]
    assert len(slots) == 9 and slots[4].casefold().endswith('igraine\\knight\\quicksilver_e.dds')
    assert slots[5].casefold().endswith('igraine\\knight\\hands_f_m.dds')
    sets = ET.parse(PRESET).getroot().findall('SliderSet')
    selected = [s for s in sets if s.get('name') == 'Igraine Hands CBBE 3BA']
    assert len(selected) == 1
    selected = selected[0]
    assert selected.findtext('SourceFile') == 'HandsF.nif'
    assert selected.findtext('DataFolder') == 'Igraine Knight CBBE 3BA'
    assert selected.findtext('OutputFile') == 'HandsF'
    assert sha(SOURCE) == '1397122df98a064f24057e60f50f8d183c715fa2b660d73e010f6af4a7d1ba02'
    assert sha(MORPH) == '94003fee159c22d12491414f1c75f1832668ef8c6b8ee06277fca6108ab9c493'
    assert sha(MASK) == '1c5f854333b695638858f1a4ca75ec1e917ed39c4e0c371dd41ef55ca5d86e44'
    assert sha(CUBEMAP) == '4e67563091799fc034c12748b9ce50b4e02302dd58e5b286b068cd31751ed077'
    read_shader = shader_reader()
    source_shader = read_shader(SOURCE)
    morph_shader = read_shader(MORPH)
    assert source_shader == morph_shader
    assert source_shader['shader_type'] == 1 and source_shader['environment_mapping']
    assert not MASK_DEST.exists() and not CUBE_DEST.exists(), 'Review an existing repair instead of overwriting it'
    report = {
        'schema': 'skyrim.igraine_material_audit.v1',
        'status': 'READY_FOR_PRIVATE_RESOURCE_INSTALL',
        'authored_preset': pin(PRESET),
        'authored_mesh': pin(SOURCE),
        'runtime_morph': pin(MORPH),
        'texture_slots': slots,
        'shader': source_shader,
        'shader_meaning': 'BSLSP_ENVMAP=1; SLSF1_ENVIRONMENT_MAPPING=1<<7; source and generated morph are identical',
        'nifly_dll': pin(NIFLY / 'NiflyDLL.dll'),
        'nifdefs': pin(NIFLY / 'pyn/nifdefs.py'),
        'private_resource_mapping': [
            {'source': pin(MASK), 'destination': str(MASK_DEST), 'basis': 'Exact authored mask present in the source package'},
            {'source': pin(CUBEMAP), 'destination': str(CUBE_DEST), 'basis': 'Byte-identical to official stock Skyrim - Textures3.bsa textures/cubemaps/ore_quicksilver_e.dds; explicit typed environment-map repair, not an invented texture'}
        ],
        'candidate_bytes_absent_before_install': True,
        'original_packs_modified': False,
        'mesh_or_controls_modified': False,
        'required_next': 'Install only these two private resource copies into the already-active ZZ83 layer, then run an actual MO2 VFS/resource closure probe. No in-game proof is implied.'
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        output = args.output.resolve()
        assert output.is_relative_to(BASE / 'integration/research/vfs_validation')
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
