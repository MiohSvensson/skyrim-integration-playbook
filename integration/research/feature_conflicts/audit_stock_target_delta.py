"""Mark old TuLED vs coherent stock changes at every selected feature target."""
from pathlib import Path
import json
import sys

sys.dont_write_bytecode = True
from analyze_fields import BASE, OUT, scan, diff
from build_compat_plan import file_guard


def main():
    audit = json.loads((OUT / 'raw_field_comparison.json').read_text(encoding='utf-8'))
    keys = {(r['origin'], int(r['object_id'], 16)) for f in audit['features'] for r in f['override_records']}
    old_root = BASE.parent / 'TuLED/STOCK GAME/Skyrim Special Edition/Data'
    cleaned = BASE.parent / 'TuLED/File Mod Skyrim SE/mods/Cleaned Vanilla ESM'
    result = []
    for name in ('Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm'):
        old = cleaned / name if (cleaned / name).exists() else old_root / name
        new = BASE / 'repairs/consistent_stock/Data' / name
        left, _, _ = scan(old, wanted=keys)
        right, _, _ = scan(new, wanted=keys)
        changes = []
        for key in sorted(set(left) | set(right)):
            d = diff(left.get(key), right.get(key))
            if d:
                changes.append({'record': f'{key[0]}|{key[1]:06X}', 'signature': (right.get(key) or left[key])['signature'],
                                'old_present': key in left, 'new_present': key in right, 'raw_field_changes': d})
        result.append({'filename': name, 'old_input': file_guard(old), 'new_input': file_guard(new),
                       'old_matching_records': len(left), 'new_matching_records': len(right),
                       'changed_record_count': len(changes), 'changes': changes})
    report = {'basis': 'Original TuLED selected Cleaned Vanilla ESM overlay for four DLC/update masters; original STOCK GAME Skyrim.esm for base game. Final consistent_stock overlay replaces all five.',
              'comparison': 'Exact raw record/subrecord differences at selected feature override targets, with canonical origin identities. Different cache/localized encodings remain explicitly raw and are not called semantic regressions.',
              'target_count': len(keys), 'files': result}
    (OUT / 'coherent_stock_target_delta.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Old/new stock target deltas:', [(r['filename'], r['changed_record_count']) for r in result])


if __name__ == '__main__':
    main()
