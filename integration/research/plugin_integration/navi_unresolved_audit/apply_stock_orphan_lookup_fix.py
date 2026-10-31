"""Bound only the verified original-stock orphan in four research PAS drafts.

No dispatched script, runtime file, original plugin, profile, or shared DB is
written. Existing native byte-vector comparators remain exactly unchanged.
"""
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[3]
RESEARCH=BASE/'integration/research'
FILES=[RESEARCH/'forgotten_city_navigation'/n for n in
       ('DatabaseForgottenCityNavigationDraft.pas','DatabaseVerifyForgottenCityNavigationDraft.pas')]
FILES += [RESEARCH/'glen_region_navigation'/n for n in
          ('DatabaseGlenmorilNavigationDraft.pas','DatabaseVerifyGlenmorilNavigationDraft.pas')]

HELPER=r'''function IsKnownStockOrphan(info: IInterface): Boolean;
var
  owner, recordElement, keyElement, mergeElement, parentElement: IInterface;
  stream: TBytesStream;
  reader: TBinaryReader;
  i: Integer;
begin
  Result := False;
  if not Assigned(info) then Exit;
  owner := GetFile(info);
  if not SameText(GetFileName(owner), 'Skyrim.esm') then Exit;
  recordElement := ContainingMainRecord(info);
  if not Assigned(recordElement) then Exit;
  if Signature(recordElement) <> 'NAVI' then Exit;
  if GetLoadOrderFormID(recordElement) <> $00012FB4 then Exit;
  keyElement := Req(info, 'Navmesh');
  if GetNativeValue(keyElement) <> $00028E37 then Exit;
  Need(not Assigned(LinksTo(keyElement)), 'Known stock orphan unexpectedly resolves; re-audit');
  if not stockOrphanGuardChecked then begin
    // The external SHA preflight/producer inventory pins whole Skyrim.esm
    // 06a9881f6ab277afd2a82e71f8a3719183b7031db4d9c78a7f40c08e1e4ffa91.
    // This additional CRC guard reads the actual injected VFS filename.
    Need(SameText(IntToHex(wbCRC32File(DataPath + 'Skyrim.esm'), 8), '66212483'),
      'Known stock orphan file CRC changed');
    stockOrphanGuardChecked := True;
    AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_LOOKUP_ONLY|Skyrim.esm|028E37|PAYLOAD_SHA256=8a220fa216d44545e8367bde7fd0d3fe7bcd43b1598f7eb131aa99d4fe3a7304');
  end;
  // All fields of the original49-byte NVMI are checked, not its ordinal.
  // No copy/output record can enter this original-Skyrim-only allowance.
  Need(ElementCount(info) = 12, 'Known stock orphan NVMI member count changed');
  Need(GetNativeValue(Req(info, 'Category')) = 0, 'Known stock orphan category changed');
  Need(GetNativeValue(Req(info, 'X')) = -3391.8515625, 'Known stock orphan X changed');
  Need(GetNativeValue(Req(info, 'Y')) = 285.758941650390625, 'Known stock orphan Y changed');
  Need(GetNativeValue(Req(info, 'Z')) = 239.091033935546875, 'Known stock orphan Z changed');
  mergeElement := Req(info, 'Preferred Merges Flag');
  Need(VarType(GetNativeValue(mergeElement)) = 8209, 'Known stock orphan merge bytes type changed');
  stream := TBytesStream.Create(GetNativeValue(mergeElement));
  try
    Need(stream.Size = 4, 'Known stock orphan merge bytes length changed');
    stream.Position := 0; reader := TBinaryReader.Create(stream);
    try
      for i := 0 to 3 do Need(reader.ReadByte = 0, 'Known stock orphan merge bytes changed');
    finally reader.Free; end;
  finally stream.Free; end;
  Need(ElementCount(Req(info, 'Edge Links')) = 0, 'Known stock orphan edge links changed');
  Need(ElementCount(Req(info, 'Preferred Edge Links')) = 0, 'Known stock orphan preferred links changed');
  Need(ElementCount(Req(info, 'Door Links')) = 0, 'Known stock orphan door links changed');
  Need(GetNativeValue(Req(info, 'Is Island')) = 0, 'Known stock orphan island changed');
  Need(ElementCount(Req(info, 'PathingCell')) = 3, 'Known stock orphan pathing layout changed');
  Need(SameText(IntToHex(GetNativeValue(Req(info, 'PathingCell\CRC Hash')), 8), 'A5E9A03C'), 'Known stock orphan path CRC changed');
  Need(GetNativeValue(Req(info, 'PathingCell\Parent Worldspace')) = 0, 'Known stock orphan world changed');
  parentElement := Req(info, 'PathingCell\Parent');
  Need(ElementCount(parentElement) = 1, 'Known stock orphan parent union changed');
  parentElement := ElementByIndex(parentElement, 0);
  Need(BaseName(parentElement) = 'Parent Cell', 'Known stock orphan parent branch changed');
  Need(GetNativeValue(parentElement) = $00028E34, 'Known stock orphan parent cell changed');
  Result := True;
end;

'''


def sha(data):return hashlib.sha256(data).hexdigest()
def pin(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':sha(path.read_bytes())}


def main():
    audit=json.loads((OWN/'final_navi_key_audit.json').read_text('utf-8'))
    guard=audit['orphan']
    assert audit['all_input_plugin_SHA_verified'] and audit['counts']['absent_NVMI_keys']==1
    assert guard['source_file_sha256']=='06a9881f6ab277afd2a82e71f8a3719183b7031db4d9c78a7f40c08e1e4ffa91'
    assert guard['NVMI_payload_sha256']=='8a220fa216d44545e8367bde7fd0d3fe7bcd43b1598f7eb131aa99d4fe3a7304'
    # These exact scalar literals + empty arrays reconstruct every serialized
    # field; this independently checks the PAS guard's float precision/layout.
    rebuilt=struct.pack('<IIfffIIII B III',0x28E37,0,-3391.8515625,285.758941650390625,
                        239.091033935546875,0,0,0,0,0,0xA5E9A03C,0,0x28E34)
    assert rebuilt.hex()==guard['NVMI_payload_hex'] and sha(rebuilt)==guard['NVMI_payload_sha256']
    archive=OWN/'frozen/before_stock_orphan_fix'
    assert not archive.exists(),'Already applied; inspect immutable manifest instead of blind repeat'
    archive.mkdir(parents=True)
    before=[];after=[];diffs=[]
    for path in FILES:
        old=path.read_text('utf-8');assert 'IsKnownStockOrphan' not in old
        backup=archive/(path.name+'.frozen.txt');backup.write_bytes(path.read_bytes())
        before.append({'source':pin(path),'frozen_copy':pin(backup)})
        text=old.replace('\nprocedure Need(ok: Boolean;', '\nvar stockOrphanGuardChecked: Boolean;\n\nprocedure Need(ok: Boolean;',1)
        assert text!=old
        text=text.replace('function InfoFor(naviRecord, navMaster: IInterface): IInterface;',HELPER+'function InfoFor(naviRecord, navMaster: IInterface): IInterface;',1)
        assert text.count('function IsKnownStockOrphan(')==1
        text=text.replace("    Need(Assigned(linked), 'Unresolved NAVI/NVMI Navmesh key');\n    if SameRecord(linked, navMaster) then begin",
                          "    if not Assigned(linked) then begin\n      Need(IsKnownStockOrphan(item), 'Unresolved NAVI/NVMI Navmesh key outside exact source guard');\n      Need(GetLoadOrderFormID(MasterOrSelf(navMaster)) <> $00028E37, 'Missing requested target cannot be ignored');\n    end else if SameRecord(linked, navMaster) then begin",1)
        assert 'outside exact source guard' in text
        if 'ForgottenCity' in path.name:
            old_part="  Need(Assigned(r), 'Unresolved NVMI key');"
            new_part="  if not Assigned(r) then begin\n    Need(IsKnownStockOrphan(info), 'Unresolved NVMI key outside exact source guard');\n    Exit;\n  end;"
        else:
            old_part="begin Result:=False;r:=LinksTo(Req(info,'Navmesh'));Need(Assigned(r),'NAVI key unresolved');r:=MasterOrSelf(r);"
            new_part="begin Result:=False;r:=LinksTo(Req(info,'Navmesh'));\n if not Assigned(r) then begin Need(IsKnownStockOrphan(info),'NAVI key unresolved outside exact source guard');Exit;end;\n r:=MasterOrSelf(r);"
        assert text.count(old_part)==1
        text=text.replace(old_part,new_part,1)
        # Explicit initialization, independent of interpreter variable defaults.
        initialize=text.index('function Initialize:')
        before_init=text[:initialize];init=text[initialize:]
        at=re.search(r'\bbegin\b',init).end();init=init[:at]+'\n  stockOrphanGuardChecked := False;'+init[at:]
        text=before_init+init
        # The previously audited generic native-vector comparison is untouched.
        a=old[old.index('procedure AssertNativeByteVector'):old.index('procedure AssertTree')]
        b=text[text.index('procedure AssertNativeByteVector'):text.index('procedure AssertTree')]
        assert a==b
        path.write_text(text,encoding='utf-8',newline='\n')
        after.append(pin(path))
        diffs.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile=str(backup),tofile=str(path)))
    (OWN/'stock_orphan_lookup_changes.diff').write_text(''.join(diffs),encoding='utf-8',newline='\n')
    manifest={'schema':'skyrim.bounded_navi_orphan_lookup_fix.v1','utc':datetime.now(timezone.utc).isoformat(),
              'status':'AUTHORING_DRAFTS_UPDATED_NATIVE_EXECUTION_AND_RELOAD_PENDING','before':before,'after':after,
              'audit':pin(OWN/'final_navi_key_audit.json'),'patcher':pin(__file__),
              'diff':pin(OWN/'stock_orphan_lookup_changes.diff'),'orphan_guard':guard,
              'typed_guard_reconstructs_exact_49_bytes':True,'native_vector_comparator_unchanged':True,
              'external_preflight_required':{'source_plugin':'Skyrim.esm','sha256':guard['source_file_sha256'],
                  'reason':'Actual VFS CRC is checked in PAS; full SHA is pinned independently by candidate preflight and complete producer input inventory.'},
              'semantics':['Only the exact original Skyrim.esm NAVI012FB4/028E37 nil entry may be skipped by lookup/classification. No unrelated nil key is accepted.','The allowance cannot apply to any output copy because it requires owning file Skyrim.esm, its native NAVI ID and all12 typed NVMI fields with exact floats/merge bytes/counts/pathing parent.','No record or field is removed, rewritten or remapped by this guard. Target duplicate checks and full nontarget binary/typed preservation remain strict.'],
              'limits':['No dispatched task PAS or runtime/profile/plugin edited.','Not xEdit compiled/executed by this agent. Root must use fresh producer, independent full-NAVI binary verifier, private install and fresh typed reload.']}
    (OWN/'stock_orphan_lookup_fix_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':manifest['status'],'files':len(after),'manifest':str(OWN/'stock_orphan_lookup_fix_manifest.json')},indent=2))


if __name__=='__main__':main()
