unit UserScript;

// DRAFT. Not yet compiled/executed. Inspect source SHA guards and run only in
// the final Database-owned MO2 VFS with xEdit 4.1.5f, normal record definitions.
// All edits affect a NEW in-memory plugin. Original records are never edited.
// If any exception occurs after plugin creation, export nothing and close
// xEdit without saving that incomplete plugin or unrelated files.

const
  VERIFY_ONLY = True;
  PATCH_NAME = 'Database Glenmoril Underground Door Compatibility.esp';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\navmesh_patch\candidate\Database Glenmoril Underground Door Compatibility.esp';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then
    raise Exception.Create('BOUNDED_NAVM_STOP: ' + messageText);
end;

function ReqFile(fileName: string): IInterface;
begin
  Result := FileByName(fileName);
  Need(Assigned(Result), 'Required loaded file absent: ' + fileName);
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Typed field absent: ' + path);
end;

function SameRecord(a, b: IInterface): Boolean;
begin
  Result := False;
  if not Assigned(a) then Exit;
  if not Assigned(b) then Exit;
  Result := GetLoadOrderFormID(MasterOrSelf(a)) = GetLoadOrderFormID(MasterOrSelf(b));
end;

function CanonicalRecordText(e: IInterface): string;
var r: IInterface; mask: Integer;
begin
  Result := '<no-record>';
  if not Assigned(e) then Exit;
  if ElementType(e) = etMainRecord then r := e else r := ContainingMainRecord(e);
  if not Assigned(r) then Exit;
  r := MasterOrSelf(r); mask := $00FFFFFF;
  if GetIsESL(GetFile(r)) then mask := $00000FFF;
  Result := LowerCase(GetFileName(GetFile(r))) + '|' + IntToHex(GetLoadOrderFormID(r) and mask, 6);
end;

function NativeText(e: IInterface): string;
var r: IInterface;
begin
  Result := '<missing>';
  if not Assigned(e) then Exit;
  if (BaseName(e)='Version Control Info 1') or (BaseName(e)='Version Control Info 2') then begin
    r:=ContainingMainRecord(e);
    if Assigned(r) then begin
      if BaseName(e)='Version Control Info 1' then Result:=IntToHex(GetFormVCS1(r),8)
      else Result:=IntToHex(GetFormVCS2(r),4);
      Exit;
    end;
  end;
  if DefType(e) = dtByteArray then begin Result := GetEditValue(e); Exit; end;
  try Result := GetNativeValue(e); except Result := '<native unavailable>'; end;
end;

function ComparisonContext(a,b: IInterface): string;
begin
  Result := ' | dst=' + CanonicalRecordText(a);
  if Assigned(a) then Result := Result + ' file=' + GetFileName(GetFile(a)) + ' path=' + FullPath(a) + ' native=' + NativeText(a);
  Result := Result + ' | src=' + CanonicalRecordText(b);
  if Assigned(b) then Result := Result + ' file=' + GetFileName(GetFile(b)) + ' path=' + FullPath(b) + ' native=' + NativeText(b);
end;

procedure NeedCompared(ok: Boolean; labelText: string; a,b: IInterface);
begin
  if not ok then Need(False,labelText+ComparisonContext(a,b));
end;

procedure AssertTree(a, b: IInterface; labelText: string);
var
  i: Integer;
  la, lb: IInterface;
begin
  NeedCompared(Assigned(a), labelText + ': left element missing',a,b);
  NeedCompared(Assigned(b), labelText + ': right element missing',a,b);
  NeedCompared(BaseName(a) = BaseName(b), labelText + ': field definition changed',a,b);
  NeedCompared(ElementCount(a) = ElementCount(b), labelText + ': child count changed',a,b);
  if ElementCount(a) > 0 then begin
    for i := 0 to ElementCount(a) - 1 do
      AssertTree(ElementByIndex(a, i), ElementByIndex(b, i), labelText + '/' + BaseName(ElementByIndex(b, i)) + '[' + IntToStr(i) + ']');
    Exit;
  end;
  if (DefType(a) = dtByteArray) or (DefType(b) = dtByteArray) then begin
    NeedCompared(DefType(a) = DefType(b), labelText + ': byte-array type changed',a,b);
    // In 4.1.5f NativeValue is a Variant byte array, not a comparable scalar.
    // ToEditValue renders every byte as hex (wbInterface:18536-18556,18586+).
    NeedCompared(GetEditValue(a) = GetEditValue(b), labelText + ': exact byte array changed',a,b);
    Exit;
  end;
  la := LinksTo(a);
  lb := LinksTo(b);
  if Assigned(la) then begin
    if ElementType(la) = etMainRecord then begin
      NeedCompared(Assigned(lb), labelText + ': unresolved counterpart FormID',a,b);
      NeedCompared(ElementType(lb) = etMainRecord, labelText + ': counterpart is not a record',a,b);
      NeedCompared(SameRecord(la, lb), labelText + ': resolved FormID changed',a,b);
      Exit;
    end;
  end;
  // Exact native numeric comparison, not rounded display strings. Non-record
  // LinksTo callbacks on vertex/triangle indices are deliberately not FormIDs.
  NeedCompared(GetNativeValue(a) = GetNativeValue(b), labelText + ': native value changed',a,b);
end;

function FieldToken(e: IInterface): string;
begin
  Result := Signature(e);
  if Result = '' then Result := BaseName(e);
end;

function UniqueTop(recordElement: IInterface; tokenText: string): IInterface;
var i: Integer; e: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(recordElement) - 1 do begin
    e := ElementByIndex(recordElement, i);
    if (BaseName(e) <> 'Record Header') and (FieldToken(e) = tokenText) then begin
      Need(not Assigned(Result), 'Duplicate top-level field token: ' + tokenText);
      Result := e;
    end;
  end;
end;

function UniqueChild(containerElement: IInterface; childName: string): IInterface;
var i: Integer; e: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(containerElement) - 1 do begin
    e := ElementByIndex(containerElement,i);
    if BaseName(e) = childName then begin
      Need(not Assigned(Result),'Duplicate exact child '+childName+ComparisonContext(e,Result));
      Result := e;
    end;
  end;
end;

procedure AssertRecordHeader(copyRecord, sourceRecord: IInterface; labelText: string);
var a,b,x,y: IInterface; i: Integer; fieldName: string;
begin
  Need(Signature(copyRecord)=Signature(sourceRecord),labelText+': signature changed'+ComparisonContext(copyRecord,sourceRecord));
  Need(SameRecord(copyRecord,sourceRecord),labelText+': canonical FormID changed'+ComparisonContext(copyRecord,sourceRecord));
  Need(GetFormVersion(copyRecord)=GetFormVersion(sourceRecord),labelText+': Form Version changed dst='+IntToStr(GetFormVersion(copyRecord))+' src='+IntToStr(GetFormVersion(sourceRecord))+ComparisonContext(copyRecord,sourceRecord));
  Need(GetFormVCS1(copyRecord)=GetFormVCS1(sourceRecord),labelText+': VCS1 changed dst='+IntToHex(GetFormVCS1(copyRecord),8)+' src='+IntToHex(GetFormVCS1(sourceRecord),8)+ComparisonContext(copyRecord,sourceRecord));
  Need(GetFormVCS2(copyRecord)=GetFormVCS2(sourceRecord),labelText+': VCS2 changed dst='+IntToHex(GetFormVCS2(copyRecord),4)+' src='+IntToHex(GetFormVCS2(sourceRecord),4)+ComparisonContext(copyRecord,sourceRecord));
  a:=Req(copyRecord,'Record Header');b:=Req(sourceRecord,'Record Header');
  Need(ElementCount(a)=ElementCount(b),labelText+': header member count changed'+ComparisonContext(a,b));
  for i:=0 to ElementCount(b)-1 do begin
    y:=ElementByIndex(b,i);fieldName:=BaseName(y);x:=UniqueChild(a,fieldName);
    Need(Assigned(x),labelText+': header field missing '+fieldName+ComparisonContext(x,y));
    // Data Size is derived serialization length. FormID is compared above as
    // canonical record identity, never as a file-local master-index integer.
    if fieldName='Version Control Info 1' then
      Need(GetFormVCS1(copyRecord)=GetFormVCS1(sourceRecord),labelText+': exact VCS1 changed'+ComparisonContext(x,y))
    else if fieldName='Version Control Info 2' then
      Need(GetFormVCS2(copyRecord)=GetFormVCS2(sourceRecord),labelText+': exact VCS2 changed'+ComparisonContext(x,y))
    else if (fieldName<>'Data Size') and (fieldName<>'FormID') then
      AssertTree(x,y,labelText+'/Record Header/'+fieldName);
  end;
  for i:=0 to ElementCount(a)-1 do begin
    x:=ElementByIndex(a,i);Need(Assigned(UniqueChild(b,BaseName(x))),labelText+': extra header field'+ComparisonContext(x,b));
  end;
end;

function KnownNoCopyParentField(recordElement, field: IInterface): Boolean;
var tokenText: string;
begin
  tokenText := FieldToken(field);
  // Exact 4.1.5f WRLD definitions: RNAM and OFST explicitly carry
  // dfNoCopyAsOverride. MHDT DOES NOT in this version and is compared below.
  Result := (Signature(recordElement) = 'WRLD') and
    ((tokenText = 'RNAM') or (tokenText = 'Large References') or (tokenText = 'OFST'));
end;

function IgnoredInteriorWater(recordElement, field: IInterface): Boolean;
begin
  Result := False;
  if (Signature(recordElement) = 'CELL') and (FieldToken(field) = 'XCLW') then
    Result := (GetNativeValue(Req(recordElement, 'DATA')) and 1) <> 0;
  // 4.1.5f wbCELLXCLWGetConflictPriority: interior water height is cpIgnore
  // because Skyrim interior cells do not use this field. Exterior is strict.
end;

procedure AssertUnchangedRecord(copyRecord, sourceRecord: IInterface; labelText: string);
var
  i: Integer;
  sourceField, copyField: IInterface;
  tokenText: string;
begin
  AssertRecordHeader(copyRecord, sourceRecord, labelText);
  // Serialized length/compression bytes and file-local header FormID are not
  // payload fields; the typed record identity and all remaining fields are.
  for i := 0 to ElementCount(sourceRecord) - 1 do begin
    sourceField := ElementByIndex(sourceRecord, i);
    if (BaseName(sourceField)<>'Record Header') and not IgnoredInteriorWater(sourceRecord, sourceField) then begin
      tokenText := FieldToken(sourceField);
      copyField := UniqueTop(copyRecord, tokenText);
      if not KnownNoCopyParentField(sourceRecord, sourceField) then
        Need(Assigned(copyField), labelText + ': missing field ' + tokenText + ComparisonContext(copyField,sourceField));
      // No-copy tables may be absent. If present, they must still be exact.
      if Assigned(copyField) then AssertTree(copyField, sourceField, labelText + '/' + tokenText);
    end;
  end;
  for i := 0 to ElementCount(copyRecord) - 1 do begin
    copyField := ElementByIndex(copyRecord, i);
    if (BaseName(copyField)<>'Record Header') and not IgnoredInteriorWater(copyRecord, copyField) then
      Need(Assigned(UniqueTop(sourceRecord, FieldToken(copyField))), labelText + ': unexpected payload field ' + FieldToken(copyField)+ComparisonContext(copyField,sourceRecord));
  end;
end;

function CopyOverride(sourceRecord, targetFile: IInterface): IInterface;
begin
  // Main-record payload requires aDeepCopy=True; False creates only a shell.
  // TwbMainRecord.AssignInternal copies fields, not its separate ChildGroup.
  Result := wbCopyElementToFile(sourceRecord, targetFile, False, True);
  Need(Assigned(Result), 'Main-record payload copy failed');
  // AssignInternal resets author stamps to defaults (4.1.5f core:8554+).
  // Preserve source metadata explicitly, as well as the source form version.
  SetFormVCS1(Result, GetFormVCS1(sourceRecord));
  SetFormVCS2(Result, GetFormVCS2(sourceRecord));
  SetFormVersion(Result, GetFormVersion(sourceRecord));
end;

procedure AssertOneNVNM(r: IInterface);
begin
  Need(Signature(r) = 'NAVM', 'Target signature is not NAVM');
  Need(not GetIsDeleted(r), 'NAVM is deleted');
  Need(ElementCount(r) = 2, 'Unexpected NAVM top-level fields beyond header/NVNM');
  Need(Signature(ElementByIndex(r, 1)) = 'NVNM', 'Unexpected NAVM field order');
  Need(GetNativeValue(Req(r, 'NVNM\Version')) = 12, 'Unexpected NVNM version');
  Need(ElementCount(Req(r, 'NVNM\Vertices')) = 470, 'Vertex count changed');
  Need(ElementCount(Req(r, 'NVNM\Triangles')) = 532, 'Triangle count changed');
  Need(ElementCount(Req(r, 'NVNM\Edge Links')) = 0, 'Unexpected edge links');
  Need(ElementCount(Req(r, 'NVNM\Cover Triangles')) = 0, 'Unexpected cover triangles');
  // Missing in simple-record mode; no byte-array editing fallback is allowed.
  Req(ElementByIndex(Req(r, 'NVNM\Triangles'), 502), 'Vertex 0');
  Req(ElementByIndex(Req(r, 'NVNM\Triangles'), 502), 'Flags');
end;

procedure AssertOtherGeometry(a, b: IInterface);
var
  ga, gb, x, y: IInterface;
  i: Integer;
  n: string;
begin
  ga := Req(a, 'NVNM');
  gb := Req(b, 'NVNM');
  Need(ElementCount(ga) = ElementCount(gb), 'NVNM definition/member count changed');
  for i := 0 to ElementCount(ga) - 1 do begin
    x := ElementByIndex(ga, i);
    y := ElementByIndex(gb, i);
    n := BaseName(x);
    Need(n = BaseName(y), 'NVNM member order changed');
    if (n <> 'Triangles') and (n <> 'Door Triangles') then
      AssertTree(x, y, 'unchanged geometry/' + n);
  end;
end;

procedure AssertTriangles(r, vanilla: IInterface; kind: string);
var
  a, b, ta, tb, fa, fb: IInterface;
  i, j, expected: Integer;
begin
  a := Req(r, 'NVNM\Triangles');
  b := Req(vanilla, 'NVNM\Triangles');
  Need(ElementCount(a) = ElementCount(b), 'Triangle array size changed');
  for i := 0 to ElementCount(b) - 1 do begin
    ta := ElementByIndex(a, i);
    tb := ElementByIndex(b, i);
    Need(ElementCount(ta) = 8, 'Typed Triangle shape is not 4.1.5f');
    Need(ElementCount(tb) = 8, 'Typed vanilla Triangle shape is not 4.1.5f');
    for j := 0 to 7 do begin
      fa := ElementByIndex(ta, j);
      fb := ElementByIndex(tb, j);
      if BaseName(fa) = 'Flags' then begin
        Need(BaseName(fb) = 'Flags', 'Triangle Flags field order changed');
        expected := GetNativeValue(fb);
        if ((kind = 'GLEN') and (i = 502)) or
           ((kind = 'AK') and (i = 404)) or
           ((kind = 'PATCH') and ((i = 404) or (i = 502))) then
          expected := 3072;
        Need(GetNativeValue(fa) = expected, 'Unexpected triangle flags at ' + IntToStr(i));
      end else
        AssertTree(fa, fb, 'triangle/' + IntToStr(i) + '/' + BaseName(fa));
    end;
  end;
end;

function DoorAt(r: IInterface; triangle: Integer): IInterface;
var
  a, item: IInterface;
  i, found: Integer;
begin
  Result := nil;
  found := 0;
  a := Req(r, 'NVNM\Door Triangles');
  for i := 0 to ElementCount(a) - 1 do begin
    item := ElementByIndex(a, i);
    Need(ElementCount(item) = 3, 'Unexpected Door Triangle structure');
    if GetNativeValue(Req(item, 'Triangle before door')) = triangle then begin
      Result := item;
      Inc(found);
    end;
  end;
  Need(found = 1, 'Expected exactly one Door Triangle for ' + IntToStr(triangle));
end;

procedure AssertDoor(r: IInterface; triangle: Integer; owner: string; objectID: Integer);
var
  item, linked, origin: IInterface;
begin
  item := DoorAt(r, triangle);
  Need(IntToHex(GetNativeValue(Req(item, 'CRC Hash')), 8) = 'E48B73F3', 'Door CRC differs');
  linked := LinksTo(Req(item, 'Door Ref'));
  Need(Assigned(linked), 'Unresolved typed Door Ref');
  Need(Signature(linked) = 'REFR', 'Door Ref is not REFR');
  origin := MasterOrSelf(linked);
  Need(SameText(GetFileName(GetFile(origin)), owner), 'Door Ref origin changed');
  Need((GetLoadOrderFormID(origin) and $00FFFFFF) = objectID, 'Door Ref object ID changed');
end;

procedure AssertDoors(r: IInterface; kind: string);
var
  expected: Integer;
begin
  expected := 1;
  if (kind = 'GLEN') or (kind = 'AK') then expected := 2;
  if kind = 'PATCH' then expected := 3;
  Need(ElementCount(Req(r, 'NVNM\Door Triangles')) = expected, 'Door Triangle count changed');
  AssertDoor(r, 2, 'Skyrim.esm', $07BD1B);
  if (kind = 'GLEN') or (kind = 'PATCH') then
    AssertDoor(r, 502, 'Glenmoril.esm', $0122F4);
  if (kind = 'AK') or (kind = 'PATCH') then
    AssertDoor(r, 404, 'AKSkyrimUnderground.esm', $2C376B);
end;

function OverrideIn(f, masterRecord: IInterface; owner: string): IInterface;
begin
  Result := RecordByFormID(f, LoadOrderFormIDtoFileFormID(f, GetLoadOrderFormID(masterRecord)), True);
  Need(Assigned(Result), 'Source override missing: ' + owner);
  Need(SameText(GetFileName(GetFile(Result)), owner), 'Source lookup fell back to a master: ' + owner);
end;

procedure AssertNAVMChain(masterRecord: IInterface; verifyMode: Boolean);
var
  i: Integer;
  r: IInterface;
  owner: string;
begin
  for i := 0 to OverrideCount(masterRecord) - 1 do begin
    r := OverrideByIndex(masterRecord, i);
    owner := GetFileName(GetFile(r));
    Need(SameText(owner, 'Glenmoril.esm') or SameText(owner, 'AKSkyrimUnderground.esm') or
         (verifyMode and SameText(owner, PATCH_NAME)), 'Unreviewed NAVM override in chain: ' + owner);
  end;
  owner := GetFileName(GetFile(WinningOverride(masterRecord)));
  if verifyMode then
    Need(SameText(owner, PATCH_NAME), 'New patch is not final NAVM winner')
  else
    Need(SameText(owner, 'AKSkyrimUnderground.esm'), 'Final source NAVM winner is not AK');
end;

function WinnerExcludingPatch(cellMaster: IInterface): IInterface;
var
  i: Integer;
  r: IInterface;
begin
  Result := cellMaster;
  for i := 0 to OverrideCount(cellMaster) - 1 do begin
    r := OverrideByIndex(cellMaster, i);
    if not SameText(GetFileName(GetFile(r)), PATCH_NAME) then
      if GetLoadOrder(GetFile(r)) > GetLoadOrder(GetFile(Result)) then Result := r;
  end;
end;

function InfoFor(naviRecord, navMaster: IInterface): IInterface;
var
  infos, item, linked: IInterface;
  i, found: Integer;
begin
  Result := nil;
  found := 0;
  infos := ElementByPath(naviRecord, 'Navmesh Infos');
  if not Assigned(infos) then Exit;
  for i := 0 to ElementCount(infos) - 1 do begin
    item := ElementByIndex(infos, i);
    linked := LinksTo(Req(item, 'Navmesh'));
    Need(Assigned(linked), 'Unresolved NAVI/NVMI Navmesh key');
    if SameRecord(linked, navMaster) then begin
      Result := item;
      Inc(found);
    end;
  end;
  Need(found < 2, 'Duplicate target NVMI keys in one NAVI');
end;

procedure AssertInfoOther(a, b: IInterface);
var
  i: Integer;
  x, y: IInterface;
begin
  Need(ElementCount(a) = ElementCount(b), 'NVMI member count differs');
  for i := 0 to ElementCount(a) - 1 do begin
    x := ElementByIndex(a, i);
    y := ElementByIndex(b, i);
    Need(BaseName(x) = BaseName(y), 'NVMI member order changed');
    if BaseName(x) <> 'Door Links' then AssertTree(x, y, 'unchanged target NVMI/' + BaseName(x));
  end;
end;

procedure RemapInfoReferences(copyInfo, sourceInfo: IInterface);
var
  i: Integer;
  linked: IInterface;
begin
  Need(BaseName(copyInfo) = BaseName(sourceInfo), 'NVMI typed relink field mismatch');
  Need(ElementCount(copyInfo) = ElementCount(sourceInfo), 'NVMI typed relink shape mismatch');
  if ElementCount(sourceInfo) > 0 then begin
    for i := 0 to ElementCount(sourceInfo) - 1 do
      RemapInfoReferences(ElementByIndex(copyInfo, i), ElementByIndex(sourceInfo, i));
    Exit;
  end;
  linked := LinksTo(sourceInfo);
  if Assigned(linked) then
    if ElementType(linked) = etMainRecord then
      SetEditValue(copyInfo, IntToHex(GetLoadOrderFormID(linked), 8));
end;

function InfoDoor(info, target: IInterface): IInterface;
var
  doors, item, linked: IInterface;
  i, found: Integer;
begin
  Result := nil;
  found := 0;
  doors := Req(info, 'Door Links');
  for i := 0 to ElementCount(doors) - 1 do begin
    item := ElementByIndex(doors, i);
    Need(ElementCount(item) = 2, 'Unexpected NAVI Door Link structure');
    Need(IntToHex(GetNativeValue(Req(item, 'CRC Hash')), 8) = 'E48B73F3', 'NAVI Door Link CRC changed');
    linked := LinksTo(Req(item, 'Door Ref'));
    Need(Assigned(linked), 'Unresolved NAVI Door Ref');
    if SameRecord(linked, target) then begin
      Result := item;
      Inc(found);
    end;
  end;
  Need(found = 1, 'Expected exactly one matching NAVI Door Link');
end;

procedure AssertInfoDoors(info, vanilla, glen, ak: IInterface; kind: string);
var
  expected: Integer;
begin
  expected := 1;
  if (kind = 'GLEN') or (kind = 'AK') then expected := 2;
  if kind = 'PATCH' then expected := 3;
  Need(ElementCount(Req(info, 'Door Links')) = expected, 'NAVI target Door Link count changed');
  InfoDoor(info, LinksTo(Req(DoorAt(vanilla, 2), 'Door Ref')));
  if (kind = 'GLEN') or (kind = 'PATCH') then
    InfoDoor(info, LinksTo(Req(DoorAt(glen, 502), 'Door Ref')));
  if (kind = 'AK') or (kind = 'PATCH') then
    InfoDoor(info, LinksTo(Req(DoorAt(ak, 404), 'Door Ref')));
end;

function EffectiveInfoExcludingPatch(naviMaster, navMaster: IInterface): IInterface;
var
  i: Integer;
  r, item: IInterface;
  owner: string;
begin
  Result := InfoFor(naviMaster, navMaster);
  Need(Assigned(Result), 'Vanilla target NVMI absent');
  for i := 0 to OverrideCount(naviMaster) - 1 do begin
    r := OverrideByIndex(naviMaster, i);
    owner := GetFileName(GetFile(r));
    if not SameText(owner, PATCH_NAME) then begin
      item := InfoFor(r, navMaster);
      if Assigned(item) then begin
        Need(SameText(owner, 'Glenmoril.esm') or SameText(owner, 'AKSkyrimUnderground.esm'),
          'Unreviewed source writes target NVMI: ' + owner);
        if GetLoadOrder(GetFile(item)) > GetLoadOrder(GetFile(Result)) then Result := item;
      end;
    end;
  end;
  Need(SameText(GetFileName(GetFile(Result)), 'AKSkyrimUnderground.esm'), 'Effective prior target NVMI source is not AK');
end;

procedure AssertNoTargetPath(e, navMaster: IInterface);
var
  i: Integer;
  linked: IInterface;
begin
  if not Assigned(e) then Exit;
  if ElementCount(e) > 0 then begin
    for i := 0 to ElementCount(e) - 1 do AssertNoTargetPath(ElementByIndex(e, i), navMaster);
    Exit;
  end;
  linked := LinksTo(e);
  if Assigned(linked) then
    if ElementType(linked) = etMainRecord then
      Need(not SameRecord(linked, navMaster), 'Final NAVI precomputed/deleted table uses target NAVM; separate investigation required');
end;

procedure AssertOtherInfos(copyNavi, sourceNavi, navMaster: IInterface);
var
  a, b, x, y: IInterface;
  i, j: Integer;
begin
  a := Req(copyNavi, 'Navmesh Infos');
  b := Req(sourceNavi, 'Navmesh Infos');
  i := 0;
  j := 0;
  // Linear ordered comparison. Adding the single sorted target is the only
  // permitted array difference; any unexpected reordering fails closed.
  while j < ElementCount(b) do begin
    y := ElementByIndex(b, j);
    if not SameRecord(LinksTo(Req(y, 'Navmesh')), navMaster) then begin
      while i < ElementCount(a) do begin
        x := ElementByIndex(a, i);
        if not SameRecord(LinksTo(Req(x, 'Navmesh')), navMaster) then Break;
        Inc(i);
      end;
      Need(i < ElementCount(a), 'An unrelated NVMI entry disappeared');
      AssertTree(ElementByIndex(a, i), y, 'unchanged other NVMI/' + IntToStr(j));
      Inc(i);
    end;
    Inc(j);
  end;
  while i < ElementCount(a) do begin
    x := ElementByIndex(a, i);
    Need(SameRecord(LinksTo(Req(x, 'Navmesh')), navMaster), 'Unexpected new unrelated NVMI entry');
    Inc(i);
  end;
end;

procedure AssertNaviRest(copyNavi, sourceNavi: IInterface);
var
  i: Integer;
  x, y: IInterface;
begin
  Need(ElementCount(copyNavi) = ElementCount(sourceNavi), 'NAVI top-level structure changed');
  AssertRecordHeader(copyNavi, sourceNavi, 'NAVI header');
  for i := 0 to ElementCount(sourceNavi) - 1 do begin
    y := ElementByIndex(sourceNavi, i);
    if (BaseName(y)<>'Record Header') then begin
      x := UniqueTop(copyNavi,FieldToken(y));Need(Assigned(x),'NAVI field missing'+ComparisonContext(x,y));
      if BaseName(y) <> 'Navmesh Infos' then AssertTree(x, y, 'unchanged NAVI/' + BaseName(y));
    end;
  end;
  for i:=0 to ElementCount(copyNavi)-1 do begin
    x:=ElementByIndex(copyNavi,i);
    if BaseName(x)<>'Record Header' then Need(Assigned(UniqueTop(sourceNavi,FieldToken(x))),'NAVI extra field'+ComparisonContext(x,sourceNavi));
  end;
end;

procedure AssertOnlyExistingOverrides(patchFile, navMaster, cellMaster, naviMaster: IInterface);
var
  i, navCount, cellCount, naviCount: Integer;
  r: IInterface;
  sig: string;
begin
  navCount := 0;
  cellCount := 0;
  naviCount := 0;
  for i := 0 to RecordCount(patchFile) - 1 do begin
    r := RecordByIndex(patchFile, i);
    sig := Signature(r);
    if sig <> 'TES4' then begin
      if sig = 'NAVM' then begin
        Need(SameRecord(r, navMaster), 'Unexpected NAVM/new FormID');
        Inc(navCount);
      end else if sig = 'CELL' then begin
        Need(SameRecord(r, cellMaster), 'Unexpected CELL/new FormID');
        Inc(cellCount);
      end else if sig = 'NAVI' then begin
        Need(SameRecord(r, naviMaster), 'Unexpected NAVI/new FormID');
        Inc(naviCount);
      end else
        Need(False, 'Unexpected generated record signature: ' + sig);
      Need(SameText(GetFileName(GetFile(MasterOrSelf(r))), 'Skyrim.esm'), 'Own/new records are forbidden');
    end;
  end;
  Need(navCount = 1, 'Expected one existing Skyrim NAVM override');
  Need(cellCount = 1, 'Expected one unchanged existing Skyrim CELL container override');
  Need(naviCount = 1, 'Expected one existing Skyrim NAVI override');
  Need(GetIsESL(patchFile), 'Patch lacks ESL flag');
end;

function Initialize: Integer;
var
  vanillaFile, glenFile, akFile, patchFile: IInterface;
  vanilla, glen, ak, parentCell, cellSource, cellCopy, navCopy: IInterface;
  sourceDoor, newDoor, targetDoor, doors: IInterface;
  naviMaster, glenNavi, akNavi, naviSource, naviCopy: IInterface;
  vanillaInfo, glenInfo, akInfo, effectiveInfo, copyInfo, glenInfoDoor: IInterface;
  stream: TFileStream;
begin
  Result := 1;
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1,
    'This draft is restricted to a Database-owned Data view');
  if VERIFY_ONLY then
    Need(FileExists(DataPath + PATCH_NAME), 'Reload verification requires an installed candidate in VFS Data');
  vanillaFile := ReqFile('Skyrim.esm');
  glenFile := ReqFile('Glenmoril.esm');
  akFile := ReqFile('AKSkyrimUnderground.esm');
  Need(not GetIsESL(glenFile), 'Glen must remain a full master');
  Need(not GetIsESL(akFile), 'AK must remain a full master');
  vanilla := RecordByFormID(vanillaFile, $00016F5D, False);
  Need(Assigned(vanilla), 'Skyrim NAVM 016F5D absent');
  glen := OverrideIn(glenFile, vanilla, 'Glenmoril.esm');
  ak := OverrideIn(akFile, vanilla, 'AKSkyrimUnderground.esm');
  AssertNAVMChain(vanilla, VERIFY_ONLY);
  AssertOneNVNM(vanilla);
  AssertOneNVNM(glen);
  AssertOneNVNM(ak);
  Need(GetNativeValue(Req(ElementByIndex(Req(vanilla, 'NVNM\Triangles'), 404), 'Flags')) = 2048, 'Vanilla tri404 changed');
  Need(GetNativeValue(Req(ElementByIndex(Req(vanilla, 'NVNM\Triangles'), 502), 'Flags')) = 2048, 'Vanilla tri502 changed');
  AssertOtherGeometry(glen, vanilla);
  AssertOtherGeometry(ak, vanilla);
  AssertTriangles(glen, vanilla, 'GLEN');
  AssertTriangles(ak, vanilla, 'AK');
  AssertDoors(vanilla, 'VANILLA');
  AssertDoors(glen, 'GLEN');
  AssertDoors(ak, 'AK');
  parentCell := RecordByFormID(vanillaFile, $00016D72, False);
  Need(Assigned(parentCell), 'Expected Skyrim parent CELL absent');
  // The 'Parent' union resolves to a scalar Parent Cell in this interior.
  // TwbUnion/UnionDoInit keep that scalar in the union itself, not a nested
  // child named Parent Cell (4.1.5f wbImplementation.pas:21594-21608).
  Need(SameRecord(LinksTo(Req(vanilla, 'NVNM\Pathing Cell\Parent')), parentCell), 'Unexpected NAVM parent CELL');
  cellSource := WinnerExcludingPatch(parentCell);
  AddMessage('BOUNDED_NAVM_CELL_SOURCE|' + GetFileName(GetFile(cellSource)) + '|00016D72');
  naviMaster := RecordByFormID(vanillaFile, $00012FB4, False);
  Need(Assigned(naviMaster), 'Expected Skyrim NAVI absent');
  glenNavi := OverrideIn(glenFile, naviMaster, 'Glenmoril.esm');
  akNavi := OverrideIn(akFile, naviMaster, 'AKSkyrimUnderground.esm');
  vanillaInfo := InfoFor(naviMaster, vanilla);
  glenInfo := InfoFor(glenNavi, vanilla);
  akInfo := InfoFor(akNavi, vanilla);
  Need(Assigned(vanillaInfo), 'Vanilla target NVMI absent');
  Need(Assigned(glenInfo), 'Glen target NVMI absent');
  Need(Assigned(akInfo), 'AK target NVMI absent');
  AssertInfoOther(glenInfo, vanillaInfo);
  AssertInfoOther(akInfo, vanillaInfo);
  AssertInfoDoors(vanillaInfo, vanilla, glen, ak, 'VANILLA');
  AssertInfoDoors(glenInfo, vanilla, glen, ak, 'GLEN');
  AssertInfoDoors(akInfo, vanilla, glen, ak, 'AK');
  effectiveInfo := EffectiveInfoExcludingPatch(naviMaster, vanilla);
  AssertTree(effectiveInfo, akInfo, 'Effective AK NVMI');
  naviSource := WinnerExcludingPatch(naviMaster);
  Req(naviSource, 'Navmesh Infos');
  AssertNoTargetPath(ElementByPath(naviSource, 'NVPP'), vanilla);
  AssertNoTargetPath(ElementByPath(naviSource, 'NVSI'), vanilla);
  AddMessage('BOUNDED_NAVM_NAVI_SOURCE|' + GetFileName(GetFile(naviSource)) + '|00012FB4');

  if VERIFY_ONLY then begin
    patchFile := ReqFile(PATCH_NAME);
    navCopy := OverrideIn(patchFile, vanilla, PATCH_NAME);
    cellCopy := OverrideIn(patchFile, parentCell, PATCH_NAME);
    naviCopy := OverrideIn(patchFile, naviMaster, PATCH_NAME);
    Need(SameText(GetFileName(GetFile(WinningOverride(naviMaster))), PATCH_NAME), 'Patch is not final NAVI winner');
  end else begin
    Need(not Assigned(FileByName(PATCH_NAME)), 'Patch already loaded; refuse overwrite');
    Need(not FileExists(DataPath + PATCH_NAME), 'Patch already exists in VFS Data');
    Need(not FileExists(OUTPUT_FILE), 'Candidate output already exists; refuse overwrite');
    patchFile := AddNewFileName(PATCH_NAME);
    Need(Assigned(patchFile), 'Could not create new in-memory patch');
    AddMasterIfMissing(patchFile, 'Skyrim.esm');
    AddMasterIfMissing(patchFile, 'Glenmoril.esm');
    AddMasterIfMissing(patchFile, 'AKSkyrimUnderground.esm');
    AddMasterIfMissing(patchFile, GetFileName(GetFile(cellSource)));
    AddMasterIfMissing(patchFile, GetFileName(GetFile(naviSource)));
    Need(AddRequiredElementMasters(cellSource, patchFile, False, True), 'CELL required masters failed');
    Need(AddRequiredElementMasters(ak, patchFile, False, True), 'AK required masters failed');
    sourceDoor := DoorAt(glen, 502);
    Need(AddRequiredElementMasters(sourceDoor, patchFile, False, True), 'Glen Door required masters failed');
    Need(AddRequiredElementMasters(naviSource, patchFile, False, True), 'Final NAVI required masters failed');
    Need(AddRequiredElementMasters(akInfo, patchFile, False, True), 'AK NVMI required masters failed');
    SortMasters(patchFile);
    Need(MasterCount(patchFile) <= 253, 'NAVI forwarding would exceed conservative master limit');
    // Explicitly preserve the final CELL winner before container recursion.
    cellCopy := CopyOverride(cellSource, patchFile);
    Need(Assigned(cellCopy), 'CELL copy failed');
    navCopy := CopyOverride(ak, patchFile);
    Need(Assigned(navCopy), 'NAVM copy failed');
    AssertTree(Req(navCopy, 'NVNM'), Req(ak, 'NVNM'), 'Initial AK copy');
    SetNativeValue(Req(ElementByIndex(Req(navCopy, 'NVNM\Triangles'), 502), 'Flags'),
      GetNativeValue(Req(ElementByIndex(Req(glen, 'NVNM\Triangles'), 502), 'Flags')));
    doors := Req(navCopy, 'NVNM\Door Triangles');
    newDoor := ElementAssign(doors, HighInteger, sourceDoor, False);
    Need(Assigned(newDoor), 'Typed Door Triangle append failed');
    targetDoor := LinksTo(Req(sourceDoor, 'Door Ref'));
    Need(Assigned(targetDoor), 'Glen source Door Ref no longer resolves');
    // SetEditValue consumes the resolved LOAD-ORDER form, then xEdit writes the
    // target-file namespace. No source raw master-index bytes are reused.
    SetEditValue(Req(newDoor, 'Door Ref'), IntToHex(GetLoadOrderFormID(targetDoor), 8));
    naviCopy := CopyOverride(naviSource, patchFile);
    Need(Assigned(naviCopy), 'Final NAVI copy failed');
    AssertUnchangedRecord(naviCopy, naviSource, 'Initial full final NAVI copy');
    copyInfo := InfoFor(naviCopy, vanilla);
    if not Assigned(copyInfo) then begin
      copyInfo := ElementAssign(Req(naviCopy, 'Navmesh Infos'), HighInteger, akInfo, False);
      Need(Assigned(copyInfo), 'Typed target NVMI append failed');
      RemapInfoReferences(copyInfo, akInfo);
    end;
    Need(Assigned(copyInfo), 'Typed target NVMI forwarding failed');
    AssertTree(copyInfo, akInfo, 'Initial exact AK NVMI copy');
    glenInfoDoor := InfoDoor(glenInfo, targetDoor);
    newDoor := ElementAssign(Req(copyInfo, 'Door Links'), HighInteger, glenInfoDoor, False);
    Need(Assigned(newDoor), 'Typed NAVI Glen Door append failed');
    SetEditValue(Req(newDoor, 'Door Ref'), IntToHex(GetLoadOrderFormID(targetDoor), 8));
    SetIsESL(patchFile, True);
  end;

  AssertOneNVNM(navCopy);
  AssertOtherGeometry(navCopy, ak);
  AssertTriangles(navCopy, vanilla, 'PATCH');
  AssertDoors(navCopy, 'PATCH');
  AssertTree(Req(navCopy, 'Record Header\Record Flags'), Req(ak, 'Record Header\Record Flags'), 'NAVM flags');
  AssertUnchangedRecord(cellCopy, cellSource, 'Unchanged final CELL winner');
  copyInfo := InfoFor(naviCopy, vanilla);
  Need(Assigned(copyInfo), 'Output target NVMI absent');
  AssertInfoOther(copyInfo, akInfo);
  AssertInfoDoors(copyInfo, vanilla, glen, ak, 'PATCH');
  AssertOtherInfos(naviCopy, naviSource, vanilla);
  AssertNaviRest(naviCopy, naviSource);
  AssertOnlyExistingOverrides(patchFile, vanilla, parentCell, naviMaster);
  Need(Check(navCopy) = '', 'New NAVM Check contains diagnostics: ' + Check(navCopy));
  Need(Check(cellCopy) = '', 'Copied CELL Check contains diagnostics: ' + Check(cellCopy));
  Need(Check(naviCopy) = '', 'Copied NAVI Check contains diagnostics: ' + Check(naviCopy));
  if not VERIFY_ONLY then begin
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));
    stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
    try
      FileWriteToStream(patchFile, stream, 0); // rmNo; avoid known reset-modified serializer assertion.
    finally
      stream.Free;
    end;
    AddMessage('BOUNDED_NAVM_CANDIDATE_EXPORTED|' + OUTPUT_FILE);
  end;
  if VERIFY_ONLY then
    AddMessage('BOUNDED_NAVM_RELOAD_TYPED_PASS|NAVM=Skyrim.esm:016F5D|CELL=Skyrim.esm:016D72|NAVI=Skyrim.esm:012FB4|OWN_RECORDS=0|DOORS=3')
  else
    AddMessage('BOUNDED_NAVM_INMEMORY_TYPED_PASS|NAVM=Skyrim.esm:016F5D|CELL=Skyrim.esm:016D72|NAVI=Skyrim.esm:012FB4|OWN_RECORDS=0|DOORS=3');
  Result := 0;
end;

end.
