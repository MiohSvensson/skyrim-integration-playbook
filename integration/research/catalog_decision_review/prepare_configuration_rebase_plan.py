"""Prepare exact private configuration candidates; never apply to runtime."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import os

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[2]
TARGET=BASE/'UnifiedSkyrim'
LAYER='ZZ86 Verified stale script assignments'


def sha(data):return hashlib.sha256(data).hexdigest()


def info(path):
    data=path.read_bytes();stat=path.stat()
    return {'path':str(path),'sha256':sha(data),'bytes':len(data),'nlink':stat.st_nlink,
            'encoding':'utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8',
            'bom_hex':'efbbbf' if data.startswith(b'\xef\xbb\xbf') else '',
            'newline':'CRLF' if b'\r\n' in data and b'\n' not in data.replace(b'\r\n',b'') else 'mixed_or_LF',
            'terminal_newline':data.endswith(b'\r\n')}


def replaced(data,rules):
    output=data
    for row in rules:
        old=row['old_line'].encode('utf-8')+b'\r\n'
        new=row['new_line'].encode('utf-8')+b'\r\n'
        assert output.count(old)==1,(row,output.count(old))
        output=output.replace(old,new,1)
        row['old_line_bytes_hex']=old.hex();row['new_line_bytes_hex']=new.hex()
    return output


def winner(profile,relative):
    lines=(profile/'modlist.txt').read_text(encoding='utf-8-sig').splitlines()
    for line in lines:
        if line.startswith('+'):
            path=TARGET/'mods'/line[1:]/relative
            if path.is_file():return line[1:],path
    path=TARGET/'Game/Data'/relative
    return ('Game/Data',path) if path.is_file() else (None,None)


def main():
    work=OUT/'configuration_rebase';staged=work/'candidates';staged.mkdir(parents=True,exist_ok=True)
    reshade=TARGET/'Game/ReShade.ini';preset=TARGET/'Game/LED REshade.ini'
    crash=TARGET/'mods/T4459 Crash Logger SSE/SKSE/Plugins/CrashLogger.ini'
    destination=TARGET/'mods'/LAYER/'SKSE/Plugins/CrashLogger.ini'
    assert not destination.exists(),'Private target already exists; require fresh reviewed plan'
    reshadeInfo=info(reshade);crashInfo=info(crash);presetInfo=info(preset)
    assert reshadeInfo['sha256']=='1fa6393e14e9b923f2090c2f323aa46fdd2753015983df53c308db9b602a68a5'
    assert crashInfo['sha256']=='288c775d9ff77dfeb8fadfa30281a421aec1dcadddb732af2c3d24c49fdf127f'
    assert presetInfo['sha256']=='4f826e0dbcb98e981ecb9dad56eb5520e73e301ff64bfc191ce56d86e36c190a'
    assert reshadeInfo['nlink']==1 and reshadeInfo['newline']=='CRLF' and crashInfo['newline']=='CRLF'
    rulesR=[{'section':'GENERAL','key':'IntermediateCachePath',
             'old_line':r'IntermediateCachePath=C:\Users\USER\AppData\Local\Temp\ReShade',
             'new_line':'IntermediateCachePath='+str(TARGET/'cache/reshade')},
            {'section':'GENERAL','key':'PresetPath',
             'old_line':r'PresetPath=C:\Modding 2\File Mod Skyrim SE\mods\Reshade\Root\LED REshade.ini',
             'new_line':'PresetPath='+str(preset)}]
    rulesC=[{'section':'Debug','key':'Symcache Directory','old_line':r'Symcache Directory = c:\symcache',
             'new_line':'Symcache Directory = '+str(TARGET/'cache/crashlogger/symbols')},
            {'section':'Debug','key':'Crashlog Directory','old_line':'Crashlog Directory = ',
             'new_line':'Crashlog Directory = '+str(TARGET/'logs/crashlogger')}]
    stagedR=staged/'ReShade.ini';stagedC=staged/'SKSE/Plugins/CrashLogger.ini';stagedC.parent.mkdir(parents=True,exist_ok=True)
    stagedR.write_bytes(replaced(reshade.read_bytes(),rulesR));stagedC.write_bytes(replaced(crash.read_bytes(),rulesC))
    assert stagedR.read_bytes().startswith(b'[GENERAL]\r\n')
    assert stagedC.read_bytes().startswith(b'\xef\xbb\xbf[Debug]\r\n')
    profiles=[]
    for name in ('Unified Skyrim','Unified Build'):
        folder=TARGET/'profiles'/name;modlist=folder/'modlist.txt'
        provider,path=winner(folder,'SKSE/Plugins/CrashLogger.ini')
        assert provider=='T4459 Crash Logger SSE' and path==crash
        assert '+'+LAYER in modlist.read_text(encoding='utf-8-sig').splitlines()
        profiles.append({'profile':str(folder),'modlist_sha256':sha(modlist.read_bytes()),
                         'overlay_enabled':True,'current_winning_provider':provider,'current_winner':str(path),
                         'current_winner_sha256':sha(path.read_bytes())})
    controls=BASE/'integration/source_control_files_before.json'
    expected=json.loads(controls.read_text(encoding='utf-8'));checks=[]
    for row in expected:
        path=Path(row['path']);actual=sha(path.read_bytes())
        checks.append({'path':str(path),'expected_sha256':row['sha256'],'actual_sha256':actual,'matches':actual==row['sha256']})
    assert len(checks)==145 and all(r['matches'] for r in checks)
    backup=TARGET/'validation/configuration_rebase/backups'/('ReShade.ini.'+reshadeInfo['sha256']+'.before')
    dirs=[TARGET/'cache/reshade',TARGET/'cache/crashlogger/symbols',TARGET/'logs/crashlogger',destination.parent,backup.parent]
    report={'schema':1,'utc':datetime.now(timezone.utc).isoformat(),'status':'PREPARED_REVIEWABLE_PLAN_NOT_APPLIED',
            'owner_application_gate':'Root only; wait until active producer/xEdit/MO2 session has closed. Authoring child never modifies runtime/profile/original files.',
            'scope':'Exactly four INI value changes in two private configuration files; raw-line byte replacements preserve every other byte, BOM, CRLF and trailing newline.',
            'profile_preflight':profiles,
            'original_control_manifest':{'path':str(controls),'sha256':sha(controls.read_bytes()),'files':145,'all_current_hashes_match':True,
                                         'checks':checks},
            'directory_creation_list':[{'path':str(p),'exists_at_plan_time':p.is_dir()} for p in dirs],
            'operations':[
                {'kind':'private_root_atomic_replace','destination':str(reshade),'before':reshadeInfo,'require_nlink':1,
                 'staged_candidate':info(stagedR),'line_replacements':rulesR,
                 'backup':{'path':str(backup),'expected_sha256':reshadeInfo['sha256'],'create_private_copy_before_replacement':True},
                 'atomic_policy':'Copy staged bytes to a new private temporary sibling, verify candidate SHA and nlink1, then os.replace onto exact destination. Never write through an existing hardlink. Refuse if beforeSHA/nlink changed.',
                 'preset_dependency':presetInfo},
                {'kind':'new_private_overlay_file','source_read_only':crashInfo,'destination':str(destination),'destination_must_be_absent':True,
                 'layer':LAYER,'layer_already_enabled_in_both_profiles':True,'staged_candidate':info(stagedC),'line_replacements':rulesC,
                 'atomic_policy':'Create parent directories, copy staged bytes into a new private temporary sibling, verify SHA/nlink1, then atomically create destination only while absent; refuse unexpected existing target. Never edit, replace or hardlink the baseline provider. Re-resolve both profiles and require this exact overlay as winning configuration.'}],
            'after_application_checks':[
                'Both destination SHA equal their staged candidate SHA; new files have nlink1.',
                'Original T4459 source SHA and all145 original control file hashes unchanged.',
                'All unrelated INI bytes/BOM/line endings equal source except exactly the four listed raw lines.',
                'Both profiles resolve CrashLogger.ini to ZZ86; do not edit any modlist or plugin list.',
                'ReShade PresetPath resolves actual guarded Game/LED REshade.ini; configured cache/log directories all inside Database.',
                'Run final current-configuration scan after final producer/install steps; do not treat pre-application reports as post-application proof.'],
            'preserved_nonruntime_metadata':['Two old ParallaxGen user.json files and TexGen provenance remain untouched; final generation must use its own fresh guarded configuration.'],
            'game_was_not_started':True}
    (work/'config_rebase_plan.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('PREPARED ONLY:',work/'config_rebase_plan.json')
    for p in (stagedR,stagedC):print(p.name,sha(p.read_bytes()),'bytes',p.stat().st_size,'nlink',p.stat().st_nlink)
    print('Original controls145/145 unchanged; runtime destinations not modified')


if __name__=='__main__':main()
