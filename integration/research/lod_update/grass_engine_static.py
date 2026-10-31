"""Read-only static 1.5.97 cache reader inspection, never executes game code."""
import bisect
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
DB=OWN.parents[2]
SPEC=importlib.util.spec_from_file_location('material_static',OWN.parent/'supplemental_import/inspect_material_engine.py')
M=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(M)
import capstone

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--exe');parser.add_argument('--name',default='grass_engine_static');args=parser.parse_args()
    assert args.name.replace('_','').isalnum()
    library=DB/'UnifiedSkyrim/mods/T4172 Address Library for SKSE Plugins/SKSE/Plugins/version-1-5-97-0.bin'
    mapping,meta=M.address_library(library)
    exe=Path(args.exe) if args.exe else DB/'UnifiedSkyrim/Game/SkyrimSE.exe';data=exe.read_bytes()
    pe=struct.unpack_from('<I',data,0x3c)[0];opt=pe+24
    image=struct.unpack_from('<Q',data,opt+24)[0]
    n=struct.unpack_from('<H',data,pe+6)[0];opts=struct.unpack_from('<H',data,pe+20)[0]
    sections=[]
    for i in range(n):
        p=opt+opts+40*i;vs,rva,rs,raw=struct.unpack_from('<IIII',data,p+8)
        sections.append((rva,rva+max(vs,rs),raw))
    def off(rva):
        for s,e,o in sections:
            if s<=rva<e:return o+rva-s
        raise ValueError(hex(rva))
    er,es=struct.unpack_from('<II',data,opt+112+24)
    funcs=[struct.unpack_from('<III',data,p) for p in range(off(er),off(er)+es,12)]
    starts=[f[0] for f in funcs];md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_64)
    inverse={v:k for k,v in mapping.items()}
    def function(rva):
        i=bisect.bisect_right(starts,rva)-1
        s,e,_=funcs[i] if i>=0 and funcs[i][0]<=rva<funcs[i][1] else (rva,rva+128,0)
        code=data[off(s):off(s)+e-s];lines=[]
        for ins in md.disasm(code,image+s):
            row={'rva':f'{ins.address-image:08X}','instruction':ins.mnemonic+' '+ins.op_str}
            if ins.mnemonic in ('call','jmp') and ins.op_str.startswith('0x'):
                dest=int(ins.op_str,16)-image
                if dest in inverse:row['target_library_id']=inverse[dest]
                row['target_rva']=f'{dest:08X}'
            lines.append(row)
        return {'address_library_id':inverse.get(s),'start_rva':f'{s:08X}','end_rva':f'{e:08X}',
                'sha256':hashlib.sha256(code).hexdigest(),'instructions':lines}
    chosen=[15204,15206,74601,74600,74602,74621]
    report={'game_path':str(exe),'game_sha256':hashlib.sha256(data).hexdigest(),
            'address_library_sha256':hashlib.sha256(library.read_bytes()).hexdigest(),'address_library':meta,
            'functions':[function(mapping[i]) for i in chosen if i in mapping]}
    # Also collect direct callees, deduplicated, so source field reads can be traced.
    targets={int(x['target_rva'],16) for f in report['functions'] for x in f['instructions'] if 'target_rva' in x}
    report['direct_callees']=[function(v) for v in sorted(targets) if any(s<=v<e for s,e,_ in sections)]
    (OWN/(args.name+'.json')).write_text(json.dumps(report,indent=2)+'\n')
    print([(f['address_library_id'],f['start_rva'],len(f['instructions'])) for f in report['functions']])
if __name__=='__main__':main()
