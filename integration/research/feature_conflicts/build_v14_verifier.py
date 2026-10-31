"""Derive a new verifier without editing any frozen v13 script or manifest."""
from pathlib import Path
import hashlib
import json

OUT=Path(__file__).resolve().parent


def main():
    source=OUT/'verify_compatibility.py';text=source.read_text(encoding='utf-8')
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='978b71df33fffe3f3a63b0b3f32db1a0a168e5c093ed1faf071f3aab414f83da'
    old="""        elif tag in ('VMAD', 'FULL'):
            v = canonical(r)[tag]
"""
    new="""        elif tag in ('VMAD', 'FULL'):
            v = canonical(r)[tag]
            if tag == 'VMAD':
                from quest_vmad_tail import canonical_quest_tail
                from vmad_audit import parse_vmad
                parsed = parse_vmad(value, lambda fid: formvalue(r, fid))
                if parsed['version'] != 5:
                    raise ValueError('Unsupported Sofia VMAD script version')
                assert len(v) == 1
                v[0].pop('tail_hex')
                v[0]['typed_quest_tail'] = canonical_quest_tail(
                    bytes.fromhex(parsed['tail_hex']), parsed['object_format'], lambda fid: formvalue(r, fid))
"""
    assert text.count(old)==1
    (OUT/'verify_compatibility_v14.py').write_text(text.replace(old,new,1),encoding='utf-8')
    print('Created separate v14 binary verifier; frozen v13 files untouched')


if __name__=='__main__':main()
