"""Assemble verified, bounded import instructions. Never writes runtime data."""
import hashlib
import json
from pathlib import Path
import struct
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
from bsarch_readonly import extract_files
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from quest_resource_seeds import records, plugin_header


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(rel):
    return json.loads((BASE / rel).read_text(encoding='utf-8-sig'))


def provenance(path):
    return {'path': str(path), 'sha256': sha(path)}


def item(path, destination, category, **extra):
    path = Path(path)
    assert path.is_file(), path
    return {'category': category, 'source_kind': 'loose', 'source_path': str(path),
            'source_sha256': sha(path), 'size_bytes': path.stat().st_size,
            'destination_relative': destination.replace('\\', '/').lower(), **extra}


def main():
    OWN.mkdir(parents=True, exist_ok=True)
    prepared_path = BASE / 'integration/bodyslide_prepared.json'
    prepared = load('integration/bodyslide_prepared.json')
    evidence_path = BASE / 'integration/research/bodyslide_validation/green_nun_bodytri_rebind_evidence.json'
    green = json.loads(evidence_path.read_text(encoding='utf-8'))
    overrides = {Path(x['source']): x for x in green['candidates']}
    entries = []
    projects = []
    for job in prepared['jobs']:
        output_root = Path(job['output'])
        for project in job['expected_projects']:
            paths = project['generated_paths'] + [project['output_stem'] + '.tri']
            projects.append({'pack': job['pack'], 'project': project['curated_set_name'],
                             'plugins': project['plugins'], 'output_root': str(output_root),
                             'destinations': paths})
            for relative in paths:
                generated = output_root / relative
                override = overrides.get(generated)
                selected = Path(override['candidate']) if override else generated
                if override:
                    assert sha(generated) == override['source_sha256']
                    assert sha(selected) == override['candidate_sha256']
                entries.append(item(selected, relative, 'bodyslide_generated',
                    pack=job['pack'], project=project['curated_set_name'],
                    plugins=project['plugins'], generated_original=provenance(generated),
                    candidate_override=bool(override),
                    override_evidence=provenance(evidence_path) if override else None))
    assert len(projects) == 47 and len(entries) == 141
    assert len({x['destination_relative'] for x in entries}) == len(entries)
    assert sum(x['candidate_override'] for x in entries) == 2
    supplement = load('integration/research/vfs_validation/eula_effect_texture_supplement.json')
    eula = supplement['source_candidates'][0]
    entry = item(eula['physical_path'], supplement['path_key'], 'effect_shader_texture',
                 source_mod_id=eula['id'], source_mod_name=eula['name'],
                 required_by={'path': supplement['referenced_by'], 'field': supplement['typed_field']})
    assert entry['source_sha256'] == eula['sha256']
    entries.append(entry)
    closure_path = BASE / 'integration/research/feature_patch_closure/patch_resource_manifest.json'
    closure = json.loads(closure_path.read_text(encoding='utf-8'))
    extracts = [x for x in closure['resources'] if x['decision'] == 'stage_exact_source_resource']
    assert len(extracts) == 3
    for resource in extracts:
        source = resource['selected_source']
        assert source['kind'] == 'bsa'
        assert sha(source['archive_physical']) == source['archive_sha256']
        payload = extract_files(source['archive_physical'], {source['entry']: source['sha256']})[source['entry']]
        assert len(payload) == source['bytes']
        local = OWN / 'author_patch_assets' / resource['path_key']
        local.parent.mkdir(parents=True, exist_ok=True)
        if local.exists():
            assert local.read_bytes() == payload
        else:
            local.write_bytes(payload)
        entries.append(item(local, resource['path_key'], 'author_patch_display_model',
            author_extraction={'archive_path': source['archive_physical'],
                'archive_sha256': source['archive_sha256'], 'member': source['entry'],
                'member_sha256': source['sha256'], 'archive_id': source['archive_id'],
                'source_mod_id': source['mod_id']}, requested_by=resource['requested_by']))
    for sequence in closure['sequence_files_to_generate']:
        plugin = next(x for x in closure['plugins'] if x['name'] == sequence['plugin'])
        assert sha(plugin['source_path']) == plugin['sha256']
        header = plugin_header(plugin['source_path'])
        ids = []
        for record in records(plugin['source_path'], masters=header['masters'], name=plugin['name'], signatures={'QUST'}):
            if record['flags'] & 0x20 or record['fid'] >> 24 != len(header['masters']):
                continue
            dnam = next((v for t, v in record['fields'] if t == 'DNAM'), b'')
            if len(dnam) >= 2 and struct.unpack_from('<H', dnam)[0] & 1:
                ids.append(record['fid'])
        assert [f'{x:08X}' for x in ids] == sequence['raw_own_sge_formids']
        payload = struct.pack('<' + 'I' * len(ids), *ids)
        path = OWN / 'generated_sequence' / sequence['path_key']
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            assert path.read_bytes() == payload
        else:
            path.write_bytes(payload)
        entries.append(item(path, sequence['path_key'], 'generated_own_sge_sequence',
            defining_plugin=plugin['name'], defining_plugin_source=provenance(plugin['source_path']),
            raw_fixed_formids=[f'{x:08X}' for x in ids], bytes_hex=payload.hex(),
            algorithm='Little-endian uint32 FixedFormID of every nondeleted own QUST with DNAM Start Game Enabled bit; no runtime load-order IDs.'))
    assert len(entries) == 148
    assert len({x['destination_relative'] for x in entries}) == 148
    validation = BASE / 'integration/research/bodyslide_validation/all47_corrected_candidates_topology.json'
    report = json.loads(validation.read_text(encoding='utf-8'))
    assert report['status'] == 'PASS_STATIC_GENERATED_NIF_TRI_TOPOLOGY'
    result = {'schema': 'skyrim.supplemental_import.v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'VERIFIED_IMPORT_PLAN_NOT_DEPLOYED_BY_THIS_SCRIPT',
        'scope': '47 BodySlide project outputs, two exact generated-copy BODYTRI substitutions, one original Eula texture, three original Forgotten City display NIFs, and three own-SGE sequence files.',
        'counts': {'projects': 47, 'body_outputs': 141, 'body_nif': 94, 'body_tri': 47,
                   'candidate_overrides': 2, 'original_dds': 1, 'original_patch_nif': 3, 'generated_seq': 3, 'effective_import_files': 148},
        'constraints': ['Copy only listed destinations; do not import entire mixed source mods.',
            'Revalidate every source SHA before copying; any mismatch is fatal.',
            'Keep both Green Nun endpoint overrides together with the exact generated project TRI.',
            'Place these bounded output resources above their imported equipment/feature sources.',
            'This plan does not modify plugin records or source archives, and does not claim in-game rendering.'],
        'provenance': [provenance(prepared_path), provenance(evidence_path), provenance(validation), provenance(closure_path)],
        'body_projects': projects, 'imports': entries}
    out = OWN / 'supplemental_import_plan.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'counts': result['counts'], 'path': str(out), 'sha256': sha(out)}))


if __name__ == '__main__':
    main()
