"""Find exact output-path SliderSets and validate their input NIF/OSD/BSD closure.

Read-only sources; no BodySlide process is launched and no inputs are copied.
"""
import collections
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import time
import xml.etree.ElementTree as ET

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
TOOLROOT='calientetools/bodyslide/'
SHAPEROOT=TOOLROOT+'shapedata/'


def key(value):return value.replace('\\','/').strip('/').casefold()
def win(path):
    s=str(Path(path).absolute());return s if s.startswith('\\\\?\\') else '\\\\?\\'+s
def parse(path):return ET.parse(win(path)).getroot()
def sha(path):
    h=hashlib.sha256()
    with open(win(path),'rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def osd_names(path):
    size=Path(win(path)).stat().st_size;names={}
    with open(win(path),'rb') as f:
        magic,version,count=struct.unpack('<III',f.read(12));assert magic==0x4f534400 and version==1,(magic,version)
        for _ in range(count):
            n=struct.unpack('<B',f.read(1))[0];name=f.read(n).decode('utf-8','replace');diffs=struct.unpack('<H',f.read(2))[0]
            names[name]=diffs;f.seek(diffs*14,1);assert f.tell()<=size
        assert f.tell()==size,(f.tell(),size)
    return names


def main():
    c=sqlite3.connect((ROOT/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    mods={r['id']:dict(r) for r in c.execute('select * from mods')};packs={r['id']:r['name'] for r in c.execute('select id,name from packs')}
    active=collections.defaultdict(dict)
    for r in c.execute('''select p.name,pm.mod_id,pm.list_order from profile_mods pm join profiles r on r.id=pm.profile_id
      join packs p on p.id=r.pack_id where r.is_selected=1 and pm.enabled=1 and pm.mod_id is not null'''):active[r['name']][r['mod_id']]=r['list_order']
    closure=json.loads((OUT/'gear_resource_closure.json').read_text(encoding='utf-8'))
    selected=[]
    for filename in ['gear_builder_manifest_batch1_48.json','gear_builder_manifest_batch2.json']:
        selected.extend(json.loads((OUT/filename).read_text(encoding='utf-8'))['plugins'])
    names={r['name'].casefold() for r in selected};target_owners=collections.defaultdict(set);plugin_targets=collections.defaultdict(set)
    for row in closure['candidates']:
        if row['name'].casefold() not in names:continue
        assets={a['path_key']:a for a in row['assets']}
        for ref in row['direct_asset_references']:
            target=ref['key']
            if ref['signature']!='ARMA' or not target.endswith('.nif') or assets[target]['base_presence']['kind']!='missing':continue
            target_owners[target].add(row['name']);plugin_targets[row['name']].add(target)
    cache={}
    def resolve(pack,pathkey):
        ck=(pack,pathkey)
        if ck in cache:return cache[ck]
        rs=[]
        for row in c.execute('select mod_id,relative_path,size_bytes from files indexed by ix_file_path where path_key=? and virtual_candidate=1',(pathkey,)):
            if row['mod_id'] in active[pack]:rs.append(dict(row))
        if rs:
            row=min(rs,key=lambda r:active[pack][r['mod_id']]);m=mods[row['mod_id']]
            result={'pack':pack,'path_key':pathkey,'path':str(Path(m['path'])/row['relative_path']),'mod_id':m['id'],'mod_name':m['name'],'bytes':row['size_bytes']}
        else:result=None
        cache[ck]=result;return result
    visible={}
    for row in c.execute("select mod_id,path_key,relative_path,size_bytes from files where extension in ('.osp','.xml') and virtual_candidate=1"):
        pk=row['path_key'];folder=pk.rsplit('/',1)[0]
        if not folder.startswith((TOOLROOT+'slidersets/',TOOLROOT+'slidergroups/')) and folder not in (TOOLROOT+'slidersets',TOOLROOT+'slidergroups'):continue
        m=mods[row['mod_id']];pack=packs[m['pack_id']]
        if row['mod_id'] not in active[pack]:continue
        ck=(pack,pk)
        if ck not in visible or active[pack][row['mod_id']]<active[pack][visible[ck]['mod_id']]:visible[ck]=dict(row)|{'pack':pack,'path':str(Path(m['path'])/row['relative_path'])}
    configs={};build_choices={}
    for pack,mid in [('Anno',1494),('Burida',1980),('TuLED',4360)]:
        d=Path(mods[mid]['path'])/'CalienteTools/BodySlide';general=parse(d/'Config.xml');ui=parse(d/'BodySlide.xml');choice=parse(d/'BuildSelection.xml')
        configs[pack]={'tool_directory':str(d),'general_config':str(d/'Config.xml'),'ui_config':str(d/'BodySlide.xml'),
          'selected_outfit':ui.findtext('SelectedOutfit'),'selected_preset':ui.findtext('SelectedPreset'),'build_morphs':ui.findtext('BuildMorphs'),
          'game_data_path':general.findtext('GameDataPath'),'output_data_path':general.findtext('OutputDataPath'),
          'skeleton_reference':general.findtext('Anim/DefaultSkeletonReference'),'body_family':'CBBE/3BA base; UI selection is not proof of all prebuilt mesh presets.'}
        build_choices[pack]={key(r.attrib['path']):r.attrib['choice'] for r in choice.findall('OutputChoice')}
    projects=[];errors=[];groups=[];osd_cache={};scanned=collections.Counter()
    for index,row in enumerate(visible.values()):
        try:root=parse(row['path'])
        except Exception as e:errors.append({'path':row['path'],'error':repr(e)});continue
        pack=row['pack']
        if '/slidergroups/' in row['path_key']:
            for group in root.findall('Group'):
                members=[e.attrib.get('name','') for e in group.findall('Member')]
                groups.append({'pack':pack,'path':row['path'],'path_key':row['path_key'],'group':group.attrib.get('name'),'members':members})
            continue
        scanned[pack]+=1
        for ordinal,slider in enumerate(root.findall('SliderSet')):
            output=slider.find('OutputFile');outputpath=slider.findtext('OutputPath') or '';outputname=output.text if output is not None and output.text else ''
            stem=key(outputpath+'/'+outputname)
            if not stem.startswith('meshes/'):stem='meshes/'+stem
            weighted=output is None or output.attrib.get('GenWeights','true').casefold()=='true'
            generated=[stem+'_0.nif',stem+'_1.nif'] if weighted else [stem+'.nif']
            matches=[p for p in generated if p in target_owners]
            if not matches:continue
            name=slider.attrib.get('name');folder=slider.findtext('DataFolder') or slider.findtext('SetFolder') or '';source=slider.findtext('SourceFile') or ''
            required=collections.defaultdict(set);data_key=key(SHAPEROOT+folder+'/'+source);required[data_key].add('SourceFile')
            target_folders={}
            for shape in list(slider.findall('Shape'))+list(slider.findall('BaseShapeName')):
                target_folders[shape.attrib.get('target',shape.text)]=shape.attrib.get('DataFolder',folder).split(';')
            missing=[];dataset_issues=[];refs=[]
            for element in slider.findall('Slider/Data'):
                value=(element.text or '').replace('\\','/');target=element.attrib.get('target');local=element.attrib.get('local','false').casefold()=='true'
                folders=[folder] if local else target_folders.get(target,[folder])
                if value.casefold().endswith('.bsd'):file=value;dataset=None
                elif '/' in value:file,dataset=value.rsplit('/',1)
                else:dataset_issues.append({'reference':value,'issue':'No physical data file separator'});continue
                alternatives=[key(SHAPEROOT+f+'/'+file) for f in folders]
                source_ref=next((resolve(pack,p) for p in alternatives if resolve(pack,p)),None)
                if source_ref:
                    required[source_ref['path_key']].add('SliderData')
                    if dataset and file.casefold().endswith('.osd'):
                        pp=source_ref['path']
                        if pp not in osd_cache:
                            try:osd_cache[pp]={'names':osd_names(pp),'error':None}
                            except Exception as e:osd_cache[pp]={'names':{},'error':repr(e)}
                        od=osd_cache[pp]
                        if od['error'] or dataset not in od['names']:dataset_issues.append({'path_key':source_ref['path_key'],'dataset':dataset,'issue':od['error'] or 'Named OSD dataset missing'})
                else:missing.append({'alternatives':alternatives,'reference':value,'target':target})
                refs.append({'physical_file':file,'dataset':dataset,'target':target,'local':local,'folders':folders})
            inputs=[]
            for pk,roles in required.items():
                found=resolve(pack,pk)
                if found:inputs.append(found|{'roles':sorted(roles)})
                else:missing.append({'alternatives':[pk],'reference':source,'role':'SourceFile'})
            family='CBBE_3BA' if re.search(r'cbbe|3ba|3bbb',name+' '+folder,re.I) else 'BHUNP_UUNP' if re.search(r'bhunp|uunp|\bunp\b',name+' '+folder,re.I) else 'UBE' if re.search(r'\bube\b',name+' '+folder,re.I) else 'unspecified'
            chosen=build_choices[pack].get(stem);ischoice=chosen==name if chosen else None
            projects.append({'pack':pack,'osp_path':row['path'],'osp_path_key':row['path_key'],'osp_source_mod_id':row['mod_id'],
              'set_ordinal':ordinal,'name':name,'data_folder':folder,'source_file':source,'output_stem':stem,'generated_paths':generated,
              'matches_adopted_armor_models':matches,'requested_by':sorted({n for p in matches for n in target_owners[p]}),
              'gen_weights':weighted,'prevent_morph_file':output is not None and output.attrib.get('PreventMorphFile','false').casefold()=='true',
              'family':family,'saved_output_choice':chosen,'is_saved_choice':ischoice,'inputs':inputs,'missing_inputs':missing,
              'dataset_issues':dataset_issues,'input_closure_passed':not missing and not dataset_issues,
              'slider_count':len(slider.findall('Slider')),'shape_count':len(slider.findall('Shape')),
              'zap_defaults':[{'name':s.attrib.get('name'),'small':s.attrib.get('small'),'big':s.attrib.get('big'),'hidden':s.attrib.get('hidden')} for s in slider.findall('Slider') if s.attrib.get('zap','false').casefold()=='true'],
              'data_references':refs})
        if index%500==0:print('scanned tool files',index+1,'/',len(visible),flush=True)
    for project in projects:
        project['original_groups']=[{'name':g['group'],'source_path':g['path'],'source_path_key':g['path_key']} for g in groups if g['pack']==project['pack'] and project['name'] in g['members']]
    summary=[]
    for plugin in selected:
        name=plugin['name'];targetset=plugin_targets[name];ps=[p for p in projects if name in p['requested_by']]
        covered={v for p in ps if p['input_closure_passed'] for v in p['matches_adopted_armor_models']};compatible={v for p in ps if p['input_closure_passed'] and p['family'] in ('CBBE_3BA','unspecified') for v in p['matches_adopted_armor_models']}
        summary.append({'plugin':name,'source_pack':plugin['pack'],'dedicated_armor_model_count':len(targetset),
          'matching_projects':len(ps),'closed_projects':sum(p['input_closure_passed'] for p in ps),
          'model_paths_without_any_closed_input':sorted(targetset-covered),'model_paths_without_CBBE_or_unspecified_closed_input':sorted(targetset-compatible),
          'missing_bodytri_from_original_source':plugin['missing_optional_morph_tri'],
          'status':'static_item_no_body_build_required' if not targetset else 'pregenerated_only_for_unmatched_models' if targetset-covered else 'exact_output_inputs_available_requires_variant_choice'})
    result={'scope':'Only output-path-exact matches for 52 adopted item plugins. Existing source files were not changed and BodySlide was not launched.',
      'tool_version':'5.7.0.0 (TuLED PE FileVersion)','configs':configs,'source_files_scanned':dict(scanned),'source_parse_errors':errors,
      'projects':projects,'plugins':summary,
      'osd_tables_checked':len(osd_cache),'osd_check_scope':'Header/version, named datasets, record lengths and EOF; vertex delta payload values not exhaustively audited.',
      'counts':{'plugins':len(selected),'dedicated_model_paths':len(target_owners),'matching_slider_sets':len(projects),
        'closed_slider_sets':sum(p['input_closure_passed'] for p in projects),'plugins_with_missing_morphs':sum(bool(p['missing_bodytri_from_original_source']) for p in summary)},
      'source_code_reference':{'tag':'v5.7.0','directory':str(OUT/'bodyslide_source'),
        'cli':'https://raw.githubusercontent.com/ousnius/BodySlide-and-Outfit-Studio/v5.7.0/src/program/BodySlideApp.h',
        'cli_supported':['-gbuild','-p','-t','-tri']}}
    (OUT/'bodyslide_input_closure.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result['counts'],ensure_ascii=False,indent=2))
    print('status',dict(collections.Counter(p['status'] for p in summary)))


if __name__=='__main__':main()
