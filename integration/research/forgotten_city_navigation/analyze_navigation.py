"""Exact source-only Forgotten City / coherent Skyrim / TuLED USSEP comparison.

No plugins are modified and no coordinate tolerances are used. All matches use
unchanged IEEE-754 vertex bytes, typed triangle tuples and canonical FormIDs.
"""
import collections
import hashlib
import json
import struct
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(OUT.parent/'navmesh_patch'))
from verify_candidate import Plugin, fields, geometry, navi_model, NAVI

PRIMARY = 'skyrim.esm|108AB4'
NEIGHBOR = 'skyrim.esm|107528'
SOURCE = Path(r'E:\stock\Skyrim collection\Anno\iniRePather-Skyrim\mods\The Forgotten City\ForgottenCity.esp')
VANILLA = ROOT/'repairs/consistent_stock/Data/Skyrim.esm'
USSEP = ROOT/'xedit_runs/TuLED/Data/Unofficial Skyrim Special Edition Patch.esp'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


class View:
    def __init__(self, plugin, identity):
        self.plugin = plugin
        self.record = plugin.get(identity,'NAVM')
        self.model, self.triangles = geometry(plugin,self.record)
        data = next(data for tag,data in fields(plugin.payload(self.record)) if tag == 'NVNM')
        count = struct.unpack_from('<I',data,16)[0]
        self.vertices = [data[20+i*12:32+i*12] for i in range(count)]
        assert count == self.model['vertex_count']

    def xyz(self,index):
        return list(struct.unpack('<fff',self.vertices[index]))

    def face_key(self,triangle):
        return tuple(sorted(self.vertices[index].hex() for index in triangle[:3]))

    def winding_key(self,triangle):
        keys = [self.vertices[index].hex() for index in triangle[:3]]
        return min(tuple(keys[i:]+keys[:i]) for i in range(3))

    def normalized(self,index):
        triangle = self.triangles[index]
        edges = []
        for side in range(3):
            edge = triangle[side+3]
            endpoints = sorted([self.vertices[triangle[side]].hex(),self.vertices[triangle[(side+1)%3]].hex()])
            if triangle[6] & (1<<side):
                assert 0 <= edge < len(self.model['edges'])
                link = {'kind':'external',**self.model['edges'][edge]}
            elif edge == -1:
                link = {'kind':'border'}
            else:
                assert 0 <= edge < len(self.triangles)
                link = {'kind':'internal','face':self.face_key(self.triangles[edge])}
            edges.append({'endpoints':endpoints,'link':link})
        return {'face':self.face_key(triangle),'winding':self.winding_key(triangle),
                'flags_without_external_bits':triangle[6]&~7,'cover_flags':triangle[7],
                'edges':sorted(edges,key=lambda x:x['endpoints'])}

    def portals_to(self,identity):
        result=[]
        for index,triangle in enumerate(self.triangles):
            for side in range(3):
                if triangle[6] & (1<<side):
                    edge_index=triangle[side+3]
                    link=self.model['edges'][edge_index]
                    if link['navmesh']==identity:
                        result.append({'source_triangle':index,'side':side,'edge_index':edge_index,
                                       'link':link,'source_triangle_vertices':triangle[:3]})
        return result

    def summary(self):
        return {'plugin':self.plugin.path.name,'path':str(self.plugin.path),'record':self.record,
                'geometry':self.model}


def compare_faces(a,b):
    matches=collections.defaultdict(list)
    for index,triangle in enumerate(b.triangles):matches[b.face_key(triangle)].append(index)
    mapped=[]
    removed=[]
    for index,triangle in enumerate(a.triangles):
        ids=matches.get(a.face_key(triangle),[])
        if ids:mapped.append({'source':index,'matches':ids})
        else:removed.append({'index':index,'vertices':triangle[:3],'xyz':[a.xyz(v) for v in triangle[:3]]})
    akeys={a.face_key(t) for t in a.triangles}
    added=[{'index':i,'vertices':t[:3],'xyz':[b.xyz(v) for v in t[:3]]} for i,t in enumerate(b.triangles) if b.face_key(t) not in akeys]
    return {'matched_faces':len(mapped),'removed_faces':removed,'added_faces':added,'mapping':mapped}


def cross_link_proof(base_primary, feature_neighbor, old_primary, old_neighbor):
    outward=[]
    inward=[]
    for portal in base_primary.portals_to(NEIGHBOR):
        target=portal['link']['triangle']
        target_survives=(target < len(feature_neighbor.triangles) and
            old_neighbor.face_key(old_neighbor.triangles[target]) == feature_neighbor.face_key(feature_neighbor.triangles[target]))
        ordered_survives=(target < len(feature_neighbor.triangles) and
            [old_neighbor.vertices[v] for v in old_neighbor.triangles[target][:3]] ==
            [feature_neighbor.vertices[v] for v in feature_neighbor.triangles[target][:3]])
        reciprocal=[p for p in feature_neighbor.portals_to(PRIMARY)
                    if p['source_triangle']==target and p['link']['triangle']==portal['source_triangle']]
        outward.append({**portal,'target_face_preserved_at_same_index':target_survives,
                        'ordered_target_vertices_preserved':ordered_survives,
                        'reciprocal_in_feature':reciprocal})
    for portal in feature_neighbor.portals_to(PRIMARY):
        target=portal['link']['triangle']
        target_survives=(target < len(base_primary.triangles) and
            old_primary.face_key(old_primary.triangles[target]) == base_primary.face_key(base_primary.triangles[target]))
        ordered_survives=(target < len(base_primary.triangles) and
            [old_primary.vertices[v] for v in old_primary.triangles[target][:3]] ==
            [base_primary.vertices[v] for v in base_primary.triangles[target][:3]])
        reciprocal=[p for p in base_primary.portals_to(NEIGHBOR)
                    if p['source_triangle']==target and p['link']['triangle']==portal['source_triangle']]
        inward.append({**portal,'target_face_preserved_at_same_index':target_survives,
                       'ordered_target_vertices_preserved':ordered_survives,
                       'reciprocal_in_base':reciprocal})
    return {'USSEP_to_FC':outward,'FC_to_USSEP':inward}


def cell_context(feature_data):
    rows=[]
    for record in feature_data['override_records']:
        if record['signature'] in {'NAVM','CELL'}:
            rows.append({'signature':record['signature'],'id':record['origin']+'|'+record['object_id'],
                         'source_groups':record['feature_record']['groups'],
                         'base_plugin':record['base_record']['plugin'],
                         'base_path':record['base_record']['path']})
    return rows


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    plugins={'vanilla':Plugin(VANILLA),'feature':Plugin(SOURCE),'USSEP':Plugin(USSEP)}
    primary={key:View(value,PRIMARY) for key,value in plugins.items()}
    neighbors={key:View(plugins[key],NEIGHBOR) for key in ('vanilla','feature')}
    a,f,u=primary['vanilla'],primary['feature'],primary['USSEP']
    assert a.vertices == f.vertices
    raw_changed=[i for i,(x,y) in enumerate(zip(a.triangles,f.triangles)) if x!=y]
    semantic_changed=[{'index':i,'vanilla':a.normalized(i),'feature':f.normalized(i),
                       'vanilla_tuple':a.triangles[i],'feature_tuple':f.triangles[i]}
                      for i in range(len(a.triangles)) if a.normalized(i)!=f.normalized(i)]
    geometry_diff=compare_faces(a,u)
    changed_vertices=[{'index':i,'vanilla':a.xyz(i),'USSEP':u.xyz(i),
                       'vanilla_hex':a.vertices[i].hex(),'USSEP_hex':u.vertices[i].hex()}
                      for i in range(min(len(a.vertices),len(u.vertices))) if a.vertices[i]!=u.vertices[i]]
    new_vertices=[{'index':i,'xyz':u.xyz(i),'hex':u.vertices[i].hex()} for i in range(len(a.vertices),len(u.vertices))]
    mapping=[m for m in geometry_diff['mapping'] if m['source']==50]
    proof=cross_link_proof(u,neighbors['feature'],a,neighbors['vanilla'])
    navi={key:navi_model(value,value.get(NAVI,'NAVI')) for key,value in plugins.items()}
    summaries={}
    for key,model in navi.items():
        summaries[key]={'targets':{identity:model['infos'].get(identity) for identity in (PRIMARY,NEIGHBOR)},
                        'precomputed_target_paths':{identity:[i for i,path in enumerate(model['precomputed']['paths']) if identity in path]
                             for identity in (PRIMARY,NEIGHBOR)} if model['precomputed'] else {},
                        'precomputed_target_roadmarkers':[x for x in model['precomputed']['roadmarkers'] if x['navmesh'] in (PRIMARY,NEIGHBOR)] if model['precomputed'] else []}
    feature_path=OUT.parent/'feature_conflicts/raw_field_comparison.json'
    feature_json=json.loads(feature_path.read_text(encoding='utf-8'))
    feature=next(x for x in feature_json['features'] if x['plugin'].lower()=='forgottencity.esp')
    feature_navmeshes=[]
    for row in feature['override_records']:
        if row['signature']=='NAVM':
            identity=row['origin']+'|'+row['object_id']
            source_view=View(plugins['feature'],identity)
            vanilla_view=View(plugins['vanilla'],identity)
            feature_navmeshes.append({'id':identity,'source_vertices':len(source_view.vertices),
                'vanilla_vertices':len(vanilla_view.vertices),'source_triangles':len(source_view.triangles),
                'vanilla_triangles':len(vanilla_view.triangles),'source_doors':source_view.model['doors'],
                'base_winner':row['base_record']['plugin']})
    callers=[]
    source_navmesh_count=0
    for record in plugins['feature'].records:
        if record['signature']!='NAVM':continue
        source_navmesh_count+=1
        model,triangles=geometry(plugins['feature'],record)
        hits=[{'edge_index':i,**edge} for i,edge in enumerate(model['edges']) if edge['navmesh'] in (PRIMARY,NEIGHBOR)]
        if hits:callers.append({'source':record['id'],'links':hits})
    seven_keys=[row['id'] for row in feature_navmeshes]
    seven_nvmi={}
    for identity in seven_keys:
        desired='USSEP' if identity==PRIMARY else 'feature'
        seven_nvmi[identity]={'desired_source':desired,'model':navi[desired]['infos'].get(identity),
            'source_precomputed_hits':{name:sum(identity in path for path in model['precomputed']['paths'])
                for name,model in navi.items() if model['precomputed']}}
    bad_outward=[port for port in proof['USSEP_to_FC'] if not port['reciprocal_in_feature'] or not port['target_face_preserved_at_same_index']]
    bad_inward=[port for port in proof['FC_to_USSEP'] if not port['reciprocal_in_base'] or not port['target_face_preserved_at_same_index']]
    assert len(semantic_changed)==1 and semantic_changed[0]['index']==50
    assert len(mapping)==1 and mapping[0]['matches']==[50]
    assert len(bad_outward)==1 and bad_outward[0]['source_triangle']==50 and bad_outward[0]['side']==2
    assert not bad_inward
    assert all(port['ordered_target_vertices_preserved'] for port in proof['USSEP_to_FC'] if port['source_triangle']!=50)
    assert all(port['ordered_target_vertices_preserved'] for port in proof['FC_to_USSEP'])
    removed_index=bad_outward[0]['edge_index']
    assert removed_index==6
    candidate_triangles=[list(triangle) for triangle in u.triangles]
    for i,triangle in enumerate(u.triangles):
        for side in range(3):
            if triangle[6]&(1<<side):
                edge=triangle[3+side]
                if edge==removed_index:
                    assert i==50 and side==2
                    candidate_triangles[i][3+side]=-1
                    candidate_triangles[i][6]&=~(1<<side)
                elif edge>removed_index:
                    candidate_triangles[i][3+side]=edge-1
    expected_triangle_sha=hashlib.sha256(b''.join(struct.pack('<hhh hhh HH',*t) for t in candidate_triangles)).hexdigest()
    expected_edges=[edge for i,edge in enumerate(u.model['edges']) if i!=removed_index]
    report={'status':'READ_ONLY_COMPOSITION_ANALYSIS_NO_PATCH_CREATED',
        'sources':{key:{'path':str(value.path),'sha256':digest(value.path)} for key,value in plugins.items()},
        'primary':{key:value.summary() for key,value in primary.items()},
        'neighbor':{key:value.summary() for key,value in neighbors.items()},
        'feature_raw_changed_triangles':raw_changed,'feature_semantic_changes':semantic_changed,
        'USSEP_vertex_changes':changed_vertices,'USSEP_new_vertices':new_vertices,
        'USSEP_face_changes':geometry_diff,'changed_feature_triangle_USSEP_mapping':mapping,
        'neighbor_feature_face_changes':compare_faces(neighbors['vanilla'],neighbors['feature']),
        'cross_link_proof':proof,'NAVI':summaries,
        'all_feature_NAVM_scanned':source_navmesh_count,'all_feature_callers_to_focus_pair':callers,
        'seven_shared_NVMI_plan':seven_nvmi,
        'bounded_candidate_plan':{'disposition':'STATICALLY_BOUNDABLE_CANDIDATE_XEDIT_BUILD_RELOAD_AND_NATIVE_CHECKS_REQUIRED',
            'base_geometry':'USSEP entire existing NAVM; no vertex or face creation/movement',
            'source_feature_delta':'Remove only the authored portal at triangle50 Edge2-0',
            'removed_USSEP_edge_index':removed_index,'removed_edge':u.model['edges'][removed_index],
            'triangle50_before':u.triangles[50],'triangle50_expected':candidate_triangles[50],
            'external_index_remap':'For every other external edge reference >6, subtract one after deleting only Edge Links[6]. Internal triangle indices remain unchanged.',
            'expected_triangles_sha256':expected_triangle_sha,'expected_edge_links':expected_edges,
            'unchanged_vertices_sha256':u.model['vertices_sha256'],'unchanged_grid_sha256':u.model['grid_sha256'],
            'NAVI':'Forward exact USSEP target NVMI and exact authored FC other six shared NVMI; retain every other final source NAVI entry/NVPP/NVSI. Stop if actual final topology/source winners differ.',
            'no_guessed_coordinates_or_CRC':True,'new_own_records':0},
        'related_cells':cell_context(feature),'feature_navmeshes':feature_navmeshes,
        'feature_fields_source':{'path':str(feature_path),'sha256':digest(feature_path),
            'reference_profile_hashes':feature_json['profile_hashes_after']},
        'limitations':['Based on selected source snapshots and consistent stock; actual final VFS preflight remains necessary.',
                       'No approximate coordinate matching or generated geometry is used. No game/UI launched.']}
    (OUT/'comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'raw_changed':len(raw_changed),'semantic_changed':len(semantic_changed),
       'USSEP_changed_vertices':len(changed_vertices),'USSEP_new_vertices':len(new_vertices),
       'USSEP_faces_matched':geometry_diff['matched_faces'],
       'USSEP_faces_removed':len(geometry_diff['removed_faces']),'USSEP_faces_added':len(geometry_diff['added_faces']),
       'neighbor_faces_removed':[x['index'] for x in report['neighbor_feature_face_changes']['removed_faces']],
       'outward_cross_ports':len(proof['USSEP_to_FC']),'inward_cross_ports':len(proof['FC_to_USSEP']),
       'outward_missing_reciprocals':[x['source_triangle'] for x in proof['USSEP_to_FC'] if not x['reciprocal_in_feature']],
       'inward_missing_reciprocals':[x['source_triangle'] for x in proof['FC_to_USSEP'] if not x['reciprocal_in_base']],
       'output':str(OUT/'comparison.json')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
