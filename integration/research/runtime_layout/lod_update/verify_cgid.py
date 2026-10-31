"""Independent bounded CGID parser; never edits caches or runtime data.

Schema is pinned to FasterNGIO 1.6 NgioCacheWriter.{h,cpp} and CellCache.cpp.
It validates structural compatibility, not the game's rendering or collision.
"""
import argparse
import collections
import hashlib
import json
import math
import re
import struct
from pathlib import Path

OUT=Path(__file__).resolve().parent
NAME=re.compile(r'^(.+)x(-?\d+)y(-?\d+)(?:\.(WIN|SPR|SUM|AUT))?\.cgid$',re.I)


def parse(path, strict=True):
    data=Path(path).read_bytes()
    offset=0
    def take(count):
        nonlocal offset
        assert count>=0 and offset+count<=len(data),'Truncated CGID field/payload'
        result=data[offset:offset+count]
        offset+=count
        return result
    def u32():return struct.unpack('<I',take(4))[0]
    count=u32()
    assert count<=4096,'Implausible grass group count'
    groups=[]
    total_blades=0
    for _ in range(count):
        size=u32()
        assert 1<size<=1024,'Invalid model path byte count'
        model=take(size)
        assert model[-1:]==b'\0' and b'\0' not in model[:-1],'Invalid path terminator'
        assert b'..' not in model and b':' not in model and not model.startswith((b'/',b'\\')),'Unsafe/nonrelative model path'
        assert model[:-1].lower().endswith(b'.nif'),'Grass model is not a NIF'
        wave=struct.unpack('<f',take(4))[0]
        assert math.isfinite(wave),'Nonfinite wave period'
        form_id=u32()
        flags=list(take(3))
        assert all(value in (0,1) for value in flags),'Invalid grass shader booleans'
        blocks=u32()
        assert blocks<=65536,'Implausible geometry block count'
        blades=0
        for _ in range(blocks):
            descriptor=take(36)
            values=struct.unpack('<9I',descriptor)
            bounds=struct.unpack('<6f',descriptor[:24])
            assert all(math.isfinite(value) for value in bounds),'Nonfinite geometry bounds'
            assert all(value>=0 for value in bounds[3:]),'Negative geometry extent'
            triangle_count,blade_count,stride=values[6:]
            assert 0<blade_count<=8191,'Invalid/excessive blades per block'
            assert stride==16,'Unexpected instance stride, requires schema investigation'
            take(blade_count*stride*2)
            blades+=blade_count
        total_blades+=blades
        groups.append({'model':model[:-1].decode('utf-8','backslashreplace'),'form_id':f'{form_id:08X}',
                       'wave_period':wave,'flags':flags,'blocks':blocks,'blades':blades})
    if strict:assert offset==len(data),'Trailing unparsed CGID bytes'
    assert count>0 or data==b'\0\0\0\0','Invalid empty-cache encoding'
    repeats=len(data)//offset if len(data)%offset==0 and data==data[:offset]*(len(data)//offset) else None
    return {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'groups':groups,'blades':total_blades,
            'parsed_prefix_bytes':offset,'trailing_bytes':len(data)-offset,'identical_complete_prefix_repetitions':repeats}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('cache',nargs='+')
    parser.add_argument('--output',default=str(OUT/'cgid_verification.json'))
    parser.add_argument('--world',action='append',help='Only these editor IDs may occur; repeated option allowed')
    args=parser.parse_args()
    destination=Path(args.output).resolve()
    assert destination.is_relative_to(OUT),'Report must stay in this research directory'
    files=[]
    for item in args.cache:
        path=Path(item)
        if path.is_dir():
            assert not list(path.rglob('*.fail')),'Generation contains .fail markers'
            files.extend(path.rglob('*.cgid'))
        else:files.append(path)
    assert files,'No cache files'
    results=[]
    worlds=collections.Counter()
    empty=0
    for path in sorted(set(files)):
        match=NAME.match(path.name)
        assert match,f'Unexpected cache filename: {path.name}'
        world=match.group(1)
        if args.world:assert world.lower() in {name.lower() for name in args.world},'Unplanned cache world'
        result=parse(path)
        empty+=not result['groups']
        worlds[world]+=1
        results.append({'path':str(path.resolve()),'world':world,'cell':[int(match.group(2)),int(match.group(3))],
                        'season':match.group(4),**result})
    report={'status':'STRUCTURAL_CGID_PASS_RUNTIME_NOT_TESTED','schema_source':'FasterNGIO 1.6 commit 5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40',
            'files':len(results),'empty_files':empty,'logical_bytes':sum(row['bytes'] for row in results),
            'blades':sum(row['blades'] for row in results),'world_counts':dict(worlds),'results':results,
            'limitations':['Does not validate NIF availability in BSA/loose effective asset winners.',
              'Does not validate positions against final LAND, collision or runtime scripts; retain generator diagnostics and perform source/setting audit.',
              'Does not prove game rendering; game launch remains prohibited.']}
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','files','empty_files','logical_bytes','blades','world_counts')}))


if __name__=='__main__':main()
