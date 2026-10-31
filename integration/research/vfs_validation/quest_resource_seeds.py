"""Typed feature-plugin resource seeds; this script never changes runtime data.

Preview uses nominated source plugins and makes no final-view claim. Final mode
uses only profile-enabled imported feature plugins and their actual file winners.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import sqlite3
import struct
import sys
import zlib

sys.dont_write_bytecode=True
from vfs_common import *
sys.path.insert(0,str(BASE/'rootcause'))
from plugin_binary import subs
sys.path.insert(0,str(BASE/'integration/research/feature_conflicts'))
from vmad_audit import parse_vmad

PLANNED={'wyrmstooth.esp','[longshou]worldinpainting_zerohall.esp','[longshou]uf6.esp',
 'moonandstar_mas.esp','forgottenmagic_redone.esp','sofiafollower.esp','hothfollower.esp','bendoonsse.esp',
 'glenmoril.esm','forgottencity.esp','forgotten city music fix.esp'}


class Reader:
    def __init__(self,data,pos=0):self.data=data;self.pos=pos
    def take(self,fmt):
        out=struct.unpack_from('<'+fmt,self.data,self.pos);self.pos+=struct.calcsize('<'+fmt)
        return out[0] if len(out)==1 else out
    def string(self):
        n=self.take('H');b=self.data[self.pos:self.pos+n];assert len(b)==n;self.pos+=n
        return b.decode('utf-8')


def vmad_scripts(data,signature):
    """Decode main scripts, typed fragment script names and quest-alias scripts."""
    main=parse_vmad(data,lambda fid:f'{fid:08X}')
    result=[(s['name'],'VMAD attached script') for s in main['scripts']]
    r=Reader(data,main['consumed_script_bytes'])
    if r.pos==len(data):return result
    if signature not in ('INFO','PACK','PERK','QUST','SCEN'):
        raise ValueError(('Unexpected nonfragment VMAD tail',signature,len(data)-r.pos))
    r.take('B') # extra bind data version
    def script_fragment(prefix):
        r.take('B');script=r.string();fragment=r.string()
        if script:result.append((script,prefix+':'+fragment))
    if signature in ('INFO','PACK','SCEN'):
        flags=r.take('B');filename=r.string()
        if filename:result.append((filename,'VMAD fragment file'))
        mask=7 if signature=='PACK' else 3
        assert not flags&~mask,('Unknown fragment flag bits',signature,flags)
        for _ in range((flags&mask).bit_count()):script_fragment('VMAD '+signature+' fragment')
        if signature=='SCEN':
            for _ in range(r.take('H')):
                r.take('BI');script_fragment('VMAD scene phase fragment')
    elif signature=='PERK':
        filename=r.string()
        if filename:result.append((filename,'VMAD fragment file'))
        for _ in range(r.take('H')):r.take('I');script_fragment('VMAD perk fragment')
    elif signature=='QUST':
        count=r.take('H');filename=r.string()
        if filename:result.append((filename,'VMAD fragment file'))
        for _ in range(count):r.take('II');script_fragment('VMAD quest-stage fragment')
        # Aliases are optional only if the VMAD payload ends here.
        if r.pos<len(data):
            for _ in range(r.take('H')):
                r.take('Q') # typed VMAD object reference (format is inherited)
                alias=parse_vmad(data[r.pos:],lambda fid:f'{fid:08X}')
                result.extend((s['name'],'VMAD quest alias script') for s in alias['scripts'])
                r.pos+=alias['consumed_script_bytes']
    assert r.pos==len(data),('Unconsumed VMAD fragment bytes',signature,r.pos,len(data))
    return result


def records(path,only_identities=None,masters=None,name=None,signatures=None):
    """One bounded bytes buffer, parse only needed payloads, discard each record."""
    data=Path(lp(path)).read_bytes();pos=0
    while pos<len(data):
        if pos+24>len(data):raise ValueError('Truncated plugin header')
        sig=data[pos:pos+4].decode('ascii');size=struct.unpack_from('<I',data,pos+4)[0]
        if sig=='GRUP':
            if size<24 or pos+size>len(data):raise ValueError('Invalid GRUP')
            pos+=24;continue
        flags,fid=struct.unpack_from('<II',data,pos+8)
        if pos+24+size>len(data):raise ValueError('Invalid record bounds')
        idx=fid>>24;owner=masters[idx] if masters is not None and idx<len(masters) else name
        identity=key(owner or '')+'|'+f'{fid&0xffffff:06x}'
        wanted=sig!='TES4' and (only_identities is None or identity in only_identities) and (signatures is None or sig in signatures)
        if wanted:
            payload=data[pos+24:pos+24+size]
            if flags&0x40000:
                n=struct.unpack_from('<I',payload)[0];payload=zlib.decompress(payload[4:]);assert len(payload)==n
            yield {'sig':sig,'fid':fid,'identity':identity,'flags':flags,'fields':subs(payload),'payload_sha256':hashlib.sha256(payload).hexdigest()}
        pos+=24+size


def text(raw):
    b=raw.rstrip(b'\0')
    if not b or b'\0' in b:return None
    try:return b.decode('utf-8')
    except UnicodeDecodeError:return None


def runtime_path(value,root):
    v=key(value).lstrip('/')
    if v.startswith('data/'):v=v[5:]
    if not v.startswith(root+'/'):v=root+'/'+v
    return key(posixpath.normpath(v))


def preview_plugins():
    manifest=BASE/'integration/research/plugin_integration/feature_builder_manifest.json'
    j=json.loads(manifest.read_text(encoding='utf-8'));out=[];mod_ids=set()
    for f in j['features']:
        for r in f.get('plugins',[])+f.get('optional_selected_patches',[]):
            if key(r['name']) not in PLANNED and not any(key(x['name']) in PLANNED for x in f.get('plugins',[])):continue
            mod_ids.update(m['id'] for m in f.get('mods',[]))
            replacement=r.get('validated_replacement')
            source=(replacement.get('candidate') or replacement.get('path')) if isinstance(replacement,dict) else replacement
            source=source or r['source_path']
            if key(r['name'])=='moonandstar_mas.esp':source=str(BASE/'integration/research/plugin_integration/moonstar_cleanup_candidate/MoonAndStar_MAS.esp')
            out.append({'name':r['name'],'physical_path':source,'feature':f['feature']})
    followers=json.loads((BASE/'integration/research/feature_conflicts/follower_source_consumers.json').read_text(encoding='utf-8'))
    out.extend({'name':r['plugin'],'physical_path':r['path'],'feature':r['plugin']} for r in followers)
    source_db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    for r in followers:
        row=source_db.execute('select id from mods where path=?',(str(Path(r['path']).parent),)).fetchone()
        if row:mod_ids.add(row[0])
    return out,[{'path':str(manifest),'sha256':digest(manifest)}],mod_ids


def feature_source_mod_ids(feature,manifest):
    """Accept the importer journal's exact standalone source list, not plugin collection roots."""
    result={r['id'] for r in feature.get('mod_sources',[])}
    label=feature.get('name',feature.get('feature'))
    result.update(r['id'] for r in manifest.get('source_mods',[]) if r.get('feature')==label)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--expect',required=True);p.add_argument('--output',required=True)
    p.add_argument('--manifest',default=str(BASE/'integration/imported_features.json'))
    p.add_argument('--preview-sources',action='store_true');p.add_argument('--resolve',action='store_true',help='Resolve typed required seeds in the expected physical view; does not claim actual VFS success.')
    p.add_argument('--exceptions',help='Exact bounded authored resource-gap contract manifest; never a filename-only ignore list.')
    p.add_argument('--xedit-reference-result',help='Actual MO2 full-context BoundedQuestConsumerAudit producer result.json, required for unused UF6/Ben source gaps.')
    a=p.parse_args();out=safe_output(a.output)
    db=sqlite3.connect(Path(a.expect).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    expect=json.loads(db.execute("select value from metadata where key='expectations'").fetchone()[0])
    physical={r['path_key']:dict(r) for r in db.execute('select * from files')}
    active={key(r['name']):r for r in expect['plugins']};errors=[];excluded=[]
    if not a.preview_sources and controls(Path(expect['target']),Path(expect['profile']))!=expect['control_hashes']:
        errors.append({'kind':'profile_changed_since_expectation_snapshot'})
    if a.preview_sources:selected,provenance,mod_ids=preview_plugins()
    else:
        manifest=Path(a.manifest);j=json.loads(manifest.read_text(encoding='utf-8'));provenance=[{'path':str(manifest),'sha256':digest(manifest)}]
        selected=[];mod_ids=set()
        for feature in j['features']:
            enabled=False
            for r in feature['plugins']:
                name=r['name'] if isinstance(r,dict) else r
                if key(name) in active:
                    selected.append({**active[key(name)],'feature':feature.get('name',feature.get('feature'))});enabled=True
                else:excluded.append({'plugin':name,'reason':'Not enabled in the exact expectation profile'})
            if enabled:mod_ids.update(feature_source_mod_ids(feature,j))
        # Include all enabled selected patches and new integration/nav plugins
        # that depend on these feature namespaces, even if separately journaled.
        selected_names={key(r['name']) for r in selected}
        changed=True
        while changed:
            changed=False
            for plugin in expect['plugins']:
                name_key=key(plugin['name'])
                if name_key not in selected_names and {key(m) for m in plugin['masters']}&selected_names:
                    selected.append({**plugin,'feature':'Enabled dependent patch / navigation / compatibility'})
                    selected_names.add(name_key);changed=True
    seeds=collections.defaultdict(list);script_names=set();counters=collections.Counter();plugin_rows=[];sequence=[];identities={};plugin_meta={}
    def add(k,request):
        if k:seeds[key(k)].append(request)
    def consume(plugin,r):
        if r['flags']&0x20:return
        sig=r['sig'];fields=r['fields'];edid=next((text(v) for t,v in fields if t=='EDID'),None)
        origin={'plugin':plugin['name'],'record':r['identity'],'signature':sig,'edid':edid}
        for tag,raw in fields:
            value=text(raw)
            if tag in ('MODL','MOD2','MOD3','MOD4','MOD5') and value:
                child=asset_key(value,parent=None)
                if child and child.endswith(('.nif','.tri','.dds')):add(child,{**origin,'field':tag})
            elif sig=='TXST' and tag in ('TX00','TX01','TX02','TX03','TX04','TX05','TX06','TX07') and value:
                add(asset_key(value,'texture'),{**origin,'field':tag})
            elif tag in ('ICON','MICO','ICO2','MIC2') and value and value.lower().endswith('.dds'):
                add(asset_key(value,'texture'),{**origin,'field':tag})
            elif sig=='SNDR' and tag=='ANAM' and value:
                v=runtime_path(value,'sound')
                if Path(v).suffix in ('.wav','.xwm'):add(v,{**origin,'field':'ANAM sound descriptor'})
                else:errors.append({'kind':'unrecognized_sndr_path','value':value,**origin})
            elif sig=='MUST' and tag in ('ANAM','BNAM') and value:
                v=runtime_path(value,'music')
                add(v,{**origin,'field':tag+' music track'})
            elif sig=='RACE' and tag=='ANAM' and value and value.lower().endswith(('.nif','.hkx')):
                add(asset_key(value),{**origin,'field':'ANAM skeleton model'})
            elif sig=='HDPT' and tag in ('NAM0','NAM1') and value and value.lower().endswith('.tri'):
                add(asset_key(value),{**origin,'field':tag+' head-part morph'})
            elif tag=='VMAD':
                counters['vmad_records']+=1
                try:
                    for script,where in vmad_scripts(raw,sig):
                        script=script.replace('\\','/').rsplit('/',1)[-1]
                        if script.lower().endswith(('.psc','.pex')):script=script[:-4]
                        if not re.fullmatch(r'[A-Za-z0-9_$ .-]+',script):raise ValueError(('Nonliteral script name',script))
                        script_names.add(key(script));add('scripts/'+script+'.pex',{**origin,'field':where})
                except Exception as ex:errors.append({'kind':'vmad_parse_failed',**origin,'error':repr(ex)})
        if sig=='INFO':counters['dialogue_info_records']+=1
    for plugin in selected:
        h=plugin_header(plugin['physical_path']);plugin_meta[key(plugin['name'])]=dict(plugin,**h)
        if not a.preview_sources and h['sha256']!=plugin['sha256']:errors.append({'kind':'feature_plugin_changed_since_expectations','plugin':plugin['name']})
        n=0;sge=[]
        for r in records(plugin['physical_path'],masters=h['masters'],name=plugin['name']):
            n+=1;identities[r['identity']]=(plugin,r)
            if r['sig']=='QUST':
                d=next((v for t,v in r['fields'] if t=='DNAM'),b'')
                if len(d)>=2 and struct.unpack_from('<H',d)[0]&1:sge.append({'identity':r['identity'],'raw_form_id':f'{r["fid"]:08X}','owned':r['fid']>>24>=len(h['masters'])})
        plugin_rows.append({'name':plugin['name'],'feature':plugin.get('feature'),'path':plugin['physical_path'],'sha256':h['sha256'],'records':n,'sge_quests':sge})
        own_sge=[r for r in sge if r['owned']]
        if sge:
            seq='seq/'+Path(plugin['name']).stem+'.seq'
            sequence.append({'plugin':plugin['name'],'path_key':key(seq),'own_sge_quests':own_sge,'overridden_sge_quests':[r for r in sge if not r['owned']],
              'requirement':'Own start-game-enabled quests are sequence candidates per xEdit. Overridden quests additionally require the original master SGE comparison; no generated bytes are written by this script.'})
        print('feature parsed',plugin['name'],n,'records',flush=True)
    if not a.preview_sources:
        # Forward every touched identity through the actual complete enabled load order.
        namespaces={r.split('|',1)[0] for r in identities};wanted=set(identities)
        for plugin in expect['plugins']:
            if not ({key(plugin['name'])}|{key(m) for m in plugin['masters']})&namespaces:continue
            for r in records(plugin['physical_path'],wanted,plugin['masters'],plugin['name']):identities[r['identity']]=(plugin,r)
        final_sge=collections.defaultdict(list)
        for winner,r in identities.values():
            owner=r['identity'].split('|',1)[0]
            if r['sig']!='QUST' or r['flags']&0x20 or owner not in plugin_meta:continue
            d=next((v for t,v in r['fields'] if t=='DNAM'),b'')
            if len(d)>=2 and struct.unpack_from('<H',d)[0]&1:
                raw=(len(plugin_meta[owner]['masters'])<<24)|(r['fid']&0xffffff)
                final_sge[owner].append({'identity':r['identity'],'raw_form_id':f'{raw:08X}','owned':True,'winning_record_plugin':winner['name']})
        if any(r['overridden_sge_quests'] for r in sequence):errors.append({'kind':'sequence_master_sge_comparison_pending'})
        sequence=[{'plugin':plugin_meta[owner]['name'],'path_key':key('seq/'+Path(plugin_meta[owner]['name']).stem+'.seq'),
          'own_sge_quests':rows,'overridden_sge_quests':[],'requirement':'Final complete-load-order SGE flags; IDs encoded in the defining feature plugin namespace per xEdit FixedFormID.'} for owner,rows in final_sge.items()]
    for candidate in sequence:
        if candidate['own_sge_quests']:add(candidate['path_key'],{'plugin':candidate['plugin'],'field':'Own Start Game Enabled quest sequence','records':[r['identity'] for r in candidate['own_sge_quests']]})
    for plugin,r in identities.values():consume(plugin,r)
    # These files are supplied by the exact selected source mods, so their
    # existence is an authored requirement. No unvoiced INFO filenames are guessed.
    provided_counts=collections.Counter()
    provided_archive_hashes={}
    if mod_ids:
        source_db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
        holders=','.join('?' for _ in mod_ids)
        query=f'''select f.path_key,null,null from files f where f.mod_id in ({holders}) and f.virtual_candidate=1
          union select e.path_key,a.path,a.sha256 from bsa_entries e join bsa_sources s on s.archive_id=e.archive_id
          join bsa_archives a on a.id=e.archive_id
          where s.mod_id in ({holders}) and s.source_kind='mod' and e.status='ok' '''
        associated={key(n) for n in expect['archive_names']}
        for k,archive_path,archive_sha in source_db.execute(query,list(mod_ids)*2):
            if archive_path and not a.preview_sources:
                basename=key(Path(archive_path).name)
                if basename not in associated or basename not in physical:continue
                if basename not in provided_archive_hashes:provided_archive_hashes[basename]=digest(physical[basename]['physical_path'])
                if provided_archive_hashes[basename]!=archive_sha:continue
            field=None
            if k.startswith('sound/voice/') and k.endswith(('.fuz','.xwm','.wav','.lip')):field='Authored provided voice asset'
            elif k.startswith(('meshes/actors/character/facegendata/facegeom/','textures/actors/character/facegendata/facetint/')) and k.endswith(('.nif','.dds')):field='Authored provided FaceGen asset'
            elif k.startswith('video/') and k.endswith('.bik'):field='Authored provided feature video'
            if field:add(k,{'field':field,'source_mod_ids':sorted(mod_ids)});provided_counts[field]+=1
    resources=[{'path_key':k,'requested_by':v,'kind':'pex' if k.endswith('.pex') else 'seq' if k.endswith('.seq') else 'model' if k.endswith('.nif') else 'texture' if k.endswith('.dds') else 'sound' if k.endswith(('.wav','.xwm')) else 'other'} for k,v in sorted(seeds.items())]
    resolved=[];runtime_seeds=collections.defaultdict(list);sequence_checks=[];documented_missing=[];exception_contract=None;exception_audit=None
    if a.exceptions:
        if a.preview_sources:errors.append({'kind':'bounded_exceptions_require_final_enabled_context'})
        else:
            from bounded_quest_exceptions import BoundedQuestExceptions
            try:
                exception_contract=BoundedQuestExceptions(a.exceptions,expect['plugins'],identities,a.xedit_reference_result,target=expect['target'])
                exception_audit=exception_contract.audit();errors.extend(exception_audit['errors'])
            except Exception as ex:errors.append({'kind':'bounded_exception_manifest_invalid','error':repr(ex)})
    if a.resolve:
        sys.path.insert(0,str(BASE/'rootcause'));from bsarch_readonly import extract_files
        names,_=active_archive_names(Path(expect['profile']),expect['enabled_plugins'],physical)
        archives={key(n):dict(physical[key(n)],order=i) for i,n in enumerate(names)}
        catalog=ResourceCatalog(physical,archives);catalog.archive_hashes.update(expect['archive_hashes_required']);catalog.archive_hashes.update(provided_archive_hashes)
        for n,r in enumerate(resources):
            k=r['path_key'];paths=[k]
            if r['kind']=='sound':paths.append(k[:-4]+('.xwm' if k.endswith('.wav') else '.wav'))
            present=[(v,catalog.resolve(v)) for v in paths if catalog.resolve(v)['kind']!='missing']
            resolved.append({'path_key':k,'kind':r['kind'],'alternatives':paths,'present':[{'path_key':v,'location':loc} for v,loc in present]})
            for v,loc in present:runtime_seeds[v].append({'declared_path':k,'requested_by':r['requested_by']})
            if not present:
                approved=exception_contract.match_missing(r,paths) if exception_contract else None
                if approved:documented_missing.append(approved)
                else:errors.append({'kind':'typed_feature_resource_missing','path_key':k,'alternatives':paths,'resource_kind':r['kind'],'requested_by':r['requested_by']})
            elif r['kind']=='seq':
                loc=present[0][1]
                if loc['kind']=='loose':b=Path(lp(loc['physical_path'])).read_bytes()
                else:b=extract_files(loc['archive_physical'],{loc['entry']:loc['sha256']})[loc['entry']]
                if len(b)%4:errors.append({'kind':'invalid_seq_size','path_key':k,'bytes':len(b)})
                else:
                    ids=struct.unpack('<'+'I'*(len(b)//4),b);candidate=next(x for x in sequence if x['path_key']==k)
                    expected_ids=[int(x['raw_form_id'],16) for x in candidate['own_sge_quests']]
                    missing=[f'{x:08X}' for x in expected_ids if x not in ids]
                    sequence_checks.append({'path_key':k,'bytes':len(b),'ids':[f'{x:08X}' for x in ids],'missing_expected_sge':missing})
                    if missing:errors.append({'kind':'seq_missing_own_sge_quests','path_key':k,'missing':missing})
            if n%1000==0:print('feature resources resolved',n+1,'/',len(resources),flush=True)
    report={'status':'PREVIEW_NOT_FINAL_VIEW' if a.preview_sources else 'FAIL' if errors else 'PHYSICAL_TYPED_SEEDS_READY_WITH_DOCUMENTED_SOURCE_LIMITATIONS' if documented_missing else 'PHYSICAL_TYPED_SEEDS_READY_NO_VFS_PASS',
      'mode':'source_preview' if a.preview_sources else 'actual_enabled_physical_plugin_winners','expectations':str(Path(a.expect).resolve()),
      'resolution_performed':a.resolve,
      'control_hashes':expect['control_hashes'],'manifest_provenance':provenance,'plugins':plugin_rows,'excluded':excluded,
      'counts':{'plugins':len(plugin_rows),'touched_final_records':len(identities),'required_seeds':len(resources),'script_names':len(script_names),**counters},
      'authored_provided_asset_counts':dict(provided_counts),'source_mod_ids':sorted(mod_ids),
      'required_seeds':resources,'resolved':resolved,
      'resolved_runtime_seeds':[{'path_key':k,'sources':v} for k,v in sorted(runtime_seeds.items())],
      'sequence_candidates':sequence,'sequence_checks':sequence_checks,'errors':errors,
      'documented_missing_source_resources':documented_missing,'bounded_exception_audit':exception_audit,
      'audio_resolution_basis':{'path':str(OWN/'official_audio_format_artifact_evidence.json'),'sha256':digest(OWN/'official_audio_format_artifact_evidence.json'),
        'rule':'Same-stem WAV/XWM alternatives only; all actually present alternatives become SHA-verifiable seeds. Official shipped plugin WAV declarations with only stock XWM members support this static resolution rule. No playback claim.'},
      'speech_policy':{'classification':'optional_unproven_voice_coverage','info_records':counters['dialogue_info_records'],
        'reason':'Plugin INFO text does not prove an authored external FUZ filename. Missing inferred speech is not made fatal. Imported complete voice resources must separately be enumerated from actual loose/BSA filename winners; no PSC is accepted in place of executable PEX.'},
      'schema_sources':[str(BASE/'sources/TES5Edit/Core/wbDefinitionsTES5.pas'),str(BASE/'sources/TES5Edit/Core/wbDefinitionsCommon.pas'),str(BASE/'sources/TES5Edit/xEdit/xeMainForm.pas')],
      'limitations':['No runtime VFS is claimed by this generator.','Dynamic script-built filenames, script class dependencies and complete dialogue voice coverage require additional evidence.','References that are empty or not typed resource fields are not guessed.']}
    write_json(out,report);print(json.dumps({'status':report['status'],'counts':report['counts'],'errors':len(errors),'output':str(out)},ensure_ascii=False),flush=True)
    return 2 if errors else 0


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
