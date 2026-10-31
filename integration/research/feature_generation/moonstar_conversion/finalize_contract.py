"""Resolve the exact effective original asset; generate narrow, read-only evidence."""
import collections
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent;OUT=ROOT.parent;DB=OUT.parents[2]
sys.path.insert(0,str(DB/'integration'));import runtime_inventory as ri
sys.path.insert(0,str(OUT.parent/'vfs_validation'));from vfs_common import ResourceCatalog,active_archive_names,key
from compare_typed import snapshot

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def raw_table(data):
    p=data.index(b'\n')+1
    def n(fmt):
        nonlocal p
        x=struct.unpack_from('<'+fmt,data,p)[0];p+=struct.calcsize(fmt);return x
    def s(fmt='I'):
        nonlocal p
        size=n(fmt);x=data[p:p+size];p+=size;return x
    version=n('I');endian=n('B');user=n('I');count=n('I');stream=n('I')
    assert (version,endian,user,stream)==(0x14020007,1,12,82)
    exports=[s('B').hex() for _ in range(3)];types=[s().decode() for _ in range(n('H'))]
    indices=[n('H') for _ in range(count)];sizes=[n('I') for _ in range(count)]
    strings_count=n('I');n('I');strings=[s().decode('utf8') for _ in range(strings_count)]
    groups=[n('I') for _ in range(n('I'))];blocks=[]
    for i,(t,size) in enumerate(zip(indices,sizes)):
        assert t<len(types) and p+size<=len(data)
        blocks.append({'index':i,'type':types[t],'size':size,'offset':p,'sha256':hashlib.sha256(data[p:p+size]).hexdigest()});p+=size
    roots=[n('I') for _ in range(n('I'))]
    assert p==len(data) and all(i<count for i in roots)
    return {'version':version,'endian':endian,'user':user,'stream':stream,'blocks':blocks,'strings':strings,'roots':roots,'groups':groups,'EOF_exact':True,'block_types':dict(collections.Counter(x['type'] for x in blocks))}

def main():
    ri.PROFILE=DB/'UnifiedSkyrim/profiles/Unified Build';mods=ri.active_mods();physical={}
    for provider,folder in mods+[('Game/Data',DB/'UnifiedSkyrim/Game/Data')]:
        if not folder.is_dir():continue
        for f in folder.iterdir():
            if f.is_file():physical.setdefault(key(f.name),{'relative_path':f.name,'physical_path':str(f),'provider':provider,'size_bytes':f.stat().st_size})
    names=ri.plugin_names(mods);archives,_=active_archive_names(ri.PROFILE,names,physical)
    catalog=ResourceCatalog(physical,{key(n):dict(physical[key(n)],order=i) for i,n in enumerate(archives)})
    results=[]
    for name in ('wg_0.nif','wg_1.nif'):
        k='meshes/mwl/'+name;provider,file=ri.resolve(k,mods)
        if file:loc={'kind':'loose','physical_path':str(file),'provider':provider,'sha256':sha(file)}
        else:loc=catalog.resolve(k)
        assert loc['kind'] in ('bsa','loose')
        lotd=ROOT/'LOTD_author_original'/name;moon=ROOT/'originals/meshes/mwl'/name
        options={sha(lotd):lotd,sha(moon):moon};assert loc['sha256'] in options,'Unknown effective winner requires a fresh typed parse'
        actual=options[loc['sha256']];snap=snapshot(actual);raw=raw_table(actual.read_bytes());shape=snap['shapes'][0]
        assert len(snap['shapes'])==1 and len(snap['nodes'])==41 and len(raw['blocks'])==47
        assert all(x['properties']['extraDataCount']==0 and x['properties']['controllerID']==0xffffffff for x in snap['nodes'].values())
        assert shape['properties']['extraDataCount']==0 and shape['properties']['controllerID']==0xffffffff
        assert shape['shader_properties']['extraDataCount']==0 and shape['shader_properties']['controllerID']==0xffffffff
        assert set(raw['block_types'])=={'NiNode','NiTriShape','NiTriShapeData','BSDismemberSkinInstance','NiSkinData','NiSkinPartition','BSLightingShaderProperty','BSShaderTextureSet'}
        refs=sorted(t.replace('\\','/').lower() for t in shape['textures'].values() if t)
        result={'path_key':k,'sha256':loc['sha256'],'provider':loc,'parsed_copy':str(actual),'bytes':actual.stat().st_size,'stream':82,
          'typed_snapshot':str(ROOT/(name+'.typed_'+('LOTD' if actual==lotd else 'original')+'.json')),
          'typed_snapshot_sha256':sha(ROOT/(name+'.typed_'+('LOTD' if actual==lotd else 'original')+'.json')),
          'block_table':raw,'geometry':{'shapes':1,'nodes':41,'vertices':len(shape['vertices']),'triangles':len(shape['triangles']),'bones':len(shape['bone_names']),'partitions':len(shape['partitions'])},
          'external_refs':[{'path':t,'kind':'texture','via':'BSShaderTextureSet'} for t in refs],
          'BODYTRI_refs':[],'behavior_refs':[],'extra_data_count':0,'controller_refs':[],'native_runtime_verified':False,
          'consumer':{'ARMA':'MoonAndStar_MAS.esp|015024','EDID':'MASWraithguardAA','slot':'MOD2' if name=='wg_0.nif' else 'MOD3','ARMO':'MoonAndStar_MAS.esp|015023'},
          'checks':['Exact file SHA selected through final loose/logical archive priority; BSA archive SHA matches indexed contents.',
            'All47 table-declared blocks bounded and footer roots/EOF validated; no unknown block classes.',
            'Author Nifly CPU reader loads all41nodes/shape, vertex triangle normal UV arrays, skin transforms,39bone weights,3partition memberships, shader and texture slots.',
            'All vertices finite; all triangle/weight indices valid; each vertex weight sum within0.001 of1; every skin bone resolves to a node.',
            'No extra-data blocks, no node/shape/shader extra-data or controller links; no BODYTRI/behavior external reference in the file.'],
          'limitations':['Stream82 is author-library FO3-range, retained exactly; no claim of SSE100 conversion or native rendering proof.',
            'Author Skyrim SE Nexus page claims SE/AE compatibility, but exact official Moon3.2 archive has not been downloaded/hash-proven. Local LOTD source is independent corroboration only.']}
        results.append(result)
    report={'status':'EXACT_TWO_EFFECTIVE_ORIGINAL_BS82_FORMAT_EXCEPTIONS_NOT_REPAIRED','profile':str(ri.PROFILE),'profile_controls':{n:sha(ri.PROFILE/n) for n in ('plugins.txt','modlist.txt','loadorder.txt')},
      'reader_release':json.loads((OUT/'primary_sources/PyNifly/binary_manifest.json').read_text()),
      'reader_dll_sha256':sha(OUT/'primary_sources/PyNifly/addon/io_scene_nifly/NiflyDLL.dll'),
      'parser_script':str(Path(__file__)),'parser_script_sha256':sha(__file__),
      'comparison_script':str(ROOT/'compare_typed.py'),'comparison_script_sha256':sha(ROOT/'compare_typed.py'),
      'entries':results,'acceptance':'Only path AND exact actual winning SHA match; any SHA/provider/schema change requires re-audit. Keep effective original bytes; CAO candidate rejected.',
      'CAO_result':'Only resaved stream82; bounding sphere changed, no SSE100 conversion. No candidate deployed.',
      'game_started':False}
    (ROOT/'effective_bs82_contract.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps([{k:r[k] for k in ('path_key','sha256','provider','geometry')} for r in results],ensure_ascii=True,indent=2))
if __name__=='__main__':main()
