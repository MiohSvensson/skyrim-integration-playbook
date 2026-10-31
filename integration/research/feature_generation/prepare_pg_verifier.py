"""Pin private PG results and emit a read-only xEdit4.1.5f metadata verifier.

Run AFTER a successful pg_child.py invocation. Does not launch any GUI, add a
plugin to a profile, edit a plugin or deploy an asset. The parent loads the
frozen final source plugins plus the generated DB outputs into xEdit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'navmesh_patch'));from verify_candidate import Plugin

def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def q(s):return "'"+str(s).replace("'","''")+"'"
def owned(p):
    p=Path(p).resolve();assert p.is_relative_to(OUT/'pg_runs');return p

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);a=ap.parse_args();run=owned(a.run)
    manifest=run/'manifest.json';m=json.loads(manifest.read_text(encoding='utf8'));result=json.loads((run/'result.json').read_text(encoding='utf8'))
    assert result['status']=='PRIVATE_PG_OUTPUT_CREATED_NOT_DEPLOYED_PENDING_TYPED_RECORD_AND_NIF_REVIEW'
    assert result['manifest_sha256']==sha(manifest)
    dest=run/'typed_verifier';assert not dest.exists(),'Use existing frozen verifier, or explicitly preserve and prepare a new version'
    inventory=json.loads((run/'output_inventory.json').read_text(encoding='utf8'));outputs=[];meshes=[];all_rows=[];target_ids={};txsts=0
    for row in inventory:
        p=owned(row['path']);assert sha(p)==row['sha256'] and p.stat().st_nlink==1
        if p.suffix.lower()=='.nif':meshes.append(row['relative'].replace('/','\\').lower())
        elif p.suffix.lower()=='.esp':
            assert p.name.lower()=='dbpatcher.esp' or re.fullmatch('db_[1-9][0-9]*\\.esp',p.name.lower())
            outputs.append(p.name.lower());plugin=Plugin(p)
            for r in plugin.records:
                if r['signature']=='TES4':continue
                assert not r['id'].startswith('UNMAPPED|')
                if plugin.name=='dbpatcher.esp':
                    assert r['signature']=='TXST' and r['id'].startswith('dbpatcher.esp|');txsts+=1
                else:
                    assert not r['id'].startswith(plugin.name+'|')
                    assert r['id'] not in target_ids,'Duplicate final override across DB splits'
                    target_ids[r['id']]=r['signature']
    assert meshes,'No generated NIF outputs to verify'
    sources={};input_names=[];source_hashes=[]
    for row in m['plugins']:
        p=Path(row['path']);assert sha(p)==row['sha256'],'Frozen source input drift: '+str(p)
        plugin=Plugin(p);assert plugin.name==row['name_key']
        assert plugin.name not in outputs,'Clashing new namespace'
        input_names.append(plugin.name);source_hashes.append({'path':str(p),'sha256':row['sha256']})
        for r in plugin.records:
            if r['id'] in target_ids:
                assert r['signature']==target_ids[r['id']]
                sources[r['id']]=plugin.name
    assert sources.keys()==target_ids.keys(),'Output overrides lack a final source winner'
    dest.mkdir()
    files={'expected_sources.txt':'\n'.join(k.lower()+'='+sources[k] for k in sorted(sources))+'\n',
      'allowed_files.txt':'\n'.join(input_names)+'\n','allowed_meshes.txt':'\n'.join(sorted(set(meshes)))+'\n',
      'output_names.txt':'\n'.join(sorted(outputs))+'\n'}
    for name,text in files.items():(dest/name).write_text(text,encoding='utf8')
    # Reuse the audited helpers (native byte union support, canonical LinksTo),
    # excluding all navigation-specific writers and record copy procedures.
    common=(OUT.parent/'navmesh_patch/DatabaseBoundedNavmeshDraft.pas').read_text(encoding='utf8')
    start=common.index('procedure Need(');end=common.index('function FieldToken(')
    common=common[start:end].replace('BOUNDED_NAVM_STOP: ','PG_TYPED_STOP: ')
    old='  // Exact native numeric comparison, not rounded display strings. Non-record'
    insert="""  if (DefType(a)=dtLString) or (DefType(a)=dtString) or (DefType(a)=dtLenString) then begin
    NeedCompared(GetEditValue(a)=GetEditValue(b),labelText+': resolved text changed',a,b);Exit;
  end;
  NeedCompared(typeA=typeB,labelText+': scalar native Variant type changed',a,b);
"""
    assert old in common;common=common.replace(old,insert+old)
    constants={'EXPECTED_SOURCE_FILE':dest/'expected_sources.txt','ALLOWED_FILES_FILE':dest/'allowed_files.txt',
      'ALLOWED_MESH_FILE':dest/'allowed_meshes.txt','OUTPUT_NAMES_FILE':dest/'output_names.txt','AUDIT_FILE':dest/'audit.tsv'}
    code='unit UserScript;\n// READ ONLY. Generated after a frozen private PG run; no edits/save calls.\nconst\n'
    code+=''.join('  '+k+' = '+q(v)+';\n' for k,v in constants.items())
    code+=f'  EXPECTED_OVERRIDE_COUNT = {len(sources)};\n  EXPECTED_TXST_COUNT = {txsts};\n\n'
    body=(OUT/'pg_metadata_verifier_body.pas').read_text(encoding='utf8')
    # Pascal global var declarations must precede all function declarations.
    i=body.index('function ModelKey(');decl=body[:i];body=body[i:]
    code+=decl+'\n'+common+'\n'+body
    script=dest/'DatabasePGMetadataVerifier.pas';script.write_text(code,encoding='utf8')
    report={'status':'PREPARED_READ_ONLY_XEDIT_VERIFIER_NOT_EXECUTED','xEdit_version':'4.1.5f','run_manifest':str(manifest),'run_manifest_sha256':sha(manifest),
      'script':str(script),'script_sha256':sha(script),'output_inventory_sha256':sha(run/'output_inventory.json'),
      'override_count':len(sources),'new_TXST_count':txsts,'output_plugins':outputs,'source_plugins':source_hashes,
      'sources':sources,'artifacts':{str(p):sha(p) for p in dest.iterdir() if p.is_file()},
      'verification_surface':['All non-model payload recursively exact: canonical resolved FormIDs, native scalars, byte vectors; localized strings compare resolved exact text.',
        'Allowed model changes only filename pointing to an actual emitted NIF; existing alternate-texture subset with original unique3Dname, nonnegative newindex and old/newDB-ownerTXSTcanonicaltarget.',
        'Derived Model Information may be omitted; when retained it must remain exact. No unknown payload skipped.',
        'Headers strict signature/canonicalID/formversion/allflags except storage compression; author VCS changes are audited separately.',
        'DBPatcher owns TXST only; DB_n only existing source overrides; all loaded non-output plugins must be frozen input names; each current source winner name must match independently parsed final order.'],
      'required_after_xEdit':['Check audit.tsv final PASS_METADATA_ONLY matches counts; any exception means reject outputs.',
        'Resolve every TXST_TEXTURE row in actual final resource catalog, all refs valid and provider hashes pinned.',
        'Read emitted NIFs with typed author parser: preserve geometry/skinning, allow only declared renderer shader/material/texture changes, verify every alternate3DIndex maps to actual named output shape.',
        'Do not deploy before private source/output hashes rechecked and final full xEdit error scan passed.'],
      'limits':['Not a native rendering test. Numeric native equality does not claim preservation of serialized negative-zero or NaN bit payload; unsupported scalar/array comparison stops.',
        'This script has not yet been compiled/executed; parent must run in final xEdit4.1.5f and retain actual audit/log.']}
    (dest/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:report[k] for k in ('status','script','script_sha256','override_count','new_TXST_count')},ensure_ascii=True))
if __name__=='__main__':main()
