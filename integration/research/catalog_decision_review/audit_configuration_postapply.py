"""Independent post-application state audit; all runtime/source inputs read only."""
from pathlib import Path
from datetime import datetime,timezone
import collections
import hashlib
import json
import sqlite3
import sys

sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
TARGET=BASE/'UnifiedSkyrim'
POST=OUT/'postapply'
sys.path.insert(0,str(OUT))
from prepare_configuration_rebase_plan import winner


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setting(data,section,key):
    text=data.decode('utf-8-sig');current=None;matches=[]
    for line in text.splitlines():
        stripped=line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):current=stripped[1:-1]
        elif current==section and '=' in line and not stripped.startswith((';','#')):
            left,right=line.split('=',1)
            if left.strip()==key:matches.append(right.strip())
    assert len(matches)==1,(section,key,matches)
    return matches[0]


def main():
    POST.mkdir(exist_ok=True)
    path=OUT/'configuration_rebase/config_rebase_plan.json';plan=json.loads(path.read_text(encoding='utf-8'))
    appliedPath=BASE/'integration/configuration_rebase_applied.json';applied=json.loads(appliedPath.read_text(encoding='utf-8'))
    assert sha(path)==applied['plan_sha256']=='89ed07c5d29abe5315ca00645e3fe84b6df0f0fc908d7fc5108b5f46f4492360'
    rows=[]
    for operation in plan['operations']:
        target=Path(operation['destination']);candidate=Path(operation['staged_candidate']['path'])
        data=target.read_bytes();assert data==candidate.read_bytes()
        assert sha(target)==operation['staged_candidate']['sha256'] and target.stat().st_nlink==1
        original=Path(operation.get('source_read_only',{}).get('path',operation.get('backup',{}).get('path','')))
        expected_before=operation.get('source_read_only',operation.get('before'))
        assert sha(original)==expected_before['sha256']
        expected=original.read_bytes();checks=[]
        for replacement in operation['line_replacements']:
            old=bytes.fromhex(replacement['old_line_bytes_hex']);new=bytes.fromhex(replacement['new_line_bytes_hex'])
            assert expected.count(old)==1
            expected=expected.replace(old,new,1)
            wanted=replacement['new_line'].split('=',1)[1].strip()
            actual=setting(data,replacement['section'],replacement['key']);assert actual==wanted
            checks.append({'section':replacement['section'],'key':replacement['key'],'expected':wanted,'actual':actual,'matches':True})
        assert expected==data
        rows.append({'path':str(target),'sha256':sha(target),'nlink':target.stat().st_nlink,
                     'source_or_backup':str(original),'source_or_backup_sha256':sha(original),'byte_difference_is_exactly_two_declared_lines':True,
                     'encoding_bom_and_other_bytes_preserved':True,'settings':checks})
    # Resolve the same data path independently in both current profiles.
    profile_checks=[]
    for name in ('Unified Skyrim','Unified Build'):
        profile=TARGET/'profiles'/name
        provider,path=winner(profile,'SKSE/Plugins/CrashLogger.ini')
        assert provider=='ZZ86 Verified stale script assignments'
        assert sha(path)=='e766936676882fb17d26c0aa69710468494b70ed58d5832f84453f7acf6a3fe8'
        profile_checks.append({'profile':str(profile),'modlist_sha256':sha(profile/'modlist.txt'),
                               'winner_provider':provider,'winner':str(path),'winner_sha256':sha(path)})
    # Source controls and original physical provider never receive an edit.
    controlsPath=BASE/'integration/source_control_files_before.json'
    controls=json.loads(controlsPath.read_text(encoding='utf-8'));control_checks=[]
    for row in controls:
        actual=sha(row['path']);assert actual==row['sha256']
        control_checks.append({'path':row['path'],'sha256':actual,'matches':True})
    assert len(control_checks)==145
    db=sqlite3.connect((BASE/'integration/files.sqlite').as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    journal=[dict(r) for r in db.execute("select f.*,u.source from files f join units u on u.id=f.unit_id where f.dest_key='game/reshade.ini'")]
    assert len(journal)==1;entry=journal[0]
    source=Path(entry['source'])/entry['relative_path']
    target=TARGET/entry['destination']
    assert entry['storage']=='private' and entry['status']=='materialized' and entry['error'] is None
    assert entry['sha256']==sha(source)==sha(target)=='0f46697ae5601498b6eeecab8332388d26e0276303c575bd079af8794bdda53b'
    assert entry['size_bytes']==target.stat().st_size==2815
    assert entry['mtime_ns']==target.stat().st_mtime_ns
    previous=applied['previous_root_journal_mapping'];originalRoot=Path(previous['source'])/previous['relative_path']
    assert sha(originalRoot)==previous['sha256']=='1fa6393e14e9b923f2090c2f323aa46fdd2753015983df53c308db9b602a68a5'
    baseline=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True)
    originalCrash=Path(baseline.execute('select path from mods where id=4459').fetchone()[0])/'SKSE/Plugins/CrashLogger.ini'
    assert sha(originalCrash)=='288c775d9ff77dfeb8fadfa30281a421aec1dcadddb732af2c3d24c49fdf127f'
    scans=[];classified=[]
    for directory in ('final_profile','build_profile'):
        scanPath=POST/directory/'active_configuration_absolute_paths.json';scan=json.loads(scanPath.read_text(encoding='utf-8'))
        assert scan['modlist_unchanged'] and not scan['errors'] and not scan['old_source_pack_path_matches']
        assert scan['modlist_sha256_after']==sha(Path(scan['profile'])/'modlist.txt')
        stale=[];categories=collections.Counter()
        for item in scan['absolute_paths']:
            relative=item['relative'].replace('\\','/').casefold();scope=item['scope'];value=item['absolute_path_text']
            if scope=='MO2' or scope in ('final-profile','build-profile') and relative=='skyrimcustom.ini':kind='current_Database_path'
            elif scope in ('final-profile','build-profile') and relative=='skyrim.ini':kind='screenshot_overridden_by_SkyrimCustom'
            elif scope=='game-root' and relative=='reshade.ini':
                assert str(TARGET) in value;kind='verified_rebased_ReShade_path'
            elif relative=='skse/plugins/crashlogger.ini':
                assert str(TARGET) in value and item['provider']=='ZZ86 Verified stale script assignments'
                kind='verified_rebased_CrashLogger_path'
            elif relative in ('cfg/user.json','pgpatcher/cfg/user.json'):kind='preserved_old_offline_ParallaxGen_settings'
            elif relative=='textures/dyndolod/lod/texgen_sse.ini':kind='preserved_TexGen_provenance'
            elif relative=='skse/plugins/improvedcamerase/improvedcamerase.ini':kind='Windows_system_fonts'
            elif relative.startswith(('skse/plugins/dynamicstringdistributor/','interface/translations/')):kind='translation_regex_false_positive'
            elif 'readme' in relative or relative=='sam/menu/spec.yaml' or relative.startswith('scripts/source/') or relative.endswith('cmakelists.txt'):kind='documentation_or_source_example'
            else:
                kind='unclassified';stale.append(item)
            categories[kind]+=1
            classified.append({'scan_profile':scan['profile'],'classification':kind,**item})
        assert not stale,stale
        scans.append({'path':str(scanPath),'sha256':sha(scanPath),'profile':scan['profile'],
                      'winning_data_configurations':scan['unique_winning_data_configurations'],'scanned_files':scan['scanned_files'],
                      'scanned_bytes':scan['scanned_bytes'],'literal_absolute_path_matches':scan['absolute_path_matches'],
                      'old_original_pack_path_matches':0,'unclassified_matches':0,'read_errors':0,'classification_counts':dict(categories)})
    report={'status':'POST_APPLY_READ_ONLY_STATE_PASS','utc':datetime.now(timezone.utc).isoformat(),
            'applied_receipt':{'path':str(appliedPath),'sha256':sha(appliedPath)},'operations':rows,'profile_winners':profile_checks,
            'root_journal':entry,'root_journal_source_resolves_current_private_candidate':True,
            'original_ReShade':{'path':str(originalRoot),'sha256':sha(originalRoot),'unchanged':True},
            'original_CrashLogger':{'path':str(originalCrash),'sha256':sha(originalCrash),'unchanged':True},
            'baseline_CrashLogger':plan['operations'][1]['source_read_only'],'original_controls':control_checks,
            'original_control_count':145,'original_controls_unchanged':True,'configuration_rescans':scans,
            'directories':[{'path':r['path'],'exists':Path(r['path']).is_dir()} for r in plan['directory_creation_list']],
            'game_started_by_this_audit':False,
            'limits':['Current physical profile-priority resolution, not an injected usvfs probe or game execution.',
                      'Rescans cover loose configured text extensions plus immediate Game/profile/MO2 configurations. Offline-tool provenance and documentation examples remain preserved.',
                      'The prior failed application rollback is described in the parent receipt/history; this independent audit proves current applied state, backups and source integrity, not past execution events.']}
    assert all(r['exists'] for r in report['directories'])
    (POST/'configuration_rebase_postapply_verified.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (POST/'classified_configuration_paths.json').write_text(json.dumps(classified,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('POST_APPLY PASS:4 exact values,2 profiles,private nlink1,root journal+backup+2originalsources,145controls unchanged;2 full config rescans pass')


if __name__=='__main__':main()
