"""Create a bounded, non-executed build recipe and curated tool-only XML sets."""
import collections
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from bodyslide_inputs import key,parse,win


def main():
    audit=json.loads((OUT/'bodyslide_input_closure.json').read_text(encoding='utf-8'))
    closure=json.loads((OUT/'gear_resource_closure.json').read_text(encoding='utf-8'))
    by_plugin={r['plugin']:r for r in audit['plugins']};chosen_names={r.casefold() for r in by_plugin}
    parse_cache={}
    def element(project):
        path=project['osp_path']
        if path not in parse_cache:parse_cache[path]=parse(path)
        e=parse_cache[path].findall('SliderSet')[project['set_ordinal']]
        assert e.attrib['name']==project['name'];return e
    for project in audit['projects']:
        e=element(project)
        evidence=' '.join([project['name'],project['data_folder'],*[(s.text or '')+' '+s.attrib.get('DataFolder','') for s in e.findall('Shape')],
          *[g['name'] for g in project['original_groups']]])
        if re.search(r'\bube\b',evidence,re.I):family='UBE'
        elif re.search(r'cbbe|3ba|3bbb',evidence,re.I):family='CBBE_3BA'
        elif re.search(r'bhunp|uunp|\bunp\b',evidence,re.I):family='BHUNP_UUNP'
        else:family='unspecified'
        project['resolved_family']=family
    morph_targets=collections.defaultdict(set);global_morphs=[]
    for row in closure['candidates']:
        if row['name'].casefold() not in chosen_names:continue
        assets={a['path_key']:a for a in row['assets']}
        missing=set(row['missing_optional_morph_tri'])
        for edge in row['asset_edges']:
            if edge['to'] not in missing or not edge['field'].startswith('NiStringExtraData:BODYTRI'):continue
            mesh=edge['from']
            if assets[mesh]['base_presence']['kind']!='missing':
                global_morphs.append({'plugin':row['name'],'mesh':mesh,'missing_source_tri':edge['to'],'action':'inherit_global_base_model_and_its_own_morph_binding'});continue
            morph_targets[mesh].add(row['name'])
    selected={};unresolved=[]
    for mesh,owners in sorted(morph_targets.items()):
        options=[p for p in audit['projects'] if mesh in p['generated_paths'] and p['input_closure_passed'] and not p['prevent_morph_file']]
        compatible=[p for p in options if p['resolved_family']=='CBBE_3BA']
        if not compatible:
            # Rigged feet/cloth accessory sets can be family-unspecified; preserve as review candidates.
            unresolved.append({'mesh':mesh,'plugins':sorted(owners),'reason':'No declared CBBE/3BA input set with complete named-data closure',
              'other_closed_sets':[{'pack':p['pack'],'name':p['name'],'family':p['resolved_family'],'osp':p['osp_path']} for p in options]});continue
        score=lambda p:(p['is_saved_choice'] is not True,p['pack']!='TuLED',p['pack']!='Anno',p['name'].casefold(),p['osp_path'].casefold())
        best=min(compatible,key=score);pid=(best['pack'],best['osp_path'],best['set_ordinal'])
        selected.setdefault(pid,{'project':best,'meshes':set(),'plugins':set()})
        selected[pid]['meshes'].add(mesh);selected[pid]['plugins'].update(owners)
    plan=OUT/'bodyslide_plan';plan.mkdir(exist_ok=True)
    inputs={};projects=[];groups=collections.defaultdict(list)
    for number,(pid,row) in enumerate(selected.items(),1):
        p=row['project'];original=element(p);e=copy.deepcopy(original)
        unique=f"Database Morph {p['pack']} {number:03d} - {p['name']}";e.set('name',unique)
        root=ET.Element('SliderSetInfo',version='1');root.append(e)
        folder=plan/p['pack']/'SliderSets';folder.mkdir(parents=True,exist_ok=True)
        target=folder/f'DatabaseMorph_{number:03d}.osp';ET.ElementTree(root).write(target,encoding='utf-8',xml_declaration=True)
        # Verify every curated value except its tool-facing set name remains the authored XML.
        check=copy.deepcopy(e);check.set('name',original.attrib['name']);assert ET.tostring(check)==ET.tostring(original)
        group='Database Morph Repair - '+p['pack'];groups[p['pack']].append(unique)
        projects.append({'pack':p['pack'],'original_set_name':p['name'],'curated_set_name':unique,'curated_osp':str(target),
          'author_osp':p['osp_path'],'author_set_ordinal':p['set_ordinal'],'output_stem':p['output_stem'],
          'generated_paths':p['generated_paths'],'repair_meshes':sorted(row['meshes']),'plugins':sorted(row['plugins']),
          'group':group,'resolved_family':p['resolved_family'],'source_saved_output_choice':p['saved_output_choice'],
          'zap_defaults_preserved':p['zap_defaults'],'inputs':p['inputs']})
        for r in p['inputs']:inputs[p['pack'],r['path_key']]=r
    commands=[]
    for pack,names in groups.items():
        root=ET.Element('SliderGroups');group=ET.SubElement(root,'Group',name='Database Morph Repair - '+pack)
        for name in names:ET.SubElement(group,'Member',name=name)
        folder=plan/pack/'SliderGroups';folder.mkdir(exist_ok=True);path=folder/'DatabaseMorphRepair.xml';ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        commands.append({'source_pack':pack,'group':'Database Morph Repair - '+pack,
          'required_private_config_project_path':f'Database/integration/BodySlideInputs/{pack}',
          'argument_vector':['-gbuild','Database Morph Repair - '+pack,'-p','- Zeroed Sliders -','-tri','-t',r'E:\stock\Skyrim collection\Database\integration\Generated\BodySlide_MorphRepair'],
          'execute':False,'requirements':'Use a private Database BodySlide 5.7.0 tool copy/config. Import only listed ShapeData to its per-pack ProjectPath. Do not run the original executable or keep its original OutputDataPath.'})
    report={'scope':'Proposed bounded morph maintenance recipe only; no BodySlide execution, no original source edits and no generated NIF/TRI claims.',
      'configs':audit['configs'],'source_scan':audit['counts'],'missing_morph_meshes':len(morph_targets),
      'curated_projects':projects,'input_sources':list(inputs.values()),'unresolved_morph_targets':unresolved,'global_morphs_retained_from_base':global_morphs,
      'commands_not_executed':commands,
      'summary':{'curated_projects':len(projects),'repair_meshes_with_declared_CBBE_closed_inputs':len({m for r in projects for m in r['repair_meshes']}),
        'unresolved_meshes':len(unresolved),'required_unique_input_files':len(inputs),'required_input_logical_bytes':sum(r['bytes'] for r in inputs.values()),
        'affected_plugins_in_plan':len({n for r in projects for n in r['plugins']})},
      'constraints':[
        'Do not mix BHUNP/UBE projects into a CBBE/3BA build solely because the output filename matches.',
        'Per-pack private ProjectPath prevents foreign ShapeData or preset files from overriding the base global tool inputs. Curated set names/group prevent unintended batch targets.',
        'All required OSD named datasets and input-file presence were checked; a successful build and geometry/material/morph verification are still required.',
        'Saved SelectedPreset is UI state and cannot prove historical prebuilt meshes were generated with that preset.',
        'A missing BODYTRI is a morph limitation in the prebuilt source. It is not repaired by copying a similarly named TRI with different vertex topology.',
        'After any build, validate NIF target shapes and vertex-count compatibility with TRI, required textures/physics, exact allowed output set and any renderer material processing.',
        'Only tool-facing SliderSet name changed in curated OSP XML; authored shape definitions, source paths, slider defaults, zaps and output names remain unchanged.',
      ]}
    (OUT/'bodyslide_maintenance_plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=['# 新增裝備的 BodySlide 可維護性','','本次只讀掃描與建立工具用配方，未執行 BodySlide、未修改來源。',
      '',f"52份裝備的694個專屬ARMA模型路徑，找到415個精確輸出相符的SliderSet；407個已閉合輸入檔案及OSD具名資料集。27份來源插件至少有一項BODYTRI缺件。",'',
      f"有明確CBBE/3BA且輸入閉合的建議有界配方：{report['summary']['curated_projects']}個專案，覆蓋{report['summary']['repair_meshes_with_declared_CBBE_closed_inputs']}個需morph修復的模型；尚有{len(unresolved)}個模型沒有可確認的CBBE/3BA重建方案。",'',
      '兩包目前UI都保存 `- Zeroed Sliders -` 和 `BuildMorphs=true`，也都啟用OBody NG。這只證明目前工具設定；不能反推每份預生成網格的歷史preset。缺TRI的衣服可顯示既有模型，但OBody變形功能不能據此宣告完整。', '',
      'TuLED工具版本是5.7.0，已按對應tag原始碼確認只支援 `-gbuild`、`-p`、`-t`、`-tri`。新wiki的 `--build`／`--filter` 不套用此版本。', '',
      '配方位於 `bodyslide_plan/<pack>/SliderSets` 與 `SliderGroups`，每項只改工具顯示名稱以隔離同名專案，其餘XML值原樣保留。ShapeData來源清單在 `bodyslide_maintenance_plan.json`；按pack分開私有ProjectPath，不覆蓋基底CBBE/3BA工具輸入。', '',
      '原TuLED Config.xml的OutputDataPath指向原包Body Slide Output，不能直接使用。後續若實際重建，須建立Database私有工具/config，使用JSON中明確的 `-t` 輸出到Database，重建後再核對NIF/TRI拓撲、材質、物理及允許輸出清單。', '',
      '作者來源：[BodySlide 5.7.0 CLI定義](https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/v5.7.0/src/program/BodySlideApp.h#L198)、[輸入資料夾與具名OSD載入](https://github.com/ousnius/BodySlide-and-Outfit-Studio/blob/v5.7.0/src/components/SliderSet.cpp#L173)。']
    (OUT/'BodySlide維護方案.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
