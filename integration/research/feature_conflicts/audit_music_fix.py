"""Check the actual MusicFix compiled script and its exact soft references."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
from analyze_fields import BASE, OUT, scan


def main():
    source = Path(r'E:\stock\Skyrim collection\Anno\iniRePather-Skyrim\mods\遗忘之城音频修复-The Forgotten City Music Bug Fixer')
    output = OUT / 'music_fix'
    for folder in ('pex', 'psc', 'asm', 'tmp'):
        (output / folder).mkdir(parents=True, exist_ok=True)
    original = source / 'Scripts/aaa_FCTriggerBoxScript.pex'
    pex = output / 'pex' / original.name
    pex.write_bytes(original.read_bytes())
    assert hashlib.sha256(pex.read_bytes()).digest() == hashlib.sha256(original.read_bytes()).digest()
    env = os.environ.copy()
    env['TEMP'] = env['TMP'] = str(output / 'tmp')
    tool = BASE / 'tools/Champollion-1.3.2/Champollion.exe'
    args = [str(tool), str(pex), '-p', str(output / 'psc'), '-a', str(output / 'asm'), '--no-debug-line']
    run = subprocess.run(args, cwd=output, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (output / 'decompiler.log').write_bytes(run.stdout)
    assert run.returncode == 0 and b'ERROR:' not in run.stdout
    psc = output / 'psc' / 'aaa_FCTriggerBoxScript.psc'
    text = psc.read_text(encoding='utf-8-sig')
    # Champollion prints decimal integer literals for these calls.
    calls = re.findall(r'GetFormFromFile\((0x[0-9a-fA-F]+|\d+),\s*"([^"\n]+)"', text, re.I)
    audit = json.loads((OUT / 'raw_field_comparison.json').read_text(encoding='utf-8'))
    feature = next(f for f in audit['features'] if f['plugin'] == 'ForgottenCity.esp')
    keys = {(name.casefold(), int(value, 0) & 0xFFFFFF) for value, name in calls}
    records, _, _ = scan(feature['path'], wanted=keys)
    refs = []
    for value, name in calls:
        key = (name.casefold(), int(value, 0) & 0xFFFFFF)
        r = records.get(key)
        refs.append({'literal': value, 'plugin': name, 'object_id': f'{key[1]:06X}', 'found': bool(r),
                     'signature': r['signature'] if r else None,
                     'edid': next((v.rstrip(b'\0').decode('utf-8') for t, v in r['fields'] if t == 'EDID'), '') if r else None})
    supplied = source / 'Source/Scripts/aaa_FCTriggerBoxScript.psc'
    result = {'pex': str(original), 'pex_sha256': hashlib.sha256(original.read_bytes()).hexdigest(),
              'copied_identical_pex': str(pex), 'decompiler': str(tool), 'decompiler_sha256': hashlib.sha256(tool.read_bytes()).hexdigest(),
              'supplied_source': str(supplied), 'supplied_source_sha256': hashlib.sha256(supplied.read_bytes()).hexdigest(),
              'decompiled': str(psc), 'decompiled_sha256': hashlib.sha256(psc.read_bytes()).hexdigest(),
              'return_code': run.returncode, 'lookup_calls': refs,
              'soft_dependency': 'GetModByName/GetFormFromFile ForgottenCity.esp; no hard MAST, must ship/load with ForgottenCity and unchanged filename.',
              'scope': 'Static compiled-script literals mapped by lower 24-bit object IDs against the exact selected ForgottenCity plugin; no in-game trigger/music validation.'}
    (output / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    assert len(refs) == 10 and all(r['found'] for r in refs), refs
    assert [r['signature'] for r in refs].count('QUST') == 1 and [r['signature'] for r in refs].count('MUSC') == 9
    print('MusicFix compiled lookups verified:', len(refs), 'target records')


if __name__ == '__main__':
    main()
