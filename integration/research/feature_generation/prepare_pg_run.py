"""Prepare a fresh private incoming-only PG run; never launches the tool or MO2."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;DB=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'lod_update'))
from runtime_common import final_inputs,sha,TARGET

def main():
    p=argparse.ArgumentParser();p.add_argument('--profile',choices=['Unified Build','Unified Skyrim'],default='Unified Build');p.add_argument('--run-name',required=True)
    p.add_argument('--source-exclusions');p.add_argument('--accept-exclusion-sha');a=p.parse_args();assert re.fullmatch('[A-Za-z0-9_-]+',a.run_name)
    exclusions=[];exclusion_decision=None
    if a.source_exclusions:
        proposal=Path(a.source_exclusions).resolve();assert proposal.is_relative_to(OUT) and sha(proposal)==a.accept_exclusion_sha,'Explicit exact proposal SHA required'
        review=json.loads(proposal.read_text(encoding='utf8'));assert review['reader_gaps']==0 and review['all_3842_sources_attempted']
        exclusions=review['proposed_exclusions'];assert len({r['path_key'] for r in exclusions})==len(exclusions)
        assert all(re.fullmatch('[0-9a-f]{64}',r['source_sha256']) and r['recommended_action']=='EXCLUDE_FROM_PRIVATE_PG_KEEP_AUTHOR_ORIGINAL_BYTES' and r['source_repaired'] is False for r in exclusions)
        exclusion_decision={'proposal':str(proposal),'sha256':sha(proposal),'accepted_by_explicit_exact_SHA_argument':True,'action':'PG exclusion only. Preserve all effective source assets and report source limitations without repair claim.'}
    else:assert a.accept_exclusion_sha is None
    profile,mods,plugins=final_inputs(a.profile);run=OUT/'pg_runs'/a.run_name;assert not run.exists(),'Use fresh run name';run.mkdir(parents=True)
    staged=json.loads((OUT/'private_pg_tool_manifest.json').read_text());source=Path(staged['destination']);tool=run/'tool';files=[]
    for r in staged['files']:
        src=Path(r['destination']);assert sha(src)==r['destination_sha256'];dest=tool/src.relative_to(source);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dest);assert dest.stat().st_nlink==1 and sha(dest)==r['destination_sha256'];files.append({'path':str(dest),'sha256':sha(dest),'bytes':dest.stat().st_size})
    allow=json.loads((OUT/'incoming_effective_mesh_allowlist.json').read_text());excluded='meshes\\architecture\\revenant\\castle\\slumn\\whgrayquarter04.nif'
    excluded_paths={r['path_key'].lower().replace('\\','/') for r in exclusions};assert excluded_paths<={s.lower().replace('\\','/') for s in allow}
    allow=[s for s in allow if s.lower().replace('\\','/') not in excluded_paths]
    template=DB.parent/'TuLED/File Mod Skyrim SE/overwrite/PGPatcher/cfg/user.json';config=json.loads(template.read_text());params=config['params'];params['game']['dir']=str(TARGET/'Game');params['modmanager'].update(type=2,mo2instancedir=str(TARGET/'MO2'),mo2useloosefileorder=True)
    params['output'].update(dir=str(run/'output'),zip=False);params['meshrules']['allowlist']=allow;params['meshrules']['blocklist'].extend([excluded]+[s.replace('/','\\') for s in sorted(excluded_paths)])
    params['shaderpatcher'].update(parallax=False,complexmaterial=False,truepbr=True,truepbr_checkpaths=True,truepbr_printnonexistentpaths=True)
    params['shadertransforms'].update(parallaxtocm=False,parallaxtocm_onlywhenrequired=True)
    params['postpatcher'].update(fixsss=False,hairflowmap=False);params['prepatcher'].update(disablemlp=False,fixmeshlighting=False)
    params['processing'].update(bsa=True,enabledebuglogging=True,enabletracelogging=True,highmem=False,multithread=True,pluginesmify=False,pluginpatching=True)
    cfg=tool/'cfg/user.json';cfg.parent.mkdir(exist_ok=True);cfg.write_text(json.dumps(config,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(run/'output').mkdir()
    watched=['plugins.txt','modlist.txt','loadorder.txt','Skyrim.ini','SkyrimPrefs.ini','SkyrimCustom.ini','settings.ini','archives.txt'];snapshot={n:sha(profile/n) for n in watched if (profile/n).exists()}
    rules=json.loads((OUT/'active_PBR_rules.json').read_text(encoding='utf-8'));rule_files=[{'path':r['path'],'sha256':sha(r['path'])} for r in rules]
    warnings=[]
    if any(r['name_key']=='dyndolod.esp' for r in plugins):warnings.append('PG author refuses active DynDOLOD.esp: use a generation profile with old DynDOLOD outputs disabled.')
    for name,folder in mods:
        if 'texgen' in name.lower() and 'output' in name.lower():warnings.append('Disable old TexGen output layer before actual PG per author workflow: '+name)
    manifest={'status':'PREPARED_PRIVATE_INCOMING_PG_NOT_EXECUTED','profile':a.profile,'profile_path':str(profile),'profile_sha256':snapshot,'plugins':plugins,'run':str(run),'tool':str(tool/'PGPatcher.exe'),
        'tool_files':files,'user_config':str(cfg),'user_config_sha256':sha(cfg),'config_template_source':str(template),'config_template_sha256':sha(template),'rule_files':rule_files,
        'allowlist_source_sha256':sha(OUT/'incoming_effective_mesh_allowlist.json'),'PBR_closure_sha256':sha(OUT/'pbr_texture_closure.json'),'CS_settings_evidence_sha256':sha(OUT/'runtime_renderer_settings.json'),
        'namespace_ledger_sha256':sha(OUT/'PGMutagen_namespace_ledger.json'),'expected_output_names':{'TXST_owner':'DBPatcher.esp','override_regex':'^DB_[1-9][0-9]*\\.esp$'},
        'output':str(run/'output'),'expected_mesh_allowlist':allow,'blocked_single_mesh':excluded,'source_exclusions':exclusions,'source_exclusion_decision':exclusion_decision,'net8_root':str(OUT/'tools/dotnet8'),'net8_version':'8.0.33',
        'cache_policy':{'explicit_owned_paths':['cfg','log','output','tmp','appdata','localappdata','symbols'],'database_only_formal_run_blocked':False,'os_driver_cache_boundary_acknowledged':True,'os_driver_cache_boundary':'PG0.9.9.5 unconditionally initializes hardware D3D11 and a compute shader. Windows/NVIDIA may maintain an OS-managed driver shader cache outside Database. Parent explicitly accepted this OS-managed boundary; every tool-controlled temp/cache/log/output remains in Database. Do not change global GPU/security/privacy settings.',
            'KnownFolder_usage':'BethesdaGame uses actual Documents/LocalAppData KnownFolders to read INIs/plugins.txt, not as an explicit application write cache. Child must prove those VFS reads resolve to the frozen profile; environment override alone is not accepted.',
            'texture_generation':'CM/parallax transforms, FixSSS and hairflowmap disabled. Only existing TruePBR texture paths/NIF/material patching; author unconditionally copies its fixed dynamic black cubemap asset. GPU initialization remains mandatory.'},
        'source_native_preseed_note':'Native main.cpp still calls PopulateObjs(output/PGPatcher.esp). Fresh output is mandatory and that legacy seed file must be absent, so no stale/base TXST IDs are imported. Managed new ModKey and written filename are both DBPatcher.esp; split names/new SkyrimMod keys both DB_<n>.esp. No resume or incremental overwrite supported.',
        'required_before_launch':warnings,'trace_policy':'Required: native loaded rule sequence + per mesh/blockID/name/3DIndex texture slots/winning config. Preserve all PGPatcher*.log rotations; no new native helper is used.','reserve_GiB':32,'output_budget_GiB':5,'root_launch':['python','Database/integration/run_mo2_child.py','--profile',a.profile,'FRESH_TASK','Database/integration/logged_child.py','FRESH_TASK',str(OUT/'pg_child.py'),'--manifest',str(run/'manifest.json'),'--run-tool']}
    assert snapshot=={n:sha(profile/n) for n in snapshot},'Profile drift';(run/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'run':str(run),'tool_files':len(files),'allowlist':len(allow),'blocked_single_mesh':excluded,'required_before_launch':warnings},ensure_ascii=True))
if __name__=='__main__':main()
