"""Read-only final-scope catalogue audit; never invokes the catalogue writer."""
from pathlib import Path
from datetime import datetime,timezone
import ast
import collections
import csv
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata

sys.dont_write_bytecode=True
BASE=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
TARGET=BASE/'UnifiedSkyrim'


def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def key(s):return unicodedata.normalize('NFC',str(s)).casefold()


def main():
    source_path=BASE/'integration/catalog.py';source_text=source_path.read_text(encoding='utf-8')
    category_node=next(x for x in ast.parse(source_text).body if isinstance(x,ast.FunctionDef) and x.name=='category')
    env={'re':re};exec(compile(ast.Module(body=[category_node],type_ignores=[]),str(source_path),'exec'),env)
    category=env['category']
    db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    originals=[dict(r) for r in db.execute('''select m.*,p.name pack,pm.enabled original_enabled,pm.list_order
      from mods m join packs p on p.id=m.pack_id
      left join profiles pr on pr.pack_id=p.id and pr.is_selected=1
      left join profile_mods pm on pm.mod_id=m.id and pm.profile_id=pr.id order by m.id''')]
    assert len(originals)==6495 and len({r['id'] for r in originals})==6495
    baseline=json.loads((BASE/'integration/baseline_mods.json').read_text(encoding='utf-8'));base={r['id']:r for r in baseline}
    raw_overrides=json.loads((BASE/'integration/decision_overrides.json').read_text(encoding='utf-8'))
    merged={};override_rows=collections.defaultdict(list)
    for r in raw_overrides:
        mid=int(r['mod_id']);override_rows[mid].append(r)
        if mid not in merged:merged[mid]=dict(r);continue
        prior=merged[mid];assert prior['decision']==r['decision']
        for field in ('reason','directory','evidence'):
            vals=list(dict.fromkeys(v for v in (prior.get(field),r.get(field)) if v))
            if vals:prior[field]='; '.join(vals)
    hashes={r['mod_id']:dict(r) for r in db.execute("select * from mod_tree_hashes where status='complete'")}
    for r in db.execute("select * from mod_tree_hashes where content_sha256 is not null and content_sha256<>''"):
        if r['status'] in ('ok','complete','verified'):hashes[r['mod_id']]=dict(r)
    by_hash=collections.defaultdict(list)
    for mid in base:
        if mid in hashes:by_hash[hashes[mid]['content_sha256']].append(mid)
    profiles={}
    for name in ('Unified Skyrim','Unified Build'):
        folder=TARGET/'profiles'/name
        mods={key(line[1:]):line.startswith('+') for line in (folder/'modlist.txt').read_text(encoding='utf-8-sig').splitlines() if line.startswith(('+','-'))}
        plugins={key(line[1:]):line[1:] for line in (folder/'plugins.txt').read_text(encoding='utf-8-sig').splitlines() if line.startswith('*')}
        profiles[name]={'folder':str(folder),'mod_states':mods,'plugins':plugins,
            'modlist_sha256':sha(folder/'modlist.txt'),'plugins_sha256':sha(folder/'plugins.txt'),
            'enabled_mod_directories':sum(mods.values()),'active_explicit_plugins':len(plugins)}
    rows=[]
    for mod in originals:
        mid=mod['id'];rep=None;directory=base[mid]['directory'] if mid in base else None
        if mid in base:decision='enabled_baseline';group='selected_baseline'
        elif mid in hashes and hashes[mid]['content_sha256'] in by_hash:
            rep=by_hash[hashes[mid]['content_sha256']][0];decision='deduplicated_exact';group='full_mod_tree_sha256'
        elif not mod['original_enabled']:decision='retained_in_catalog';group='originally_disabled'
        else:decision='not_enabled_pending_or_alternative';group=category(mod['name'])
        before=decision
        if mid in merged:
            change=merged[mid];decision=change['decision'];group=change.get('category',group)
            directory=change.get('directory',directory);rep=change.get('representative_mod_id',rep)
        if decision=='deduplicated_exact' and rep in merged:
            representative_decision=merged[rep]['decision']
            if representative_decision.startswith('disabled_'):
                decision='retained_exact_duplicate_of_disabled_source'
            elif representative_decision=='replaced_by_regenerated_output':
                decision='retained_exact_duplicate_of_replaced_generated_output'
        final='retained_source_alternative_not_adopted' if decision=='not_enabled_pending_or_alternative' else decision
        rows.append({'mod_id':mid,'pack':mod['pack'],'name':mod['name'],'source_path':mod['path'],'source_exists':Path(mod['path']).is_dir(),
            'original_enabled':mod['original_enabled'],'initial_decision':before,'wip_decision':decision,'final_decision_preview':final,
            'category':group,'representative_mod_id':rep,'directory':directory,'override':merged.get(mid)})
    by_id={r['mod_id']:r for r in rows};issues=[];base_links=[];temporary_build_exclusions=[]
    for mid,r in base.items():
        dest=TARGET/'mods'/r['directory'];states={name:p['mod_states'].get(key(r['directory'])) for name,p in profiles.items()}
        item={'mod_id':mid,'directory':r['directory'],'exists':dest.is_dir(),'is_reparse':bool(getattr(dest.lstat(),'st_file_attributes',0)&0x400) if dest.exists() else None,
              'catalogue_preview_decision':by_id[mid]['wip_decision'],'profile_enabled':states}
        base_links.append(item)
        if not item['exists']:issues.append({'kind':'MISSING_BASELINE_DIRECTORY','mod_id':mid,'directory':r['directory']})
        if by_id[mid]['wip_decision']=='enabled_baseline' and not all(v is True for v in states.values()):
            item={'kind':'BASELINE_LABEL_NOT_ACTUALLY_ENABLED','mod_id':mid,'directory':r['directory'],'states':states}
            if mid in (5861,4621) and states=={'Unified Skyrim':True,'Unified Build':False}:
                item['classification']='Known temporary Build-only exclusion of old Synthesis/DynDOLOD generation inputs; final profile still enabled pending replacement'
                temporary_build_exclusions.append(item)
            else:issues.append(item)
    dedup_invalid=[]
    for r in rows:
        if r['wip_decision']!='deduplicated_exact':continue
        rep=r['representative_mod_id'];representative=by_id[rep];directory=base[rep]['directory']
        enabled={name:p['mod_states'].get(key(directory)) for name,p in profiles.items()}
        if representative['wip_decision']!='enabled_baseline' or not all(v is True for v in enabled.values()):
            dedup_invalid.append({'mod_id':r['mod_id'],'pack':r['pack'],'name':r['name'],'representative_mod_id':rep,'representative_name':representative['name'],
                                  'representative_decision':representative['wip_decision'],'representative_directory':directory,'profile_enabled':enabled})
    equipment=json.loads((BASE/'integration/imported_equipment.json').read_text(encoding='utf-8'))
    features=json.loads((BASE/'integration/imported_features.json').read_text(encoding='utf-8'))
    selected=equipment['plugins']+features['plugins'];plugin_links=[]
    profile=profiles['Unified Build'];modlines=(Path(profile['folder'])/'modlist.txt').read_text(encoding='utf-8-sig').splitlines()
    active_dirs=[line[1:] for line in modlines if line.startswith('+')]
    root_files={}
    for directory in active_dirs:
        folder=TARGET/'mods'/directory
        if not folder.is_dir():continue
        for p in folder.iterdir():
            if p.is_file() and p.suffix.casefold() in ('.esm','.esp','.esl'):root_files.setdefault(key(p.name),(directory,p))
    for p in (TARGET/'Game/Data').iterdir():
        if p.is_file() and p.suffix.casefold() in ('.esm','.esp','.esl'):root_files.setdefault(key(p.name),('Game/Data',p))
    for r in selected:
        name=r['name'];found=root_files.get(key(name));mid=r['source_mod_id'];decision=by_id[mid]
        expected_dir=r.get('layer',equipment['layer'])
        dirs=decision['directory'].split('; ') if decision['directory'] else []
        expected=TARGET/'mods'/expected_dir/name
        linked={'plugin':name,'source_mod_id':mid,'decision':decision['wip_decision'],'catalogue_directories':dirs,'expected_directory':expected_dir,
                'active_in_profiles':{n:key(name) in p['plugins'] for n,p in profiles.items()},'selected_file_exists':expected.is_file(),
                'winner_directory':found[0] if found else None,'winner_path':str(found[1]) if found else None,
                'winner_sha256':sha(found[1]) if found else None,
                'expected_directory_retained_in_merged_catalogue':expected_dir in dirs}
        plugin_links.append(linked)
        if not all(linked['active_in_profiles'].values()) or not linked['selected_file_exists'] or not linked['expected_directory_retained_in_merged_catalogue']:
            issues.append({'kind':'ADOPTED_PLUGIN_LINKAGE_PROBLEM','detail':linked})
    for mid,r in merged.items():
        if r['decision'].startswith(('adopted','partially_adopted')):
            for directory in r.get('directory','').split('; '):
                if not directory:continue
                if not (TARGET/'mods'/directory).is_dir() or not all(p['mod_states'].get(key(directory)) is True for p in profiles.values()):
                    issues.append({'kind':'ADOPTED_DIRECTORY_MISSING_OR_DISABLED','mod_id':mid,'directory':directory})
    summary=json.loads((BASE/'integration/catalog_summary.json').read_text(encoding='utf-8'))
    persisted=sqlite3.connect((BASE/'integration/integration.sqlite').as_uri()+'?mode=ro',uri=True)
    persisted.row_factory=sqlite3.Row;persisted_rows=[dict(r) for r in persisted.execute('select * from mod_decisions')]
    mismatches=[]
    for r in persisted_rows:
        current=by_id[r['mod_id']]
        if r['decision']!=current['wip_decision'] or r.get('directory')!=current['directory']:
            mismatches.append({'mod_id':r['mod_id'],'persisted_decision':r['decision'],'current_wip_logic':current['wip_decision'],
                               'persisted_directory':r.get('directory'),'current_directory':current['directory']})
    duplicate={str(mid):{'raw_rows':vals,'merged':merged[mid]} for mid,vals in override_rows.items() if len(vals)>1}
    assert merged[1666]['directory']=='F01 Wyrmstooth; F02 The Forgotten City'
    assert all(n in merged[1666]['reason'] for n in ('DBM_Wyrmstooth_Patch.esp','DBM_ForgottenCity_Patch.esp'))
    output={'written_utc':datetime.now(timezone.utc).isoformat(),'status':'READ_ONLY_LOGIC_AND_CURRENT_PHYSICAL_LINKAGE_AUDIT',
      'catalogue_generator':str(source_path),'catalogue_generator_sha256':sha(source_path),
      'original_mods':len(originals),'original_pack_counts':dict(collections.Counter(r['pack'] for r in rows)),
      'missing_original_source_directories':[r['mod_id'] for r in rows if not r['source_exists']],
      'wip_decision_preview':dict(collections.Counter(r['wip_decision'] for r in rows)),
      'final_flag_decision_preview':dict(collections.Counter(r['final_decision_preview'] for r in rows)),
      'raw_override_rows':len(raw_overrides),'unique_override_mods':len(merged),'duplicate_override_merges':duplicate,
      'baseline_directories':base_links,'deduplicated_rows_with_inactive_or_relabelled_representatives':dedup_invalid,
      'temporary_build_only_generation_exclusions':temporary_build_exclusions,
      'profile_snapshots':{n:{k:v for k,v in p.items() if k not in ('mod_states','plugins')} for n,p in profiles.items()},
      'adopted_plugins':{'equipment_count':len(equipment['plugins']),'feature_count':len(features['plugins']),'links':plugin_links},
      'persisted_catalogue_summary':summary,'persisted_rows':len(persisted_rows),'persisted_differences_from_current_logic':mismatches,
      'issues':issues,'limits':[
          'The writer was not invoked. Current shared CSV/DB may deliberately precede override imports; final --final must be run only after completion.',
          'Category regex is triage; it does not prove cross-language identity, incompatibility or absence of valuable unselected content.',
          'Whole-tree SHA identity excludes meta.ini and describes original content, not final winning overlay files or game runtime behavior.',
          'Directory active and plugin active are distinct. Baseline mods may contain disabled optional ESPs or files superseded by repaired/generated overlays.',
          'Materialized selected sources use journaled NTFS hardlinks for immutable asset types and private copies for writable/plugin inputs, not directory junctions.',
          'No new BSA-wide hashing or game launch was done in this read-only catalogue audit.'
      ]}
    (OUT/'catalogue_logic_and_linkage.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'final_decision_preview.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Originals',len(rows),'baseline',len(base),'overrides',len(raw_overrides),'unique',len(merged))
    print('WIP preview',output['wip_decision_preview']);print('Final preview',output['final_flag_decision_preview'])
    print('Persisted stale rows',len(mismatches),'linkage issues',len(issues),'dedup inactive representatives',len(dedup_invalid))
    for r in issues[:12]:print(r)
    for r in dedup_invalid[:8]:print('DEDUP_REP',r)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
