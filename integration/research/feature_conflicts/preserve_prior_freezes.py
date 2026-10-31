"""Preserve exact research PAS v9/v10 bodies without modifying dispatched files."""
from pathlib import Path
import hashlib
import json

OUT=Path(__file__).resolve().parent
NAMES=['DatabaseFeatureCompatibilityDraft.pas','DatabaseQuestFeatureCompatibilityDraft.pas',
       'DatabaseVerifyFeatureCompatibilityDraft.pas','DatabaseVerifyQuestFeatureCompatibilityDraft.pas']
EXPECTED={
 'v9':['7bbd6079e4b798af331d0604aa9662be381097b4fb2790ca16e7a6ce9a8a2731','49502cb083dacea7548a20f6a09c90d59e44e11cb05fd3846df412073a914b46','c22a9c3729a40ddee1f1a85250023ce4400767424a714dc0e5ce7bfcb4efdf03','c39a213555ef636d4fa729d3d1c5e029ea92413c14d5ce685e9e9ebd17bd6e21'],
 'v10':['74034aa4c3f74e19b074b5de581e45142d152458677ba26e314e02c489b0ba16','4b2cdd412560c6cf972abdd414d9a4f0a15715275570ca5247757c0bb8ed17f6','7590bbc19cd1eb17c82d2092591ef05ba6e32a11256c7653048deefe9831f1b8','679979cec98c37d563e332c909b30be50ce231ee5fa0d111bbb60350c9701cf9']}
ADDED='''  if (Signature(r) = 'DIAL') and ((t = 'INOM') or (t = 'INOA')) then begin
    Need(DefType(field) = dtArray, 'Unexpected exact-tag editor INFO-order definition: ' + t);
    // These two lists are dynamically reconstructed from this file's visible
    // masters/overrides and may be absent, empty or repopulated after copies.
    // Exact 4.1.5f flags them InternalEditOnly/DontAssign/DontSave. They never
    // enter serialized gameplay payload; binary verifiers reject stored tags.
    Result := True;
  end;
'''
NEW='''  Result := (Signature(r) = 'WRLD') and ((t = 'RNAM') or (t = 'Large References') or (t = 'OFST'));
  // Exact 4.1.5f: WRLD RNAM/OFST are no-copy-as-override; MHDT is strict.
  // Only omission is allowed for these serialized no-copy-as-override tables.
  // Present tables remain exact. DIAL INOM/INOA are separate unsaved caches.
'''
OLD='''  Result := ((Signature(r) = 'WRLD') and ((t = 'RNAM') or (t = 'Large References') or (t = 'OFST'))) or
    ((Signature(r) = 'DIAL') and ((t = 'INOM') or (t = 'INOA')));
  // Exact 4.1.5f: WRLD RNAM/OFST are no-copy-as-override, not MHDT.
  // MHDT is strict here. DIAL response count and interior XCLW are cpIgnore.
'''
# Actual v9 comments from the authoring template, separate from earlier drafts.
OLD='''  Result := ((Signature(r) = 'WRLD') and ((t = 'RNAM') or (t = 'Large References') or (t = 'OFST'))) or
    ((Signature(r) = 'DIAL') and ((t = 'INOM') or (t = 'INOA')));
  // Exact 4.1.5f: WRLD RNAM/OFST are no-copy-as-override; MHDT is strict.
  // DIAL INOM/INOA are editor-only INFO-order arrays, dfDontSave/dfDontAssign.
  // Only omission is allowed. If both sides expose a field it remains exact.
'''


def write_once(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():assert path.read_bytes()==data,'Refuse overwrite different frozen bytes: '+str(path)
    else:path.write_bytes(data)


def main():
    current=[(OUT/n).read_bytes() for n in NAMES]
    assert [hashlib.sha256(b).hexdigest() for b in current]==EXPECTED['v10']
    rows=[]
    for version in ('v9','v10'):
        for index,name in enumerate(NAMES):
            data=current[index]
            if version=='v9':
                text=data.decode('utf-8').replace('\r\n','\n');assert text.count(ADDED)==1 and text.count(NEW)==1
                data=text.replace(ADDED,'',1).replace(NEW,OLD,1).replace('\n','\r\n').encode('utf-8')
            digest=hashlib.sha256(data).hexdigest();assert digest==EXPECTED[version][index],(version,name,digest)
            dest=OUT/'version_freezes'/version/name;write_once(dest,data)
            rows.append({'version':version,'path':str(dest),'sha256':digest,
                         'provenance':'Exact v10 bytes' if version=='v10' else 'Reverse the documented v9-to-v10 INOM policy-only change; exact delivered v9 SHA independently matches'})
    old=OUT/'draft_version_manifest.json'
    write_once(OUT/'version_freezes/v9/draft_version_manifest.json',old.read_bytes())
    for name in ('compatibility_template.pas','verify_compatibility.py','verify_quest_extension.py','analyze_fields.py',
                 'compat_patch_plan.json','quest_extension_plan.json','pascal_api_audit.json','copy_contract_audit.json'):
        write_once(OUT/'version_freezes/v10'/name,(OUT/name).read_bytes())
    report={'status':'EXACT_VERSION_BODIES_PRESERVED','files':rows,
            'limits':'Only research artifacts are copied. Root dispatched Edit Scripts and runtime outputs are not modified. v9 prior metadata manifest is preserved as-is; not every obsolete report body is recoverable.'}
    write_once(OUT/'version_freezes/prior_version_freezes.json',(json.dumps(report,indent=2)+'\n').encode())
    print('Preserved exact v9/v10:',len(rows),'PAS bodies')


if __name__=='__main__':main()
