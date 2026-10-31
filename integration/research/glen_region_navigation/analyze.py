"""Exact door-face composition against the actual TuLED region/city winners."""
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'forgotten_city_navigation'))
from analyze_navigation import Plugin,View,compare_faces
sys.path.insert(0,str(OUT.parent/'navmesh_patch'))
from verify_candidate import navi_model,NAVI,fields

PATHS={
 'vanilla':ROOT/'repairs/consistent_stock/Data/Skyrim.esm',
 'Glen':ROOT/'xedit_runs/Anno/Data/Glenmoril.esm',
 'AK':ROOT/'xedit_runs/TuLED/Data/AKSkyrimUnderground.esm',
 'AncientLand':ROOT/'xedit_runs/TuLED/Data/AncientLand2.esp',
 'RedBag':ROOT/'xedit_runs/TuLED/Data/RedBag\'s Falkreath.esp',
}


def sha(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def parent_cell(plugin,record):
 target=record['offset']
 with plugin.path.open('rb') as stream:
  def descend(start,end,current=None):
   pos=start
   while pos<end:
    stream.seek(pos);header=stream.read(24);assert len(header)==24
    size=struct.unpack_from('<I',header,4)[0]
    if header[:4]==b'GRUP':
     assert size>=24
     if pos+24<=target<pos+size:
      typ=struct.unpack_from('<i',header,12)[0]
      if typ in (6,8,9,10):current=plugin.identity(struct.unpack_from('<I',header,8)[0])
      return descend(pos+24,pos+size,current)
    else:
     if pos==target:return current
     size+=24
    pos+=size
   raise AssertionError('NAVM not found in group chain')
  result=descend(0,plugin.path.stat().st_size)
 assert result and result.startswith('skyrim.esm|')
 return result


def component(view,start):
 seen={start};pending=[start];errors=[];ports=[]
 while pending:
  index=pending.pop();triangle=view.triangles[index]
  assert not triangle[6]&8
  for side,edge in enumerate(triangle[3:6]):
   if triangle[6]&(1<<side):
    if not 0<=edge<len(view.model['edges']):errors.append({'kind':'external_index','triangle':index,'side':side});continue
    ports.append({'triangle':index,'side':side,**view.model['edges'][edge]});continue
   if edge==-1:continue
   if not 0<=edge<len(view.triangles):errors.append({'kind':'internal_index','triangle':index,'side':side});continue
   other=view.triangles[edge]
   if not any(not other[6]&(1<<s) and back==index for s,back in enumerate(other[3:6])):
    errors.append({'kind':'missing_reciprocal','triangle':index,'neighbor':edge})
   shared=set(view.vertices[v] for v in triangle[:3])&set(view.vertices[v] for v in other[:3])
   if len(shared)<2:errors.append({'kind':'no_shared_geometry_edge','triangle':index,'neighbor':edge})
   if not other[6]&8 and edge not in seen:seen.add(edge);pending.append(edge)
 return {'component_size':len(seen),'total_triangles':len(view.triangles),'external_port_count':len(ports),
         'existing_door_exits':[door for door in view.model['doors'] if door['triangle'] in seen],
         'external_neighbors':sorted({p['navmesh'] for p in ports}),
         'water_triangles':sum(bool(view.triangles[i][6]&512) for i in seen),
         'errors':errors,'all_ports':ports,
         'scope':'Static non-deleted navmesh adjacency; not an in-game actor/slope/collision test.'}


def main():
 sys.stdout.reconfigure(encoding='utf-8')
 plugins={key:Plugin(path) for key,path in PATHS.items()}
 navis={key:navi_model(plugin,plugin.get(NAVI,'NAVI')) for key,plugin in plugins.items()}
 profile=ROOT/'UnifiedSkyrim/profiles/Unified Skyrim/plugins.txt'
 load=[line.lstrip('*').lower() for line in profile.read_text(encoding='utf-8-sig').splitlines() if line.startswith('*')]
 cases=[('skyrim.esm|016F5D','AK',[502]),('skyrim.esm|0EC466','AncientLand',[34]),('skyrim.esm|0EC469','RedBag',[116,325])]
 results=[]
 for identity,base_key,source_triangles in cases:
  source=View(plugins['Glen'],identity);stock=View(plugins['vanilla'],identity)
  base=View(plugins[base_key],identity)
  assert source.vertices==stock.vertices
  expected_door_indices=set(source_triangles)
  raw_changes=[];semantic=[]
  for i in range(len(stock.triangles)):
   if source.triangles[i]!=stock.triangles[i]:raw_changes.append(i)
   if source.normalized(i)!=stock.normalized(i):semantic.append(i)
  assert set(semantic)==expected_door_indices
  faces=collections.defaultdict(list)
  for i,triangle in enumerate(base.triangles):faces[base.face_key(triangle)].append(i)
  mappings=[]
  for old in source_triangles:
   wanted=source.face_key(source.triangles[old]);matches=faces.get(wanted,[])
   assert len(matches)==1,(identity,old,matches)
   new=matches[0]
   assert source.winding_key(source.triangles[old])==base.winding_key(base.triangles[new])
   flags=base.triangles[new][6]
   assert not flags&(8|512|1024),'Deleted/water/already-door face requires separate review'
   bfs=component(base,new)
   assert not bfs['errors'] and (bfs['external_port_count']>0 or bfs['existing_door_exits'])
   doors=[door for door in source.model['doors'] if door['triangle']==old and door['door'].startswith('glenmoril.esm|')]
   assert len(doors)==1
   source_info=navis['Glen']['infos'][identity]
   matching_info=[door for door in source_info['doors'] if door['door']==doors[0]['door']]
   assert len(matching_info)==1 and matching_info[0]['crc']==doors[0]['crc']
   mappings.append({'source_triangle':old,'base_triangle':new,'source_vertices':source.triangles[old][:3],
     'base_vertices':base.triangles[new][:3],'exact_XYZ':[source.xyz(v) for v in source.triangles[old][:3]],
     'coordinate_bytes':[source.vertices[v].hex() for v in source.triangles[old][:3]],
     'unique_face_matches':matches,'same_winding':True,'base_tuple':base.triangles[new],
     'base_flags':flags,'expected_flags':flags|1024,'authored_door':doors[0],
     'connected_component':bfs})
  base_info=navis[base_key]['infos'][identity]
  all_neighbors=sorted(set(base_info['edges']+base_info['preferred_edges']))
  geometric_neighbors=sorted({edge['navmesh'] for edge in base.model['edges']})
  assert all_neighbors==geometric_neighbors
  hits={key:[] if navi['precomputed'] is None else [i for i,path in enumerate(navi['precomputed']['paths']) if identity in path]
        for key,navi in navis.items()}
  assert all(not values for values in hits.values())
  planned_triangles=[list(t) for t in base.triangles]
  planned_doors=list(base.model['doors'])
  for mapping in mappings:
   planned_triangles[mapping['base_triangle']][6]|=1024
   planned_doors.append({**mapping['authored_door'],'triangle':mapping['base_triangle']})
  results.append({'identity':identity,'selected_base':base_key,'selected_base_plugin':plugins[base_key].path.name,
   'source_Glen_geometry':source.model,'base_geometry':base.model,
   'source_navm_header':source.record,'base_navm_header':base.record,
   'source_raw_changed_triangles':raw_changes,'source_logical_changed_triangles':semantic,
   'geometry_face_comparison':compare_faces(stock,base),
   'mappings':mappings,'source_NVMI':source_info,'base_NVMI':base_info,
   'expected_NVMI_neighbor_union':all_neighbors,'base_parent_cell':parent_cell(plugins[base_key],base.record),
   'precomputed_target_paths':hits,
   'expected_triangles_sha256':hashlib.sha256(b''.join(struct.pack('<hhh hhh HH',*t) for t in planned_triangles)).hexdigest(),
   'expected_door_triangles':sorted(planned_doors,key=lambda d:(d['triangle'],d['door'])),
   'composition':'Preserve complete selected base geometry/adjacency/grid and non-door NVMI; OR only Door bit on unique mapped faces, transfer exact Glen typed Door Triangle with mapped ordinal and exact NAVI Door Link.'})
 comparisons=[]
 for key in ('AncientLand','RedBag'):
  identity='skyrim.esm|0EC469'
  present=[r for r in plugins[key].records if r['signature']=='NAVM' and r['id']==identity]
  if not present:continue
  v=View(plugins[key],identity);g=View(plugins['Glen'],identity)
  for old in (116,325):
   match=[i for i,t in enumerate(v.triangles) if v.face_key(t)==g.face_key(g.triangles[old])]
   comparisons.append({'source_triangle':old,'base':key,'matches':match})
 report={'status':'STATIC_COMPOSITION_BOUNDABLE_DRAFT_ONLY_NO_PLUGIN_CREATED',
  'sources':{key:{'path':str(plugin.path),'sha256':sha(plugin.path)} for key,plugin in plugins.items()},
  'profile':str(profile),'profile_sha256':sha(profile),
  'profile_base_order':{name:load.index(name.lower()) if name.lower() in load else None for name in ['AKSkyrimUnderground.esm','AncientLand2.esp',"RedBag's Falkreath.esp",'Glenmoril.esm']},
  'cases':results,'alternative_AncientLand_RedBag_mappings':comparisons,
  'new_own_records':0,'new_coordinates':0,'new_CRCs':0,
  'limitations':['No game or GUI launched; no actor path/collision behavior tested.',
    'Actual final VFS source hashes, winners and candidate typed/binary checks remain required.',
    'The final 0EC469 base is RedBag, whose mapped door325 becomes triangle86; copying raw325 would be wrong.']}
 (OUT/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({'status':report['status'],'mappings':[{'id':c['identity'],'base':c['selected_base'],'parent':c['base_parent_cell'],
  'doors':[(m['source_triangle'],m['base_triangle'],m['connected_component']['component_size'],m['connected_component']['external_port_count']) for m in c['mappings']]} for c in results]},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
