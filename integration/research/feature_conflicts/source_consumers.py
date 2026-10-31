"""Read-only typed consumers within the three donor follower plugins."""
from pathlib import Path
import collections
import json
import struct
from analyze_fields import BASE, OUT, canonical, digest, formvalue, key_for, scan
from vmad_audit import parse_vmad


def main():
    audit=json.loads((OUT/'raw_field_comparison.json').read_text(encoding='utf-8'))
    result=[]
    for plugin in ('SofiaFollower.esp','HothFollower.esp','BenDoonSSE.esp'):
        info=next(p for p in audit['features'] if p['plugin']==plugin)
        targets={f"{r['origin']}|{r['object_id']}" for r in info['override_records'] if r['signature'] in ('ACHR','REFR')}
        if plugin=='SofiaFollower.esp':targets.add('skyrim.esm|09845C')
        all_records,_,_=scan(info['path'])
        consumers=[];errors=[]
        for rec in all_records.values():
            alias=None;alias_name=None
            context={'consumer':formvalue(rec,rec['fid']),'signature':rec['signature'],
                'edid':next((v.rstrip(b'\0').decode('utf-8','replace') for k,v in rec['fields'] if k=='EDID'),'')}
            for tag,value in rec['fields']:
                if tag=='ALST' and len(value)==4:alias=struct.unpack('<I',value)[0]
                if tag=='ALID':alias_name=value.rstrip(b'\0').decode('utf-8','replace')
                if tag in ('ALFR','ALPC','PKID') and len(value)==4:
                    target=formvalue(rec,struct.unpack('<I',value)[0])
                    if target in targets:consumers.append(context|{'field':tag,'target':target,'alias_id':alias,'alias_name':alias_name})
                elif tag=='NAME' and rec['signature'] in ('ACHR','REFR') and len(value)==4:
                    target=formvalue(rec,struct.unpack('<I',value)[0])
                    if target in targets:consumers.append(context|{'field':tag,'target':target})
                elif tag=='VMAD':
                    try:
                        parsed=parse_vmad(value,lambda fid:formvalue(rec,fid))
                        for ref in parsed['references']:
                            if ref['form'] in targets:consumers.append(context|{'field':'VMAD','target':ref['form'],'property':ref})
                    except (AssertionError,ValueError,struct.error,IndexError) as exc:
                        errors.append(context|{'error':str(exc)})
        summarized={target:[r for r in consumers if r['target']==target] for target in sorted(targets)}
        result.append({'plugin':plugin,'path':info['path'],'sha256':digest(info['path']),
            'target_consumers':summarized,'vmad_parse_errors':errors,
            'scope':'Within-source typed PKID/ALFR/ALPC/VMAD references. Not a complete final xEdit reference graph or Papyrus dynamic lookup proof.'})
    (OUT/'follower_source_consumers.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for r in result:
        print(r['plugin'],'targets',len(r['target_consumers']),'with consumers',sum(bool(v) for v in r['target_consumers'].values()),'VMAD errors',len(r['vmad_parse_errors']))
        if r['plugin']=='SofiaFollower.esp':print('Sofia global PACK consumers',json.dumps(r['target_consumers']['skyrim.esm|09845C'],ensure_ascii=False))
        for key,values in r['target_consumers'].items():
            if values and key!='skyrim.esm|09845C':print(key,[(v['signature'],v['edid'],v['field'],v.get('property',{}).get('property')) for v in values])


if __name__=='__main__':main()
