"""Record/subrecord three-way audit of the selected donor features; no mutation."""
from pathlib import Path
from datetime import datetime, timezone
import collections
import hashlib
import json
import mmap
import re
import sqlite3
import struct
import sys
import zlib

sys.dont_write_bytecode=True
BASE=Path(r'E:\stock\Skyrim collection\Database')
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'rootcause'))
from plugin_binary import subs
from vmad_audit import parse_vmad

STRINGS={}
STRING_EVIDENCE={}
VMAD_FAILURES={}
DEFS=OUT/'source_4_1_5f/wbDefinitionsTES5.pas'
DEFS_TEXT=DEFS.read_text(encoding='utf-8-sig')
def exact_parameter_forms():
    enum=re.search(r'TCTDAFunctionParamType\s*=\s*\((.*?)\);',DEFS_TEXT,re.S)[1]
    enum=re.sub(r'//[^\n]*|\{.*?\}',' ',enum,flags=re.S)
    names=re.findall(r'\bpt\w+\b',enum)
    start=DEFS_TEXT.index("wbUnion('Parameter #1', wbCTDAParam1Decider")
    start=DEFS_TEXT.index('[',start)+1
    members=[];paren=0;bracket=1;quoted=False;i=start;member=start
    while bracket:
        ch=DEFS_TEXT[i]
        if quoted:
            if ch=="'":
                if DEFS_TEXT[i+1]=="'":i+=1
                else:quoted=False
        elif ch=="'":quoted=True
        elif ch=='(':paren+=1
        elif ch==')':paren-=1
        elif ch=='[':bracket+=1
        elif ch==']':
            bracket-=1
            if not bracket:members.append(DEFS_TEXT[member:i].strip())
        elif ch==',' and bracket==1 and paren==0:
            members.append(DEFS_TEXT[member:i].strip());member=i+1
        i+=1
    assert len(members)==len(names)+1,(len(members),len(names))
    return {name for name,definition in zip(names,members[1:]) if definition.startswith('wbFormID')}
PARAM_FORMS=exact_parameter_forms()
CONDITIONS={}
for m in re.finditer(r'\(Index:\s*(\d+);\s*Name:\s*\x27([^\x27]+)\x27([^)]*)\)',DEFS_TEXT):
    CONDITIONS[int(m[1])]={'name':m[2],**{f'param{n}':t for n,t in re.findall(r'ParamType([123]):\s*(pt\w+)',m[3])}}


def lstring(rec,tag,value):
    if not rec['localized']:
        return value.rstrip(b'\0').decode('utf-8','replace')
    assert len(value)==4,(rec['plugin'],tag,len(value))
    index=struct.unpack('<I',value)[0]
    extension='dlstrings' if tag=='DESC' or rec['signature'] in ('QUST','BOOK') and tag=='CNAM' else 'ilstrings' if rec['signature']=='INFO' and tag!='RNAM' else 'strings'
    key=(Path(rec['plugin']).stem.casefold(),extension)
    if key not in STRINGS:
        name=f'{key[0]}_english.{extension}'
        path=None
        for root in (BASE/'repairs/consistent_stock/Data/Strings',BASE/'xedit_runs/TuLED/Data/Strings'):
            if root.exists():
                path=next((p for p in root.iterdir() if p.name.casefold()==name),None)
                if path:break
        if not path:
            STRINGS[key]={};STRING_EVIDENCE['|'.join(key)]={'missing':name}
        else:
            data=path.read_bytes();count,size=struct.unpack_from('<II',data);offset=8+count*8
            assert offset+size==len(data)
            table={}
            for n in range(count):
                i,off=struct.unpack_from('<II',data,8+n*8);pos=offset+off
                if extension=='strings':end=data.index(0,pos);raw=data[pos:end]
                else:
                    length=struct.unpack_from('<I',data,pos)[0];raw=data[pos+4:pos+4+length].rstrip(b'\0')
                table[i]=raw.decode('utf-8','replace')
            STRINGS[key]=table;STRING_EVIDENCE['|'.join(key)]={'path':str(path),'sha256':hashlib.sha256(data).hexdigest(),'entries':count}
    return STRINGS[key].get(index,f'UNRESOLVED_LSTRING_{index:08X}') if index else ''


def formvalue(rec,value):
    if not value:return 'NULL'
    name,obj=key_for(value,rec['masters'],rec['plugin'])
    return f'{name}|{obj:06X}'


def condition(rec,value,strings=None):
    if len(value)!=32:return {'opaque_sha256':hashlib.sha256(value).hexdigest()}
    flags=value[0];func=struct.unpack_from('<H',value,8)[0];definition=CONDITIONS.get(func,{})
    result={'flags':flags,'comparison':formvalue(rec,struct.unpack_from('<I',value,4)[0]) if flags&4 else value[4:8].hex(),
        'function':func,'function_name':definition.get('name','UNKNOWN')}
    for i,offset in ((1,12),(2,16)):
        typ=definition.get(f'param{i}','ptNone');raw=struct.unpack_from('<I',value,offset)[0]
        if typ in ('ptReference','ptObjectReference','ptActor','ptPackage') and flags&0x0a:typ='ptAliasOrPackdata'
        if typ=='ptVariableName':
            if strings is None:raise ValueError('Typed variable parameter requires its paired CIS context')
            val={'cis_tag':'CIS'+str(i),'cis_bytes':strings.get('CIS'+str(i),b'').hex()}
        else:val=formvalue(rec,raw) if typ in PARAM_FORMS else raw
        result[f'param{i}']={'type':typ,'value':val}
    runon,ref,unknown=struct.unpack_from('<III',value,20)
    result.update(run_on=runon,reference=formvalue(rec,ref) if runon==2 else ref,unknown=unknown)
    return result


SINGLE_REFS={
    'CELL':{'LTMP','XLCN','XCWT','XILL','XCCM','XCAS','XEZN','XCMO','XCIM','XOWN','XGLB'},
    'INFO':{'TPIC','PNAM','TCLT','DNAM','SNAM','LNAM','ANAM','TWAT','ONAM'},
    'DIAL':{'QNAM','BNAM'},
    'ARMA':{'RNAM','NAM0','NAM1','NAM2','NAM3','SNDD','ONAM','MODL'},
    'HDPT':{'HNAM','CNAM','TNAM','RNAM'},
    'REFR':{'NAME','XLRL','XLCN','XEZN','XOWN','XGLB'},
    'ACHR':{'NAME','XLRL','XLCN','XEZN','XOWN','XGLB'},
}


def condition_groups(rec):
    result={};current=None
    for index,(tag,value) in enumerate(rec['fields']):
        if tag=='CTDA':
            current={'raw':value,'strings':{},'field_index':index};result[index]=current
        elif tag in ('CIS1','CIS2') and current is not None:
            if tag in current['strings']:raise ValueError('Duplicate CIS subrecord inside a single CTDA group')
            current['strings'][tag]=value
        else:current=None
    return result


def candidate_condition_storage_issues(rec):
    issues=[]
    for group in condition_groups(rec).values():
        value=group['raw']
        if len(value)!=32:continue
        fn=struct.unpack_from('<H',value,8)[0];definition=CONDITIONS.get(fn,{})
        for number,offset in ((1,12),(2,16)):
            if definition.get('param'+str(number))!='ptVariableName':continue
            cis='CIS'+str(number)
            if struct.unpack_from('<I',value,offset)[0]!=0:issues.append({'function':fn,'parameter':number,'reason':'Typed copied variable U32 storage must normalize to zero','raw':value[offset:offset+4].hex()})
            if cis not in group['strings']:issues.append({'function':fn,'parameter':number,'reason':'Paired CIS string is absent'})
    return issues


def candidate_editor_metadata_issues(rec):
    if rec['signature']!='DIAL':return []
    return [{'tag':tag,'reason':'Exact xEdit4.1.5f editor-only INOM/INOA metadata must never be serialized'}
            for tag,value in rec['fields'] if tag in ('INOM','INOA')]


def canonical(rec):
    if rec is None:return {}
    result=collections.defaultdict(list);sig=rec['signature'];groups=condition_groups(rec)
    for field_index,(tag,value) in enumerate(rec['fields']):
        if sig=='DIAL' and tag=='TIFC':continue  # xEdit cpIgnore generated count
        if sig=='WRLD' and tag in ('OFST','RNAM'):continue  # exact 4.1.5f no-copy tables; MHDT remains strict
        if sig=='CELL' and tag=='XCLW' and dict(rec['fields']).get('DATA',b'\0')[0]&1:continue  # xEdit cpIgnore for interiors
        if tag=='FULL' or sig=='INFO' and tag in ('NAM1','RNAM'):
            v={'text':lstring(rec,tag,value)}
        elif sig=='CELL' and tag=='XCLC':
            v={'coordinates':list(struct.unpack_from('<ii',value)),'land_flags':value[8] if len(value)>8 else 0}
        elif sig=='CELL' and tag=='XCLR':
            v=sorted(formvalue(rec,i[0]) for i in struct.iter_unpack('<I',value))
        elif sig=='FLST' and tag=='LNAM':
            v=formvalue(rec,struct.unpack('<I',value)[0])
        elif sig=='LCTN' and tag in ('ACSR','LCSR'):
            assert len(value)%16==0
            for offset in range(0,len(value),16):
                result['$SPECIAL_REFS'].append([*[formvalue(rec,x) for x in struct.unpack_from('<III',value,offset)],*struct.unpack_from('<hh',value,offset+12)])
            continue
        elif sig=='LCTN' and tag in ('ACUN','LCUN'):
            assert len(value)%12==0
            for offset in range(0,len(value),12):
                result['$UNIQUE_NPCS'].append([formvalue(rec,x) for x in struct.unpack_from('<III',value,offset)])
            continue
        elif tag=='CTDA':v=condition(rec,value,groups[field_index]['strings'])
        elif tag in SINGLE_REFS.get(sig,set()) and len(value)==4:
            v={'form':formvalue(rec,struct.unpack('<I',value)[0])}
        elif tag=='XESP' and sig in ('REFR','ACHR') and len(value)==8:
            parent=struct.unpack_from('<I',value)[0];v={'parent':formvalue(rec,parent),'flags':value[4]}
        elif tag=='VMAD':
            try:
                parsed=parse_vmad(value,lambda fid:formvalue(rec,fid))
                v={'scripts':parsed['scripts'],'tail_hex':parsed['tail_hex']}
            except (ValueError,AssertionError,struct.error,IndexError) as exc:
                v={'opaque_sha256':hashlib.sha256(value).hexdigest(),'parse_error':str(exc)}
                VMAD_FAILURES[rec['path']+'|'+f"{rec['fid']:08X}"]=str(exc)
        elif sig=='ARMA' and tag in ('BODT','BOD2'):
            v={'slots':struct.unpack_from('<I',value)[0],'armor_type':struct.unpack_from('<I',value,8 if tag=='BODT' else 4)[0],
                'general_flags':value[4] if tag=='BODT' else 0};tag='$BIPED'
        elif sig=='ARMA' and tag in ('MO2T','MO3T','MODT'):
            # Model texture cache bytes are kept as explicit caches, never called gameplay-equivalent here.
            v={'cache_sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)}
        elif len(value)>2048:v={'opaque_sha256':hashlib.sha256(value).hexdigest(),'bytes':len(value)}
        else:v={'hex':value.hex()}
        result[tag].append(v)
    for name in ('$SPECIAL_REFS','$UNIQUE_NPCS'):
        if name in result:result[name].sort(key=str)
    if sig=='FLST' and 'LNAM' in result:result['LNAM'].sort()
    if sig=='ARMA' and 'MODL' in result:result['MODL'].sort(key=str)
    result['$FLAGS']=[rec['flags']]
    return dict(result)


def canonical_diff(a,b):
    aa=canonical(a);bb=canonical(b)
    return [{'field':tag,'a':aa.get(tag),'b':bb.get(tag)} for tag in sorted(set(aa)|set(bb)) if aa.get(tag)!=bb.get(tag)]


def j(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def header(path):
    with Path(path).open('rb') as f:
        raw=f.read(24);data=f.read(struct.unpack_from('<I',raw,4)[0])
    fields=subs(data)
    return [v.rstrip(b'\0').decode('utf-8','replace') for k,v in fields if k=='MAST']


def key_for(fid,masters,name):
    index=fid>>24
    return ((masters[index] if index<len(masters) else name).casefold(),fid&0xffffff)


def scan(path,wanted=None,overrides_only=False):
    path=Path(path);masters=header(path);records={};counts=collections.Counter();own=collections.Counter()
    with path.open('rb') as f, mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ) as data:
        localized=bool(struct.unpack_from('<I',data,8)[0]&0x80)
        pos=0;stack=[]
        while pos<len(data):
            while stack and pos>=stack[-1][0]:stack.pop()
            sig=data[pos:pos+4].decode('ascii');size=struct.unpack_from('<I',data,pos+4)[0]
            if sig=='GRUP':
                label,kind=struct.unpack_from('<Ii',data,pos+8);stack.append((pos+size,label,kind));pos+=24;continue
            flags,fid=struct.unpack_from('<II',data,pos+8)
            if sig!='TES4':
                key=key_for(fid,masters,path.name);counts[sig]+=1
                if fid>>24>=len(masters):own[sig]+=1
                if (wanted is None or key in wanted) and (not overrides_only or fid>>24<len(masters)):
                    body=data[pos+24:pos+24+size]
                    if flags&0x40000:
                        n=struct.unpack_from('<I',body)[0];body=zlib.decompress(body[4:]);assert len(body)==n
                    groups=[]
                    for _,label,kind in stack:
                        groups.append((kind,key_for(label,masters,path.name) if kind in (1,6,7,8,9,10) else label))
                    records[key]={'signature':sig,'fid':fid,'flags':flags&~0x40000,
                        'offset':pos,'fields':subs(body),'groups':groups,'path':str(path),'plugin':path.name,'masters':masters,'localized':localized}
            pos+=24+size
        assert pos==len(data)
    return records,dict(counts),dict(own)


def diff(a,b):
    aa=collections.defaultdict(list);bb=collections.defaultdict(list)
    for k,v in a['fields'] if a else []:aa[k].append(v)
    for k,v in b['fields'] if b else []:bb[k].append(v)
    out=[]
    for tag in sorted(set(aa)|set(bb)):
        for i in range(max(len(aa[tag]),len(bb[tag]))):
            x=aa[tag][i] if i<len(aa[tag]) else None;y=bb[tag][i] if i<len(bb[tag]) else None
            if x!=y:
                out.append({'field':tag,'occurrence':i,'a_bytes':len(x) if x is not None else None,
                    'b_bytes':len(y) if y is not None else None,'a_hex':x.hex() if x is not None and len(x)<2048 else None,
                    'b_hex':y.hex() if y is not None and len(y)<2048 else None,
                    'a_sha256':hashlib.sha256(x).hexdigest() if x is not None else None,
                    'b_sha256':hashlib.sha256(y).hexdigest() if y is not None else None})
    if a and b and a['flags']!=b['flags']:out.append({'field':'$FLAGS','a_flags':a['flags'],'b_flags':b['flags']})
    return out


def meta(rec):
    if not rec:return None
    return {k:v for k,v in rec.items() if k!='fields'}|{'edid':next((v.rstrip(b'\0').decode('utf-8','replace') for k,v in rec['fields'] if k=='EDID'),'')}


def main():
    profile=BASE/'UnifiedSkyrim/profiles/Unified Skyrim'
    before={n:digest(profile/n) for n in ['modlist.txt','plugins.txt','loadorder.txt']}
    active={s[1:].casefold() for s in (profile/'plugins.txt').read_text(encoding='utf-8-sig').splitlines() if s.startswith('*')}
    disabled={n.casefold() for n in j(BASE/'integration/research/base_diagnostics/recommended_actions.json')['disabled_plugin_union']}
    generated={'synthesis - patch.esp','dyndolod.esm','dyndolod.esp','occlusion.esp'}
    loadorder=[s for s in (profile/'loadorder.txt').read_text(encoding='utf-8-sig').splitlines() if s and not s.startswith('#')]
    positions={n.casefold():i for i,n in enumerate(loadorder)}
    active|={'skyrim.esm','update.esm','dawnguard.esm','hearthfires.esm','dragonborn.esm'}
    selected=j(BASE/'integration/research/plugin_integration/feature_builder_manifest.json')
    features=[]
    for group in ('features','followers'):
        for feature in selected[group]:
            if feature['feature'] in ('Glenmoril','Moon and Star'):continue
            for plugin in feature['plugins']:
                path=plugin['validated_replacement']['candidate'] if plugin.get('validated_replacement') else plugin['source_path']
                records,counts,own=scan(path,overrides_only=True)
                features.append({'feature':feature['feature'],'plugin':plugin['name'],'path':path,'sha256':digest(path),
                    'record_counts':counts,'own_counts':own,'overrides':records})
    keys=set().union(*(set(f['overrides']) for f in features))
    stock={};official={}
    for name in ['Skyrim.esm','Update.esm','Dawnguard.esm','HearthFires.esm','Dragonborn.esm']:
        path=BASE/'repairs/consistent_stock/Data'/name
        rs,_,_=scan(path,wanted=keys)
        for key,r in rs.items():
            r['load_position']=positions.get(name.casefold(),-1);official[key]=r
            if key[0]==name.casefold():stock[key]=r
    c=sqlite3.connect((BASE/'baseline/plugin_records.sqlite').as_uri()+'?mode=ro',uri=True)
    origin_ids={n:i for i,n in c.execute('select id,name_key from origins')}
    base_candidates=collections.defaultdict(list)
    providers={}
    for key in keys:
        for pid,pname,path,offset in c.execute('''select p.id,p.name,p.path,r.byte_offset from records r
            join plugins p on p.id=r.plugin_id where r.pack_id=3 and r.origin_id=? and r.object_id=?''',(origin_ids.get(key[0],-1),key[1])):
            n=pname.casefold()
            if n not in active or n in disabled or n in generated or n in ('skyrim.esm','update.esm','dawnguard.esm','hearthfires.esm','dragonborn.esm'):continue
            providers[n]=(pname,path);base_candidates[key].append(n)
    base_records={}
    for name,(pname,path) in providers.items():
        wanted={k for k,names in base_candidates.items() if name in names}
        rs,_,_=scan(path,wanted=wanted)
        for k,r in rs.items():
            r['load_position']=positions.get(name,-1)
            if k not in base_records or r['load_position']>base_records[k]['load_position']:base_records[k]=r
    for k,r in official.items():
        if k not in base_records:base_records[k]=r
    output=[]
    for f in features:
        entries=[]
        for k,rec in sorted(f['overrides'].items()):
            v=stock.get(k);b=base_records.get(k)
            dv=diff(v,rec);db=diff(v,b);sb=diff(b,rec)
            cv=canonical_diff(v,rec) if rec['signature']!='NAVI' else []
            cb=canonical_diff(v,b) if rec['signature']!='NAVI' else []
            cs=canonical_diff(b,rec) if rec['signature']!='NAVI' else []
            changed_source={r['field'] for r in cv};changed_base={r['field'] for r in cb}
            conflict_fields=sorted(changed_source&changed_base&{r['field'] for r in cs})
            flag_analysis=None
            if v and b:
                source_mask=v['flags']^rec['flags'];base_mask=v['flags']^b['flags']
                flag_analysis={'source_changed_mask':source_mask,'base_changed_mask':base_mask,'overlapping_mask':source_mask&base_mask,
                    'merged_flags':(b['flags']&~source_mask)|(rec['flags']&source_mask)}
                if '$FLAGS' in conflict_fields and not source_mask&base_mask:conflict_fields.remove('$FLAGS')
            entry={'origin':k[0],'object_id':f'{k[1]:06X}','signature':rec['signature'],
                'feature_record':meta(rec),'vanilla_record':meta(v),'base_record':meta(b),
                'source_from_vanilla':dv,'base_from_vanilla':db,'source_vs_base':sb,
                'field_overlap':sorted({r['field'] for r in dv}&{r['field'] for r in db}),
                'canonical_source_from_vanilla':cv,'canonical_base_from_vanilla':cb,'canonical_source_vs_base':cs,
                'canonical_conflicting_fields':conflict_fields,
                'flag_bit_analysis':flag_analysis,
                'classification':'source-raw-ITM' if v and not dv else 'feature-introduces-base-absent-record' if not v else 'source-and-base-raw-identical' if b and not sb else 'needs-semantic-field-review'}
            entries.append(entry)
        output.append({k:v for k,v in f.items() if k!='overrides'}|{'override_records':entries})
    after={n:digest(profile/n) for n in before}
    report={'written_utc':datetime.now(timezone.utc).isoformat(),'profile':str(profile),'profile_hashes_before':before,'profile_hashes_after':after,
        'profile_unchanged_while_reading':before==after,'coherent_stock':str(BASE/'repairs/consistent_stock/Data'),
        'disabled_original_plugins':sorted(disabled),'excluded_rebuilt_generated_plugins':sorted(generated),
        'note':'Raw and limited typed canonical differences are preserved. Canonical normalizes English localized strings, documented CELL XCLC unused bytes, region/race-list sorting, LCTN added/master reference arrays, CTDA typed arguments and listed FormID fields. Exact xEdit 4.1.5f schema applies: WRLD MHDT is strict and retained in canonical comparisons. Only WRLD RNAM/OFST no-copy tables, DIAL TIFC and interior CELL XCLW documented derived values are excluded. NAVI requires its own entry/geometry audit. Group VC stamps are excluded. All record data is read-only.',
        'schema_source':{'TES5':str(DEFS),'TES5_sha256':digest(DEFS),'provenance':str(OUT/'source_4_1_5f/provenance.json'),'cell_grid':str(OUT/'source_4_1_5f/wbDefinitionsCommon.pas'),'cell_grid_lines':[495,519],'MHDT':{'path':str(DEFS),'lines':[5189,5219],'rule':'Strict; this tag has no no-copy flag in xedit-4.1.5f'}},
        'localization_sources':STRING_EVIDENCE,
        'vmad_parse_failures':VMAD_FAILURES,
        'features':output}
    (OUT/'raw_field_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for f in output:
        print(f['plugin'],'own',sum(f['own_counts'].values()),'overrides',len(f['override_records']))
        for r in f['override_records']:
            print(r['signature'],r['origin'],r['object_id'],r['classification'],
                  'source',','.join(sorted({z['field'] for z in r['canonical_source_from_vanilla']})),
                  'base',r['base_record']['plugin'] if r['base_record'] else '-',','.join(sorted({z['field'] for z in r['canonical_base_from_vanilla']})),
                  'conflict',','.join(r['canonical_conflicting_fields']))
    c.close()


if __name__=='__main__':main()
