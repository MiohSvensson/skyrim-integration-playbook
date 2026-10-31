"""Read-only Nifly author-library comparison of all geometry/skinning fields."""
import collections
import ctypes
import hashlib
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;OUT=ROOT.parent
sys.path.insert(0,str(OUT/'primary_sources/PyNifly/addon/io_scene_nifly'))
from pyn.pynifly import NifFile

def plain(x):
    if isinstance(x,ctypes.Array):return [plain(v) for v in x]
    if isinstance(x,ctypes.Structure):return {n:plain(getattr(x,n)) for n,_ in x._fields_ if n not in ('nameID','rootMaterialNameID')}
    if isinstance(x,bytes):return x.hex()
    if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
    if isinstance(x,(list,tuple)):return [plain(v) for v in x]
    if isinstance(x,set):return sorted(plain(v) for v in x)
    if hasattr(x,'__dict__'):return {k:plain(v) for k,v in x.__dict__.items() if not k.startswith('_')}
    return x

def snapshot(path):
    nif=NifFile(str(path));nodes={};shapes=[]
    for name,node in nif.nodes.items():
        nodes[name]={'properties':plain(node.properties),'parent':node.parent.name if node.parent else None,'transform':plain(node.transform)}
    for s in nif.shapes:
        verts=plain(s.verts);tris=plain(s.tris);normals=plain(s.normals);uvs=plain(s.uvs);weights={n:sorted(plain(v)) for n,v in s.bone_weights.items()}
        assert len(verts)==len(normals)==len(uvs)>0 and all(len(v)==3 and all(math.isfinite(x) for x in v) for v in verts)
        assert all(len(t)==3 and all(0<=x<len(verts) for x in t) for t in tris)
        sums=[0.0]*len(verts)
        for bone,wts in weights.items():
            assert bone in nodes
            for i,w in wts:assert 0<=i<len(verts) and math.isfinite(w) and 0<=w<=1.00001;sums[i]+=w
        assert all(abs(w-1)<0.001 for w in sums),'Unweighted or non-normalized vertex'
        shapes.append({'name':s.name,'block_type':s.blockname,'properties':plain(s.properties),'vertices':verts,'triangles':tris,'normals':normals,'UVs':uvs,
            'bone_names':s.bone_names,'bone_weights':weights,'skin_to_bone':{n:plain(s.get_shape_skin_to_bone(n)) for n in weights},'global_to_skin':plain(s.global_to_skin),
            'partitions':plain(s.partitions),'partition_triangles':plain(s.partition_tris),'shader_properties':plain(s.shader.properties),'textures':dict(s.shader.textures),
            'weight_sum_min':min(sums),'weight_sum_max':max(sums)})
    result={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'nifly_classification':nif.game,'nodes':nodes,'shapes':shapes,'library_log':NifFile.message_log()}
    nif.close();return result

def main():
    results=[]
    for name in ('wg_0.nif','wg_1.nif'):
        originals=snapshot(ROOT/'originals/meshes/mwl'/name);candidate=snapshot(ROOT/'candidate/meshes/mwl'/name);lotd=snapshot(ROOT/'LOTD_author_original'/name)
        (ROOT/(name+'.typed_original.json')).write_text(json.dumps(originals,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (ROOT/(name+'.typed_candidate.json')).write_text(json.dumps(candidate,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        (ROOT/(name+'.typed_LOTD.json')).write_text(json.dumps(lotd,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        shape_a=originals['shapes'][0];shape_b=candidate['shapes'][0];shape_l=lotd['shapes'][0]
        compare={key:shape_a[key]==shape_b[key] for key in shape_a};lcompare={key:shape_a[key]==shape_l[key] for key in shape_a}
        results.append({'name':name,'source_sha256':originals['sha256'],'candidate_sha256':candidate['sha256'],'LOTD_sha256':lotd['sha256'],'node_properties_and_transforms_identical':originals['nodes']==candidate['nodes'],
            'LOTD_node_properties_and_transforms_identical':originals['nodes']==lotd['nodes'],'source_shape_count':len(originals['shapes']),'source_node_count':len(originals['nodes']),
            'vertices':len(shape_a['vertices']),'triangles':len(shape_a['triangles']),'bones':len(shape_a['bone_weights']),'partitions':len(shape_a['partitions']),
            'candidate_comparison':compare,'LOTD_comparison':lcompare,'library_log':originals['library_log'],
            'author_library_classification':originals['nifly_classification']})
    report={'status':'TYPED_PARSE_PASS_ORIGINAL_BS82_NO_SSE_CONVERSION_CLAIM','reader':'BadDogSkyrim/PyNifly official releaseV30.2.0 NiflyDLL CPU read API; raw full block structure separately bounded in first_run_comparison.json',
        'reader_binary_manifest':str(OUT/'primary_sources/PyNifly/binary_manifest.json'),'files':results,
        'native_runtime_verified':False,'limits':['Nifly labels stream82 as FO3-range even though bone names/shader classes are Skyrim assets. This successful typed read is source-format proof, not an in-game render test.',
            'CAO candidate remains82 and must not be advertised/deployed as an SSE100 repair. Keep exact original source files if accepted by parent with a two-file format exception.']}
    (ROOT/'typed_comparison.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2)[:6000])
if __name__=='__main__':main()
