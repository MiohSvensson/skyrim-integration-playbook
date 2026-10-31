"""Configure a private MO2 application and local profile; never start the game."""
import hashlib
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from materialize import BASE, TARGET, guard_destination

PROFILE = 'Unified Skyrim'


def main():
    marker = TARGET/'.integration-managed.json'
    assert marker.is_file(), 'Staging ownership marker is required'
    app = TARGET/'MO2'
    if not app.exists():
        shutil.copytree(BASE/'tools/MO2-official-2.5.2', app)
    assert not (app/'plugins/fomod_plus_installer.dll').exists()
    assert not any('rootbuilder' in p.name.casefold() for p in (app/'plugins').iterdir())
    profile = TARGET/'profiles'/PROFILE
    profile.mkdir(parents=True, exist_ok=True)
    source = BASE/'mo2_vfs/TuLED/instance/profiles/Database restored upstream'
    for name in ['plugins.txt', 'loadorder.txt', 'archives.txt', 'Skyrim.ini', 'SkyrimPrefs.ini', 'SkyrimCustom.ini', 'initweaks.ini']:
        file = source/name
        dest = guard_destination(profile/name)
        if not dest.exists() and file.is_file():
            shutil.copyfile(file, dest)
    mods = json.loads((BASE/'integration/baseline_mods.json').read_text(encoding='utf-8'))
    # MO2 stores the left pane in descending priority.
    lines = ['# TuLED complete baseline; source names and decisions are in integration/baseline_mods.json',
             '+ZZ TuLED original overwrite'] + ['+'+m['directory'] for m in reversed(mods)]
    (profile/'modlist.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    (profile/'settings.ini').write_text('[General]\nLocalSaves=true\nLocalSettings=true\nAutomaticArchiveInvalidation=false\n', encoding='utf-8')
    (profile/'saves').mkdir(exist_ok=True)
    for name in ['overwrite', 'downloads', 'cache/web', 'cache/xedit', 'logs', 'tmp', 'outputs', 'screenshots',
                 'sandbox/APPDATA', 'sandbox/LOCALAPPDATA', 'sandbox/TEMP']:
        (TARGET/name).mkdir(parents=True, exist_ok=True)
    # Preserve the chosen base language/font/distributor stack and graphics settings.
    custom = profile/'SkyrimCustom.ini'
    if custom.exists():
        text = custom.read_text(encoding='utf-8-sig')
        text = '\n'.join('sScreenShotBaseName='+str(TARGET/'screenshots/ScreenShot') if line.lower().startswith('sscreenshotbasename=') else line for line in text.splitlines())+'\n'
        custom.write_text(text, encoding='utf-8')
    gamepath = str(TARGET/'Game').replace('\\', '\\\\')
    ini = f'''[General]
gameName=Skyrim Special Edition
selected_profile=@ByteArray({PROFILE})
gamePath=@ByteArray({gamepath})
game_edition=Steam
version=2.5.2
first_start=false
backup_install=false

[PluginPersistance]
Python%20Proxy\\tryInit=false
Configurator\\enabled=false

[Settings]
base_directory={TARGET.as_posix()}
mod_directory={(TARGET/'mods').as_posix()}
profiles_directory={(TARGET/'profiles').as_posix()}
overwrite_directory={(TARGET/'overwrite').as_posix()}
download_directory={(TARGET/'downloads').as_posix()}
cache_directory={(TARGET/'cache/web').as_posix()}
offline_mode=true
check_for_updates=false
profile_local_inis=true
profile_local_saves=true
profile_archive_invalidation=false
skip_file_suffixes=.mohidden
skip_directories=.git
log_level=1
lock_gui=true

[customExecutables]
size=2
1\\title=SKSE 2.0.20 - Unified Skyrim
1\\binary={(TARGET/'Game/skse64_loader.exe').as_posix()}
1\\workingDirectory={(TARGET/'Game').as_posix()}
1\\arguments=
1\\hide=false
1\\toolbar=false
1\\ownicon=false
1\\steamAppID=489830
2\\title=xEdit - Unified Skyrim
2\\binary={(BASE/'tools/xedit/SSEEdit64.exe').as_posix()}
2\\workingDirectory={(BASE/'tools/xedit').as_posix()}
2\\arguments=-SSE -D:\"{(TARGET/'Game/Data').as_posix()}\" -P:\"{(profile/'plugins.txt').as_posix()}\" -I:\"{(profile/'Skyrim.ini').as_posix()}\" -C:\"{(TARGET/'cache/xedit').as_posix()}\"
2\\hide=false
2\\toolbar=false
2\\ownicon=false
'''
    (app/'ModOrganizer.ini').write_text(ini, encoding='utf-8')
    (app/'portable.txt').touch(exist_ok=True)
    data = {'profile': str(profile), 'mo2': str(app/'ModOrganizer.exe'),
            'game': str(TARGET/'Game'), 'base_mods': len(mods),
            'mo2_exe_sha256': hashlib.sha256((app/'ModOrganizer.exe').read_bytes()).hexdigest(),
            'game_was_not_started': True,
            'note': 'Initial complete baseline configuration; additions/repairs and final validation still pending'}
    (BASE/'integration/runtime_configuration.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
