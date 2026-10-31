"""Bounded CGID identity normalization; defaults to planning, never edits a source.

Only a parent-reviewed --materialize invocation creates private overlay files.
Each source stream is independently parsed to EOF; every byte other than its
documented four-byte grassFormID fields remains identical.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import sys
from datetime import datetime,timezone
sys.dont_write_bytecode=True
from runtime_common import OUT,DB,owned,sha
from audit_grass_identity import norm

def streams(data):
    p=0;result=[]
    def take(n):
        nonlocal p
        assert n>=0 and p+n<=len(data),'Truncated cache field'
        b=data[p:p+n];p+=n;return b
    def u32():return struct.unpack('<I',take(4))[0]
    while p<len(data):
        start=p;count=u32();assert count<=4096,'Implausible group count'
        groups=[]
        for _ in range(count):
            size=u32();assert 1<size<=1024
            model=take(size);assert model[-1:]==b'\0' and b'\0' not in model[:-1]
            assert model[:-1].lower().endswith(b'.nif') and not any(x in model for x in (b'..',b':'))
            wave=struct.unpack('<f',take(4))[0];assert math.isfinite(wave)
            offset=p;fid=u32();flags=take(3);assert all(x in (0,1) for x in flags)
            blocks=u32();assert blocks<=65536;blades=0
            for b in range(blocks):
                descriptor=take(36);bounds=struct.unpack('<6f',descriptor[:24]);assert all(math.isfinite(x) for x in bounds) and all(x>=0 for x in bounds[3:])
                _,bc,stride=struct.unpack_from('<3I',descriptor,24);assert 0<bc<=8191 and stride==16
                take(bc*stride*2);blades+=bc
            groups.append({'model':model[:-1].decode('utf-8'),'form_id':f'{fid:08X}','offset':offset,'blades':blades,'blocks':blocks})
        result.append({'start':start,'end':p,'groups':groups})
    assert p==len(data)
    return result

def mask_sha(data,offsets):
    h=hashlib.sha256();p=0
    for offset in sorted(offsets):
        assert p<=offset and offset+4<=len(data)
        h.update(data[p:offset]);h.update(b'\0\0\0\0');p=offset+4
    h.update(data[p:]);return h.hexdigest()

def plan():
    audit_path=OUT/'grass_identity_audit.json';audit=json.loads(audit_path.read_text(encoding='utf-8'))
    final=audit['final_GRAS'];plugins={p['name_key']:p for p in audit['final_plugins']}
    original=audit['source_profiles']['TuLED']['GRAS'];index=collections.defaultdict(list)
    for ident,g in final.items():
        owner,obj=ident.split('|');kind=plugins[owner]['kind'];low=int(obj,16)&(0xFFF if kind=='light' else 0xFFFFFF)
        index[(kind,low,norm(g['model']))].append(g)
    files=[];errors=[];identities={};prefixes=collections.defaultdict(set);counts=collections.Counter()
    for entry in audit['results']:
        source=Path(entry['path']);data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==entry['sha256'],'Source drift'
        parsed=streams(data);edits=[];first_blades=0
        for sn,stream in enumerate(parsed):
            seen={}
            for gn,g in enumerate(stream['groups']):
                fid=int(g['form_id'],16);kind='light' if fid>>24==0xFE else 'full';low=fid&(0xFFF if kind=='light' else 0xFFFFFF)
                matches=index.get((kind,low,norm(g['model'])),[])
                if len(matches)!=1:
                    errors.append({'path':str(source),'stream':sn,'group':gn,'cached':g,'matches':[m['canonical'] for m in matches]});continue
                target=matches[0];ident=target['canonical'];old=original.get(ident)
                if old is None or old['payload_sha256']!=target['payload_sha256']:
                    errors.append({'path':str(source),'canonical':ident,'error':'Original/final GRAS payload differs or missing'});continue
                if target['runtime_id'] in seen:
                    errors.append({'path':str(source),'stream':sn,'error':'Normalization would collide two groups in one stream','canonical':ident,'earlier':seen[target['runtime_id']],'group':g});continue
                seen[target['runtime_id']]=g['form_id']
                key=g['form_id']+'|'+norm(g['model']);observed={'cached_id':g['form_id'],'model':g['model'],'canonical':ident,'final_runtime_id':target['runtime_id'],
                    'original_GRAS_payload_sha256':old['payload_sha256'],'final_GRAS_payload_sha256':target['payload_sha256']}
                if key in identities:assert identities[key]==observed
                identities[key]=observed;prefix=f'{fid>>12:05X}' if kind=='light' else f'{fid>>24:02X}';prefixes[prefix].add(ident.split('|')[0])
                if g['form_id']!=target['runtime_id']:
                    edits.append({'offset':g['offset'],'old':g['form_id'],'new':target['runtime_id'],'canonical':ident,'stream':sn,'group':gn,'model':g['model']})
                if sn==0:first_blades+=g['blades']
                counts['groups_all_streams']+=1
            counts['streams']+=1
        counts['files_with_appended_streams']+=len(parsed)>1;counts['first_stream_blades']+=first_blades;counts['changed_form_id_fields']+=len(edits);counts['changed_files']+=bool(edits)
        files.append({'source':str(source),'destination_relative':'Grass/'+source.name,'bytes':len(data),'source_sha256':entry['sha256'],
            'streams':len(parsed),'first_stream_groups':len(parsed[0]['groups']),'first_stream_blades':first_blades,'id_edits':edits,
            'other_bytes_masked_sha256':mask_sha(data,[e['offset'] for e in edits])})
    # A historical index must consistently denote one canonical owner throughout all cached epochs.
    for prefix,owners in prefixes.items():
        if len(owners)!=1:errors.append({'prefix':prefix,'owners':sorted(owners),'error':'Ambiguous historical owner'})
    report={'utc':datetime.now(timezone.utc).isoformat(),'status':'BOUNDED_PRIVATE_OVERLAY_READY_NOT_MATERIALIZED' if not errors else 'STOP_UNRESOLVED_CACHE_IDENTITY',
        'source_audit_sha256':sha(audit_path),'final_profile':audit['final_profile'],'final_plugins_sha256':audit['final_plugins_sha256'],'final_modlist_sha256':audit['final_modlist_sha256'],
        'schema':'FasterNGIO 1.6 NgioCacheWriter: count,path-length,path,wave-f32,grass-runtime-u32,3 booleans,block-count,36-byte descriptors,32-byte instance payloads',
        'resolution_rule':'Unique full/light kind + objectID + exact case-insensitive slash-normalized MODL across all final winning GRAS; same canonical GRAS full payload in original TuLED and final; every historical prefix maps consistently to exactly one owner. Reject ambiguity/collision.',
        'all_bytes_preserved_except':'Exactly four documented grassFormID bytes per listed offset, in every appended complete stream. No position/geometry/header/material/filename changes.',
        'activation':'Not activated. Use as higher-priority private overlay only after parent review; generated final-profile caches must win above it for changed cells/worlds.',
        'limitations':['Original shipped caches already contain multiple historical load-order epochs; original current plugins.txt alone cannot identify every cached owner.',
            'This identity normalization does not validate grass placement against changed LAND, collision or runtime scripts. Those cells/worlds need generation.',
            'Do not claim cache ID shift itself proves a missing/wrong-grass runtime bug: offline reader analysis uses matching-version Anno reference image, not executing the packaged TuLED image.'],
        'statistics':dict(counts),'source_bytes':sum(f['bytes'] for f in files),'private_overlay_bytes':sum(f['bytes'] for f in files if f['id_edits']),
        'prefix_owners':{k:sorted(v) for k,v in prefixes.items()},'identity_map':list(identities.values()),'errors':errors,'files':files}
    owned(OUT/'grass_cache_remap_plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','statistics','source_bytes','private_overlay_bytes','prefix_owners','errors')},ensure_ascii=False),flush=True)

def materialize(run_name):
    assert re.fullmatch('[A-Za-z0-9_-]+',run_name)
    manifest_path=OUT/'grass_cache_remap_plan.json';p=json.loads(manifest_path.read_text(encoding='utf-8'))
    assert p['status']=='BOUNDED_PRIVATE_OVERLAY_READY_NOT_MATERIALIZED' and not p['errors']
    profile=Path(p['final_profile']);assert sha(profile/'plugins.txt')==p['final_plugins_sha256'] and sha(profile/'modlist.txt')==p['final_modlist_sha256'],'Refresh identity audit and plan after profile drift'
    dest=owned(OUT/'remap_runs'/run_name);assert not dest.exists();dest.mkdir(parents=True)
    assert shutil.disk_usage(OUT).free>32*1024**3+p['private_overlay_bytes']+256*1024**2,'Keep reserve and full private overlay budget'
    (dest/'plan_used.json').write_bytes(manifest_path.read_bytes());done=[]
    try:
        for row in p['files']:
            if not row['id_edits']:continue
            source=Path(row['source']);assert source.resolve().is_relative_to((DB.parent/'TuLED/File Mod Skyrim SE/mods/Grass Cache/grass').resolve())
            data=source.read_bytes();assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['source_sha256'],'Source cache drift'
            patched=bytearray(data)
            for e in row['id_edits']:
                assert struct.unpack_from('<I',data,e['offset'])[0]==int(e['old'],16)
                struct.pack_into('<I',patched,e['offset'],int(e['new'],16))
            assert mask_sha(patched,[e['offset'] for e in row['id_edits']])==row['other_bytes_masked_sha256']
            assert len(streams(patched))==row['streams']
            path=owned(dest/row['destination_relative']);path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as output:output.write(patched)
            assert path.stat().st_nlink==1 and path.read_bytes()==patched and sha(source)==row['source_sha256']
            done.append({'destination':str(path),'bytes':len(patched),'source_sha256':row['source_sha256'],'output_sha256':sha(path),'edits':len(row['id_edits']),'other_bytes_identical':True})
        status='PRIVATE_GRASS_IDENTITY_OVERLAY_VERIFIED_NOT_ACTIVATED'
    except Exception as error:
        status='FAIL_PARTIAL_OVERLAY_NOT_ACTIVATED';done.append({'error':repr(error)})
    (dest/'result.json').write_text(json.dumps({'status':status,'plan_sha256':sha(manifest_path),'files':done},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(status,len(done));return 0 if status.startswith('PRIVATE_') else 1

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');p=argparse.ArgumentParser();p.add_argument('--materialize',metavar='RUN_NAME');a=p.parse_args()
    sys.exit(materialize(a.materialize) if a.materialize else plan())
