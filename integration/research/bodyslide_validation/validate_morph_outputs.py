"""Validate generated NIF/TRI structure, both weight endpoints and morph indices."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from nif_tri import OWN,BASE,nif,tri


def key(s):return str(s).replace('\\','/').casefold()
def main():
    p=argparse.ArgumentParser();p.add_argument('--prepared',default=str(BASE/'integration/bodyslide_prepared.json'))
    p.add_argument('--pack',choices=['Anno','Burida']);p.add_argument('--output',required=True)
    p.add_argument('--overlay-candidates',help='Read reviewed research candidates over generated files; no source/runtime file is modified.')
    a=p.parse_args();out=Path(a.output).resolve();assert out.is_relative_to(OWN) and out!=OWN
    overlay=Path(a.overlay_candidates).resolve() if a.overlay_candidates else None
    prepared=json.loads(Path(a.prepared).read_text(encoding='utf-8'));rows=[];errors=[];missing=[];counts=collections.Counter();observed=set()
    for job in prepared['jobs']:
        if a.pack and job['pack']!=a.pack:continue
        root=Path(job['output']);expected=set()
        for project in job['expected_projects']:
            row={'project':project['curated_set_name'],'pack':job['pack'],'nifs':[],'tri':None,'checks':[]};byweight=[]
            tri_rel=project['output_stem']+'.tri';expected.add(key(tri_rel));tri_path=root/tri_rel
            for rel in project['generated_paths']:
                expected.add(key(rel));path=overlay/rel if overlay and (overlay/rel).is_file() else root/rel
                if not path.is_file():missing.append(str(path));continue
                try:
                    data=nif(path);row['nifs'].append(data);byweight.append(data);counts['nifs']+=1
                    refs={key(v).removeprefix('meshes/') for v in data['bodytri_references']}
                    if refs!={key(tri_rel).removeprefix('meshes/')}:
                        errors.append({'kind':'bodytri_path_not_exact_expected','path':str(path),'expected':tri_rel,'actual':data['bodytri_references']})
                except Exception as e:errors.append({'kind':'nif_structure_failed','path':str(path),'error':repr(e)})
            if len(byweight)==2:
                first={s['name']:s for s in byweight[0]['shapes']};second={s['name']:s for s in byweight[1]['shapes']}
                if list(first)!=list(second):errors.append({'kind':'weight_shape_order_or_names_differ','project':row['project'],'weight_shapes':[list(first),list(second)]})
                for name in first.keys()&second.keys():
                    one,two=first[name],second[name]
                    if any(one[k]!=two[k] for k in ['vertex_count','triangle_count','triangle_stream_sha256']):
                        errors.append({'kind':'weight_topology_differs','project':row['project'],'shape':name,'weight0':one,'weight1':two})
                row['checks'].append('Both weight shape names/order, vertex counts, triangle counts and stored global triangle streams compared.')
            if not tri_path.is_file():missing.append(str(tri_path))
            else:
                try:
                    parsed=tri(tri_path);row['tri']=parsed;counts['tris']+=1
                    for group in parsed['groups']:
                        for endpoint in byweight:
                            matches=[s for s in endpoint['shapes'] if s['name']==group['shape']]
                            if len(matches)!=1:raise ValueError(('TRI shape is absent/ambiguous in endpoint',group['shape'],endpoint['path']))
                            for morph in group['morphs']:
                                if morph['maximum_vertex_index']>=matches[0]['vertex_count']:
                                    raise ValueError(('TRI morph index exceeds generated endpoint vertices',group['shape'],morph,endpoint['path']))
                        counts['morph_shapes']+=1;counts['morphs']+=len(group['morphs'])
                    row['checks'].append('Entire position/UV TRI parsed to exact EOF; every morph index checked against both generated endpoint shape vertex counts.')
                except Exception as e:errors.append({'kind':'tri_structure_or_mesh_index_closure_failed','path':str(tri_path),'error':repr(e)})
            counts['projects']+=1;rows.append(row)
        for f in root.rglob('*'):
            if f.is_file():
                rel=key(f.relative_to(root));observed.add((job['pack'],rel))
                if rel not in expected:errors.append({'kind':'unexpected_generated_output','pack':job['pack'],'path':str(f)})
    result={'status':'FAIL' if errors or missing else 'PASS_STATIC_GENERATED_NIF_TRI_TOPOLOGY',
      'prepared':str(Path(a.prepared).resolve()),'prepared_sha256':hashlib.sha256(Path(a.prepared).read_bytes()).hexdigest(),
      'pack_filter':a.pack,'candidate_overlay':str(overlay) if overlay else None,'counts':dict(counts),'missing':missing,'errors':errors,'projects':rows,
      'scope':'Static generated-output inspection. Both endpoints are verified together; original NIFs are not replaced during validation.',
      'limitations':['No game was launched; this does not establish runtime visual quality or physics playback.','Bounds and stored indices establish matching topology, not a guarantee against all artist-authored clipping.','TRI is numeric TRIP FourCC 0x54524950, on-disk PIRT; head morph TRI is intentionally rejected.'],
      'primary_schema_sources':[str(BASE/'sources/nifxml/nif.xml'),str(OWN/'source/TriFile.cpp')]}
    out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'counts':result['counts'],'missing':len(missing),'errors':len(errors),'output':str(out)},ensure_ascii=False),flush=True)
    return 2 if errors or missing else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
