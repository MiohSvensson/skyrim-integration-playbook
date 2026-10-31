"""Only reads frozen model copies; all artifacts stay in this directory."""
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent;OUT=OWN.parent
import lighting_schema as l

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    frozen=json.loads((OUT/'pg_runs/nif_cpu_preflight_002/nif_inputs/manifest.json').read_text(encoding='utf8'))
    geometry=json.loads((OUT/'pg_runs/nif_cpu_preflight_002/source_reaudit_ec513533833e/result.json').read_text(encoding='utf8'))
    src=json.loads((OUT/'source_inspection.json').read_text(encoding='utf8'))
    keys=['meshes/0waxe/0jm/0hall/00hall01.nif']
    for stream in (100,83):
        keys.append(next(r['path_key'] for r in src['nifs'] if r['bs_version']==stream and r['path_key'] in frozen['entries'] and any(s['skinned'] for s in r['shaders'])))
    rows=[];snapshots=[]
    for i,key in enumerate(keys):
        row=frozen['entries'][key];s=l.snapshot(row['snapshot']);snapshots.append(s)
        g=json.loads(Path(geometry['entries'][key]['typed_snapshot']).read_text(encoding='utf8'))
        assert s['sha256']==row['sha256']==g['sha256']
        assert len(s['shapes'])==len(g['shapes'])
        assert [(x['name'],x['vertex_count']) for x in s['shapes']]==[(x['name'],x['vertices']) for x in g['shapes']]
        assert all(x['paths'] for x in s['shapes'])
        for sh in s['shapes']:assert not l.compare_shape(sh,sh,[],s['stream'])['issues']
        dest=OWN/f'fixture_{i}.json';dest.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        rows.append({'path_key':key,'sha256':s['sha256'],'stream':s['stream'],'shape_count':s['shape_count'],'vertices':sum(x['vertex_count'] for x in s['shapes']),
          'storage':sorted(set(x['storage'] for x in s['shapes'])),'source_geometry_proof':geometry['entries'][key]['typed_snapshot'],
          'counts_match_parent_author_API':True,'all_no_recipe_identity_checks_passed':True,'snapshot':str(dest),'snapshot_sha256':sha(dest)})
    checks={}
    colors=list(itertools.product(range(0,256,17),repeat=3))
    assert len(colors)==4096
    for c in colors:assert l.rgb8_hsl_operation(list(c),1,1)==list(c)
    checks['4096_RGB_grid_identity_lum1_sat1']=True
    for v in range(256):assert l.rgb8_hsl_operation([v,v,v],1,0)==[v,v,v]
    checks['all256_gray_identity']=True
    known=[([255,0,0],1,0,[128,128,128]),([128,128,128],2,1,[1,1,1]),([32,64,128],.5,1,[115,150,220]),([4,195,23],0,1,[255,255,255]),([128,64,32],2,1,[0,0,0])]
    known_results=[]
    for rgb,lm,sm,expected in known:
        actual=l.rgb8_hsl_operation(rgb,lm,sm);assert actual==expected,(rgb,actual,expected)
        known_results.append({'before':rgb,'lum_mult':lm,'sat_mult':sm,'expected':expected,'actual':actual})
    checks['known_HSL_clamp_round_vectors']=True
    sse=next(x for x in snapshots[1]['shapes'] if x['has_colors']);after=copy.deepcopy(sse)
    recipes=[{'vertex_color_lum_mult':.5,'vertex_color_sat_mult':.25}]
    after['colors']=l.apply_color_recipes(sse,recipes)['colors'];assert not l.compare_shape(sse,after,recipes,100)['issues']
    assert all(a[3]==b[3] for a,b in zip(sse['colors'],after['colors']));checks['real_SSE_color_replay_and_alpha_preserved']=True
    bad=copy.deepcopy(after);bad['colors'][0][0]=(bad['colors'][0][0]+1)%256
    assert l.compare_shape(sse,bad,recipes,100)['issues'];checks['one_wrong_RGB_byte_rejected']=True
    le=next(x for x in snapshots[2]['shapes'] if x['has_colors']);assert l.apply_color_recipes(le,recipes)['colors']==le['colors'];checks['LE_float_colors_not_HSL_rewritten']=True
    base=snapshots[0]['shapes'][0];bad=copy.deepcopy(base);bad['normal_encoding'][0][0]^=1
    assert l.compare_shape(base,bad,[],100)['issues'];checks['undeclared_normal_byte_rejected']=True
    bad=copy.deepcopy(base);bad['normals'][0][0]=float('nan')
    assert l.compare_shape(base,bad,[{'smooth_angle':75}],100)['issues'];checks['declared_normal_NaN_rejected']=True
    bad=copy.deepcopy(base);bad['descriptor']['value']^=1<<45
    assert l.compare_shape(base,bad,[{'smooth_angle':75}],100)['issues'];checks['unauthorized_UV_descriptor_flag_rejected']=True
    bad=copy.deepcopy(base);bad['descriptor']['value']^=1<<8
    assert l.compare_shape(base,bad,[{'vertex_colors':True}],100)['issues'];checks['wrong_derived_offset_rejected']=True
    added=copy.deepcopy(base);added['has_colors']=True;added['colors']=[[255]*4 for _ in range(base['vertex_count'])]
    flags=(base['descriptor']['value']>>44)&0xFFFF;desc,stride=l.rebuild_sse_descriptor(base['descriptor']['value'],flags|32,False)
    added['descriptor']['value']=desc;added['descriptor']['shape_data_size']=stride*added['vertex_count']+6*added['descriptor']['shape_num_triangles']
    proof=l.normalization_allowance(base,added,[{'vertex_colors':True}],100)
    assert set(proof['properties'])=={'hasVertexColors','vertexDesc'};checks['explicit_color_enable_exact_layout_accepted']=True
    b=copy.deepcopy(added);b['descriptor']['value']^=1<<55
    assert l.compare_shape(base,b,[{'vertex_colors':True}],100)['issues'];checks['descriptor_reserved_bit_rejected']=True
    b=copy.deepcopy(base);b['descriptor']['value']^=1<<54
    assert l.compare_shape(base,b,[{'smooth_angle':75}],100)['issues'];checks['full_precision_flag_rejected']=True
    b=copy.deepcopy(base);b['tangent_encoding'][0][0]^=1
    assert l.compare_shape(base,b,[],100)['issues'];checks['undeclared_tangent_byte_rejected']=True
    b=copy.deepcopy(base);b['bitangent_encoding'][0][0]='00000000'
    assert l.compare_shape(base,b,[],100)['issues'];checks['undeclared_bitangent_float_rejected']=True
    checks['all_descriptor_source_identity_checks_passed']=True
    assert all(checks.values())
    sources=[OUT/'primary_sources/NiftoolsAddon/manifest.json',OUT/'primary_sources/Boost-GIL/hsl.hpp',OUT/'primary_sources/Boost-GIL/channel_algorithm.hpp',OUT/'primary_sources/PGPatcher/PatcherMeshShaderTruePBR.cpp']
    root=next((OUT/'primary_sources/PG-Nifly').glob('nifly-*'));sources += [root/'include/VertexData.hpp',root/'src/Geometry.cpp',root/'src/NifFile.cpp',root/'src/Skin.cpp']
    r={'status':'PURE_SCHEMA_LIGHTING_AND_FORMULA_FIXTURES_PASS_NOT_ACTUAL_PG','fixtures':rows,'checks':checks,'known_color_vectors':known_results,
      'module':str(OWN/'lighting_schema.py'),'module_sha256':sha(OWN/'lighting_schema.py'),'fixture_script_sha256':sha(__file__),
      'source_hashes':{str(x):sha(x) for x in sources},'native_helper_executed':False,'game_or_GUI_launched':False,'models_modified':False,
      'limits':['Color formula is a pinned-source f32 translation; actual PG output must still match predicted bytes exactly. No native C++ helper was executed.',
        'GetTree 3D indices are not guessed from header order; caller uses actual native trace/witness.','Full geometry/skin/reference checking and exact selected rule/winner provenance belong to the parent validator.',
        'Known source trailers/nonfinite values were not repaired or broadened into accepted output.']}
    (OWN/'fixture_report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps({'status':r['status'],'checks':len(checks),'module_sha256':r['module_sha256']},indent=2))
if __name__=='__main__':main()
