"""Read-only NifTools schema lighting snapshots and bounded PG verification.

No Blender import, native helper, game, Save, write-to-model or security change.
The caller supplies a selected ordered recipe; this module never guesses which
TruePBR JSON won. Every unmentioned lighting attribute remains exact.
"""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import warnings
sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
OUT=OWN.parent
DEPS=OUT/'primary_sources/NiftoolsAddon/io_scene_niftools/dependencies'
sys.path.insert(0,str(DEPS))
with warnings.catch_warnings():
    warnings.simplefilter('ignore',SyntaxWarning)
    from nifgen.formats.nif import NifFile,classes

def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def f32_bits(x):return struct.pack('<f',x).hex()
def _v3(v):return [float(v.x),float(v.y),float(v.z)]
def _byte(x):
    v=int(round((float(x)+1.0)*127.5))
    assert 0<=v<=255 and float(x)==v/127.5-1.0,'Normbyte is not exactly representable by its author codec'
    return v
def _rgba(c):
    v=[int(c.r),int(c.g),int(c.b),int(c.a)]
    assert all(0<=x<=255 for x in v),'Invalid ByteColor4'
    return v
def _bits_vectors(values):return [[f32_bits(x) for x in v] for v in values]
def _attribute(shape,name):return bool(getattr(shape.vertex_desc.vertex_attributes,name))

def rgb8_hsl_operation(rgb,lum_mult=None,sat_mult=None):
    """Boost.GIL1.86 RGB8->HSL32->PG multiply/clamp->RGB8; f32 each op.

    Alpha is handled by apply_color_recipes and never modified by this function.
    No tolerance is used when comparing predicted RGB bytes to actual output.
    """
    assert len(rgb)==3 and all(isinstance(v,int) and 0<=v<=255 for v in rgb)
    r,g,b=(f32(v/f32(255.0)) for v in rgb)
    mn=min(r,min(g,b));mx=max(r,max(g,b))
    if abs(f32(mn-mx))<.001:
        h=f32(0);s=f32(0);l=r
    else:
        diff=f32(mx-mn);summ=f32(mx+mn);l=f32(f32(mn+mx)/f32(2))
        s=f32(diff/summ) if l<f32(.5) else f32(diff/f32(f32(2)-summ))
        if abs(f32(mx-r))<f32(.0001):h=f32(f32(g-b)/diff)
        elif abs(f32(mx-g))<f32(.0001):h=f32(f32(2)+f32(f32(b-r)/diff))
        else:h=f32(f32(4)+f32(f32(r-g)/diff))
        h=f32(h/f32(6))
        if h<0:h=f32(h+f32(1))
    if lum_mult is not None:
        lum_mult=f32(lum_mult);assert math.isfinite(lum_mult)
        l=f32(f32(1)-f32(f32(f32(1)-l)*lum_mult))
    if sat_mult is not None:
        sat_mult=f32(sat_mult);assert math.isfinite(sat_mult);s=f32(s*sat_mult)
    s=min(max(s,f32(0)),f32(1));l=min(max(l,f32(0)),f32(1))
    if abs(s)<.0001:r=g=b=l
    else:
        t2=f32(l*f32(f32(1)+s)) if l<.5 else f32(f32(l+s)-f32(l*s))
        t1=f32(f32(f32(2)*l)-t2)
        third=f32(f32(1)/f32(3));sixth=f32(f32(1)/f32(6));two_thirds=f32(f32(2)/f32(3))
        tr=f32(h+third);tg=h;tb=f32(h-third)
        if tr>f32(1):tr=f32(tr-f32(1))
        if tb<f32(0):tb=f32(tb+f32(1))
        def cv(t):
            if t<sixth:return f32(t1+f32(f32(f32(t2-t1)*f32(6))*t))
            if t<f32(.5):return t2
            if t<two_thirds:return f32(t1+f32(f32(f32(t2-t1)*f32(two_thirds-t))*f32(6)))
            return t1
        r,g,b=cv(tr),cv(tg),cv(tb)
    result=[int(f32(f32(v*f32(255))+f32(.5))) for v in (r,g,b)]
    assert all(0<=v<=255 for v in result)
    return result

def apply_color_recipes(shape,ordered_recipes):
    """Return exact expected color payload and presence flag for selected rules.

    An SSE enable transition initializes opaque white per exact PG Nifly source.
    PG applies HSL only to BSTriShape/BSMeshLODTriShape, not NiTriShape83.
    """
    present=shape['has_colors'];payload=shape['colors'];count=shape['vertex_count']
    is_sse=shape['color_encoding']=='RGBA8'
    for recipe in ordered_recipes:
        if 'vertex_colors' in recipe:
            switch=recipe['vertex_colors'];assert type(switch) is bool
            if switch and not present:
                payload=[[255]*4 for _ in range(count)] if is_sse else [['0000803f']*4 for _ in range(count)]
            elif not switch:payload=[]
            present=switch
        if present and is_sse and ('vertex_color_lum_mult' in recipe or 'vertex_color_sat_mult' in recipe):
            payload=[rgb8_hsl_operation(c[:3],recipe.get('vertex_color_lum_mult'),recipe.get('vertex_color_sat_mult'))+[c[3]] for c in payload]
    return {'has_colors':present,'colors':payload}

def snapshot(input_path):
    """Return every shape by block ID with typed lighting arrays and child paths."""
    path=Path(input_path);raw=path.read_bytes();n=NifFile.from_path(str(path))
    stream=int(n.bs_header.bs_version);assert stream in (83,100),'Scope is exact SkyrimLE83/SSE100'
    blocks=list(n.blocks);assert len(blocks)==int(n.num_blocks)
    ids={id(b):i for i,b in enumerate(blocks)};paths=collections.defaultdict(list)
    def walk(b,p,ancestors):
        if b is None:return
        assert id(b) not in ancestors,'Cyclic scene children'
        paths[id(b)].append(p)
        # Match author getNodeChildren: actual declaration order, empty slots
        # excluded; every real child retains its ordinal among real children.
        for i,c in enumerate(x for x in getattr(b,'children',()) if x is not None):
            walk(c,p+'/c'+str(i),ancestors|{id(b)})
    for i,r in enumerate(n.roots):walk(r,'r'+str(i),set())
    shapes=[]
    for block_id,b in enumerate(blocks):
        if not isinstance(b,(classes.BSTriShape,classes.NiTriShape)):continue
        is_bs=isinstance(b,classes.BSTriShape)
        if is_bs:
            data=list(b.get_vertex_data());count=len(data);flags=b.vertex_desc.vertex_attributes
            has_normals=_attribute(b,'normals');has_tangents=_attribute(b,'tangents') and has_normals;has_colors=_attribute(b,'vertex_colors')
            normals=[_v3(v.normal) for v in data] if has_normals else []
            tangents=[_v3(v.tangent) for v in data] if has_tangents else []
            if has_tangents and isinstance(b,classes.BSDynamicTriShape):
                assert len(b.vertices)==count,'Dynamic bitangentX/vertex stream count conflict'
                bitangents=[[float(b.vertices[i].w),float(v.bitangent_y),float(v.bitangent_z)] for i,v in enumerate(data)]
            else:bitangents=[[float(v.bitangent_x),float(v.bitangent_y),float(v.bitangent_z)] for v in data] if has_tangents else []
            normal_encoding=[[_byte(x) for x in v] for v in normals]
            tangent_encoding=[[_byte(x) for x in v] for v in tangents]
            bitangent_encoding=[[f32_bits(v[0]),_byte(v[1]),_byte(v[2])] for v in bitangents]
            colors=[_rgba(v.vertex_colors) for v in data] if has_colors else []
            storage='NiSkinPartition.vertex_data' if flags.skinned else 'shape.vertex_data'
            declared_count=int(b.num_vertices);assert declared_count in (0,count),'Declared vertex count conflicts with effective vertex storage'
            shader=getattr(b,'shader_property',None)
            desc=int(b.vertex_desc);main_size=((desc&0xFF00)>>8)*4
            # The bundled author schema has no variable extra-float vertex
            # member; refuse it instead of pretending those bytes were read.
            assert main_size<=16 or not flags.vertex,'Extra-float vertex layout needs an explicit schema extension'
            skin_part=getattr(getattr(b,'skin',None),'skin_partition',None)
            descriptor={'value':desc,'shape_data_size':int(b.data_size),'shape_num_triangles':int(b.num_triangles),
              'dynamic':isinstance(b,classes.BSDynamicTriShape),'dynamic_data_size':int(b.dynamic_data_size) if isinstance(b,classes.BSDynamicTriShape) else None,
              'skinned':bool(flags.skinned),'extra_float_count':0,
              'storage_descriptor':int(skin_part.vertex_desc) if skin_part else None,
              'storage_vertex_size':int(skin_part.vertex_size) if skin_part else None,
              'storage_data_size':int(skin_part.data_size) if skin_part else None,
              'partition_descriptors':[int(x.vertex_desc) for x in skin_part.partitions] if skin_part else []}
        else:
            d=b.data;assert d is not None
            count=int(d.num_vertices);has_normals=bool(d.has_normals);has_tangents=bool(len(d.tangents));has_colors=bool(d.has_vertex_colors)
            normals=[_v3(v) for v in d.normals] if has_normals else []
            tangents=[_v3(v) for v in d.tangents] if has_tangents else []
            bitangents=[_v3(v) for v in d.bitangents] if has_tangents else []
            normal_encoding=_bits_vectors(normals);tangent_encoding=_bits_vectors(tangents);bitangent_encoding=_bits_vectors(bitangents)
            colors=[[f32_bits(float(getattr(c,k))) for k in ('r','g','b','a')] for c in d.vertex_colors] if has_colors else []
            storage='NiTriShapeData';declared_count=count
            shader=getattr(b,'shader_property',None)
            descriptor=None
        for name,values,present in [('normals',normals,has_normals),('tangents',tangents,has_tangents),('bitangents',bitangents,has_tangents),('colors',colors,has_colors)]:
            assert len(values)==(count if present else 0),f'Incomplete {name} array in block{block_id}'
        shapes.append({'block_id':block_id,'block_type':b.__class__.__name__,'name':str(b.name),'paths':paths[id(b)],
          'shader_block_id':ids.get(id(shader)) if shader else None,'source_shader_block_id':ids.get(id(shader)) if shader else None,
          'source_node_path':paths[id(b)],'vertex_count':count,'vertex_data_length':count,'declared_vertex_count':declared_count,'storage':storage,
          'layout_flags':{'vertex_attributes':int(b.vertex_desc.vertex_attributes) if is_bs else None,
            'normals':has_normals,'tangents':has_tangents,'colors':has_colors,
            'bs_data_flags':None if is_bs else int(d.bs_data_flags),'data_flags':None if is_bs else int(d.data_flags)},
          'descriptor':descriptor,
          'has_normals':has_normals,'has_tangents':has_tangents,'has_colors':has_colors,
          'normals':normals,'tangents':tangents,'bitangents':bitangents,'normal_encoding':normal_encoding,'tangent_encoding':tangent_encoding,'bitangent_encoding':bitangent_encoding,
          'color_encoding':'RGBA8' if is_bs else 'FLOAT32_RGBA_BITS','colors':colors})
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'stream':stream,'block_count':len(blocks),'shape_count':len(shapes),'shapes':shapes,
      'reader':'Official NifTools addonv0.1.1 bundled purePython nifgen. This module performs no writes to models.','native_visual_test':False}

def _unit_issues(values,stream,label,count):
    issues=[]
    if len(values)!=count:issues.append(label+': count differs from vertex count')
    # Normbyte step2/255, nearest quantization maxcomponenterror1/255.
    # The Euclidean norm error is bounded by sqrt(3)/255 plus f32 decode noise.
    bound=math.sqrt(3)/255+4*2**-23 if stream==100 else 1e-5
    for i,v in enumerate(values):
        if len(v)!=3 or not all(math.isfinite(x) for x in v):issues.append(f'{label}[{i}]: nonfinite/incomplete');continue
        if abs(math.sqrt(sum(x*x for x in v))-1)>bound:issues.append(f'{label}[{i}]: outside unit bound {bound:.9g}')
    return issues

def rebuild_sse_descriptor(old_descriptor,final_flags,dynamic=False,extra_float_count=0):
    """Exact CalcDataSizes layout for stream100 (PG-pinned Nifly source).

    Upper24bits/reserved bits survive. Offsets and stride are wholly derived
    from the unchanged non-lighting flags and specifically authorized lighting
    flags. Only the explicit extra-float count is permitted; snapshots reject
    layouts the bundled schema cannot fully parse.
    """
    assert 0<=final_flags<=0xFFFF and isinstance(extra_float_count,int) and extra_float_count>=0
    sizes=[0]*9
    if final_flags&1:sizes[0]=4
    sizes[0]+=extra_float_count
    if final_flags&2:sizes[1]=1
    if final_flags&4:sizes[2]=1
    if final_flags&8:
        sizes[3]=1
        if final_flags&16:sizes[4]=1
    if final_flags&32:sizes[5]=1
    if final_flags&64:sizes[6]=3
    if final_flags&256:sizes[8]=1
    assert not final_flags&128,'VA_LANDDATA size is not implemented by pinned CalcDataSizes; refuse unsupported input'
    # Same ClearAttributeOffsets preserves bits40..63, then normal/color flags
    # update at44..59; upper reserved bits and all other flags remain intact.
    result=old_descriptor&0xFFFFFF0000000000
    result=(result&~(0xFFFF<<44))|(final_flags<<44)
    stride=0
    for attr,size in enumerate(sizes):
        if not size:continue
        if attr!=0:result|=(stride//4)<<(4*attr+4)
        stride+=size*4
    assert stride//4<=15,'Vertex stride spills descriptor nibble; needs separate proof'
    result|=stride//4
    if dynamic:result=(result&~0xF0)|0x40
    return result,stride

def compare_descriptor(before,after,ordered_recipes,allow_serializer_rebuild=False):
    """Prove a descriptor delta; no broad masking of vertexDesc is allowed.

    Default requires exact descriptor without a flag-changing recipe. The
    caller may separately authorize the pinned unconditional FinalizeData
    canonical rebuild after complete geometry equality, never arbitrary bits.
    """
    a=before['descriptor'];b=after['descriptor'];issues=[];derived=[]
    if a is None or b is None:
        if a!=b:issues.append('Descriptor representation changed')
        if a is None and b is None:
            has_smooth=any('smooth_angle' in r for r in ordered_recipes)
            for field in ('data_flags','bs_data_flags'):
                old=before['layout_flags'][field];new=after['layout_flags'][field]
                # Exact NiGeometryData tangent-presence bit. UV/count and all
                # other metadata bits remain exact; unused non-BS flag stays
                # exact as well in this version83 scope.
                allowed=0x1000 if has_smooth and field=='bs_data_flags' else 0
                if (old^new)&~allowed:issues.append('Unauthorized LE geometry-data flags changed '+field)
        return {'status':'DESCRIPTOR_PASS' if not issues else 'STOP_DESCRIPTOR_CHANGE','issues':issues,'derived_changes':derived}
    if a['dynamic']!=b['dynamic'] or a['skinned']!=b['skinned'] or a['extra_float_count']!=b['extra_float_count']:issues.append('Non-lighting vertex layout changed')
    old_flags=(a['value']>>44)&0xFFFF;new_flags=(b['value']>>44)&0xFFFF
    has_smooth=any('smooth_angle' in r for r in ordered_recipes);has_color=any('vertex_colors' in r for r in ordered_recipes)
    permitted=(8|16 if has_smooth else 0)|(32 if has_color else 0)
    if (old_flags^new_flags)&~permitted:issues.append('Unauthorized vertex attribute flag changed')
    if bool(new_flags&8)!=after['has_normals'] or bool(new_flags&16)!=after['has_tangents'] or bool(new_flags&32)!=after['has_colors']:issues.append('Descriptor lighting flags disagree with typed payload')
    expected_flags=old_flags
    if has_smooth:
        expected_flags|=8
        if old_flags&2 and before['vertex_count']>0:expected_flags|=16
    color_expected=apply_color_recipes(before,ordered_recipes)['has_colors']
    expected_flags=(expected_flags|32) if color_expected else (expected_flags&~32)
    if new_flags!=expected_flags:issues.append('Final flags do not equal ordered author operations')
    canonical,stride=rebuild_sse_descriptor(a['value'],expected_flags,a['dynamic'],a['extra_float_count'])
    if b['value']!=a['value']:
        if not (has_smooth or has_color or allow_serializer_rebuild):issues.append('Unapproved serializer descriptor rebuild without lighting recipe')
        if b['value']!=canonical:issues.append('Descriptor differs from exact author derived stride/offset layout')
        derived.append({'field':'vertexDesc','before':a['value'],'after':b['value'],'expected':canonical})
    # Preserve all reserved/high bits even if a malformed source descriptor
    # happens to share the same known flags.
    if ((a['value']^b['value'])&0xFFFFFF0000000000)&~(permitted<<44):issues.append('Reserved or non-lighting descriptor bits changed')
    if a['dynamic_data_size']!=b['dynamic_data_size']:issues.append('Dynamic position-stream size changed')
    if before['declared_vertex_count']!=after['declared_vertex_count']:issues.append('Declared shape vertex count changed')
    if a['shape_num_triangles']!=b['shape_num_triangles']:issues.append('Declared triangle count changed')
    if b['skinned']:
        if b['shape_data_size']!=0:issues.append('SSE skinned shape inline data size is not zero')
        if b['storage_descriptor']!=b['value']:issues.append('Skin partition descriptor not forwarded from shape')
        if b['storage_vertex_size']!=stride:issues.append('Skin partition vertex stride is not derived stride')
        if b['storage_data_size']!=stride*after['vertex_count']:issues.append('Skin partition byte size is not stride*count')
        if len(a['partition_descriptors'])!=len(b['partition_descriptors']):issues.append('Skin partition descriptor count changed')
        if any(x!=b['value'] for x in b['partition_descriptors']):issues.append('Per-partition descriptor not forwarded from shape')
    elif b['shape_data_size']!=stride*after['vertex_count']+6*b['shape_num_triangles']:issues.append('Shape byte size is not derived vertices+triangles size')
    return {'status':'DESCRIPTOR_PASS' if not issues else 'STOP_DESCRIPTOR_CHANGE','issues':issues,'derived_changes':derived,
      'expected_descriptor':canonical,'expected_stride_bytes':stride,'permitted_flag_mask':permitted,'serializer_rebuild_separately_authorized':allow_serializer_rebuild}

def compare_shape(before,after,ordered_recipes,stream,allow_serializer_rebuild=False):
    """Validate lighting only; parent must independently check full geometry.

    Source/target pairing must be supplied by canonical child path, never name.
    A selected recipe's provenance/winner must be independently proved by caller.
    """
    issues=[];declared=[]
    for key in ('name','block_type','paths','vertex_count','color_encoding'):
        if before[key]!=after[key]:issues.append('Shape identity/count changed '+key)
    has_smooth=any('smooth_angle' in r for r in ordered_recipes)
    if has_smooth:
        for r in ordered_recipes:
            if 'smooth_angle' in r:assert math.isfinite(float(r['smooth_angle']))
        if not after['has_normals']:issues.append('Declared smooth operation produced no normals')
        issues += _unit_issues(after['normals'],stream,'normals',before['vertex_count'])
        if after['has_tangents']:
            issues += _unit_issues(after['tangents'],stream,'tangents',before['vertex_count'])
            issues += _unit_issues(after['bitangents'],stream,'bitangents',before['vertex_count'])
        elif before['has_tangents']:issues.append('Declared smooth operation removed tangents')
        declared.append('Explicit smooth_angle author normal/tangent operation; finite/count/unit checked, no native visual claim.')
    else:
        for key in ('has_normals','has_tangents','normal_encoding','tangent_encoding','bitangent_encoding'):
            if before[key]!=after[key]:issues.append('Undeclared lighting change '+key)
    expected=apply_color_recipes(before,ordered_recipes)
    for key in ('has_colors','colors'):
        if expected[key]!=after[key]:issues.append('Color author-formula mismatch '+key)
    descriptor=compare_descriptor(before,after,ordered_recipes,allow_serializer_rebuild)
    issues+=descriptor['issues']
    return {'status':'BOUNDED_LIGHTING_PASS' if not issues else 'STOP_UNEXPLAINED_LIGHTING_CHANGE','issues':issues,'declared_operations':declared,
      'descriptor':descriptor,
      'source_formula_color_byte_exact':expected['colors']==after['colors'],'unit_bound_source':'Nearest Normbyte quantization step2/255; unquantized float32 unit bound1e-5.',
      'limits':['Caller must prove exact selected ordered rule provenance and full geometry/skin/reference preservation.','A valid normal vector alone does not prove artist intent; only a selected explicit smooth_angle permits changes.']}

def normalization_allowance(before,after,ordered_recipes,stream,allow_serializer_rebuild=False):
    """Return only the proved CAPI shape property normalizations after PASS."""
    proof=compare_shape(before,after,ordered_recipes,stream,allow_serializer_rebuild)
    if proof['issues']:raise ValueError(proof)
    allowed={}
    if before['has_normals']!=after['has_normals']:allowed['hasNormals']={'before':int(before['has_normals']),'after':int(after['has_normals'])}
    if before['has_colors']!=after['has_colors']:allowed['hasVertexColors']={'before':int(before['has_colors']),'after':int(after['has_colors'])}
    if before['descriptor'] is not None and before['descriptor']['value']!=after['descriptor']['value']:allowed['vertexDesc']={'before':before['descriptor']['value'],'after':after['descriptor']['value']}
    return {'status':'LIGHTING_PASS_PROPERTIES_BOUNDED','properties':allowed,'normal_hash_change_authorized':any('smooth_angle' in r for r in ordered_recipes),'proof':proof}

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args();dest=Path(a.output).resolve()
    assert dest.is_relative_to(OWN) and not dest.exists();dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(snapshot(a.input),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
if __name__=='__main__':main()
