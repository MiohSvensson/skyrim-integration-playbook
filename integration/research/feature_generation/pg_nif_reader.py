"""Read-only author PyNifly CPU geometry signatures; no save/write API used."""
import collections
import ctypes
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'primary_sources/PyNifly/addon/io_scene_nifly'))
from pyn.pynifly import NifFile
from pyn.niflydll import nifly
from pyn.nifdefs import TransformBuf
from pyn.blocks.nodes import NiNode
AV_TYPES={'NiNode','BSFadeNode','BSLeafAnimNode','BSMultiBoundNode','NiBillboardNode','NiTriShape','BSTriShape','BSSubIndexTriShape','BSMeshLODTriShape','BSDynamicTriShape','NiTriStrips'}

def plain(x):
    if isinstance(x,ctypes.Array):return [plain(v) for v in x]
    if isinstance(x,ctypes.Structure):return {n:plain(getattr(x,n)) for n,_ in x._fields_}
    if isinstance(x,bytes):return x.hex()
    if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [plain(v) for v in x]
    if isinstance(x,set):return sorted(plain(v) for v in x)
    if hasattr(x,'__dict__'):return {k:plain(v) for k,v in x.__dict__.items() if not k.startswith('_')}
    return x
def token(x):
    def safe(v):
        if isinstance(v,float) and not math.isfinite(v):return {'NONFINITE_FLOAT64_BITS':struct.pack('<d',v).hex()}
        if isinstance(v,list):return [safe(a) for a in v]
        if isinstance(v,dict):return {k:safe(a) for k,a in v.items()}
        return v
    return hashlib.sha256(json.dumps(safe(plain(x)),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def raw_table(data,allow_source_trailer=False):
    p=data.index(b'\n')+1
    def n(fmt):
        nonlocal p
        v=struct.unpack_from('<'+fmt,data,p)[0];p+=struct.calcsize(fmt);return v
    def text(fmt='I'):
        nonlocal p
        size=n(fmt);v=data[p:p+size];p+=size;return v
    version=n('I');endian=n('B');user=n('I');count=n('I');stream=n('I')
    assert (version,endian,user)==(0x14020007,1,12) and stream in (83,100),'Unapproved source NIF format'
    for _ in range(3):text('B')
    types=[text().decode('utf8') for _ in range(n('H'))];indices=[n('H') for _ in range(count)];sizes=[n('I') for _ in range(count)]
    string_count=n('I');n('I');strings=[text().decode('utf8') for _ in range(string_count)]
    groups=[n('I') for _ in range(n('I'))];blocks=[]
    for i,(t,size) in enumerate(zip(indices,sizes)):
        assert t<len(types) and p+size<=len(data)
        blocks.append({'index':i,'type':types[t],'size':size,'sha256':hashlib.sha256(data[p:p+size]).hexdigest()});p+=size
    roots=[n('I') for _ in range(n('I'))];assert p<=len(data) and all(x<count for x in roots)
    if not allow_source_trailer:assert p==len(data),'Unexpected bytes after declared NIF footer'
    return {'stream':stream,'block_types':dict(collections.Counter(x['type'] for x in blocks)),'blocks':blocks,'roots':roots,'EOF_exact':p==len(data),
      'declared_core_bytes':p,'declared_core_sha256':hashlib.sha256(data[:p]).hexdigest(),'trailer_bytes':len(data)-p,'trailer_sha256':hashlib.sha256(data[p:]).hexdigest() if p<len(data) else None}

def properties_without_ids(p):
    return {k:v for k,v in plain(p).items() if k not in ('bufSize','bufType','id','nameID','rootMaterialNameID') and not k.endswith('ID')}

def snapshot(path,allow_source_trailer=False,research_inspect_nonfinite=False):
    raw=Path(path).read_bytes();table=raw_table(raw,allow_source_trailer);nif=NifFile(str(path));nodes={};shapes=[];warnings=[]
    try:
        # Official V30.2.0 explicitly warns that .nodes is name-keyed and must
        # not enumerate all nodes. Read each raw table block by ID instead.
        node_count=nifly.getNodeCount(nif._handle);assert node_count>=0
        handles=(ctypes.c_void_p*node_count)();nifly.getNodes(nif._handle,handles)
        native_nodes={nifly.getBlockID(nif._handle,h):h for h in handles};assert len(native_nodes)==node_count
        by_id={};base_accessors=[]
        for node_id,handle in native_nodes.items():
            node=nif.read_node(id=node_id,handle=handle)
            if node is None:
                # The native enumeration proves a NiNode subclass. Use its
                # documented base-NiNode accessor for complete AV geometry;
                # subclass-only bytes remain protected by exact raw comparison.
                node=NiNode(id=node_id,handle=handle,file=nif);base_accessors.append(node_id)
            by_id[node_id]=node
        for s in nif.shapes:
            assert s.id not in by_id,'Native NiNode/shape enumerations overlap'
            by_id[s.id]=s
        assert all(x is not None for x in by_id.values()),'Author API cannot instantiate every declared AVObject'
        paths=collections.defaultdict(list);child_ids={};hierarchy={}
        def walk(node_id,path,ancestors):
            assert 0<=node_id<len(table['blocks']) and node_id not in ancestors,'Invalid/cyclic AVObject child reference'
            assert len(hierarchy)<1000000,'Unexpectedly expanded shared AVObject hierarchy'
            paths[node_id].append(path)
            count=nifly.getNodeChildren(nif._handle,node_id,0,None);assert count>=0
            buffer=(ctypes.c_int*count)();assert nifly.getNodeChildren(nif._handle,node_id,count,buffer)==count
            children=list(buffer);child_ids[node_id]=children
            hierarchy[path]={'block_type':table['blocks'][node_id]['type'],'children':len(children)}
            for i,child_id in enumerate(children):walk(child_id,path+'/c'+str(i),ancestors|{node_id})
        for i,root_id in enumerate(table['roots']):walk(root_id,'r'+str(i),set())
        assert set(by_id)<=set(paths),'Unreachable/unparented AVObjects require explicit component mapping'
        keys={i:';'.join(paths[i]) for i in by_id}
        for node_id,node in by_id.items():
            props=properties_without_ids(node.properties)
            nodes[keys[node_id]]={'name':node.name,'block_type':node.blockname,'properties':props,'transform':plain(node.transform),
              'paths':paths[node_id],'child_paths':[[';'.join(paths[c]) for c in child_ids[node_id]]][0]}
        for s in nif.shapes:
            assert s.id in keys,'Shape missing from complete AVObject inventory'
            # BSDynamicTriShape keeps positions in its dynamic stream even
            # when the primary vertex descriptor's hasVertices flag isfalse.
            vertices=plain(s.verts);triangles=plain(s.tris)
            normals=plain(s.normals) if s.properties.hasNormals else [];uvs=plain(s.uvs) if s.properties.hasUV else []
            assert all(len(v)==3 for v in vertices)
            assert all(len(t)==3 and all(isinstance(x,int) and 0<=x<len(vertices) for x in t) for t in triangles)
            nonfinite=[{'array':array,'vertex':i,'component':j,'float32_bits':struct.pack('<f',v).hex()} for array,values in [('vertices',vertices),('normals',normals),('UVs',uvs)]
              for i,vector in enumerate(values) for j,v in enumerate(vector) if not math.isfinite(v)]
            if nonfinite:
                assert research_inspect_nonfinite,'Nonfinite source geometry '+s.name+': '+str(nonfinite[:5])
                warnings.append({'shape':s.name,'numeric_defects':nonfinite,'status':'SOURCE_DEFECT_NOT_REPAIRED_OR_FORMALLY_ACCEPTED'})
            # Read the native palette by ID/index. The release's convenience
            # bone_names getter truncates its final name when total length is
            # exactly300, and name-keyed aggregation also loses palette detail.
            bone_ids=s.bone_ids;weights=[];binds=[];sums=[0.0]*len(vertices)
            for pos,bone_id in enumerate(bone_ids):
                assert bone_id in keys,'Skin bone ID absent from complete typed node inventory'
                items=sorted(plain(s._bone_weights(pos)))
                weights.append({'bone':keys[bone_id],'name':by_id[bone_id].name,'weights':items})
                bind=TransformBuf();assert nifly.getShapeSkinToBoneByIndex(nif._handle,s._handle,pos,bind),'Cannot read indexed skin-to-bone transform'
                binds.append(plain(bind))
                for i,w in items:assert 0<=i<len(vertices) and math.isfinite(w) and 0<=w<=1.00001;sums[i]+=w
            if weights and any(abs(w-1)>.001 for w in sums):warnings.append({'shape':s.name,'source_weight_sum_min':min(sums),'source_weight_sum_max':max(sums)})
            geo={'vertices':token(vertices),'triangles':token(triangles),'normals':token(normals),'UVs':token(uvs),'transform':token(s.transform),
              'bone_names':token([keys[i] for i in bone_ids]),'bone_weights':token(weights),'skin_to_bone':token(binds),
              'global_to_skin':token(s.global_to_skin) if weights else None,'partitions':token(s.partitions),'partition_triangles':token(s.partition_tris)}
            shader=s.shader
            shapes.append({'key':keys[s.id],'name':s.name,'block_type':s.blockname,
              'vertices':len(vertices),'triangles':len(triangles),'bones':len(weights),'geometry':geo,
              'properties':properties_without_ids(s.properties),'vertex_colors':token(s.colors if s.properties.hasVertexColors else []),
              'shader_properties':properties_without_ids(shader.properties) if shader else None,'textures':dict(shader.textures) if shader else {}})
        assert len({s['key'] for s in shapes})==len(shapes),'Ambiguous shape hierarchy identity'
        return {'sha256':hashlib.sha256(raw).hexdigest(),'stream':table['stream'],'raw':table,'nodes':nodes,'hierarchy':hierarchy,'shapes':shapes,'source_warnings':warnings,'reader_log':NifFile.message_log(),
          'native_NiNode_count':node_count,'native_NiShape_count':len(nif.shapes),'native_base_NiNode_accessor_types':[table['blocks'][i]['type'] for i in base_accessors]}
    finally:nif.close()

def compare(before,after):
    failures=[];materials=[]
    if before['stream']!=after['stream']:failures.append('Stream representation changed; separate author-supported conversion proof required')
    old={x['key']:x for x in before['shapes']};new={x['key']:x for x in after['shapes']}
    if old.keys()!=new.keys():failures.append('Shape addition/deletion/rename')
    for name in old.keys() & new.keys():
        a=old[name];b=new[name]
        for field in ('name','block_type','vertices','triangles','bones','geometry','properties','vertex_colors'):
            if a[field]!=b[field]:failures.append('Shape '+name+' changed '+field)
        changed={field:{'before':a[field],'after':b[field]} for field in ('shader_properties','textures') if a[field]!=b[field]}
        if changed:materials.append({'shape':name,'changes':changed})
    # Shapes are NiAVObjects too: material-ID reordering is excluded, all
    # remaining typed node transforms/flags/parent geometry remain exact.
    if before['nodes']!=after['nodes']:failures.append('Typed node properties/transform/parent tree changed')
    if before['hierarchy']!=after['hierarchy']:failures.append('Complete child-ordinal hierarchy changed')
    geometry_types={'NiNode','BSFadeNode','BSLeafAnimNode','BSMultiBoundNode','NiBillboardNode','NiTriShape','NiTriShapeData','BSTriShape','BSSubIndexTriShape','BSMeshLODTriShape','BSDynamicTriShape','NiTriStrips','NiTriStripsData','BSDismemberSkinInstance','NiSkinInstance','NiSkinData','NiSkinPartition'}
    material_types={'BSLightingShaderProperty','BSEffectShaderProperty','BSShaderTextureSet','NiAlphaProperty','NiMaterialProperty','BSXFlags'}
    bc=before['raw']['block_types'];ac=after['raw']['block_types']
    for t in set(bc)|set(ac):
        if t not in material_types and bc.get(t,0)!=ac.get(t,0):failures.append('Non-material block count changed '+t)
    # Unknown/controller/collision/particle blocks cannot be silently changed.
    # Exact bytes are conservative: block-index relocation may require a new
    # typed follow-up, but is never treated as a successful comparison.
    for t in (set(bc)|set(ac))-geometry_types-material_types:
        a=sorted(x['sha256'] for x in before['raw']['blocks'] if x['type']==t);b=sorted(x['sha256'] for x in after['raw']['blocks'] if x['type']==t)
        if a!=b:failures.append('Protected non-material block bytes changed '+t)
    return {'status':'GEOMETRY_PRESERVED_RENDERER_CHANGES_RECORDED' if not failures else 'STOP_UNPROVEN_NIF_CHANGE','failures':failures,'material_changes':materials,
      'shape_index_mapping':{str(i):next(j for j,s in enumerate(after['shapes']) if s['key']==a['key']) for i,a in enumerate(before['shapes']) if a['key'] in new},
      'external_texture_refs':sorted({t.replace('\\','/').lower() for s in after['shapes'] for t in s['textures'].values() if t}),
      'limits':['Geometry equality is a CPU author-parser comparison, not native rendering proof. Renderer changes still require exact rule/TXST/texture closure review.',
        'Normal smoothing, vertex-color changes, stream conversion or protected-block relocation stop for a bounded follow-up; no implicit tolerance or shape deletion accepted.']}
