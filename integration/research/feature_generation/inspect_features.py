"""Read-only HKX/script/NIF source inventory for exactly imported_features.

All BSA contents are extracted through the pinned read-only API and checked
against the existing independently validated entry SHA. No archive is edited.
"""
import collections
import ctypes
import hashlib
import json
import re
import sqlite3
import struct
import sys
import zlib
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(DB/'rootcause'))
import bsarch_readonly as bsa
sys.path.insert(0,str(OUT.parent/'navmesh_patch'))
from verify_candidate import Plugin,fields

CALLS=(b'sendanimationevent',b'playidle',b'playanimation',b'playgamebryoanimation',b'registerforanimationevent')


def digest(data):return hashlib.sha256(data).hexdigest()


def nif(data):
    p=data.index(b'\n')+1
    def take(size):
        nonlocal p
        assert 0<=size<=len(data)-p
        value=data[p:p+size];p+=size;return value
    def n(fmt):return struct.unpack('<'+fmt,take(struct.calcsize(fmt)))[0]
    def text(fmt='I'):return take(n(fmt)).rstrip(b'\0').decode('utf-8','replace')
    assert n('I')==0x14020007 and n('B')==1
    user=n('I');count=n('I');bs=n('I');assert user==12 and bs in (83,100)
    exported=[text('B') for _ in range(3)]
    types=[text() for _ in range(n('H'))];indices=[n('H') for _ in range(count)];sizes=[n('I') for _ in range(count)]
    string_count=n('I');n('I');strings=[text() for _ in range(string_count)];groups=[n('I') for _ in range(n('I'))]
    blocks=[];textures={};graphs=[];shaders=[]
    for index,(type_index,size) in enumerate(zip(indices,sizes)):
        name=types[type_index];start=p;body=take(size);blocks.append(name)
        if name=='BSShaderTextureSet':
            save=p;p=start;textures[index]=[text() for _ in range(n('I'))];assert p==start+size;p=save
        if name=='BSBehaviorGraphExtraData':
            a,b=struct.unpack_from('<II',body);graphs.append({'name':strings[a] if a!=0xffffffff else '',
                                                          'graph':strings[b] if b!=0xffffffff else ''})
        if name=='BSLightingShaderProperty':
            shader,name_id,extras=struct.unpack_from('<III',body);assert extras<65536
            offset=16+4*extras;flags1,flags2=struct.unpack_from('<II',body,offset)
            texture_set=struct.unpack_from('<i',body,offset+24)[0]
            shaders.append({'block':index,'shader_type':shader,'flags1':f'{flags1:08X}','flags2':f'{flags2:08X}',
                            'skinned':bool(flags1&2),'parallax_flag':bool(flags1&0x800),'texture_set':texture_set})
    for shader in shaders:
        assert shader['texture_set'] in textures,'Lighting shader texture-set link invalid'
        shader['textures']=textures[shader['texture_set']]
    return {'bs_version':bs,'block_types':dict(collections.Counter(blocks)),'behavior_graphs':graphs,'shaders':shaders,
            'all_texture_sets':list(textures.values()),'strings_with_animation_paths':[s for s in strings if s.lower().endswith(('.hkx','.kf'))]}


def bsa_iter(archive,expected):
    handle=bsa.create();records={}
    try:
        result=bsa.load(handle,str(archive));assert result.code>=0,result.text
        @bsa.callback
        def visit(a,name,record,folder,context):
            key=name.replace('\\','/').lower()
            if key in expected:records[key]=record
            return False
        result=bsa.iterate(handle,visit,None);assert result.code>=0,result.text
        assert records.keys()==expected.keys(),'BSA member listing differs'
        for key,record in records.items():
            result=bsa.extract(handle,record)
            try:
                assert result.message.code>=0,result.message.text
                data=ctypes.string_at(result.buffer.data,result.buffer.size)
                assert digest(data)==expected[key]['sha256'],'BSA entry digest differs'
            finally:
                if result.buffer.data:assert bsa.freebuf(handle,result.buffer).code>=0
            yield key,data,expected[key]
    finally:bsa.close(handle);bsa.free(handle)


def main():
    sys.stdout.reconfigure(encoding='utf-8');OUT.mkdir(exist_ok=True)
    imported=json.loads((DB/'integration/imported_features.json').read_text(encoding='utf-8'))
    plan=json.loads((DB/'integration/features_preflight.json').read_text(encoding='utf-8'))
    database=sqlite3.connect('file:'+(DB/'baseline/skyrim_research.sqlite').as_posix()+'?mode=ro',uri=True);database.row_factory=sqlite3.Row
    report={'scope':'Exact imported_features.json: 14 selected plugins, 12 standalone roots, actual mapped loose files and each mapped BSA member',
       'import_manifest_sha256':digest((DB/'integration/imported_features.json').read_bytes()),'assets':[],'nifs':[],'scripts':[],
       'HKX':[],'generator_inputs':[],'errors':[],'plugin_animation_records':[]}
    hkx_out=OUT/'hkx';hkx_out.mkdir(exist_ok=True);scripts_out=OUT/'script_candidates';scripts_out.mkdir(exist_ok=True)
    pgdiff=json.loads((DB.parent/'TuLED/File Mod Skyrim SE/mods/ParallaxGen_Output (1.01)/ParallaxGen_Diff.json').read_text(encoding='utf-8'))
    pgdiff={key.lower().replace('\\','/'):value for key,value in pgdiff.items()}
    def consume(key,data,location):
        key=key.lower().replace('\\','/');suffix=Path(key).suffix;value={'path_key':key,**location,'bytes':len(data),'sha256':digest(data)}
        report['assets'].append(value)
        if any(word in key for word in ('fnis','pandora','nemesis','openanimationreplacer','dynamicanimationreplacer')):
            report['generator_inputs'].append(value)
        if suffix=='.hkx':
            strings=[value.decode('ascii') for value in re.findall(rb'[\x20-\x7e]{3,}',data)]
            path=hkx_out/(digest(data)+'.hkx');path.write_bytes(data)
            report['HKX'].append({**value,'copy':str(path),'header_hex':data[:64].hex(),'strings':strings})
        if suffix in ('.pex','.psc'):
            lower=data.lower();calls=[call.decode() for call in CALLS if call in lower]
            if calls:
                path=scripts_out/(digest(data)+suffix);path.write_bytes(data)
                report['scripts'].append({**value,'calls':calls,'copy':str(path)})
        if suffix=='.nif':
            try:
                parsed=nif(data);row={**value,**parsed,'crc32':zlib.crc32(data)&0xffffffff}
                if key in pgdiff:
                    row['old_PG_diff']=pgdiff[key];row['matches_old_PG_original']=row['crc32']==pgdiff[key]['crc32original'];row['matches_old_PG_patched']=row['crc32']==pgdiff[key]['crc32patched']
                report['nifs'].append(row)
            except Exception as error:report['errors'].append({'kind':'NIF_parse','asset':value,'error':repr(error)})
    archives=[]
    for row in plan['mappings']:
        key=row['relative'].lower().replace('\\','/');source=Path(row['source'])
        if source.suffix.lower()=='.bsa':
            archive=database.execute('SELECT id,path,sha256,status FROM bsa_archives WHERE path=?',(str(source),)).fetchone();assert archive is not None
            expected={member['path_key']:dict(member) for member in database.execute("SELECT path_key,sha256,size_bytes,status FROM bsa_entries WHERE archive_id=? AND (path_key LIKE '%.hkx' OR path_key LIKE '%.nif' OR path_key LIKE '%.pex' OR path_key LIKE '%.psc' OR path_key LIKE '%fnis%list%' OR path_key LIKE '%pandora%' OR path_key LIKE '%nemesis%')",(archive['id'],))}
            assert all(member['status']=='ok' for member in expected.values())
            archives.append({'archive':dict(archive),'mapping':row,'members':expected})
        elif source.suffix.lower() in ('.hkx','.nif','.pex','.psc') or any(word in key for word in ('fnis','pandora','nemesis','openanimationreplacer','dynamicanimationreplacer')):
            consume(key,source.read_bytes(),{'kind':'loose','physical':str(source),'layer':row['destination'].split('/')[1],'feature':row['feature']})
    for archive in archives:
        meta=archive['mapping'];print('BSA',Path(archive['archive']['path']).name,'members',len(archive['members']),flush=True)
        for key,data,_ in bsa_iter(archive['archive']['path'],archive['members']):
            consume(key,data,{'kind':'BSA','archive':archive['archive']['path'],'archive_id':archive['archive']['id'],
                              'layer':meta['destination'].split('/')[1],'feature':meta['feature']})
    for row in imported['plugins']:
        plugin=Plugin(row['selected_source'])
        for record in plugin.records:
            if record['signature'] not in ('RACE','IDLE'):continue
            raw=list(fields(plugin.payload(record)));data=dict(raw)
            report['plugin_animation_records'].append({'plugin':row['name'],**record,
              'editor_id':data.get('EDID',b'').rstrip(b'\0').decode('utf-8','replace'),
              'model_paths':[value.rstrip(b'\0').decode('utf-8','replace') for tag,value in raw if tag=='MODL'],
              'idle_file':data.get('DNAM',b'').rstrip(b'\0').decode('utf-8','replace') if record['signature']=='IDLE' else None,
              'idle_event':data.get('ENAM',b'').rstrip(b'\0').decode('utf-8','replace') if record['signature']=='IDLE' else None})
    report['counts']={'assets':len(report['assets']),'NIFs':len(report['nifs']),'HKX':len(report['HKX']),'script_candidates':len(report['scripts']),
                      'generator_input_candidates':len(report['generator_inputs']),'errors':len(report['errors'])}
    report['archive_manifest']=[{'archive':row['archive'],'mapping':row['mapping'],'audited_members':len(row['members'])} for row in archives]
    (OUT/'source_inspection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report['counts']),flush=True)


if __name__=='__main__':main()
