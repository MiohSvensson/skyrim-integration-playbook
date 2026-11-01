unit UserScript;
// Read-only fresh-process verifier for the bounded FC candidate.
// Requires exact sources, normal definitions, and an installed candidate.
const
  VERIFY_ONLY = True;
  PATCH_NAME = 'Database Forgotten City USSEP Navigation.esp';
  PROGRESS_FILE = '';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\forgotten_city_navigation\candidate_v12\Database Forgotten City USSEP Navigation.esp';

var stockOrphanGuardChecked, stockOrphanTreeDumped: Boolean;

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then
    raise Exception.Create('BOUNDED_NAVM_STOP: ' + messageText);
end;

procedure NativePhase(value: string);
var rows: TStringList;
begin
  Need(PROGRESS_FILE <> '', 'Per-task progress path was not prepared');
  rows := TStringList.Create;
  try
    rows.Add(value);
    rows.SaveToFile(PROGRESS_FILE);
  finally rows.Free; end;
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
    la := nil;
    lb := nil;
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
  la := nil;
  lb := nil;
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
  a := nil;
  b := nil;
  x := nil;
  y := nil;
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


function SharedID(i: Integer): Integer;
begin
  case i of
    0: Result := $10751B;
    1: Result := $107527;
    2: Result := $107528;
    3: Result := $107532;
    4: Result := $108AB4;
    5: Result := $108ABF;
    6: Result := $108BFA;
  else Need(False, 'Bad shared NAVM ordinal'); end;
end;

function IsSharedInfo(info: IInterface): Boolean;
var i: Integer; r: IInterface;
begin
  Result := False;
  r := LinksTo(Req(info, 'Navmesh'));
  if not Assigned(r) then begin
    Need(IsKnownStockOrphan(info), 'Unresolved NVMI key outside exact source guard');
    Exit;
  end;
  r := MasterOrSelf(r);
  if not SameText(GetFileName(GetFile(r)), 'Skyrim.esm') then Exit;
  for i := 0 to 6 do
    if (GetLoadOrderFormID(r) and $00FFFFFF) = SharedID(i) then Result := True;
end;

function EffectiveInfoBefore(naviMaster,navMaster: IInterface): IInterface;
var i: Integer; r,item: IInterface;
begin
  Result:=InfoFor(naviMaster,navMaster);
  for i:=0 to OverrideCount(naviMaster)-1 do begin
    r:=OverrideByIndex(naviMaster,i);
    if not SameText(GetFileName(GetFile(r)),PATCH_NAME) then begin
      item:=InfoFor(r,navMaster);
      if Assigned(item) then begin
        if not Assigned(Result) then Result:=item
        else if GetLoadOrder(GetFile(item))>GetLoadOrder(GetFile(Result)) then Result:=item;
      end;
    end;
  end;
  Need(Assigned(Result),'Effective prior NVMI absent');
end;

function EdgeName(side: Integer): string;
begin
  case side of
    0: Result := 'Edge 0-1';
    1: Result := 'Edge 1-2';
    2: Result := 'Edge 2-0';
  else Need(False, 'Bad triangle side'); end;
end;

function VertexName(side: Integer): string;
begin Result := 'Vertex ' + IntToStr(side); end;

function Triangle(r: IInterface; index: Integer): IInterface;
var a: IInterface;
begin
  a := Req(r, 'NVNM\Triangles');
  Need((index >= 0) and (index < ElementCount(a)), 'Triangle index outside record');
  Result := ElementByIndex(a, index);
  Need(ElementCount(Result) = 8, 'Normal 4.1.5f triangle fields required');
  Req(Result, 'Vertex 0');
  Req(Result, 'Flags');
end;

function EdgeFor(r, tri: IInterface; side: Integer): IInterface;
var index: Integer; a: IInterface;
begin
  index := GetNativeValue(Req(tri, EdgeName(side)));
  a := Req(r, 'NVNM\Edge Links');
  Need((index >= 0) and (index < ElementCount(a)), 'External link index outside Edge Links');
  Result := ElementByIndex(a, index);
end;

function LinkIs(edge, masterRecord: IInterface; triangleIndex: Integer): Boolean;
begin
  Result := SameRecord(LinksTo(Req(edge, 'Navmesh')), masterRecord) and
    (GetNativeValue(Req(edge, 'Triangle')) = triangleIndex);
end;

procedure AssertOtherNVNM(a,b: IInterface);
var ga,gb,x,y: IInterface; i: Integer; n: string;
begin
  ga := Req(a, 'NVNM'); gb := Req(b, 'NVNM');
  Need(ElementCount(ga) = ElementCount(gb), 'NVNM structure changed');
  for i := 0 to ElementCount(ga)-1 do begin
    x := ElementByIndex(ga,i); y := ElementByIndex(gb,i);
    n := BaseName(x); Need(n=BaseName(y), 'NVNM field order changed');
    if (n<>'Triangles') and (n<>'Edge Links') then AssertTree(x,y,'unchanged NVNM/'+n);
  end;
  ga := nil;
  gb := nil;
  x := nil;
  y := nil;
end;

procedure AssertAuthoredDelta(feature, vanilla, neighborMaster: IInterface);
var i,j,side,flagsA,flagsB: Integer; a,b: IInterface;
begin
  Need(ElementCount(Req(feature,'NVNM\Vertices'))=269, 'Feature vertex count changed');
  Need(ElementCount(Req(feature,'NVNM\Triangles'))=321, 'Feature triangle count changed');
  Need(ElementCount(Req(feature,'NVNM\Edge Links'))=28, 'Feature link count changed');
  Need(ElementCount(Req(vanilla,'NVNM\Edge Links'))=29, 'Vanilla link count changed');
  AssertOtherNVNM(feature,vanilla);
  for i := 0 to 320 do begin
    a := Triangle(feature,i); b := Triangle(vanilla,i);
    for j := 0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'author triangle vertices');
    AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'author cover flags');
    flagsA := GetNativeValue(Req(a,'Flags')); flagsB := GetNativeValue(Req(b,'Flags'));
    Need((flagsA and (not 7))=(flagsB and (not 7)), 'Author changed non-link triangle flags');
    for side := 0 to 2 do begin
      if (i=50) and (side=2) then begin
        Need(flagsB=2052, 'Vanilla triangle50 flags changed');
        Need(flagsA=2048, 'Feature triangle50 flags changed');
        Need(GetNativeValue(Req(a,EdgeName(side)))=-1, 'Author did not close expected edge');
        Need(LinkIs(EdgeFor(vanilla,b,side),neighborMaster,469), 'Authored removed target changed');
      end else begin
        Need((flagsA and (1 shl side))=(flagsB and (1 shl side)), 'Additional authored link-bit change');
        if (flagsB and (1 shl side))<>0 then
          AssertTree(EdgeFor(feature,a,side),EdgeFor(vanilla,b,side),'authored logical portal')
        else
          AssertTree(Req(a,EdgeName(side)),Req(b,EdgeName(side)),'authored internal adjacency');
      end;
    end;
  end;
end;

procedure AssertFaceSameAtIndex(a,b: IInterface; index: Integer);
var ta,tb,va,vb: IInterface; j,ia,ib: Integer;
begin
  ta := Triangle(a,index); tb := Triangle(b,index);
  for j := 0 to 2 do begin
    ia := GetNativeValue(Req(ta,VertexName(j)));
    ib := GetNativeValue(Req(tb,VertexName(j)));
    va := ElementByIndex(Req(a,'NVNM\Vertices'),ia);
    vb := ElementByIndex(Req(b,'NVNM\Vertices'),ib);
    AssertTree(va,vb,'exact unchanged ordered face vertex');
  end;
end;

function BackLink(r: IInterface; triIndex: Integer; targetMaster: IInterface; targetTriangle: Integer): Boolean;
var t: IInterface; side,flags: Integer;
begin
  Result := False; t := Triangle(r,triIndex); flags := GetNativeValue(Req(t,'Flags'));
  for side := 0 to 2 do
    if (flags and (1 shl side))<>0 then
      if LinkIs(EdgeFor(r,t,side),targetMaster,targetTriangle) then Result := True;
end;

procedure AssertReciprocal(primary,neighbor,vanPrimary,vanNeighbor,primaryMaster,neighborMaster: IInterface);
var i,side,flags,target,countA,countB: Integer; t,edge: IInterface;
begin
  countA := 0; countB := 0;
  for i := 0 to ElementCount(Req(primary,'NVNM\Triangles'))-1 do begin
    t := Triangle(primary,i); flags := GetNativeValue(Req(t,'Flags'));
    for side := 0 to 2 do if (flags and (1 shl side))<>0 then begin
      edge := EdgeFor(primary,t,side);
      if SameRecord(LinksTo(Req(edge,'Navmesh')),neighborMaster) then begin
        target := GetNativeValue(Req(edge,'Triangle'));
        Need(BackLink(neighbor,target,primaryMaster,i), 'Primary portal lacks authored reciprocal');
        AssertFaceSameAtIndex(neighbor,vanNeighbor,target);
        Inc(countA);
      end;
    end;
  end;
  for i := 0 to ElementCount(Req(neighbor,'NVNM\Triangles'))-1 do begin
    t := Triangle(neighbor,i); flags := GetNativeValue(Req(t,'Flags'));
    for side := 0 to 2 do if (flags and (1 shl side))<>0 then begin
      edge := EdgeFor(neighbor,t,side);
      if SameRecord(LinksTo(Req(edge,'Navmesh')),primaryMaster) then begin
        target := GetNativeValue(Req(edge,'Triangle'));
        Need(BackLink(primary,target,neighborMaster,i), 'Authored neighbor lacks primary reciprocal');
        AssertFaceSameAtIndex(primary,vanPrimary,target);
        Inc(countB);
      end;
    end;
  end;
  Need((countA=16) and (countB=16), 'Expected sixteen retained reciprocal ports');
end;

procedure AssertExternalLinkTuples(navCopy,usNav,neighborMaster: IInterface);
var i,j: Integer; linksA,linksB: IInterface;
begin
  linksA := Req(navCopy,'NVNM\Edge Links');
  linksB := Req(usNav,'NVNM\Edge Links');
  Need(LinkIs(ElementByIndex(linksB,6),neighborMaster,469), 'USSEP removed link no longer exact');
  for i := 0 to 28 do begin
    j := i;
    if i>=6 then Inc(j);
    AssertTree(ElementByIndex(linksA,i),ElementByIndex(linksB,j),'preserved external link');
  end;
  linksA := nil;
  linksB := nil;
end;

procedure AssertTriangleVertices(navCopy,usNav: IInterface);
var i,j: Integer; a,b: IInterface;
begin
  for i := 0 to 323 do begin
    a := Triangle(navCopy,i);
    b := Triangle(usNav,i);
    for j := 0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'preserved USSEP triangle vertices');
  end;
  a := nil;
  b := nil;
end;

procedure AssertTriangleCoverFlags(navCopy,usNav: IInterface);
var i: Integer; a,b: IInterface;
begin
  for i := 0 to 323 do begin
    a := Triangle(navCopy,i);
    b := Triangle(usNav,i);
    AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'preserved USSEP cover flags');
  end;
  a := nil;
  b := nil;
end;

procedure AssertTriangleTuples(navCopy,usNav: IInterface);
begin
  AssertTriangleVertices(navCopy,usNav);
  NativePhase('vertices_passed');
  AssertTriangleCoverFlags(navCopy,usNav);
  NativePhase('cover_flags_passed');
  NativePhase('triangle_flags_edges_deferred_to_separate_process');
end;

procedure AssertComposed(navCopy,usNav,neighborMaster: IInterface);
var i: Integer; a,b: IInterface;
begin
  AssertRecordHeader(navCopy,usNav,'Preserve USSEP NAVM header');
  NativePhase('header_passed');
  Need(ElementCount(navCopy)=ElementCount(usNav),'NAVM top-level member count changed');
  for i:=0 to ElementCount(usNav)-1 do begin
    b:=ElementByIndex(usNav,i);
    if BaseName(b)<>'Record Header' then begin
      a:=UniqueTop(navCopy,FieldToken(b));Need(Assigned(a),'NAVM field missing'+ComparisonContext(a,b));
      if FieldToken(b)<>'NVNM' then AssertTree(a,b,'Preserve non-NVNM fields');
    end;
  end;
  NativePhase('top_level_passed');
  a:=nil;
  b:=nil;
  Need(ElementCount(Req(navCopy,'NVNM\Vertices'))=271, 'USSEP vertices lost');
  Need(ElementCount(Req(navCopy,'NVNM\Triangles'))=324, 'USSEP triangles lost');
  Need(ElementCount(Req(usNav,'NVNM\Edge Links'))=30, 'USSEP Edge Links changed');
  Need(ElementCount(Req(navCopy,'NVNM\Edge Links'))=29, 'Expected one portal entry deletion');
  NativePhase('counts_passed');
  AssertOtherNVNM(navCopy,usNav);
  NativePhase('other_nvnm_passed');
  AssertExternalLinkTuples(navCopy,usNav,neighborMaster);
  NativePhase('external_links_passed');
  AssertTriangleTuples(navCopy,usNav);
  NativePhase('triangles_passed');
  a:=nil;
  b:=nil;
end;

procedure AssertOtherInfosFC(copyNavi,sourceNavi: IInterface);
var a,b,x,y: IInterface; i,j: Integer;
begin
  a:=Req(copyNavi,'Navmesh Infos'); b:=Req(sourceNavi,'Navmesh Infos'); i:=0; j:=0;
  while j<ElementCount(b) do begin
    y:=ElementByIndex(b,j);
    if not IsSharedInfo(y) then begin
      while i<ElementCount(a) do begin x:=ElementByIndex(a,i); if not IsSharedInfo(x) then Break; Inc(i); end;
      Need(i<ElementCount(a),'Unrelated NVMI removed');
      AssertTree(ElementByIndex(a,i),y,'unchanged unrelated NVMI'); Inc(i);
    end;
    Inc(j);
  end;
  while i<ElementCount(a) do begin Need(IsSharedInfo(ElementByIndex(a,i)),'New unrelated NVMI'); Inc(i); end;
end;

procedure AssertRecords(patchFile,primaryMaster,cellMaster,naviMaster,worldMaster: IInterface);
var i,n,c,v,w: Integer; r: IInterface; sig: string;
begin
  n:=0;c:=0;v:=0;w:=0;
  for i:=0 to RecordCount(patchFile)-1 do begin
    r:=RecordByIndex(patchFile,i);sig:=Signature(r);
    if sig<>'TES4' then begin
      if sig='NAVM' then begin Need(SameRecord(r,primaryMaster),'Unexpected NAVM');Inc(n);end
      else if sig='CELL' then begin Need(SameRecord(r,cellMaster),'Unexpected CELL');Inc(c);end
      else if sig='NAVI' then begin Need(SameRecord(r,naviMaster),'Unexpected NAVI');Inc(v);end
      else if sig='WRLD' then begin Need(SameRecord(r,worldMaster),'Unexpected WRLD');Inc(w);end
      else Need(False,'Unexpected patch record: '+sig);
      Need(SameText(GetFileName(GetFile(MasterOrSelf(r))),'Skyrim.esm'),'Own records forbidden');
    end;
  end;
  Need((n=1) and (c=1) and (v=1) and (w=1),'Expected NAVM/CELL/NAVI/WRLD four existing overrides');
  Need(GetIsESL(patchFile),'ESL flag missing');
end;

function Initialize: Integer;
var stock,feature,usFile,patchFile: IInterface;
    masterNav,vanNeighbor,neighborMaster,vanNav,featureNav,usNav,featureNeighbor: IInterface;
    cellMaster,cellSource,cellCopy,naviMaster,naviSource,naviCopy,featureNavi,usNavi,navCopy: IInterface;
    worldMaster,worldSource,worldCopy: IInterface;
    m,desired,existing,newInfo,t,sourceTri,edgeArray: IInterface;
    i,j,side,flags,index: Integer; expectedOwner: string; stream: TFileStream;
begin
  stockOrphanGuardChecked := False; stockOrphanTreeDumped := False;
  Result:=1;
  NativePhase('entered|files=' + IntToStr(FileCount));
  Need(Pos('e:\stock\skyrim collection\database\',LowerCase(DataPath))=1,'Database-owned Data required');
  stock:=ReqFile('Skyrim.esm');feature:=ReqFile('ForgottenCity.esp');usFile:=ReqFile('Unofficial Skyrim Special Edition Patch.esp');
  NativePhase('base_plugins_present');
  masterNav:=RecordByFormID(stock,$00108AB4,False);vanNav:=masterNav;
  neighborMaster:=RecordByFormID(stock,$00107528,False);vanNeighbor:=neighborMaster;
  featureNav:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(masterNav)),True);
  usNav:=RecordByFormID(usFile,LoadOrderFormIDtoFileFormID(usFile,GetLoadOrderFormID(masterNav)),True);
  featureNeighbor:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(neighborMaster)),True);
  Need(SameText(GetFileName(GetFile(featureNav)),'ForgottenCity.esp'),'Feature NAVM override absent');
  Need(SameText(GetFileName(GetFile(usNav)),'Unofficial Skyrim Special Edition Patch.esp'),'USSEP NAVM override absent');
  Need(SameText(GetFileName(GetFile(featureNeighbor)),'ForgottenCity.esp'),'Authored neighbor override absent');
  NativePhase('source_records_resolved');
  AssertAuthoredDelta(featureNav,vanNav,neighborMaster);
  NativePhase('authored_delta_passed');
  AssertFaceSameAtIndex(usNav,vanNav,50);
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 0'))=48,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 1'))=12,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 2'))=47,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Edge 2-0'))=6,'USSEP target portal index changed');
  Need(LinkIs(EdgeFor(usNav,Triangle(usNav,50),2),neighborMaster,469),'USSEP target portal changed');
  Need(ElementCount(Req(featureNeighbor,'NVNM\Triangles'))=485,'Authored neighbor triangle count changed');
  cellMaster:=RecordByFormID(stock,$00007644,False);cellSource:=WinnerExcludingPatch(cellMaster);
  worldMaster:=RecordByFormID(stock,$0000003C,False);worldSource:=WinnerExcludingPatch(worldMaster);
  naviMaster:=RecordByFormID(stock,$00012FB4,False);naviSource:=WinnerExcludingPatch(naviMaster);
  featureNavi:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(naviMaster)),True);
  usNavi:=RecordByFormID(usFile,LoadOrderFormIDtoFileFormID(usFile,GetLoadOrderFormID(naviMaster)),True);
  Req(naviSource,'Navmesh Infos');
  AddMessage('FC_NAV_CELL_SOURCE|'+GetFileName(GetFile(cellSource))+'|00007644');
  AddMessage('FC_NAV_NAVI_SOURCE|'+GetFileName(GetFile(naviSource))+'|00012FB4');
  AddMessage('FC_NAV_WRLD_SOURCE|'+GetFileName(GetFile(worldSource))+'|0000003C');
  for i:=0 to 6 do begin
    m:=RecordByFormID(stock,SharedID(i),False);Need(Assigned(m),'Shared master NAVM absent');
    expectedOwner:='ForgottenCity.esp';if VERIFY_ONLY and (SharedID(i)=$108AB4) then expectedOwner:=PATCH_NAME;
    Need(SameText(GetFileName(GetFile(WinningOverride(m))),expectedOwner),'Unreviewed final NAVM winner');
    AssertNoTargetPath(ElementByPath(naviSource,'NVPP'),m);
    AssertNoTargetPath(ElementByPath(naviSource,'NVSI'),m);
    existing:=EffectiveInfoBefore(naviMaster,m);desired:=InfoFor(featureNavi,m);
    Need(Assigned(desired),'Expected feature NVMI absent');
    AssertTree(existing,desired,'Unreviewed final effective NVMI change');
  end;
  NativePhase('existing_context_passed');
  if VERIFY_ONLY then begin
    Need(FileExists(DataPath+PATCH_NAME),'Installed candidate required for fresh reload');
    patchFile:=ReqFile(PATCH_NAME);
    navCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(masterNav)),True);
    cellCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(cellMaster)),True);
    naviCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(naviMaster)),True);
    worldCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(worldMaster)),True);
    Need(SameText(GetFileName(GetFile(WinningOverride(naviMaster))),PATCH_NAME),'Patch must be last NAVI winner');
    NativePhase('verify_patch_loaded');
  end else begin
    Need(not Assigned(FileByName(PATCH_NAME)),'Patch already loaded');
    Need(not FileExists(DataPath+PATCH_NAME),'Patch already exists in Data');
    Need(not FileExists(OUTPUT_FILE),'Candidate output exists');
    NativePhase('candidate_absence_passed');
    patchFile:=AddNewFileName(PATCH_NAME);Need(Assigned(patchFile),'Patch creation failed');
    NativePhase('candidate_created');
    AddMasterIfMissing(patchFile,'Skyrim.esm');AddMasterIfMissing(patchFile,'ForgottenCity.esp');
    AddMasterIfMissing(patchFile,'Unofficial Skyrim Special Edition Patch.esp');
    AddMasterIfMissing(patchFile,GetFileName(GetFile(cellSource)));
    AddMasterIfMissing(patchFile,GetFileName(GetFile(naviSource)));
    AddMasterIfMissing(patchFile,GetFileName(GetFile(worldSource)));
    Need(AddRequiredElementMasters(cellSource,patchFile,False,True),'CELL masters failed');
    Need(AddRequiredElementMasters(usNav,patchFile,False,True),'USSEP NAVM masters failed');
    Need(AddRequiredElementMasters(naviSource,patchFile,False,True),'Final NAVI masters failed');
    Need(AddRequiredElementMasters(worldSource,patchFile,False,True),'Final WRLD masters failed');
    for i:=0 to 6 do begin
      m:=RecordByFormID(stock,SharedID(i),False);
      if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
      Need(Assigned(desired),'Desired authored NVMI absent');
      Need(AddRequiredElementMasters(desired,patchFile,False,True),'NVMI masters failed');
    end;
    SortMasters(patchFile);Need(MasterCount(patchFile)<=253,'Master budget exceeded');
    NativePhase('masters_sorted');
    worldCopy:=CopyOverride(worldSource,patchFile);
    NativePhase('world_copied');
    cellCopy:=CopyOverride(cellSource,patchFile);
    NativePhase('cell_copied');
    navCopy:=CopyOverride(usNav,patchFile);
    Need(Assigned(cellCopy) and Assigned(navCopy),'Typed record copy failed');
    AssertTree(Req(navCopy,'NVNM'),Req(usNav,'NVNM'),'Initial exact USSEP copy');
    NativePhase('navm_initial_copy_passed');
    for i:=0 to 323 do begin
      sourceTri:=Triangle(usNav,i);t:=Triangle(navCopy,i);flags:=GetNativeValue(Req(sourceTri,'Flags'));
      for side:=0 to 2 do if (flags and (1 shl side))<>0 then begin
        index:=GetNativeValue(Req(sourceTri,EdgeName(side)));
        if index=6 then begin Need((i=50) and (side=2),'Deleted link has unexpected users');SetNativeValue(Req(t,EdgeName(side)),-1);end
        else if index>6 then SetNativeValue(Req(t,EdgeName(side)),index-1);
      end;
      if i=50 then SetNativeValue(Req(t,'Flags'),flags and (not 4));
    end;
    edgeArray:=ElementByIndex(Req(navCopy,'NVNM\Edge Links'),6);
    Remove(edgeArray);
    edgeArray:=nil;
    NativePhase('navm_geometry_composed');
    naviCopy:=CopyOverride(naviSource,patchFile);Need(Assigned(naviCopy),'NAVI copy failed');
    AssertUnchangedRecord(naviCopy,naviSource,'Initial full final NAVI copy');
    NativePhase('navi_initial_copy_passed');
    for i:=0 to 6 do begin
      m:=RecordByFormID(stock,SharedID(i),False);
      if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
      existing:=InfoFor(naviCopy,m);
      if Assigned(existing) then begin Remove(existing); existing:=nil; end;
      newInfo:=ElementAssign(Req(naviCopy,'Navmesh Infos'),HighInteger,desired,False);
      Need(Assigned(newInfo),'NVMI forwarding failed');RemapInfoReferences(newInfo,desired);
      AssertTree(newInfo,desired,'Exact selected NVMI forwarding');
    end;
    SetIsESL(patchFile,True);
    NativePhase('nvmi_forwarded');
  end;
  AssertComposed(navCopy,usNav,neighborMaster);
  NativePhase('composition_passed');
  AssertReciprocal(navCopy,featureNeighbor,vanNav,vanNeighbor,masterNav,neighborMaster);
  NativePhase('reciprocal_passed');
  AssertUnchangedRecord(cellCopy,cellSource,'Preserve final parent CELL');
  AssertUnchangedRecord(worldCopy,worldSource,'Preserve final Tamriel WRLD');
  NativePhase('parent_payloads_passed');
  for i:=0 to 6 do begin
    m:=RecordByFormID(stock,SharedID(i),False);
    if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
    existing:=InfoFor(naviCopy,m);Need(Assigned(existing),'Forwarded NVMI missing');
    AssertTree(existing,desired,'Exact selected NVMI post-check');
  end;
  AssertOtherInfosFC(naviCopy,naviSource);AssertNaviRest(naviCopy,naviSource);
  NativePhase('navi_preservation_passed');
  AssertRecords(patchFile,masterNav,cellMaster,naviMaster,worldMaster);
  NativePhase('record_whitelist_passed');
  Need(Check(navCopy)='','NAVM diagnostics: '+Check(navCopy));
  Need(Check(cellCopy)='','CELL diagnostics: '+Check(cellCopy));
  Need(Check(naviCopy)='','NAVI diagnostics: '+Check(naviCopy));
  Need(Check(worldCopy)='','WRLD diagnostics: '+Check(worldCopy));
  NativePhase('diagnostics_passed');
  if not VERIFY_ONLY then begin
    NativePhase('export_started');
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));stream:=TFileStream.Create(OUTPUT_FILE,fmCreate);
    try FileWriteToStream(patchFile,stream,0);finally stream.Free;end;
    NativePhase('export_completed');
    AddMessage('FC_NAV_CANDIDATE_EXPORTED|'+OUTPUT_FILE);
  end;
  if VERIFY_ONLY then AddMessage('FC_NAV_RELOAD_TYPED_PASS|PORTS=16/16|OWN=0|NVMI=7')
  else AddMessage('FC_NAV_INMEMORY_TYPED_PASS|PORTS=16/16|OWN=0|NVMI=7');
  if VERIFY_ONLY then NativePhase('FC_NAV_RELOAD_TYPED_PASS')
  else NativePhase('FC_NAV_INMEMORY_TYPED_PASS');
  Result:=0;
end;

end.
