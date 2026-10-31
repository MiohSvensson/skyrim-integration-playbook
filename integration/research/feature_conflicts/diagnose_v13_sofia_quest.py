"""Compare exact v13 export Sofia quest against authored source and redirect."""
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
from analyze_fields import OUT,scan
from verify_compatibility import quest_canonical


def main():
    plan=json.loads((OUT/'compat_patch_plan.json').read_text(encoding='utf-8'))
    path=OUT/'candidate/Database Feature Compatibility.esp'
    source=Path(next(g['path'] for g in plan['input_file_guards'] if g['filename'].casefold()=='sofiafollower.esp'))
    key=('sofiafollower.esp',0xAA58)
    src=scan(source,wanted={key})[0][key];candidate=scan(path)[0]
    actual=candidate[key];own=[k for k,v in candidate.items() if k[0]=='database feature compatibility.esp'];assert len(own)==1
    expected=quest_canonical(src);observed=quest_canonical(actual)
    changes=[];alias=None;redirects=0
    for index,pair in enumerate(expected['fields']):
        if pair[0]=='ALST':alias=int.from_bytes(bytes.fromhex(pair[1]),'little')
        if pair==['ALPC','skyrim.esm|09845C']:
            assert alias==1
            pair[1]=f'{own[0][0]}|{own[0][1]:06X}';redirects+=1
    for i in range(max(len(expected['fields']),len(observed['fields']))):
        left=expected['fields'][i] if i<len(expected['fields']) else None
        right=observed['fields'][i] if i<len(observed['fields']) else None
        if left!=right:changes.append({'index':i,'expected':left,'actual':right})
    result={'candidate':str(path),'candidate_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'source':str(source),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'source_flags':src['flags'],'candidate_flags':actual['flags'],
            'source_count':len(src['fields']),'candidate_count':len(actual['fields']),
            'redirects':redirects,'differences':changes,'expected':expected,'actual':observed,
            'source_raw_fields':[(t,v.hex()) for t,v in src['fields']],
            'candidate_raw_fields':[(t,v.hex()) for t,v in actual['fields']]}
    (OUT/'v13_sofia_quest_exact_diff.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Flags',src['flags'],actual['flags'],'fields',len(src['fields']),len(actual['fields']),'redirects',redirects,'different aligned fields',len(changes))
    for change in changes[:15]:print(json.dumps(change,ensure_ascii=True)[:1800])


if __name__=='__main__':main()
