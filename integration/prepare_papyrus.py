"""Private installed compiler and unmodified author/SDK sources, all under Database."""
import hashlib
import json
import shutil
from pathlib import Path

from materialize import BASE, TARGET, add_unit, build, connect, sha, utc

compiler_source = BASE.parent/'TuLED/File Mod Skyrim SE/mods/Creation Kit/Root/Papyrus Compiler'
sdk_source = BASE.parent/'TuLED/File Mod Skyrim SE/mods/Creation Kit - Source/Scripts/Source'
c = connect()
for unit, source, destination in [
    ('papyrus_compiler', compiler_source, 'tools/Papyrus/Compiler'),
    ('papyrus_sdk', sdk_source, 'tools/Papyrus/SDK'),
]:
    if not c.execute('select 1 from units where id=?', (unit,)).fetchone():
        add_unit(c, unit, source, destination, 'Private installed Papyrus tool/SDK; compiler only, never Creation Kit or Skyrim')
build(c)
c.close()
task = TARGET/'validation/moonstar_author_compile'
for name in ['source', 'output', 'decompiled', 'assembly', 'tmp']:
    (task/name).mkdir(parents=True, exist_ok=True)
source = BASE/'integration/research/vfs_validation/moonstar_author_source/MASLuckOfTheEmperorScript.psc'
expected = '86b9cef759520ad8b91e0c0faa0a9a0a82f7633155a5e9afbc26d64f90bbdaa5'
assert sha(source) == expected
destination = task/'source'/source.name
if not destination.exists():
    shutil.copyfile(source, destination)
assert sha(destination) == expected
compiler = TARGET/'tools/Papyrus/Compiler/PapyrusCompiler.exe'
sdk = TARGET/'tools/Papyrus/SDK'
command = [str(compiler), str(destination), '-f='+str(sdk/'TESV_Papyrus_Flags.flg'),
           '-i='+str(task/'source')+';'+str(sdk), '-o='+str(task/'output')]
plan = {'utc': utc(), 'compiler': str(compiler), 'compiler_sha256': sha(compiler),
        'sdk': str(sdk), 'author_source': str(source), 'author_source_sha256': expected,
        'source_copy': str(destination), 'command': command,
        'scope': 'Compile the unmodified 421-byte author source; no missing fragment logic is invented.'}
(task/'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(plan, ensure_ascii=False, indent=2))
