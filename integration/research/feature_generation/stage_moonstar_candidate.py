"""Stage the existing author tool and exactly two private MoonAndStar mesh candidates."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    root=OUT/'moonstar_conversion';root.mkdir(exist_ok=True);tool=root/'tool';assert not tool.exists(),'Preserve previous staged author tool'
    source=DB.parent/'TuLED/Tool/Cathedral Assets Optimizer';copied=[];omitted=[]
    for p in source.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(source)
        if p.name.startswith('___temp') or p.suffix.lower() in ('.log','.pdb') or p.name.lower() in ('settings.ini','settings.json'):
            omitted.append(str(rel));continue
        q=tool/rel;q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q);assert q.stat().st_nlink==1 and sha(p)==sha(q)
        copied.append({'relative':str(rel),'source':str(p),'private_path':str(q),'sha256':sha(q),'bytes':q.stat().st_size})
    inputs=[]
    for name in ('wg_0.nif','wg_1.nif'):
        p=OUT/'nif_errors'/name;data=p.read_bytes();n=data.index(b'\n')+1;assert struct.unpack_from('<I',data,n+13)[0]==82
        paths={}
        for branch in ('originals','candidate'):
            q=root/branch/'meshes/mwl'/name;q.parent.mkdir(parents=True,exist_ok=True);q.write_bytes(data);assert q.stat().st_nlink==1;paths[branch]=str(q)
        inputs.append({'member':'meshes/mwl/'+name,'source_sha256':sha(p),'bytes':len(data),'BS_version':82,**paths})
    report={'status':'PRIVATE_TWO_FILE_AUTHOR_TOOL_CANDIDATE_STAGED_NOT_EXECUTED','tool':str(tool/'Cathedral_Assets_Optimizer.exe'),'tool_files':copied,'omitted_old_work_files':omitted,
        'input_directory':str(root/'candidate'),'input_files':inputs,'source_evidence':str(OUT/'moonstar_legacy_nif_consumers.json'),
        'GUI_actions_for_parent':['Launch only this private CAO copy with cwd=its own tool folder and TEMP/TMP/APPDATA/LOCALAPPDATA under moonstar_conversion/sandbox.',
            'Explicitly choose candidate directory above before processing; never accept a remembered source-pack/game Data path.',
            'Use Skyrim Special Edition mesh conversion to stream100. Process ordinary skinned meshes, not head parts; limit scan to the two candidate files.',
            'Disable BSA, textures and animations. Do not repack or process the MoonAndStar archive. Preserve original branch and every tool log.',
            'If necessary optimization skips these version82 files, a private full mesh optimization/resave candidate may be tried; if author tool reports unsupported version, STOP. Never force-edit only the header.',
            'Do not deploy until both resulting NIFs reparse as SSE100 and skeleton/bone weights/shape counts/triangles/texture references are compared against originals; unexpected geometry/material/bone loss rejects candidate.'],
        'execution_limits':['The source-provided SSE NIF Optimizer /opt path still shows a GUI in OnInit; this agent did not invoke it or CAO.',
            'Version82 is outside the expected83/100 schema of the static audit; that observation alone does not prove an in-game crash.',
            'This private folder is a review candidate, not a converted or runtime-verified fix.']}
    (root/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(report['tool'],len(copied),'files',sum(r['bytes'] for r in copied),'bytes')
if __name__=='__main__':main()
