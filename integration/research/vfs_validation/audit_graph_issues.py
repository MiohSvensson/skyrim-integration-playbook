"""Bounded read-only evidence for Rihad fallback slots and reserved SoS clips."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys

sys.dont_write_bytecode=True
from vfs_common import *
sys.path.insert(0,str(BASE/'rootcause'))
from nif_inventory import inventory
from plugin_binary import read


def shader_view(path):
    b=Path(path).read_bytes();inv=inventory(path);out=[]
    for block in inv['blocks']:
        if block['type']!='BSLightingShaderProperty':continue
        o=block['offset'];stype,ni,nextra=struct.unpack_from('<III',b,o)
        texref=struct.unpack_from('<I',b,o+40+4*nextra)[0]
        out.append({'shader_block':block['index'],'shader_type':stype,
          'flags1':f'{struct.unpack_from("<I",b,o+16+4*nextra)[0]:08X}',
          'flags2':f'{struct.unpack_from("<I",b,o+20+4*nextra)[0]:08X}',
          'texture_block':texref,'textures':inv['blocks'][texref]['textures']})
    return {'path':str(path),'sha256':inv['sha256'],'shaders':out}


def main():
    sq=sqlite3.connect(OWN/'phase2_expectations.sqlite');sq.row_factory=sqlite3.Row
    physical={r['path_key']:dict(r) for r in sq.execute('select * from files')}
    e=json.loads(sq.execute("select value from metadata where key='expectations'").fetchone()[0])
    boots=[shader_view(physical[f'meshes/pulcharmsolis/frbrset/f/daedricboots_{w}.nif']['physical_path']) for w in (0,1)]
    body=shader_view(physical['meshes/actors/character/character assets/femalebody_1.nif']['physical_path'])
    feet=[shader_view(physical[f'meshes/actors/character/character assets/femalefeet_{w}.nif']['physical_path']) for w in (0,1)]
    bs=[next(s for s in n['shaders'] if any('!cor' in t.lower() for t in s['textures'])) for n in boots]
    ref=next(s for s in body['shaders'] if key(s['textures'][0])=='textures/actors/character/female/femalebody_1.dds')
    assert all(s['shader_type']==5 and (s['flags1'],s['flags2'])==(ref['flags1'],ref['flags2']) for s in bs)
    assert all(n['shaders'][0]['shader_type']==5 and [key(t) for t in n['shaders'][0]['textures']]==[key(t) for t in ref['textures']] for n in feet)
    aliases=[]
    for i in (0,1,2,7):
        assert key(bs[0]['textures'][i])==key(bs[1]['textures'][i])
        source=physical[key(ref['textures'][i])]
        aliases.append({'destination':key(bs[0]['textures'][i]),'source_relative':source['relative_path'],
          'source_physical':source['physical_path'],'provider':source['provider'],'sha256':digest(source['physical_path']),
          'slot_index':i,'slot_role':{0:'diffuse/albedo',1:'model-space normal',2:'skin subsurface',7:'skin specular'}[i]})
    plugin_rows=[]
    for plugin in e['plugins']:
        if plugin['name'].casefold()!='rihadswordsmanset.esl' and 'rihadswordsmanset.esl' not in [m.casefold() for m in plugin['masters']]:continue
        masters,recs=read(plugin['physical_path'])
        own=plugin['name'].casefold()=='rihadswordsmanset.esl'
        idx=len(masters) if own else [m.casefold() for m in masters].index('rihadswordsmanset.esl')
        matched=[r for r in recs if r['sig']=='ARMA' and r['fid']>>24==idx and r['fid']&0xffffff==0xd68]
        for r in matched:
            fields={tag:v for tag,v in r['fields'] if tag not in ('MODL',)}
            plugin_rows.append({'plugin':plugin['name'],'sha256':plugin['sha256'],'fid':f'{r["fid"]:08X}',
              'edid':r['edid'],'female_model':fields.get('MOD3',b'').rstrip(b'\0').decode('utf-8'),
              'alternate_texture_fields_present':[tag for tag in fields if tag in ('MODS','MO2S','MO3S','MO4S','MO5S')],
              'explicit_skin_texture_fields_present':[tag for tag in fields if tag in ('NAM0','NAM1','NAM2','NAM3')],
              'all_field_tags':[tag for tag,_ in r['fields']]})
    sos=[]
    for k in ['meshes/auxbones/sos/behaviors/sosmalebehavior.hkx','meshes/auxbones/sos/characters/sosmalecharacter.hkx']:
        p=physical[k];b=Path(p['physical_path']).read_bytes();tokens=[t.decode('ascii') for t in re.findall(rb'[\x20-\x7e]{5,}',b)]
        custom=[t for t in tokens if re.fullmatch(r'Animations\\SOSCustom0[0-9]\.hkx',t)]
        assert len(custom)==10
        sos.append({'path':k,'physical_path':p['physical_path'],'sha256':hashlib.sha256(b).hexdigest(),'optional_tokens':custom})
    consumers=json.loads((OWN/'sos_custom_consumer_audit.json').read_text(encoding='utf-8'))
    source_files=list((OWN/'sos_source_audit/psc').glob('*.psc'))
    send_lines=[]
    for p in source_files:
        for n,line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(),1):
            if 'SendAnimationEvent' in line:send_lines.append({'path':str(p),'line':n,'text':line.strip()})
    out={'status':'EVIDENCE_READY_NO_RUNTIME_CHANGE_MADE',
      'rihad':{'boots':boots,'base_body':body,'base_feet':feet,'exact_arma_override_chain':plugin_rows,
        'schema_source':{'path':str(BASE/'sources/nifxml/nif.xml'),'commit':'970a6238218a106daaeb89a61bcda0eeaf9d08c4','shader_type_5':'Skin Tint','texture_set_slots':{'0':'diffuse','1':'normal','2':'glow/skin','7':'specular'}},
        'decision':'Four missing fallback files can be explicit aliases of the selected base female skin slots. This supplies fallback bytes only, preserves both boot NIFs and their shaders/topology, and does not override actor-skin runtime substitution.',
        'fallback_aliases':aliases},
      'sos':{'graph_files':sos,'decompiled_current_winning_framework_scripts':len(source_files),'send_animation_events':send_lines,
        'loose_pex_literal_consumers':consumers,
        'primary_firsthand_extension_documentation':{'author':'VitSu','published':'2020-08-16','url':'https://aml.name/forums/topic/3389-dobavlyaem-animaciyu-v-sos/',
          'paraphrase':'The extension tutorial identifies SOSCustom00 through 09 as empty events with no animation files and demonstrates supplying one through the matching event.'},
        'decision':'Only the ten missing optional Custom00-09 slots from these two exact framework hashes may be documented extension limitations. Do not synthesize animations. Core behavior, skeleton and named shipped clips remain mandatory.',
        'limitations':['No game or HKX behavior was executed.','Loose PEX literal absence does not prove no dynamically assembled event or unscanned BSA consumer.','Custom slots are unavailable unless a separate addon supplies the corresponding clips.']}}
    write_json(OWN/'graph_issue_evidence.json',out)
    print(json.dumps({'output':str(OWN/'graph_issue_evidence.json'),'aliases':len(aliases),'rihad_arma_override_records':len(plugin_rows),'sos_optional_slots_each':10,'current_framework_scripts':len(source_files),'loose_pex_scanned':consumers['scanned'],'custom_consumers':len(consumers['hits'])}))


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');main()
