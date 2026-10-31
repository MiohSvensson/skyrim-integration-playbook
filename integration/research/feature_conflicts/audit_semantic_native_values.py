"""Audit exact CIS variable storage and typed floating fields in all seeds."""
from pathlib import Path
import collections
import hashlib
import json
import math
import struct
import sys

sys.dont_write_bytecode = True
from analyze_fields import OUT, CONDITIONS, scan
from vmad_audit import parse_vmad


def main():
    priority=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    quest=json.loads((OUT/'quest_extension_plan.json').read_text(encoding='utf-8'))
    wanted=collections.defaultdict(set)
    for s in priority['priority_seed_records']:
        wanted[s['base_path']].add((s['origin'],int(s['object_id'],16)))
    for s in quest['rows']:
        wanted[s['seed_path']].add((s['origin'],int(s['object_id'],16)))
    paths={g['filename'].casefold():g['path'] for g in priority['input_file_guards']+quest['input_file_guards']}
    for s in priority['typed_field_operations']:
        origin,object_id=s['record'].split('|')
        wanted[paths[s['source'].casefold()]].add((origin,int(object_id,16)))
    for s in quest['rows']:
        if s['field_source']:wanted[paths[s['field_source'].casefold()]].add((s['origin'],int(s['object_id'],16)))
    wanted[paths['sofiafollower.esp']].update({('sofiafollower.esp',0xAA58),('skyrim.esm',0x9845C)})
    variable_cases=[]; float_counts=collections.Counter(); float_special=[]
    for path,keys in wanted.items():
        parsed=scan(path,wanted=keys)[0]
        for key,r in parsed.items():
            scope={'record':f'{key[0]}|{key[1]:06X}','signature':r['signature'],'provider':r['plugin'],'path':path}
            condition=None;groups=[]
            for tag,value in r['fields']:
                if tag=='CTDA':
                    condition={'raw':value,'strings':{}};groups.append(condition)
                elif tag in ('CIS1','CIS2') and condition is not None:
                    assert tag not in condition['strings'];condition['strings'][tag]=value
                else:condition=None
                offsets=[]
                if r['signature'] in ('REFR','ACHR') and tag=='DATA' and len(value)==24:offsets=range(0,24,4)
                elif r['signature'] in ('REFR','ACHR') and tag=='XSCL' and len(value)==4:offsets=[0]
                elif r['signature']=='CELL' and tag=='XCLW' and len(value)==4:offsets=[0]
                elif tag=='CTDA' and len(value)==32 and not value[0]&4:offsets=[4]
                elif r['signature']=='WRLD' and tag=='DNAM' and len(value)==8:offsets=[0,4]
                elif r['signature']=='WRLD' and tag in ('NAM0','NAM9') and len(value)==8:offsets=[0,4]
                for off in offsets:
                    raw=value[off:off+4];bits=int.from_bytes(raw,'little');f=struct.unpack('<f',raw)[0]
                    kind='finite'
                    if math.isnan(f):kind='NaN'
                    elif math.isinf(f):kind='Infinity' if f>0 else '-Infinity'
                    elif bits==0x80000000:kind='negative_zero'
                    elif bits&0x7f800000==0 and bits&0x7fffff:kind='subnormal'
                    elif bits in (0x7f7fffff,0xff7fffff):kind='MaxSingle_sentinel'
                    float_counts[kind]+=1
                    if kind!='finite':float_special.append(scope|{'field':tag,'offset':off,'raw':raw.hex(),'value_repr':repr(f),'kind':kind})
                if tag=='VMAD':
                    vmad=parse_vmad(value,lambda fid:f'{fid:08X}')
                    for script in vmad['scripts']:
                        for prop in script['properties']:
                            items=[prop['value']] if prop['type']==4 else prop['value'] if prop['type']==14 else []
                            for index,item in enumerate(items):
                                bits=item['float_bits'];raw=struct.pack('<I',bits);f=struct.unpack('<f',raw)[0];kind='finite'
                                if math.isnan(f):kind='NaN'
                                elif math.isinf(f):kind='Infinity' if f>0 else '-Infinity'
                                elif bits==0x80000000:kind='negative_zero'
                                elif bits&0x7f800000==0 and bits&0x7fffff:kind='subnormal'
                                elif bits in (0x7f7fffff,0xff7fffff):kind='MaxSingle_sentinel'
                                float_counts[kind]+=1
                                if kind!='finite':float_special.append(scope|{'field':'VMAD','script':script['name'],'property':prop['name'],'index':index,'raw':raw.hex(),'value_repr':repr(f),'kind':kind})
            for index,g in enumerate(groups):
                raw=g['raw'];fn=struct.unpack_from('<H',raw,8)[0];d=CONDITIONS.get(fn,{})
                for number,off in ((1,12),(2,16)):
                    if d.get('param'+str(number))!='ptVariableName':continue
                    cis='CIS'+str(number);string=g['strings'].get(cis)
                    variable_cases.append(scope|{'condition_index':index,'function':fn,'function_name':d['name'],'parameter':number,
                        'raw_CTDA':raw.hex(),'raw_parameter':raw[off:off+4].hex(),'native_storage_uint32':struct.unpack_from('<I',raw,off)[0],
                        'cis_tag':cis,'cis_present':string is not None,'cis_raw_hex':string.hex() if string is not None else None,
                        'cis_text_utf8':string.rstrip(b'\0').decode('utf-8','replace') if string is not None else None})
    functions={str(n):[{'function':i,'name':d['name']} for i,d in sorted(CONDITIONS.items()) if d.get('param'+str(n))=='ptVariableName'] for n in (1,2)}
    result={'sources':[{ 'path':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),'records':len(ks)} for p,ks in wanted.items()],
        'CTDA_variable_function_parameters':functions,'CTDA_variable_cases':variable_cases,
        'typed_float_scope':'All priority/quest base and typed-field donor records plus Sofia full quest/clone PACK: REFR/ACHR DATA and XSCL; CELL XCLW; non-global CTDA comparison; WRLD DNAM/NAM0/NAM9; all parsed VMAD float/float-array properties. Only exact typed fields, not arbitrary 4byte windows.',
        'typed_float_class_counts':dict(float_counts),'typed_float_special_values':float_special,
        'limits':'Source-only audit, not an xEdit run. Other typed float definitions and VMAD float properties remain covered by strict builder and full native check, not guessed from arbitrary integer bytes.'}
    (OUT/'semantic_native_value_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('CTDA variable cases',len(variable_cases),'all CIS present',all(r['cis_present'] for r in variable_cases),'float classes',dict(float_counts))
    print('0B1231',[(x['function'],x['raw_parameter'],x['cis_text_utf8']) for x in variable_cases if x['record']=='skyrim.esm|0B1231'])


if __name__=='__main__':main()
