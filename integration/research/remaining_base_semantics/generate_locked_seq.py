"""Generate only two source-hash-locked SEQ candidates, matching xEdit 4.1.5f.

No runtime files are read as output targets or modified. This restricted helper
supports the two audited plugins whose SGE quests are all new own records.
It rejects an unexpected SGE master override instead of guessing its master.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
OUT = Path(__file__).resolve().parent
BASE = OUT.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
import plugin_binary

EXPECTED = {
    'BenDoonSSE.esp': {'sha256': 'afd1e978edaffe14adb8083686a184ace484de253c89fd73d7091ac7a7d27878', 'own_sge': [0x4C76B]},
    'ForgottenMagic_Redone.esp': {'sha256': 'c8df195c3b5e23db3f7dcd0d689c21bce0e28323c3463381571216db55e8e6b4', 'own_sge': [0xD62, 0xD63]},
}


def main():
    manifest = json.loads((OUT.parent / 'plugin_integration/feature_builder_manifest.json').read_text(encoding='utf-8'))
    plugins = {p['name']: p for group in ('features', 'followers') for f in manifest[group] for p in f['plugins']}
    result = []
    for name, guard in EXPECTED.items():
        source = Path(plugins[name]['source_path'])
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert digest == guard['sha256'], 'Source changed: ' + name
        masters, records = plugin_binary.read(source)
        own_sge = []
        fixed = []
        info = []
        for record in records:
            if record['sig'] != 'QUST': continue
            fields = dict(record['fields'])
            flags = struct.unpack_from('<H', fields['DNAM'])[0] if 'DNAM' in fields else 0
            if not flags & 1: continue
            file_index, object_id = record['fid'] >> 24, record['fid'] & 0xFFFFFF
            assert file_index >= len(masters), 'Unexpected master SGE override; requires exact original-master flags: ' + name
            assert object_id >= 0x800, 'Hardcoded low range not part of this restricted generator'
            # ComputeFixedFormID normalizes self/out-of-range full slot to the
            # file's self slot (MasterCount). This is FILE-local, not load order.
            fid = (len(masters) << 24) | object_id
            own_sge.append(object_id)
            fixed.append(fid)
            info.append({'record': f'{name}|{object_id:06X}', 'editor_id': record['edid'],
                         'DNAM_flags': f'{flags:04X}', 'raw_form_id': f'{record["fid"]:08X}', 'fixed_form_id': f'{fid:08X}'})
        assert own_sge == guard['own_sge'], 'Audited SGE set/order changed: ' + name
        data = b''.join(struct.pack('<I', fid) for fid in fixed)
        target = OUT / 'seq_candidate/seq' / Path(name).with_suffix('.seq').name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists(): assert target.read_bytes() == data, 'Existing candidate differs; refuse overwrite'
        else: target.write_bytes(data)
        assert len(data) == len(info) * 4
        result.append({'plugin': name, 'source': str(source), 'source_sha256': digest, 'masters': masters,
                       'quests': info, 'output': str(target), 'bytes': len(data), 'hex': data.hex(),
                       'sha256': hashlib.sha256(data).hexdigest()})
    exact = OUT.parent / 'feature_conflicts/source_4_1_5f'
    primary = exact / 'xeMainForm.pas'
    implementation = exact / 'wbImplementation.pas'
    plan = {'status': 'BINARY_CANDIDATES_GENERATED_NOT_RUNTIME_INSTALLED', 'candidates': result,
            'primary': {'path': str(primary), 'sha256': hashlib.sha256(primary.read_bytes()).hexdigest(), 'lines': [4160, 4237],
                        'method': 'TfrmMain.mniNavCreateSEQFileClick', 'source_provenance': str(exact / 'provenance.json')},
            'fixed_form_id_primary': {'path': str(implementation), 'sha256': hashlib.sha256(implementation.read_bytes()).hexdigest(), 'lines': [8856, 8878]},
            'exact_algorithm': [
                'Skip file load order 0. Iterate its QUST group records.',
                'Include DNAM Flags bit0 (Start Game Enabled) when no Master exists, or original Master has bit0 clear.',
                'Write MainRecord.FixedFormID as consecutive little-endian Cardinal values, no header/count/terminator; filename Seq/<plugin-stem>.seq.',
                'The engine load-order prefix is NOT written. FixedFormID retains the audited file-local self slot, here 02 for two masters.',
                'This restricted generator handles only the two hash-locked own-SGE sets above. A master override is rejected and needs exact original-master flags.',
                'Unlike the full xEdit GUI implementation this helper never deletes or writes a runtime Seq file. Outputs remain this research directory.'],
            'final_requirements': ['Check selected plugin SHA still matches before overlaying these sidecars.',
                                  'Install candidate seq files as final integration assets only; do not rename the owning plugins.',
                                  'Final VFS resource audit should verify exact bytes; game startup/quest initialization remains untested.']}
    (OUT / 'seq_generation_plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('SEQ candidates:', [(r['plugin'], r['hex'], r['sha256']) for r in result])


if __name__ == '__main__': main()
