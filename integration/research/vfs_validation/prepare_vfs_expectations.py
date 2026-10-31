"""Freeze physical MO2-priority expectations without starting any application."""
import argparse
import collections
import json
import os
from pathlib import Path
import sqlite3
import sys
from datetime import datetime,timezone

sys.dont_write_bytecode=True
from vfs_common import *
from legacy_nif_contracts import LegacyNifContracts


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--target',default=str(DEFAULT_TARGET));parser.add_argument('--profile',default='Unified Skyrim');parser.add_argument('--output',required=True)
    parser.add_argument('--feature-seeds',action='append',default=[],help='Final-mode quest_resource_seeds.py --resolve report from an identical enabled plugin context.')
    parser.add_argument('--supplemental-plan',default=str(BASE/'integration/research/supplemental_import/supplemental_import_plan.json'),help='Exact per-file SHA plan for all 47 generated morph projects and bounded supplements.')
    args=parser.parse_args();target=Path(args.target).resolve();profile=target/'profiles'/args.profile;output=safe_output(args.output)
    if injected():raise RuntimeError('Generate expectations outside MO2, not in an injected process.')
    if output.exists():raise FileExistsError('Expectations are immutable; select a new output file: '+str(output))
    legacy_nif=LegacyNifContracts()
    before=controls(target,profile);mods=[(line[1:],target/'mods'/line[1:]) for line in read_text(profile/'modlist.txt').splitlines() if line.startswith('+')]
    physical={};missing=[];raw_count=0
    roots=[('overwrite',target/'overwrite')]+mods+[('Game/Data',target/'Game/Data')]
    for index,(provider,folder) in enumerate(roots):
        if not folder.is_dir():
            if provider not in ('overwrite','Game/Data'):missing.append(str(folder))
            continue
        for relative,path,st in walk(folder):
            raw_count+=1;physical.setdefault(key(relative),{'relative_path':relative,'physical_path':str(path),'provider':provider,'size_bytes':st.st_size,'mtime_ns':st.st_mtime_ns})
        if index%250==0:print('physical roots',index+1,'/',len(roots),'unique paths',len(physical),flush=True)
    enabled,absent=names(target,profile,physical);enabledkeys={key(n) for n in enabled};plugins=[];errors=[]
    for name in enabled:
        r=physical.get(key(name))
        if r is None:errors.append({'kind':'missing_enabled_plugin','plugin':name});continue
        info=plugin_header(r['physical_path']);ranges=owned_id_range(r['physical_path'],len(info['masters']),info['is_light'])
        plugins.append({'name':name,'provider':r['provider'],'physical_path':r['physical_path'],**info,'owned_id_range':ranges})
        if not ranges['light_owned_id_range_valid']:errors.append({'kind':'invalid_light_owned_id_range','plugin':name,'range':ranges})
        for master in info['masters']:
            if key(master) not in enabledkeys:errors.append({'kind':'master_not_enabled','plugin':name,'master':master})
    dlls=[]
    for k,r in physical.items():
        if k.startswith('skse/plugins/') and k.count('/')==2 and k.endswith('.dll'):
            info=dll_info(r['physical_path']);dlls.append({'path_key':k,'relative_path':r['relative_path'],'provider':r['provider'],**info})
            if info['machine']!=0x8664:errors.append({'kind':'runtime_dll_not_x64','path':k,'machine':info['machine']})
    needs_bees=[r['name'] for r in plugins if r['owned_id_range']['requires_extended_esl_low_id_support'] or r['version']>=1.709]
    bees=[r for r in dlls if 'backported' in r['path_key'] and 'esl' in r['path_key']]
    if needs_bees and not bees:errors.append({'kind':'missing_extended_esl_support_for_1_5_97','plugins':needs_bees})
    stock=[]
    for row in json.loads((BASE/'repairs/consistent_stock/manifest.json').read_text(encoding='utf-8')):
        k=key(row['relative'])
        if '/' in k or Path(k).suffix not in ('.bsa','.esm'):continue
        r=physical.get(k)
        if not r:errors.append({'kind':'missing_stock','path':k});continue
        got=digest(r['physical_path']);stock.append({'relative_path':r['relative_path'],'expected_sha256':row['sha256'],'physical_sha256':got,'provider':r['provider'],'bytes':r['size_bytes']})
        if got!=row['sha256']:errors.append({'kind':'incoherent_stock_sha','path':k,'got':got,'expected':row['sha256']})
        print('stock verified',len(stock),'sha',row['relative'],flush=True)
    if len(stock)!=23:errors.append({'kind':'stock_set_count','got':len(stock),'expected':23})
    archive_names,archive_settings=active_archive_names(profile,enabled,physical)
    archives={key(name):dict(physical[key(name)],order=i) for i,name in enumerate(archive_names)}
    catalog=ResourceCatalog(physical,archives)
    catalog.archive_hashes.update({key(r['relative_path']):r['physical_sha256'] for r in stock if r['relative_path'].lower().endswith('.bsa')})
    seeds,optional,canonical,provenance=resource_seeds();resources=[]
    feature_seed_sources=[];feature_seed_keys=set();documented_feature_source_limitations=[];bounded_exception_provenance={}
    for source in args.feature_seeds:
        source=Path(source).resolve();extra=json.loads(source.read_text(encoding='utf-8'))
        feature_seed_sources.append({'path':str(source),'sha256':digest(source)})
        if extra.get('mode')!='actual_enabled_physical_plugin_winners' or not extra.get('resolution_performed') or extra.get('errors'):
            errors.append({'kind':'feature_seed_report_not_ready','path':str(source),'mode':extra.get('mode'),'errors':extra.get('errors')})
        if extra.get('control_hashes')!=before:errors.append({'kind':'feature_seed_profile_context_changed','path':str(source)})
        context=sqlite3.connect(Path(extra['expectations']).resolve().as_uri()+'?mode=ro',uri=True)
        original=json.loads(context.execute("select value from metadata where key='expectations'").fetchone()[0]);context.close()
        if {key(r['name']):r['sha256'] for r in original['plugins']}!={key(r['name']):r['sha256'] for r in plugins}:
            errors.append({'kind':'feature_seed_plugin_sha_context_changed','path':str(source)})
        documented=extra.get('documented_missing_source_resources',[])
        audit=extra.get('bounded_exception_audit')
        if documented:
            if not audit or audit.get('errors'):errors.append({'kind':'feature_exception_audit_not_ready','path':str(source)})
            else:
                evidence=[audit['manifest']]+audit.get('evidence',[])
                if audit.get('typed_xedit_consumers'):evidence+=audit['typed_xedit_consumers']['provenance']
                for ev in evidence:
                    if digest(ev['path'])!=ev['sha256']:errors.append({'kind':'feature_exception_evidence_changed','path':ev['path']})
                    bounded_exception_provenance[ev['path']]=ev
                for row in documented:
                    if row['case_id'] not in audit['valid_case_ids']:errors.append({'kind':'feature_exception_case_not_validated','case_id':row['case_id']})
                    documented_feature_source_limitations.append(row)
        for r in extra['resolved_runtime_seeds']:
            k=key(r['path_key']);seeds[k].add('feature_typed_and_authored_resources');feature_seed_keys.add(k)
    supplemental_expected={};supplemental_provenance=None
    if args.supplemental_plan:
        source=Path(args.supplemental_plan).resolve();extra=json.loads(source.read_text(encoding='utf-8'))
        supplemental_provenance={'path':str(source),'sha256':digest(source),'counts':extra['counts']}
        if extra.get('schema')!='skyrim.supplemental_import.v1' or len(extra['imports'])!=148:
            errors.append({'kind':'supplemental_plan_invalid','path':str(source)})
        for row in extra['imports']:
            k=key(row['destination_relative'])
            if k in supplemental_expected:errors.append({'kind':'supplemental_duplicate_destination','path':k})
            supplemental_expected[k]=row['source_sha256'];seeds[k].add('bounded_supplemental_import')
            if digest(row['source_path'])!=row['source_sha256']:errors.append({'kind':'supplemental_source_changed','path':row['source_path']})
    for i,(k,tags) in enumerate(sorted(seeds.items())):
        r=catalog.resolve(k)
        if r['kind']=='loose':r['sha256']=digest(r['physical_path'])
        item={'path_key':k,'tags':sorted(tags),'location':r}
        if r['kind']=='missing':errors.append({'kind':'missing_required_resource','path':k})
        if k in supplemental_expected and r.get('sha256')!=supplemental_expected[k]:
            errors.append({'kind':'supplemental_expected_winner_changed','path':k,'actual_sha256':r.get('sha256'),'expected':supplemental_expected[k]})
        if k in canonical:
            item['canonical_rihad_sha256']=canonical[k]
            if r.get('sha256')!=canonical[k]:errors.append({'kind':'rihad_expected_winner_changed','path':k,'actual_sha256':r.get('sha256'),'expected':canonical[k]})
        resources.append(item)
        if i%750==0:print('required resources',i+1,'/',len(seeds),flush=True)
    after=controls(target,profile)
    if before!=after:errors.append({'kind':'profile_changed_during_expectation_generation'})
    slots={'full':sum(not r['is_light'] for r in plugins),'light':sum(r['is_light'] for r in plugins)}
    if slots['full']>254 or slots['light']>4096:errors.append({'kind':'slot_limit','slots':slots})
    metadata={'created_utc':datetime.now(timezone.utc).isoformat(),'target':str(target),'profile':str(profile),
      'scope':'Physical priority expectation only. No actual MO2 VFS pass is claimed by this file.',
      'control_hashes':before,'missing_mod_dirs':missing,'enabled_plugins':enabled,'absent_optional_ccc_entries':absent,
      'plugins':plugins,'dlls':dlls,'slots':slots,'stock23':stock,'resources':resources,'optional_source_morph_paths':sorted(optional),
      'extended_esl_support':{'required_by':needs_bees,'dlls':bees},
      'documented_hkx_extension_slots':documented_hkx_slots(),
      'archive_names':archive_names,'archive_settings':archive_settings,'archive_hashes_required':catalog.archive_hashes,
      'archive_order_limit':'Archive associations use current profile INI and SSE exact plugin-stem / stem - Textures naming; order is inferred without running the game.',
      'equipment_manifest_sources':provenance,'counts':{'physical_roots':len(roots),'physical_candidates':raw_count,'unique_runtime_paths':len(physical),
        'plugins':len(plugins),'dlls':len(dlls),'stock23':len(stock),'required_resources':len(resources),'rihad45':len(canonical),'feature_resource_seed_paths':len(feature_seed_keys)},
      'feature_seed_sources':feature_seed_sources,'errors':errors}
    metadata['supplemental_resource_manifest']=supplemental_provenance
    metadata['counts']['supplemental_required_resource_paths']=len(supplemental_expected)
    metadata['documented_feature_source_limitations']=documented_feature_source_limitations
    metadata['bounded_feature_exception_provenance']=list(bounded_exception_provenance.values())
    metadata['bounded_legacy_nif_format_contract']=legacy_nif.metadata()
    if missing:metadata['errors'].append({'kind':'missing_mod_dirs','paths':missing})
    c=sqlite3.connect(output);c.execute('create table metadata(key text primary key,value text)')
    c.execute('create table files(path_key text primary key,relative_path text,physical_path text,provider text,size_bytes integer,mtime_ns integer)')
    c.executemany('insert into files values(?,?,?,?,?,?)',[(k,r['relative_path'],r['physical_path'],r['provider'],r['size_bytes'],r['mtime_ns']) for k,r in physical.items()])
    c.execute('insert into metadata values(?,?)',('expectations',json.dumps(metadata,ensure_ascii=False)));c.commit();c.close()
    write_json(output.with_suffix('.summary.json'),{k:v for k,v in metadata.items() if k not in ('plugins','dlls','resources','optional_source_morph_paths')})
    print(json.dumps({'status':'EXPECTATIONS_READY' if not errors and not missing else 'EXPECTATIONS_HAVE_FAILURES','output':str(output),'counts':metadata['counts'],'errors':metadata['errors']},ensure_ascii=False),flush=True)
    return 0 if not metadata['errors'] else 2


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8');raise SystemExit(main())
