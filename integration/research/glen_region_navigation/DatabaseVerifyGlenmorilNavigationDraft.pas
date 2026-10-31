unit UserScript;
// DRAFT: requires exact-source preflight and normal xEdit4.1.5f definitions.
// Supersedes the earlier AK-only draft; do not load both candidates together.
const
 VERIFY_ONLY = True;
 PATCH_NAME = 'Database Glenmoril Navigation Compatibility.esp';
 OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\glen_region_navigation\candidate\Database Glenmoril Navigation Compatibility.esp';

var stockOrphanGuardChecked, stockOrphanTreeDumped: Boolean;

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
  if (VarType(GetNativeValue(e)) and $2000) <> 0 then begin
    Result := '<native Variant array type=' + IntToStr(VarType(GetNativeValue(e))) + '> ' + GetEditValue(e); Exit;
  end;
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

procedure AssertNativeByteVector(a,b: IInterface; labelText: string);
var
  streamA,streamB: TBytesStream;
  readerA,readerB: TBinaryReader;
  i,n,byteA,byteB: Integer;
begin
  // Exact 4.1.5f xejviScriptAdapterMisc:689-713 and2053-2062.
  // Covers byte vectors returned by dtUnion as well as dtByteArray.
  NeedCompared((VarType(GetNativeValue(a))=8209) and (VarType(GetNativeValue(b))=8209),
    labelText+': expected native Array Byte on both sides',a,b);
  streamA:=TBytesStream.Create(GetNativeValue(a));
  try
    streamB:=TBytesStream.Create(GetNativeValue(b));
    try
      NeedCompared(streamA.Size=streamB.Size,labelText+': native vector length changed',a,b);
      NeedCompared((streamA.Size>=0) and (streamA.Size<=$7FFFFFFF),labelText+': unsupported byte vector size',a,b);
      n:=streamA.Size;streamA.Position:=0;streamB.Position:=0;
      readerA:=TBinaryReader.Create(streamA);
      try
        readerB:=TBinaryReader.Create(streamB);
        try
          for i:=0 to n-1 do begin
            byteA:=readerA.ReadByte;byteB:=readerB.ReadByte;
            NeedCompared(byteA=byteB,labelText+': exact native byte changed at '+IntToStr(i)+
              ' dst='+IntToHex(byteA,2)+' src='+IntToHex(byteB,2),a,b);
          end;
          NeedCompared((streamA.Position=n) and (streamB.Position=n),labelText+': incomplete byte traversal',a,b);
        finally readerB.Free;end;
      finally readerA.Free;end;
    finally streamB.Free;end;
  finally streamA.Free;end;
end;

procedure AssertTree(a, b: IInterface; labelText: string);
var
  i,typeA,typeB: Integer;
  la, lb: IInterface;
  linkedA,linkedB,equalNative: Boolean;
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
  la := LinksTo(a);
  lb := LinksTo(b);
  linkedA:=False;linkedB:=False;
  if Assigned(la) then linkedA:=ElementType(la)=etMainRecord;
  if Assigned(lb) then linkedB:=ElementType(lb)=etMainRecord;
  if linkedA or linkedB then begin
    NeedCompared(linkedA and linkedB,labelText+': unresolved/non-record counterpart FormID',a,b);
    NeedCompared(SameRecord(la,lb),labelText+': resolved canonical FormID changed',a,b);
    Exit;
  end;
  typeA:=VarType(GetNativeValue(a));typeB:=VarType(GetNativeValue(b));
  if (typeA=8209) or (typeB=8209) then begin
    AssertNativeByteVector(a,b,labelText);Exit;
  end;
  NeedCompared(((typeA and $2000)=0) and ((typeB and $2000)=0),
    labelText+': unsupported non-byte native Variant array',a,b);
  if (DefType(a)=dtByteArray) or (DefType(b)=dtByteArray) then begin
    NeedCompared(False,labelText+': byte-array definition returned unexpected native Variant type',a,b);Exit;
  end;
  // Exact native numeric comparison, not rounded display strings. Non-record
  // LinksTo callbacks on vertex/triangle indices are deliberately not FormIDs.
  try equalNative:=GetNativeValue(a)=GetNativeValue(b);
  except NeedCompared(False,labelText+': native value is not scalar-comparable',a,b);Exit;end;
  NeedCompared(equalNative,labelText+': exact native value changed',a,b);
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

function StockFieldContext(e: IInterface; expectedText: string): string;
begin
  Result := ' | record=' + CanonicalRecordText(e) + ' path=' + FullPath(e) +
    ' actualNative=' + NativeText(e) + ' edit=' + GetEditValue(e) +
    ' nativeVarType=' + IntToStr(VarType(GetNativeValue(e))) +
    ' definition=' + IntToStr(Ord(DefType(e))) +
    ' element=' + IntToStr(Ord(ElementType(e))) + ' expected=' + expectedText;
end;

function StockSingleLE(value: Variant; seedElement: IInterface): string;
var stream: TBytesStream; writer: TBinaryWriter; reader: TBinaryReader; i: Integer;
begin
  Result := '';
  Need(VarType(GetNativeValue(seedElement)) = 8209, 'Single witness seed is not native Array Byte');
  stream := TBytesStream.Create(GetNativeValue(seedElement));
  try
    Need(stream.Size = 4, 'Single witness seed size is not4');
    stream.Position := 0; writer := TBinaryWriter.Create(stream);
    try
      // Exact4.1.5f binding xejviScriptAdapterMisc:793-795 /2077:
      // WriteSingle explicitly casts to IEEE754 Single; no decimal tolerance.
      writer.WriteSingle(value);
      Need(stream.Size = 4, 'Single witness serialized size is not4');
      stream.Position := 0; reader := TBinaryReader.Create(stream);
      try
        for i := 0 to 3 do Result := Result + IntToHex(reader.ReadByte, 2);
        Need(stream.Position = 4, 'Single witness read incomplete');
      finally reader.Free; end;
    finally writer.Free; end;
  finally stream.Free; end;
end;

procedure AssertStockSingle(info: IInterface; fieldName: string;
  expectedLiteral: Variant; expectedLE: string);
var e,seed: IInterface; actualLE,literalLE,literalText,contextText: string;
begin
  e := Req(info, fieldName); seed := Req(info, 'Preferred Merges Flag');
  literalText := expectedLiteral;
  contextText := StockFieldContext(e, expectedLE) + ' literal=' + literalText +
    ' literalVarType=' + IntToStr(VarType(expectedLiteral));
  AddMessage('NAVMI_ORPHAN_FLOAT_INPUT|' + fieldName + contextText);
  Need(DefType(e) = dtFloat, 'Known stock orphan float definition changed' + contextText);
  Need(VarType(GetNativeValue(e)) = 5, 'Known stock orphan float native Variant is not Double' + contextText);
  actualLE := StockSingleLE(GetNativeValue(e), seed);
  literalLE := StockSingleLE(expectedLiteral, seed);
  AddMessage('NAVMI_ORPHAN_FLOAT_SINGLE|' + fieldName + '|actualLE=' + actualLE +
    '|literalLE=' + literalLE + '|expectedLE=' + expectedLE + contextText);
  // wbInterface:71/16324-16332/16643-16647/16689-16703 round native
  // Single fields to6decimal places. Decimal literal equality is not a raw
  // serialized-Single test. Require every source Single byte here instead.
  Need(SameText(actualLE, expectedLE), 'Known stock orphan ' + fieldName +
    ' serialized Single bytes changed actual=' + actualLE + ' expected=' + expectedLE + contextText);
end;

procedure DumpStockOrphanTree(e: IInterface; depth: Integer; var nodes: Integer);
var i,n: Integer; linked: IInterface; nativeTypeText,editText,linksText: string;
begin
  Need(Assigned(e), 'Orphan full-tree diagnostic encountered missing element');
  Inc(nodes); Need((depth <= 12) and (nodes <= 128), 'Orphan full-tree diagnostic exceeded bounded source scope');
  n := ElementCount(e);
  nativeTypeText := '<unavailable>'; editText := '<unavailable>'; linksText := '<none>';
  try nativeTypeText := IntToStr(VarType(GetNativeValue(e))); except end;
  try editText := GetEditValue(e); except end;
  linked := LinksTo(e);
  if Assigned(linked) then begin
    if ElementType(linked) = etMainRecord then linksText := CanonicalRecordText(linked)
    else linksText := '<non-record> ' + Name(linked);
  end;
  AddMessage('NAVMI_ORPHAN_TREE|depth=' + IntToStr(depth) + '|name=' + Name(e) +
    '|base=' + BaseName(e) + '|definition=' + IntToStr(Ord(DefType(e))) +
    '|element=' + IntToStr(Ord(ElementType(e))) + '|children=' + IntToStr(n) +
    '|nativeVarType=' + nativeTypeText + '|native=' + NativeText(e) +
    '|edit=' + editText + '|record=' + CanonicalRecordText(e) +
    '|links=' + linksText + '|path=' + FullPath(e));
  for i := 0 to n - 1 do DumpStockOrphanTree(ElementByIndex(e, i), depth + 1, nodes);
end;

function IsKnownStockOrphan(info: IInterface): Boolean;
var
  owner, recordElement, keyElement, mergeElement, parentElement: IInterface;
  stream: TBytesStream;
  reader: TBinaryReader;
  i, dumpNodes: Integer;
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
    AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_CRC_GUARD_ONLY|Skyrim.esm|028E37|PAYLOAD_SHA256=8a220fa216d44545e8367bde7fd0d3fe7bcd43b1598f7eb131aa99d4fe3a7304');
  end;
  if not stockOrphanTreeDumped then begin
    AddMessage('NAVMI_ORPHAN_TREE_BEGIN|Skyrim.esm|028E37|ALL12FIELDS_BEFORE_GUARDS');
    dumpNodes := 0; DumpStockOrphanTree(info, 0, dumpNodes);
    AddMessage('NAVMI_ORPHAN_TREE_COMPLETE|NODES=' + IntToStr(dumpNodes));
    stockOrphanTreeDumped := True;
  end;
  // All fields of the original49-byte NVMI are checked, not its ordinal.
  // No copy/output record can enter this original-Skyrim-only allowance.
  Need(ElementCount(info) = 12, 'Known stock orphan NVMI member count changed');
  Need(GetNativeValue(Req(info, 'Category')) = 0, 'Known stock orphan category changed' + StockFieldContext(Req(info, 'Category'), '0'));
  AssertStockSingle(info, 'X', -3391.8515625, 'A0FD53C5');
  AssertStockSingle(info, 'Y', 285.758941650390625, '25E18E43');
  AssertStockSingle(info, 'Z', 239.091033935546875, '4E176F43');
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
  Need(GetNativeValue(Req(info, 'Is Island')) = 0, 'Known stock orphan island changed' + StockFieldContext(Req(info, 'Is Island'), '0'));
  Need(ElementCount(Req(info, 'PathingCell')) = 3, 'Known stock orphan pathing layout changed');
  Need(SameText(IntToHex(GetNativeValue(Req(info, 'PathingCell\CRC Hash')), 8), 'A5E9A03C'), 'Known stock orphan path CRC changed' + StockFieldContext(Req(info, 'PathingCell\CRC Hash'), 'A5E9A03C'));
  Need(GetNativeValue(Req(info, 'PathingCell\Parent Worldspace')) = 0, 'Known stock orphan world changed' + StockFieldContext(Req(info, 'PathingCell\Parent Worldspace'), '0'));
  parentElement := Req(info, 'PathingCell\Parent');
  // Exact4.1.5f wbNAVIParentDecider: null Parent Worldspace selects the
  // scalar Parent Cell definition. UnionDoInit does NOT allocate a child
  // for scalar unions; NativeValue/LinksTo delegate to the resolved scalar.
  Need(DefType(parentElement) = dtUnion, 'Known stock orphan parent union definition changed' + StockFieldContext(parentElement, 'dtUnion/zero-child scalar CELL'));
  Need(ElementType(parentElement) = etUnion, 'Known stock orphan parent element type changed' + StockFieldContext(parentElement, 'etUnion'));
  Need(ElementCount(parentElement) = 0, 'Known stock orphan parent scalar union gained children' + StockFieldContext(parentElement, '0children'));
  Need(GetNativeValue(parentElement) = $00028E34, 'Known stock orphan parent cell native value changed' + StockFieldContext(parentElement, '00028E34'));
  // Both original scalar referents028E37(NAVM) and028E34(parent CELL)
  // are absent in the complete SHA-frozen active record index, all signatures.
  // Preserve this exact source nil; never invent a parent or change its bytes.
  Need(not Assigned(LinksTo(parentElement)),
    'Known stock orphan parent unexpectedly resolves; re-audit' + StockFieldContext(parentElement, 'exact00028E34 / nil link'));
  AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_FULL_TYPED_GUARD_PASS|Skyrim.esm|028E37');
  Result := True;
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
    if not Assigned(linked) then begin
      Need(IsKnownStockOrphan(item), 'Unresolved NAVI/NVMI Navmesh key outside exact source guard');
      Need(GetLoadOrderFormID(MasterOrSelf(navMaster)) <> $00028E37, 'Missing requested target cannot be ignored');
    end else if SameRecord(linked, navMaster) then begin
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


function TargetID(c: Integer): Integer;
begin case c of 0:Result:=$016F5D;1:Result:=$0EC466;2:Result:=$0EC469;else Need(False,'Bad case');end;end;
function ParentID(c: Integer): Integer;
begin case c of 0:Result:=$016D72;1:Result:=$009CA3;2:Result:=$009CA0;else Need(False,'Bad case');end;end;
function BaseNameFor(c: Integer): string;
begin case c of 0:Result:='AKSkyrimUnderground.esm';1:Result:='AncientLand2.esp';2:Result:='RedBag''s Falkreath.esp';else Need(False,'Bad case');end;end;
function NewDoorCount(c: Integer): Integer;
begin if c=2 then Result:=2 else Result:=1;end;
function OldDoorCount(c: Integer): Integer;
begin if c=0 then Result:=2 else Result:=0;end;
function SourceTriangle(c,d: Integer): Integer;
begin case c of 0:Result:=502;1:Result:=34;2:if d=0 then Result:=116 else Result:=325;else Need(False,'Bad case');end;end;
function PlannedTriangle(c,d: Integer): Integer;
begin Result:=SourceTriangle(c,d);if (c=2) and (d=1) then Result:=86;end;
function DoorObject(c,d: Integer): Integer;
begin case c of 0:Result:=$0122F4;1:Result:=$014C1D;2:if d=0 then Result:=$0073D4 else Result:=$017737;else Need(False,'Bad case');end;end;
function ExpectedFaceCount(c: Integer): Integer;
begin case c of 0:Result:=532;1:Result:=349;2:Result:=312;else Need(False,'Bad case');end;end;
function ExpectedPorts(c: Integer): Integer;
begin case c of 0:Result:=0;1:Result:=16;2:Result:=17;else Need(False,'Bad case');end;end;
function EdgeName(side: Integer): string;
begin case side of 0:Result:='Edge 0-1';1:Result:='Edge 1-2';2:Result:='Edge 2-0';else Need(False,'Bad side');end;end;
function VertexName(side: Integer): string;
begin Result:='Vertex '+IntToStr(side);end;
function Tri(r: IInterface;i: Integer): IInterface;
var a:IInterface;
begin a:=Req(r,'NVNM\Triangles');Need((i>=0) and (i<ElementCount(a)),'Triangle out of bounds');Result:=ElementByIndex(a,i);Need(ElementCount(Result)=8,'Normal 4.1.5f triangle schema required');end;
function Vertex(r,t:IInterface;j:Integer):IInterface;
begin Result:=ElementByIndex(Req(r,'NVNM\Vertices'),GetNativeValue(Req(t,VertexName(j))));Need(Assigned(Result),'Vertex out of bounds');end;
function VertexEqual(a,b:IInterface):Boolean;
begin Result:=(GetNativeValue(Req(a,'X'))=GetNativeValue(Req(b,'X'))) and
 (GetNativeValue(Req(a,'Y'))=GetNativeValue(Req(b,'Y'))) and (GetNativeValue(Req(a,'Z'))=GetNativeValue(Req(b,'Z')));end;
function FaceEqual(source,st,base,bt:IInterface;rotation:Integer):Boolean;
var j:Integer;
begin Result:=True;for j:=0 to 2 do if not VertexEqual(Vertex(source,st,j),Vertex(base,bt,(j+rotation) mod 3)) then Result:=False;end;
function UniqueFace(source,base:IInterface;c,d:Integer):Integer;
var i,j,count:Integer;st,bt:IInterface;
begin
 Result:=-1;count:=0;st:=Tri(source,SourceTriangle(c,d));
 for i:=0 to ElementCount(Req(base,'NVNM\Triangles'))-1 do begin
  bt:=Tri(base,i);
  for j:=0 to 2 do if FaceEqual(source,st,base,bt,j) then begin Result:=i;Inc(count);end;
 end;
 Need(count=1,'Door face missing/ambiguous or winding reversed');
 Need(Result=PlannedTriangle(c,d),'Unique face mapping changed from audited plan');
 Need((GetNativeValue(Req(Tri(base,Result),'Flags')) and (8 or 512 or 1024))=0,'Base door face deleted/water/already bound');
end;
function EdgeFor(r,t:IInterface;side:Integer):IInterface;
var i:Integer;a:IInterface;
begin i:=GetNativeValue(Req(t,EdgeName(side)));a:=Req(r,'NVNM\Edge Links');Need((i>=0) and (i<ElementCount(a)),'External link index invalid');Result:=ElementByIndex(a,i);end;
function SourceDoor(source:IInterface;c,d:Integer):IInterface;
var a,e,r:IInterface;i,count:Integer;
begin
 Result:=nil;count:=0;a:=Req(source,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin
  e:=ElementByIndex(a,i);
  if GetNativeValue(Req(e,'Triangle before door'))=SourceTriangle(c,d) then begin
   r:=LinksTo(Req(e,'Door Ref'));Need(Assigned(r),'Glen Door Ref unresolved');r:=MasterOrSelf(r);
   if SameText(GetFileName(GetFile(r)),'Glenmoril.esm') then begin
    Need((GetLoadOrderFormID(r) and $00FFFFFF)=DoorObject(c,d),'Authored door identity changed');
    Need(Signature(r)='REFR','Door Ref is not REFR');
    Need(IntToHex(GetNativeValue(Req(e,'CRC Hash')),8)='E48B73F3','Authored CRC changed');
    Result:=e;Inc(count);
   end;
  end;
 end;
 Need(count=1,'Authored Door Triangle absent or ambiguous');
end;
procedure AssertAuthoredDoorReferences(entry:IInterface);
var r,destination:IInterface;
begin
 r:=LinksTo(Req(entry,'Door Ref'));Need(Assigned(r),'Authored door missing');r:=MasterOrSelf(r);
 AssertUnchangedRecord(WinningOverride(r),r,'Unreviewed final authored door REFR change');
 destination:=LinksTo(Req(r,'XTEL\Door'));Need(Assigned(destination),'Authored teleport destination missing');destination:=MasterOrSelf(destination);
 Need(SameText(GetFileName(GetFile(destination)),'Glenmoril.esm'),'Teleport destination source changed');
 AssertUnchangedRecord(WinningOverride(destination),destination,'Unreviewed final destination door REFR change');
 Need(SameRecord(LinksTo(Req(destination,'XTEL\Door')),r),'Authored teleport pair is not reciprocal');
end;
procedure CompareOtherNVNM(a,b:IInterface;ignoreEdgeLinks:Boolean);
var ga,gb,x,y:IInterface;i:Integer;n:string;
begin
 ga:=Req(a,'NVNM');gb:=Req(b,'NVNM');Need(ElementCount(ga)=ElementCount(gb),'NVNM schema changed');
 for i:=0 to ElementCount(ga)-1 do begin
  x:=ElementByIndex(ga,i);y:=ElementByIndex(gb,i);n:=BaseName(x);Need(n=BaseName(y),'NVNM field order changed');
  if (n<>'Triangles') and (n<>'Door Triangles') and not(ignoreEdgeLinks and (n='Edge Links')) then AssertTree(x,y,'preserved NVNM/'+n);
 end;
end;
function IsSourceDoorTriangle(c,index:Integer):Boolean;
var d:Integer;
begin Result:=False;for d:=0 to NewDoorCount(c)-1 do if index=SourceTriangle(c,d) then Result:=True;end;
procedure AssertAuthoredDelta(source,vanilla:IInterface;c:Integer);
var i,j,flags,expected:Integer;a,b:IInterface;
begin
 CompareOtherNVNM(source,vanilla,True);
 Need(ElementCount(Req(source,'NVNM\Triangles'))=ElementCount(Req(vanilla,'NVNM\Triangles')),'Glen changed triangle count');
 for i:=0 to ElementCount(Req(vanilla,'NVNM\Triangles'))-1 do begin
  a:=Tri(source,i);b:=Tri(vanilla,i);
  for j:=0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'authored vertex ordinal');
  AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'authored cover flags');
  flags:=GetNativeValue(Req(b,'Flags'));expected:=flags;if IsSourceDoorTriangle(c,i) then expected:=expected or 1024;
  Need(GetNativeValue(Req(a,'Flags'))=expected,'Glen delta exceeds the authored Door bit');
  for j:=0 to 2 do begin
   if (flags and (1 shl j))<>0 then AssertTree(EdgeFor(source,a,j),EdgeFor(vanilla,b,j),'authored logical external link')
   else AssertTree(Req(a,EdgeName(j)),Req(b,EdgeName(j)),'authored internal adjacency');
  end;
 end;
end;
procedure AssertConnected(base:IInterface;c:Integer);
var seen,queue:TStringList;position,i,j,k,n,flags,otherFlags,ports,shared,doors:Integer;
    t,other,a:IInterface;back:Boolean;
begin
 seen:=TStringList.Create;queue:=TStringList.Create;
 try
  seen.Sorted:=True;i:=PlannedTriangle(c,0);seen.Add(IntToStr(i));queue.Add(IntToStr(i));position:=0;ports:=0;doors:=0;
  while position<queue.Count do begin
   i:=StrToInt(queue[position]);Inc(position);t:=Tri(base,i);flags:=GetNativeValue(Req(t,'Flags'));
   Need((flags and (8 or 512))=0,'Base component deleted or underwater');
   for j:=0 to 2 do begin
    n:=GetNativeValue(Req(t,EdgeName(j)));
    if (flags and (1 shl j))<>0 then begin EdgeFor(base,t,j);Inc(ports);end
    else if n<>-1 then begin
     other:=Tri(base,n);otherFlags:=GetNativeValue(Req(other,'Flags'));back:=False;
     for k:=0 to 2 do if ((otherFlags and (1 shl k))=0) and (GetNativeValue(Req(other,EdgeName(k)))=i) then back:=True;
     Need(back,'Base internal adjacency is not reciprocal');shared:=0;
     for k:=0 to 2 do begin
      a:=Vertex(base,t,k);
      if VertexEqual(a,Vertex(base,other,0)) or VertexEqual(a,Vertex(base,other,1)) or VertexEqual(a,Vertex(base,other,2)) then Inc(shared);
     end;
     Need(shared>=2,'Base internal neighbors do not share an exact geometric edge');
     if (otherFlags and 8)=0 then if seen.IndexOf(IntToStr(n))<0 then begin seen.Add(IntToStr(n));queue.Add(IntToStr(n));end;
    end;
   end;
  end;
  a:=Req(base,'NVNM\Door Triangles');
  for i:=0 to ElementCount(a)-1 do if seen.IndexOf(IntToStr(GetNativeValue(Req(ElementByIndex(a,i),'Triangle before door'))))>=0 then Inc(doors);
  Need(seen.Count=ExpectedFaceCount(c),'Base connected component changed');
  Need(ports=ExpectedPorts(c),'Base component external exits changed');
  Need(doors=OldDoorCount(c),'Base component door exits changed');
  Need((ports>0) or (doors>0),'Door face has no existing reachable topological exit');
 finally seen.Free;queue.Free;end;
end;
function TargetDoor(copyNav,refRecord:IInterface;triangleIndex:Integer):IInterface;
var a,e:IInterface;i,count:Integer;
begin Result:=nil;count:=0;a:=Req(copyNav,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin e:=ElementByIndex(a,i);
  if (GetNativeValue(Req(e,'Triangle before door'))=triangleIndex) and SameRecord(LinksTo(Req(e,'Door Ref')),refRecord) then begin Result:=e;Inc(count);end;
 end;Need(count=1,'Expected mapped Door Triangle absent or duplicated');end;
procedure AssertDoorState(copyNav,base,source:IInterface;c:Integer);
var i,j,d,expected:Integer;a,b,x,y,srcDoor,refRecord:IInterface;
begin
 AssertRecordHeader(copyNav,base,'Preserve NAVM header');
 Need(ElementCount(copyNav)=ElementCount(base),'NAVM top-level fields changed');
 for i:=0 to ElementCount(base)-1 do begin
  b:=ElementByIndex(base,i);
  if BaseName(b)<>'Record Header' then begin
   a:=UniqueTop(copyNav,FieldToken(b));Need(Assigned(a),'NAVM field missing'+ComparisonContext(a,b));
   if BaseName(b)<>'NVNM' then AssertTree(a,b,'Preserve NAVM non-NVNM field');
  end;
 end;
 CompareOtherNVNM(copyNav,base,False);
 Need(ElementCount(Req(copyNav,'NVNM\Triangles'))=ExpectedFaceCount(c),'Base triangle count changed');
 for i:=0 to ExpectedFaceCount(c)-1 do begin
  a:=Tri(copyNav,i);b:=Tri(base,i);
  for j:=0 to 7 do begin
   x:=ElementByIndex(a,j);y:=ElementByIndex(b,j);
   if BaseName(x)='Flags' then begin
    expected:=GetNativeValue(y);
    for d:=0 to NewDoorCount(c)-1 do if i=PlannedTriangle(c,d) then expected:=expected or 1024;
    Need(GetNativeValue(x)=expected,'Unexpected post-copy triangle flags');
   end else AssertTree(x,y,'unchanged base triangle field');
  end;
 end;
 Need(ElementCount(Req(copyNav,'NVNM\Door Triangles'))=OldDoorCount(c)+NewDoorCount(c),'Door count changed unexpectedly');
 a:=Req(base,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin
  srcDoor:=ElementByIndex(a,i);refRecord:=LinksTo(Req(srcDoor,'Door Ref'));
  b:=TargetDoor(copyNav,refRecord,GetNativeValue(Req(srcDoor,'Triangle before door')));AssertTree(b,srcDoor,'preserve base door');
 end;
 for d:=0 to NewDoorCount(c)-1 do begin
  srcDoor:=SourceDoor(source,c,d);refRecord:=LinksTo(Req(srcDoor,'Door Ref'));
  b:=TargetDoor(copyNav,refRecord,PlannedTriangle(c,d));
  AssertTree(Req(b,'CRC Hash'),Req(srcDoor,'CRC Hash'),'preserve authored CRC');
  Need(SameRecord(LinksTo(Req(b,'Door Ref')),refRecord),'Door Ref namespace translation failed');
 end;
end;
function ParentCell(r:IInterface;expected:Integer):IInterface;
var e,p:IInterface;
begin
 Result:=nil;e:=GetContainer(r);
 while Assigned(e) do begin
  if ElementType(e)=etGroupRecord then begin p:=ChildrenOf(e);if Assigned(p) then if Signature(p)='CELL' then begin Result:=MasterOrSelf(p);Break;end;end;
  e:=GetContainer(e);
 end;
 Need(Assigned(Result),'CELL container not found');
 Need(SameText(GetFileName(GetFile(Result)),'Skyrim.esm') and ((GetLoadOrderFormID(Result) and $00FFFFFF)=expected),'CELL container changed');
end;
function EffectiveInfoBefore(naviMaster,navMaster:IInterface):IInterface;
var i:Integer;r,item:IInterface;
begin
 Result:=InfoFor(naviMaster,navMaster);
 for i:=0 to OverrideCount(naviMaster)-1 do begin r:=OverrideByIndex(naviMaster,i);
  if not SameText(GetFileName(GetFile(r)),PATCH_NAME) then begin item:=InfoFor(r,navMaster);
   if Assigned(item) then begin if not Assigned(Result) then Result:=item else if GetLoadOrder(GetFile(item))>GetLoadOrder(GetFile(Result)) then Result:=item;end;
  end;
 end;Need(Assigned(Result),'Effective prior NVMI absent');
end;
function IsTargetInfo(info:IInterface):Boolean;
var r:IInterface;i:Integer;
begin Result:=False;r:=LinksTo(Req(info,'Navmesh'));
 if not Assigned(r) then begin Need(IsKnownStockOrphan(info),'NAVI key unresolved outside exact source guard');Exit;end;
 r:=MasterOrSelf(r);
 if not SameText(GetFileName(GetFile(r)),'Skyrim.esm') then Exit;
 for i:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=TargetID(i) then Result:=True;
end;
procedure AssertOtherInfos(copyNavi,sourceNavi:IInterface);
var a,b,x,y:IInterface;i,j:Integer;
begin
 a:=Req(copyNavi,'Navmesh Infos');b:=Req(sourceNavi,'Navmesh Infos');i:=0;j:=0;
 while j<ElementCount(b) do begin y:=ElementByIndex(b,j);
  if not IsTargetInfo(y) then begin
   while i<ElementCount(a) do begin x:=ElementByIndex(a,i);if not IsTargetInfo(x) then Break;Inc(i);end;
   Need(i<ElementCount(a),'Unrelated NVMI removed');AssertTree(ElementByIndex(a,i),y,'unchanged other NVMI');Inc(i);
  end;Inc(j);
 end;
 while i<ElementCount(a) do begin Need(IsTargetInfo(ElementByIndex(a,i)),'New unrelated NVMI');Inc(i);end;
end;
procedure AssertInfoDoorState(copyInfo,baseInfo,sourceInfo,sourceNav:IInterface;c:Integer);
var a,b,entry,refRecord:IInterface;i,d:Integer;
begin
 AssertInfoOther(copyInfo,baseInfo);
 Need(ElementCount(Req(copyInfo,'Door Links'))=OldDoorCount(c)+NewDoorCount(c),'NVMI Door Link count changed');
 a:=Req(baseInfo,'Door Links');
 for i:=0 to ElementCount(a)-1 do begin entry:=ElementByIndex(a,i);refRecord:=LinksTo(Req(entry,'Door Ref'));b:=InfoDoor(copyInfo,refRecord);AssertTree(b,entry,'preserve base NVMI door');end;
 for d:=0 to NewDoorCount(c)-1 do begin entry:=SourceDoor(sourceNav,c,d);refRecord:=LinksTo(Req(entry,'Door Ref'));a:=InfoDoor(sourceInfo,refRecord);b:=InfoDoor(copyInfo,refRecord);AssertTree(b,a,'exact authored NVMI door');end;
end;
procedure AssertAllowedRecords(patchFile,worldMaster,naviMaster:IInterface);
var i,j,n,c,w,v:Integer;r:IInterface;sig:string;known:Boolean;
begin n:=0;c:=0;w:=0;v:=0;
 for i:=0 to RecordCount(patchFile)-1 do begin r:=RecordByIndex(patchFile,i);sig:=Signature(r);
  if sig<>'TES4' then begin
   Need(SameText(GetFileName(GetFile(MasterOrSelf(r))),'Skyrim.esm'),'Own/new records forbidden');
   if sig='NAVM' then begin known:=False;for j:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=TargetID(j) then known:=True;Need(known,'Unexpected NAVM');Inc(n);end
   else if sig='CELL' then begin known:=False;for j:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=ParentID(j) then known:=True;Need(known,'Unexpected CELL');Inc(c);end
   else if sig='WRLD' then begin Need(SameRecord(r,worldMaster),'Unexpected WRLD');Inc(w);end
   else if sig='NAVI' then begin Need(SameRecord(r,naviMaster),'Unexpected NAVI');Inc(v);end
   else Need(False,'Unexpected record type '+sig);
  end;
 end;Need((n=3) and (c=3) and (w=1) and (v=1),'Expected 3 NAVM + 3 CELL + WRLD + NAVI existing overrides');Need(GetIsESL(patchFile),'ESL flag missing');
end;
function Initialize:Integer;
var stock,glen,patchFile,naviMaster,glenNavi,naviSource,naviCopy,worldMaster,worldSource,worldCopy:IInterface;
    baseFile,masterNav,vanilla,sourceNav,baseNav,cellMaster,cellSource,cellCopy,navCopy:IInterface;
    baseNavi,baseInfo,sourceInfo,copyInfo,e,entry,refRecord,t,existing:IInterface;
    c,d,i,mapped,flags:Integer;expectedOwner:string;stream:TFileStream;
begin
  stockOrphanGuardChecked := False; stockOrphanTreeDumped := False;
 Result:=1;Need(Pos('e:\stock\skyrim collection\database\',LowerCase(DataPath))=1,'Database-owned Data required');
 stock:=ReqFile('Skyrim.esm');glen:=ReqFile('Glenmoril.esm');Need(not GetIsESL(glen),'Glen must remain a full master');
 naviMaster:=RecordByFormID(stock,$012FB4,False);naviSource:=WinnerExcludingPatch(naviMaster);
 glenNavi:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(naviMaster)),True);
 worldMaster:=RecordByFormID(stock,$00003C,False);worldSource:=WinnerExcludingPatch(worldMaster);
 Req(naviSource,'Navmesh Infos');
 // Entire preflight before creation; source file SHA checks are a separate prerequisite.
 for c:=0 to 2 do begin
  baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);vanilla:=masterNav;
  sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
  baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
  Need(SameText(GetFileName(GetFile(sourceNav)),'Glenmoril.esm'),'Glen override absent');
  Need(SameText(GetFileName(GetFile(baseNav)),BaseNameFor(c)),'Selected base override absent');
  expectedOwner:=BaseNameFor(c);if VERIFY_ONLY then expectedOwner:=PATCH_NAME;
  Need(SameText(GetFileName(GetFile(WinningOverride(masterNav))),expectedOwner),'Unexpected final NAVM winner/order');
  AssertAuthoredDelta(sourceNav,vanilla,c);AssertConnected(baseNav,c);ParentCell(baseNav,ParentID(c));
  baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);
  baseInfo:=InfoFor(baseNavi,masterNav);Need(Assigned(baseInfo),'Selected base NVMI absent');
  existing:=EffectiveInfoBefore(naviMaster,masterNav);AssertTree(existing,baseInfo,'Unreviewed final effective base NVMI');
  Need(ElementCount(Req(baseNav,'NVNM\Door Triangles'))=OldDoorCount(c),'Base Door Triangles changed');
  Need(ElementCount(Req(baseInfo,'Door Links'))=OldDoorCount(c),'Base NVMI Door Links changed');
  AssertNoTargetPath(ElementByPath(naviSource,'NVPP'),masterNav);AssertNoTargetPath(ElementByPath(naviSource,'NVSI'),masterNav);
  for d:=0 to NewDoorCount(c)-1 do begin mapped:=UniqueFace(sourceNav,baseNav,c,d);entry:=SourceDoor(sourceNav,c,d);AssertAuthoredDoorReferences(entry);end;
 end;
 if VERIFY_ONLY then begin Need(FileExists(DataPath+PATCH_NAME),'Installed candidate required for fresh reload');patchFile:=ReqFile(PATCH_NAME);end
 else begin
  Need(not Assigned(FileByName(PATCH_NAME)),'Patch already loaded');Need(not FileExists(DataPath+PATCH_NAME),'Patch already in VFS');Need(not FileExists(OUTPUT_FILE),'Candidate output exists');
  patchFile:=AddNewFileName(PATCH_NAME);Need(Assigned(patchFile),'Patch creation failed');
  AddMasterIfMissing(patchFile,'Skyrim.esm');AddMasterIfMissing(patchFile,'Glenmoril.esm');
  AddMasterIfMissing(patchFile,GetFileName(GetFile(naviSource)));AddMasterIfMissing(patchFile,GetFileName(GetFile(worldSource)));
  Need(AddRequiredElementMasters(naviSource,patchFile,False,True),'NAVI masters failed');Need(AddRequiredElementMasters(worldSource,patchFile,False,True),'WRLD masters failed');
  for c:=0 to 2 do begin
   baseFile:=ReqFile(BaseNameFor(c));AddMasterIfMissing(patchFile,BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
   baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
   cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);
   AddMasterIfMissing(patchFile,GetFileName(GetFile(cellSource)));
   Need(AddRequiredElementMasters(baseNav,patchFile,False,True),'NAVM masters failed');Need(AddRequiredElementMasters(cellSource,patchFile,False,True),'CELL masters failed');
   baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);
   Need(AddRequiredElementMasters(baseInfo,patchFile,False,True),'NVMI masters failed');
  end;
  SortMasters(patchFile);Need(MasterCount(patchFile)<=253,'Master budget exceeded');
  worldCopy:=CopyOverride(worldSource,patchFile);naviCopy:=CopyOverride(naviSource,patchFile);
  AssertUnchangedRecord(worldCopy,worldSource,'Initial exact final WRLD');AssertUnchangedRecord(naviCopy,naviSource,'Initial exact final NAVI');
  for c:=0 to 2 do begin
   baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
   sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
   baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
   cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);cellCopy:=CopyOverride(cellSource,patchFile);
   navCopy:=CopyOverride(baseNav,patchFile);AssertUnchangedRecord(navCopy,baseNav,'Initial exact selected base NAVM');
   baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);sourceInfo:=InfoFor(glenNavi,masterNav);
   existing:=InfoFor(naviCopy,masterNav);if Assigned(existing) then Remove(existing);
   copyInfo:=ElementAssign(Req(naviCopy,'Navmesh Infos'),HighInteger,baseInfo,False);Need(Assigned(copyInfo),'Base NVMI forwarding failed');RemapInfoReferences(copyInfo,baseInfo);
   for d:=0 to NewDoorCount(c)-1 do begin
    mapped:=UniqueFace(sourceNav,baseNav,c,d);entry:=SourceDoor(sourceNav,c,d);refRecord:=LinksTo(Req(entry,'Door Ref'));
    e:=ElementAssign(Req(navCopy,'NVNM\Door Triangles'),HighInteger,entry,False);Need(Assigned(e),'Door Triangle append failed');
    SetNativeValue(Req(e,'Triangle before door'),mapped);SetEditValue(Req(e,'Door Ref'),IntToHex(GetLoadOrderFormID(refRecord),8));
    t:=Tri(navCopy,mapped);flags:=GetNativeValue(Req(t,'Flags'));SetNativeValue(Req(t,'Flags'),flags or 1024);
    entry:=InfoDoor(sourceInfo,refRecord);e:=ElementAssign(Req(copyInfo,'Door Links'),HighInteger,entry,False);Need(Assigned(e),'NAVI Door Link append failed');SetEditValue(Req(e,'Door Ref'),IntToHex(GetLoadOrderFormID(refRecord),8));
   end;
  end;SetIsESL(patchFile,True);
 end;
 naviCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(naviMaster)),True);
 worldCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(worldMaster)),True);
 for c:=0 to 2 do begin
  baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
  sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
  baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
  navCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(masterNav)),True);
  cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);
  cellCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(cellMaster)),True);
  AddMessage('GLEN_NAV_CELL_SOURCE|'+IntToHex(ParentID(c),6)+'|'+GetFileName(GetFile(cellSource)));
  AssertUnchangedRecord(cellCopy,cellSource,'Preserve final parent CELL');AssertDoorState(navCopy,baseNav,sourceNav,c);
  baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);sourceInfo:=InfoFor(glenNavi,masterNav);copyInfo:=InfoFor(naviCopy,masterNav);
  AssertInfoDoorState(copyInfo,baseInfo,sourceInfo,sourceNav,c);
  Need(Check(navCopy)='','NAVM diagnostics: '+Check(navCopy));Need(Check(cellCopy)='','CELL diagnostics: '+Check(cellCopy));
 end;
 AssertUnchangedRecord(worldCopy,worldSource,'Preserve final WRLD');AssertNaviRest(naviCopy,naviSource);AssertOtherInfos(naviCopy,naviSource);AssertAllowedRecords(patchFile,worldMaster,naviMaster);
 Need(Check(naviCopy)='','NAVI diagnostics: '+Check(naviCopy));Need(Check(worldCopy)='','WRLD diagnostics: '+Check(worldCopy));
 AddMessage('GLEN_NAV_NAVI_SOURCE|'+GetFileName(GetFile(naviSource)));AddMessage('GLEN_NAV_WRLD_SOURCE|'+GetFileName(GetFile(worldSource)));
 if VERIFY_ONLY then Need(SameText(GetFileName(GetFile(WinningOverride(naviMaster))),PATCH_NAME),'Patch is not final NAVI winner')
 else begin ForceDirectories(ExtractFilePath(OUTPUT_FILE));stream:=TFileStream.Create(OUTPUT_FILE,fmCreate);try FileWriteToStream(patchFile,stream,0);finally stream.Free;end;AddMessage('GLEN_NAV_CANDIDATE_EXPORTED|'+OUTPUT_FILE);end;
 if VERIFY_ONLY then AddMessage('GLEN_NAV_RELOAD_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0') else AddMessage('GLEN_NAV_INMEMORY_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0');Result:=0;
end;
end.
