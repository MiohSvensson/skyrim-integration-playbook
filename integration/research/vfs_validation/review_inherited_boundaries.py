"""Review authoritative selections for ambiguous inherited mesh sources."""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2]
sys.path.insert(0, str(HERE))
import vfs_common as vfs
from mesh_sources import SourceResolver
from nif_resource_inventory import inventory

SOURCE_DIR = HERE / 'inherited_mesh_sources'
LAYER = BASE / 'UnifiedSkyrim/mods/ZZ83 Verified generated item and quest assets'


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': vfs.digest(path), 'bytes': path.stat().st_size}


def main():
    assert vfs.injected(), 'Actual MO2 VFS injection required'
    input_path = HERE / 'inherited_mesh_source_manifest.json'
    source_report = json.loads(input_path.read_text('utf-8'))
    stock = BASE / 'repairs/consistent_stock/Data/Skyrim - Meshes0.bsa'
    lotd = BASE.parent / 'TuLED/File Mod Skyrim SE/mods/[LED]Legacy of the Dragonborn v6.10.0/LegacyoftheDragonborn.bsa'
    overrides = {
        'meshes/armor/bandit/1stpersonbody1m_1.nif': {'archive': str(stock), 'entry_sha256': 'e483123be116f1d1698626d872cb006f6d4b5fb9fe90c2e01937533a3caa69aa',
            'archive_sha256': '91d0c93706846cefe4c51be5a7dee95e9042a0ad2069962b219c5bcabc75234e', 'basis': 'Exact selected TuLED stock archive for the TuLED-based integration'},
        'meshes/clothes/beggarclothes/torsom_0.nif': {'archive': str(stock), 'entry_sha256': '3b59687449f92d053f371a4e093058202f833499d5e5b7c47f48a2be37379d1c',
            'archive_sha256': '91d0c93706846cefe4c51be5a7dee95e9042a0ad2069962b219c5bcabc75234e', 'basis': 'Exact selected TuLED stock archive for the TuLED-based integration'},
        'meshes/ellise/qta_rlcoat/f/qta_rlc_jerkin1stf_1.nif': {'archive': str(lotd), 'entry_sha256': '0b11ec8b19e989bf757eaa1fdb5218c2a11759f6b547ed6dfcf0aef18ebcea51',
            'archive_sha256': '210d83b82e3715caed64e2c323592b96e387d77b79b063265f3ee24daa325db6', 'basis': 'Exact source-owner Legacy of the Dragonborn archive; do not substitute the similarly named Aeldsten asset'},
        'meshes/ellise/qta_rlcoat/f/qta_rlc_jerkinf_1.nif': {'archive': str(lotd), 'entry_sha256': '3e842d7d159cf852cd333501cd39b8f82d5a454c90d2e0e99967d2649e54abc0',
            'archive_sha256': '210d83b82e3715caed64e2c323592b96e387d77b79b063265f3ee24daa325db6', 'basis': 'Exact source-owner Legacy of the Dragonborn archive; do not substitute the similarly named Aeldsten asset'},
    }
    resolver = SourceResolver(SOURCE_DIR, overrides=overrides, strict=True)
    selected = []
    for path in overrides:
        source, basis = resolver.source_for(path)
        parsed = inventory(source)
        assert parsed['sha256'] == overrides[path]['entry_sha256']
        assert any(block.get('textures') for block in parsed['blocks'])
        selected.append({'path': path, 'source': pin(source), 'destination': str(LAYER / path), 'basis': basis})
    alias = BASE.parent / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2/meshes/dr aris tag/1stperson/1stperson_DR_Aris_Armor_0.nif'
    assert (alias.parent / '1stperson_DR_Aris_Armor_1.nif').is_file()
    selected.append({'path': 'meshes/dr aris tag/1stperson/1stperson_dr_aris_armor.nif', 'source': pin(alias),
                     'destination': str(LAYER / 'meshes/dr aris tag/1stperson/1stperson_dr_aris_armor.nif'),
                     'basis': 'Default unnumbered model derived from exact author weight-0 mesh; weight-1 is separately present'})
    effect_path = SOURCE_DIR / 'meshes/armor/dac0da/worm/headfx.nif'
    effect = inventory(effect_path)
    assert effect['sha256'] == '462a8d1f6202fe330173d15e58950ecd8872134fece2913e0128926ba82f0631'
    effects = [block for block in effect['blocks'] if block['type'] == 'BSEffectShaderProperty']
    assert len(effects) == 6
    assert all(not value.casefold().endswith(('.dds', '.png', '.tga')) for value in effect['strings'])
    effect_row = {'path': 'meshes/armor/dac0da/worm/headfx.nif', 'source': pin(effect_path),
                  'destination': str(LAYER / 'meshes/armor/dac0da/worm/headfx.nif'),
                  'basis': 'Exact author BSEffectShaderProperty mesh; no external texture filename in the NIF strings',
                  'effect_shader_count': len(effects), 'external_texture_references': []}
    handled = set(overrides) | {'meshes/dr aris tag/1stperson/1stperson_dr_aris_armor.nif', 'meshes/armor/dac0da/worm/headfx.nif'}
    remaining = [row for row in source_report['blockers'] if row['path'] not in handled]
    report = {'schema': 'skyrim.inherited_boundary_review.v1', 'status': 'BOUNDARY_SOURCE_SELECTION_PASS',
              'source_manifest_sha256': vfs.digest(input_path), 'selected_meshes': selected,
              'effect_shader': effect_row, 'source_overrides': overrides,
              'remaining_unresolved_meshes': remaining,
              'selected_mesh_count': len(selected) + 1, 'remaining_mesh_count': len(remaining),
              'installation_performed': False, 'original_packs_modified': False, 'game_launched': False}
    output = HERE / 'inherited_boundary_review_manifest.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'selected': report['selected_mesh_count'],
                      'remaining': len(remaining), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
