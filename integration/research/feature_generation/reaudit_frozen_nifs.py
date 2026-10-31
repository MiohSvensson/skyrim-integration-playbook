"""CPU re-audit existing exact private source bytes with a new reader version.

No new runtime/profile claim: provenance stays tied to the original frozen
research run. Formal PG will resolve/freeze a fresh post-Synthesis profile.
"""
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
from pg_nif_reader import snapshot,compare
from pg_nif_validate import complete_typed_node_coverage,sha,owned

def main():
    assert len(sys.argv)==2;run=owned(sys.argv[1]);assert run.name.startswith('nif_cpu_preflight_')
    source=run/'nif_inputs/manifest.json';m=json.loads(source.read_text(encoding='utf8'));rh=sha(OUT/'pg_nif_reader.py');dest=run/('source_reaudit_'+rh[:12]);assert not dest.exists();dest.mkdir()
    rows={};trailers=[];numeric=[];errors=[];fallbacks=[]
    for index,(key,row) in enumerate(sorted(m['entries'].items())):
        try:
            path=Path(row['snapshot']);assert sha(path)==row['sha256'] and path.stat().st_nlink==1
            s=snapshot(path,True,True);complete_typed_node_coverage(s);t=s['raw']
            for warning in s['source_warnings']:
                if 'numeric_defects' in warning:numeric.append({'path_key':key,'source_sha256':s['sha256'],**warning})
            if t['trailer_bytes']:
                core=run/'nif_inputs/bytes'/(t['declared_core_sha256']+'.core.nif')
                if not core.exists():core.write_bytes(path.read_bytes()[:t['declared_core_bytes']])
                assert sha(core)==t['declared_core_sha256'] and core.stat().st_nlink==1
                clean=snapshot(core,False,True);complete_typed_node_coverage(clean);proof=compare(s,clean)
                assert not proof['failures'] and not proof['material_changes'],'Trailer changes author parsed semantics'
                trailers.append({'path_key':key,'source_sha256':s['sha256'],'core_bytes':t['declared_core_bytes'],'core_sha256':t['declared_core_sha256'],'trailer_bytes':t['trailer_bytes'],'trailer_sha256':t['trailer_sha256'],'full_vs_core_author_typed_equal':True,'private_core':str(core),'adopted_for_formal_run':False})
            if s['native_base_NiNode_accessor_types']:fallbacks.append({'path_key':key,'source_sha256':s['sha256'],'types':s['native_base_NiNode_accessor_types'],'subclass_fields':'Protected exact raw block hashes; base geometry typed via author native NiNode accessor.'})
            typed=dest/(s['sha256']+'.json')
            if not typed.exists():typed.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            rows[key]={**row,'typed_snapshot':str(typed),'typed_snapshot_sha256':sha(typed),'typed_complete_node_shape_coverage':True}
        except Exception as error:
            errors.append({'path_key':key,'source_sha256':row.get('sha256'),'error':repr(error)});rows[key]={**row,'typed_status':'UNPROVEN_SOURCE_READER_GAP'}
        if index%100==0:print(json.dumps({'audited':index+1,'total':len(m['entries']),'gaps':len(errors)}),flush=True)
    r={'status':'ALL_SOURCES_READ_WITH_EXACT_FORMAT_NUMERIC_LIMITS_NOT_FORMAL' if not errors else 'SOURCE_READER_GAPS_NOT_FORMAL','entries':rows,'source_trailer_cases':trailers,'source_numeric_defects':numeric,'source_audit_gaps':errors,'base_NiNode_accessor_cases':fallbacks,
       'reader_script_sha256':rh,'reader_dll_sha256':sha(OUT/'primary_sources/PyNifly/addon/io_scene_nifly/NiflyDLL.dll'),'source_manifest':str(source),'source_manifest_sha256':sha(source),
       'all_vertices_triangles_normals_UV_bone_palettes_weights_bind_transforms_and_hierarchy_read':not errors,'native_rendering_verified':False,
       'source_provenance_context':'Original immutable research-run providers/order; formal generation must freshly resolve sources after Synthesis and profile changes.',
       'formal_adoption':'No automatic acceptance. Parent reviews precise source-only trailers and numeric exclusions. Every formal PG output stays cleanEOF/finite and strict on unapproved fields.'}
    (dest/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':r['status'],'sources':len(rows),'trailers':len(trailers),'numeric':len(numeric),'gaps':len(errors),'base_accessor':len(fallbacks),'result':str(dest/'result.json')},ensure_ascii=True),flush=True)
if __name__=='__main__':main()
