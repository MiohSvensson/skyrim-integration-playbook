"""Read-only whole-mesh, native-witnessed lighting + exact geometry adapter.

It never unions recipes from different native consumer passes. A base mesh must
match Base; a duplicate must match one complete witnessed consumer pass. Final
plugin-to-variant binding and material resource closure remain separate gates.
"""
import collections
import copy
import io
import json
import logging
import math
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
from pg_nif_reader import compare
from pg_nif_validate import sha
sys.path.insert(0,str(OUT/'lighting_schema'))
import lighting_schema as schema

SCHEMA_SHA='dc6c4d668395e7c59c61f53720f0fc6e71fdbad52432c2bb75902e126873b7b1'

def serializer_proof():
    path=OUT/'PG_serializer_derivation_proof.json';proof=json.loads(path.read_text(encoding='utf8'))
    assert proof['PG_commit']=='bf2333af2077384102bd250969ede87eb4c99367' and proof['Nifly_submodule_commit']=='c3cbdd64f18eb45f0b54975591f75db1ec5e6df0'
    assert all(sha(row['path'])==row['sha256'] for row in proof['files'])
    return {'path':str(path),'sha256':sha(path),'explicit_author_serializer_derivations_only':True}

def schema_snapshot(path):
    assert sha(OUT/'lighting_schema/lighting_schema.py')==SCHEMA_SHA
    stream=io.StringIO();handler=logging.StreamHandler(stream);handler.setLevel(logging.WARNING)
    root=logging.getLogger();root.addHandler(handler)
    try:
        result=schema.snapshot(path)
        document=schema.NifFile.from_path(str(path))
        for shape in result['shapes']:
            node=document.blocks[shape['block_id']];shader=getattr(node,'shader_property',None)
            texset=getattr(shader,'texture_set',None)
            shape['stored_texture_slots']=[str(t).lower() for t in texset.textures] if texset is not None else None
            if shape['stored_texture_slots'] is not None:
                assert len(shape['stored_texture_slots'])<=9
                shape['stored_texture_slots']+=['']*(9-len(shape['stored_texture_slots']))
            extra={}
            if isinstance(node,schema.classes.BSTriShape):
                flags=int(node.vertex_desc.vertex_attributes);data=list(node.get_vertex_data())
                assert not flags&(4|128),'Author schema does not expose full UV2/LAND payload'
                if flags&256:
                    assert all(math.isfinite(float(v.eye_data)) for v in data),'Nonfinite eye_data'
                    extra['eye_data']=[schema.f32_bits(float(v.eye_data)) for v in data]
                if flags&1 and not flags&16:extra['unused_w']=[int(v.unused_w) for v in data]
                if flags&8 and not flags&16:extra['normal_padding']=[schema._byte(float(v.bitangent_y)) for v in data]
                if isinstance(node,schema.classes.BSDynamicTriShape):
                    extra['dynamic_w']=[schema.f32_bits(float(v.w)) for v in node.vertices]
                    if flags&256:extra['expected_saved_eye_data']=[schema.f32_bits(1.0 if float(v.x)>0 else 0.0) for v in node.vertices]
            shape['supplemental_vertex_payload']=extra
    finally:root.removeHandler(handler)
    assert not stream.getvalue(),'Author schema reported recovery/size/EOF warning: '+stream.getvalue()
    for shape in result['shapes']:
        for name in ('normals','tangents','bitangents'):
            assert all(math.isfinite(x) for v in shape[name] for x in v),'Nonfinite typed lighting '+shape['name']+'/'+name
        if shape['color_encoding']=='FLOAT32_RGBA_BITS':
            assert all(math.isfinite(struct.unpack('<f',bytes.fromhex(x))[0]) for v in shape['colors'] for x in v),'Nonfinite float vertex color'
    return result

def shape_key(shape):return ';'.join(shape['paths'])

def normalized_pair(before,after,lighting_before,lighting_after,events,rules,allow_serializer_rebuild=False):
    a=copy.deepcopy(before);b=copy.deepcopy(after);by_old={shape_key(s):s for s in lighting_before['shapes']};by_new={shape_key(s):s for s in lighting_after['shapes']}
    assert set(by_old)==set(by_new)=={s['key'] for s in a['shapes']}=={s['key'] for s in b['shapes']},'Complete lighting/geometry shape pairing differs'
    selected={e['source_child_path']:e for e in events};assert len(selected)==len(events),'Repeated native shape in one consumer pass'
    assert set(selected)==set(by_old),'Native pass does not completely cover every shape'
    a_shapes={s['key']:s for s in a['shapes']};b_shapes={s['key']:s for s in b['shapes']};proofs=[]
    for k,old in by_old.items():
        new=by_new[k];event=selected[k];assert event['complete'];group=event['selected_group']
        recipes=[rules[i]['native_rule'] for i in group['ordered_rule_sequences']] if group else []
        if group:assert not group['contains_geometry_delete']
        proof=schema.normalization_allowance(old,new,recipes,before['stream'],allow_serializer_rebuild)
        ex_a=old['supplemental_vertex_payload'];ex_b=new['supplemental_vertex_payload'];smooth=any('smooth_angle' in r for r in recipes)
        for field in set(ex_a)|set(ex_b):
            if field=='expected_saved_eye_data':continue
            expected=ex_a.get(field)
            if field=='eye_data' and allow_serializer_rebuild and 'expected_saved_eye_data' in ex_a:expected=ex_a['expected_saved_eye_data']
            if field in ('unused_w','normal_padding','dynamic_w') and smooth and new['has_tangents']:continue
            assert ex_b.get(field)==expected,'Unexplained supplemental vertex payload changed '+k+'/'+field
        ap=a_shapes[k];bp=b_shapes[k]
        if proof['normal_hash_change_authorized']:ap['geometry']['normals']=bp['geometry']['normals']
        # Pure author schema has checked every exact RGBA byte/formula above.
        # No other geometry member is normalized.
        if old['colors']!=new['colors'] or old['has_colors']!=new['has_colors']:ap['vertex_colors']=bp['vertex_colors']
        for field,values in proof['properties'].items():
            expected=values
            if field=='vertexDesc':
                # Official PyNifly getNiShape exports only flags, not full
                # descriptor. Full offsets/stride were independently checked.
                expected={side:(value>>44)&0x3FF for side,value in values.items()}
            assert ap['properties'][field]==expected['before'] and bp['properties'][field]==expected['after'],'CAPI/schema property does not agree '+k+'/'+field
            for target in (ap['properties'],a['nodes'][k]['properties']):target[field]=bp['properties'][field]
        if event.get('skipped_unpatchable'):
            assert not recipes;expected_textures=old['stored_texture_slots']
        else:
            if event['has_alternate_texture']:
                # Alternate slots are emitted into TXST, not assigned to the
                # NIF by processNIFShape. Preserve original stored NIF slots.
                expected_textures=old['stored_texture_slots']
            else:expected_textures=event['modified_texture_slots'] if old['stored_texture_slots'] is not None else None
        assert new['stored_texture_slots']==expected_textures,'Actual NIF texture slots differ from native pass '+k
        if expected_textures is None:
            assert {n:v.lower() for n,v in ap['textures'].items()}=={n:v.lower() for n,v in bp['textures'].items()},'Non-TXST shader texture fields changed '+k
        proofs.append({'shape':k,'native_event':event,'ordered_rule_sha256':group['ordered_rule_sha256'] if group else [],'lighting_proof':proof})
    comparison=compare(a,b)
    comparison['limits']=['CPU geometry and author lighting-schema validation; no native rendering test.','Final model-consumer/3DIndex/TXST linkage and shader/material/resource closure remain mandatory separate gates.']
    return {'comparison':comparison,'shape_lighting_proofs':proofs}

def validate(before,after,lighting_before,lighting_after,witness,source_key,base_output,rules,allow_serializer_rebuild=False):
    groups=collections.defaultdict(list)
    for event in witness['events']:
        if event['mesh']==source_key and ((event['use']=='Base')==base_output):groups[event['use']].append(event)
    assert groups,'No matching complete native consumer pass'
    accepted=[];rejected=[]
    for use,events in groups.items():
        try:
            proof=normalized_pair(before,after,lighting_before,lighting_after,events,rules,allow_serializer_rebuild)
            if proof['comparison']['failures']:raise ValueError(proof['comparison']['failures'])
            accepted.append({'native_use':use,**proof})
        except Exception as error:rejected.append({'native_use':use,'error':repr(error)})
    assert accepted,'Output does not match any complete native pass: '+repr(rejected[:5])
    return {'status':'BOUNDED_LIGHTING_AND_EXACT_GEOMETRY_PASS_PENDING_CONSUMER_MATERIAL_CLOSURE','accepted_native_passes':accepted,'rejected_native_passes':rejected,
      'shape_recipes_mixed_between_consumers':False,'native_rendering_verified':False}
