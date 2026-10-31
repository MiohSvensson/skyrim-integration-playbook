"""Prepare bounded, per-pack BodySlide jobs using only reviewed author inputs."""
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from materialize import BASE, TARGET, add_file_mapping, build, connect, sha, utc


def main():
    report = BASE/'integration/bodyslide_prepared.json'
    assert not report.exists(), 'Already prepared; inspect ledger before repeating'
    research = BASE/'integration/research/plugin_integration'
    plan = json.loads((research/'bodyslide_maintenance_plan.json').read_text('utf-8'))
    inputs = json.loads((research/'bodyslide_input_hash_manifest.json').read_text('utf-8'))
    source = BASE.parent/'TuLED/File Mod Skyrim SE/mods/BodySlide and Outfit Studio/CalienteTools/BodySlide'
    tool_files = [source/'BodySlide x64.exe']
    for folder in ['res', 'lang']:
        tool_files.extend(p for p in (source/folder).rglob('*') if p.is_file())
    mappings = []
    jobs = []
    for pack in ['Anno', 'Burida']:
        tool = TARGET/'tools/BodySlideMorph'/pack
        project = TARGET/'inputs/BodySlideMorph'/pack
        output = TARGET/'outputs/BodySlideMorph'/pack
        output.mkdir(parents=True, exist_ok=False)
        for p in tool_files:
            mappings.append({'source': str(p), 'destination': str((tool/p.relative_to(source)).relative_to(TARGET)), 'storage': 'private'})
        for p in (research/'bodyslide_plan'/pack).rglob('*'):
            if p.is_file():
                mappings.append({'source': str(p), 'destination': str((project/p.relative_to(research/'bodyslide_plan'/pack)).relative_to(TARGET)), 'storage': 'private'})
        for row in inputs['files']:
            if row['pack'] != pack:
                continue
            assert sha(row['path']) == row['sha256'], row['path']
            relative = Path(row['path_key']).relative_to('calientetools/bodyslide')
            mappings.append({'source': row['path'], 'destination': str((project/relative).relative_to(TARGET)), 'storage': 'private', 'bytes': row['bytes']})
        jobs.append({'pack': pack, 'tool': str(tool), 'project': str(project), 'output': str(output),
                     'command': [str(tool/'BodySlide x64.exe'), '-gbuild', 'Database Morph Repair - '+pack,
                                 '-p', '- Zeroed Sliders -', '-tri', '-t', str(output)],
                     'expected_projects': [r for r in plan['curated_projects'] if r['pack'] == pack]})
    c = connect()
    add_file_mapping(c, 'bodyslide_bounded_inputs', mappings,
                     'Private BodySlide 5.7.0 app, per-pack curated author projects and 97 SHA-locked NIF/OSD inputs; no original data writes')
    build(c)
    c.close()
    for job in jobs:
        tool, project = Path(job['tool']), Path(job['project'])
        for name in ['SliderPresets', 'SliderCategories']:
            (project/name).mkdir(exist_ok=True)
        config = ET.parse(source/'Config.xml')
        root = config.getroot()
        def set_value(name, value):
            node = root.find(name)
            if node is None:
                node = ET.SubElement(root, name)
            node.text = str(value)
        set_value('GameDataPath', TARGET/'Game/Data')
        set_value('GameDataPaths/SkyrimSpecialEdition', TARGET/'Game/Data')
        set_value('OutputDataPath', job['output'])
        set_value('ProjectPath', project)
        set_value('Anim/DefaultSkeletonReference', tool/'res/skeleton_female_sse.nif')
        set_value('Language', 0)
        set_value('BSATextureScan', 'false')
        set_value('GameRegKey', '')
        set_value('GameRegVal', '')
        config.write(tool/'Config.xml', encoding='utf-8', xml_declaration=True)
        (tool/'BodySlide.xml').write_text('<BodySlideConfig><SelectedPreset>- Zeroed Sliders -</SelectedPreset><BuildMorphs>true</BuildMorphs><BodySlideFrame x="80" y="80" width="960" height="720" maximized="false" /></BodySlideConfig>\n', encoding='utf-8')
        (tool/'BuildSelection.xml').write_text('<BuildSelection />\n', encoding='utf-8')
        job['private_config_sha256'] = sha(tool/'Config.xml')
        job['tool_sha256'] = sha(tool/'BodySlide x64.exe')
    result = {'utc': utc(), 'status': 'PREPARED_NOT_EXECUTED', 'jobs': jobs,
              'plan_sha256': sha(research/'bodyslide_maintenance_plan.json'),
              'inputs_manifest_sha256': sha(research/'bodyslide_input_hash_manifest.json'),
              'scope': 'Only 47 reviewed dedicated item projects. Keep author slider/zap defaults. Fresh output, all original tools/config/data remain unchanged.'}
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'jobs': len(jobs), 'mapped_files': len(mappings), 'projects': len(plan['curated_projects'])}, indent=2))


if __name__ == '__main__':
    main()
