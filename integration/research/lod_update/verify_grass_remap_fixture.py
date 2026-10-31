"""In-memory malformed-input and all-byte preservation checks; no source writes."""
import hashlib
import json
from pathlib import Path
import struct
import sys
sys.dont_write_bytecode=True
from runtime_common import OUT,sha
from grass_cache_remap import streams,mask_sha

def main():
    p=json.loads((OUT/'grass_cache_remap_plan.json').read_text(encoding='utf-8'))
    assert p['status']=='BOUNDED_PRIVATE_OVERLAY_READY_NOT_MATERIALIZED'
    cases=[]
    for appended in (False,True):
        row=min((r for r in p['files'] if r['id_edits'] and (r['streams']>1)==appended),key=lambda r:r['bytes'])
        source=Path(row['source']);old=source.read_bytes();new=bytearray(old)
        assert sha(source)==row['source_sha256'];before=streams(old)
        for e in row['id_edits']:
            assert struct.unpack_from('<I',old,e['offset'])[0]==int(e['old'],16)
            struct.pack_into('<I',new,e['offset'],int(e['new'],16))
        changed={i for i,(a,b) in enumerate(zip(old,new)) if a!=b}
        allowed={i for e in row['id_edits'] for i in range(e['offset'],e['offset']+4)}
        assert changed and changed<=allowed and len(old)==len(new)
        assert mask_sha(old,[e['offset'] for e in row['id_edits']])==mask_sha(new,[e['offset'] for e in row['id_edits']])==row['other_bytes_masked_sha256']
        after=streams(new);assert len(before)==len(after)==row['streams']
        for a,b in zip(before,after):
            assert a['start']==b['start'] and a['end']==b['end']
            for x,y in zip(a['groups'],b['groups']):assert {k:v for k,v in x.items() if k!='form_id'}=={k:v for k,v in y.items() if k!='form_id'}
        assert source.read_bytes()==old
        tests=[]
        for label,bad in [('truncated',old[:-1]),('unexpected_trailing',old+b'\x01'),('invalid_group_count',b'\xff'*4+old[4:])]:
            try:streams(bad)
            except Exception:tests.append(label)
            else:raise AssertionError('Malformed input accepted: '+label)
        cases.append({'source':str(source),'bytes':len(old),'streams':len(before),'source_sha256':sha(source),'patched_memory_sha256':hashlib.sha256(new).hexdigest(),
            'allowed_id_fields':len(row['id_edits']),'changed_byte_count':len(changed),'all_other_bytes_identical':True,'malformed_inputs_rejected':tests})
    report={'status':'IN_MEMORY_REMAP_AND_FAIL_CLOSED_FIXTURE_PASS_NO_CACHE_MATERIALIZED','cases':cases,'script_sha256':sha(OUT/'grass_cache_remap.py'),'plan_sha256':sha(OUT/'grass_cache_remap_plan.json')}
    (OUT/'grass_remap_fixture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(report['status'])
if __name__=='__main__':main()
