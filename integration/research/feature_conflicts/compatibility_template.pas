unit UserScript;

// DRAFT, not compiled or executed by the authoring agent. Run only in a fresh
// final-profile xEdit 4.1.5f session after SHA preflight. No original file edit.
// Only a new in-memory plugin is changed; export happens after all assertions.
// CRC guards cover disk/VFS bytes, not pre-existing unsaved in-memory edits.
// If any exception occurs, close xEdit WITHOUT saving the incomplete patch.

const
  VERIFY_ONLY = False;
  PATCH_NAME = '@@PATCH@@';
  OUTPUT_FILE = '@@OUTPUT@@';

var
  patchFile, clonePack, sourceQuest, copiedQuest: IInterface;
  seedCount: Integer;
  lastNeedFailure: string;
  postChecks, postFailures: Integer;
  postVerificationPhase: Boolean;
  selfAuditSeen, selfAuditKinds: TStringList;
  selfAuditKindCounts: array[0..8191] of Integer;
  selfAuditRecords, selfAuditLeaves, selfAuditFailures: Integer;

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then begin
    lastNeedFailure := messageText;
    raise Exception.Create('FEATURE_COMPAT_STOP: ' + messageText);
  end;
end;

function ReqFile(n: string): IInterface;
begin
  Result := FileByName(n);
  Need(Assigned(Result), 'Required loaded file absent: ' + n);
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Typed path absent: ' + path);
end;

function SameRecord(a, b: IInterface): Boolean;
begin
  Result := False;
  if not Assigned(a) then Exit;
  if not Assigned(b) then Exit;
  Result := GetLoadOrderFormID(MasterOrSelf(a)) = GetLoadOrderFormID(MasterOrSelf(b));
end;

function RecordIdentity(r: IInterface): string;
var
  m: IInterface;
begin
  m := MasterOrSelf(r);
  Result := GetFileName(GetFile(m)) + '|' + IntToHex(FormID(m) and $FFFFFF, 6) +
    ' [' + GetFileName(GetFile(r)) + ']';
end;

function LeafTrace(e: IInterface): string;
begin
  if not Assigned(e) then begin Result := '<missing>'; Exit; end;
  if VarType(GetNativeValue(e)) = 8209 then
    Result := 'native=<byte-array>'
  else begin
    try Result := 'native=' + VarToStr(GetNativeValue(e));
    except Result := 'native=<non-scalar Variant; DefType=' + IntToStr(DefType(e)) + '>'; end;
  end;
  Result := BaseName(e) + ' {DefType=' + IntToStr(DefType(e)) + '/' + DefTypeAsText(e) +
    '; VarType=' + IntToStr(VarType(GetNativeValue(e))) + '/' + VarTypeAsText(GetNativeValue(e)) +
    '; ' + Result + '; edit=' + Copy(GetEditValue(e), 1, 160) + '}';
end;

procedure NeedLeaf(ok: Boolean; labelText: string; a, b: IInterface);
begin
  // Evaluate diagnostic formatting only on failure; JvInterpreter eagerly
  // evaluates ordinary procedure arguments, including unused error messages.
  if not ok then Need(False, labelText + '; left=' + LeafTrace(a) + '; right=' + LeafTrace(b));
end;

function OriginRecord(n: string; id: Integer): IInterface;
var
  f: IInterface;
begin
  f := ReqFile(n);
  // RecordByFormID(..., False) takes FILE-local IDs. An origin's own records
  // use the self index MasterCount(f), including Sofia/Hoth/Erin own forms.
  Result := RecordByFormID(f, (MasterCount(f) shl 24) or id, False);
  Need(Assigned(Result), 'Origin record missing: ' + n + '|' + IntToHex(id, 6));
  Need(SameText(GetFileName(GetFile(MasterOrSelf(Result))), n), 'Origin ownership mismatch: ' + n);
  Need((FormID(MasterOrSelf(Result)) and $FFFFFF) = id, 'Origin object ID mismatch');
end;

function InFile(n: string; masterRecord: IInterface): IInterface;
var
  f: IInterface;
begin
  f := ReqFile(n);
  Result := RecordByFormID(f, LoadOrderFormIDtoFileFormID(f, GetLoadOrderFormID(masterRecord)), True);
  Need(Assigned(Result), 'Override absent in ' + n);
  Need(SameText(GetFileName(GetFile(Result)), n), 'Lookup fell back to a master instead of ' + n);
end;

function ExcludeBase(n: string): Boolean;
begin
  Result :=
@@EXCLUDED@@;
end;

function BaseWinner(r: IInterface): IInterface;
var
  i: Integer;
  a: IInterface;
begin
  Result := MasterOrSelf(r);
  for i := 0 to OverrideCount(MasterOrSelf(r)) - 1 do begin
    a := OverrideByIndex(MasterOrSelf(r), i);
    if not ExcludeBase(GetFileName(GetFile(a))) then
      if GetLoadOrder(GetFile(a)) > GetLoadOrder(GetFile(Result)) then Result := a;
  end;
end;

procedure GuardFile(n, crc: string);
begin
  ReqFile(n);
  Need(FileExists(DataPath + n), 'VFS file absent: ' + n);
  Need(SameText(IntToHex(wbCRC32File(DataPath + n), 8), crc), 'VFS CRC changed: ' + n);
end;

procedure AssertNativeByteVector(a, b: IInterface; labelText: string);
var
  streamA, streamB: TBytesStream;
  readerA, readerB: TBinaryReader;
  i, n, byteA, byteB: Integer;
begin
  // Exact 4.1.5f adapters convert the native Variant to TBytes (one-dimensional
  // zero-based byte vector), then expose its complete bytes through a stream.
  // Unsupported Variant shapes fail the TBytes conversion instead of passing.
  NeedLeaf((VarType(GetNativeValue(a)) = 8209) and (VarType(GetNativeValue(b)) = 8209),
    labelText + ': expected both native Array Byte (varArray or varByte = 8209)', a, b);
  streamA := TBytesStream.Create(GetNativeValue(a));
  try
    streamB := TBytesStream.Create(GetNativeValue(b));
    try
      Need(streamA.Size = streamB.Size, labelText + ': native byte count changed; left=' +
        IntToStr(streamA.Size) + '; right=' + IntToStr(streamB.Size));
      Need((streamA.Size >= 0) and (streamA.Size <= $7FFFFFFF), labelText + ': unsupported native vector size');
      n := streamA.Size;
      streamA.Position := 0; streamB.Position := 0;
      readerA := TBinaryReader.Create(streamA);
      try
        readerB := TBinaryReader.Create(streamB);
        try
          for i := 0 to n - 1 do begin
            byteA := readerA.ReadByte; byteB := readerB.ReadByte;
            Need(byteA = byteB, labelText + ': exact native byte differs at offset ' + IntToStr(i) +
              '; left=' + IntToHex(byteA, 2) + '; right=' + IntToHex(byteB, 2));
          end;
          Need((streamA.Position = n) and (streamB.Position = n), labelText + ': incomplete native byte-vector traversal');
        finally readerB.Free; end;
      finally readerA.Free; end;
    finally streamB.Free; end;
  finally streamA.Free; end;
end;

function CTDAVariableParameter(e: IInterface): Integer;
var c, fn: IInterface; n: string; f: Integer;
begin
  Result := 0;
  if DefType(e) <> dtUnion then Exit;
  n := BaseName(e);
  if (n <> 'Parameter #1') and (n <> 'Parameter #2') then Exit;
  c := GetContainer(e);
  if not Assigned(c) then Exit;
  if Signature(c) <> 'CTDA' then Exit;
  fn := ElementByPath(c, 'Function');
  if not Assigned(fn) then Exit;
  f := GetNativeValue(fn);
  // Exact xedit-4.1.5f table: only these parameters are ptVariableName.
  if n = 'Parameter #1' then begin
    if (f = 447) or (f = 675) then Result := 1;
  end else if (f = 53) or (f = 79) or (f = 629) or (f = 630) then Result := 2;
end;

procedure AssertCTDAVariable(a, b: IInterface; number: Integer; labelText: string);
var cisA, cisB: IInterface; p: string;
begin
  Need(CTDAVariableParameter(a) = number, labelText + ': destination CTDA parameter type changed');
  Need(CTDAVariableParameter(b) = number, labelText + ': source CTDA parameter type changed');
  p := '..\CIS' + IntToStr(number);
  cisA := ElementByPath(GetContainer(a), p);
  cisB := ElementByPath(GetContainer(b), p);
  Need(Assigned(cisA) and Assigned(cisB), labelText + ': exact CIS variable string is absent');
  Need((Signature(cisA) = 'CIS' + IntToStr(number)) and (Signature(cisB) = 'CIS' + IntToStr(number)),
    labelText + ': variable string resolved to wrong subrecord');
  NeedLeaf(GetEditValue(cisA) = GetEditValue(cisB), labelText + ': full resolved CIS variable string changed', cisA, cisB);
  NeedLeaf((GetEditValue(a) = GetEditValue(cisA)) and (GetEditValue(b) = GetEditValue(cisB)),
    labelText + ': CTDA callback disagrees with its exact CIS string', a, b);
  // The U32 storage is unused by this callback. Its setter returns zero and
  // stores the full semantic value in CIS1/2. Offline candidate verification
  // independently requires raw U32 zero and the exact paired CIS bytes.
end;

function IsDefinedEmptyContainer(e: IInterface): Boolean;
var d, t: Integer;
begin
  d := DefType(e); t := ElementType(e);
  Result := ((d = dtArray) or (d = dtStruct) or (d = dtStructChapter) or
    (d = dtSubRecordArray) or (d = dtSubRecordStruct)) and
    ((t = etArray) or (t = etStruct) or (t = etStructChapter) or
     (t = etSubRecord) or (t = etSubRecordArray) or (t = etSubRecordStruct));
end;

procedure AssertTree(a, b: IInterface; labelText: string);
var
  i, typeA, typeB: Integer;
  la, lb: IInterface;
  equalNative: Boolean;
begin
  Need(Assigned(a) and Assigned(b), labelText + ': missing element');
  Need(BaseName(a) = BaseName(b), labelText + ': field definition changed');
  NeedLeaf(DefType(a) = DefType(b), labelText + ': field definition type changed', a, b);
  NeedLeaf(ElementType(a) = ElementType(b), labelText + ': element type changed', a, b);
  Need(Signature(a) = Signature(b), labelText + ': element signature changed');
  Need(ElementCount(a) = ElementCount(b), labelText + ': child count changed');
  if ElementCount(a) > 0 then begin
    for i := 0 to ElementCount(a) - 1 do
      AssertTree(ElementByIndex(a, i), ElementByIndex(b, i), labelText + '/' +
        BaseName(ElementByIndex(b, i)) + '[' + IntToStr(i) + ']');
    Exit;
  end;
  if IsDefinedEmptyContainer(a) or IsDefinedEmptyContainer(b) then begin
    Need(IsDefinedEmptyContainer(a) and IsDefinedEmptyContainer(b), labelText + ': empty container definition changed');
    // A defined zero-child array/struct/chapter has no scalar native value.
    // Definition name/type, element type, signature and zero count match above.
    Exit;
  end;
  la := LinksTo(a);
  lb := LinksTo(b);
  if Assigned(la) or Assigned(lb) then begin
      Need(Assigned(la) and Assigned(lb), labelText + ': one counterpart FormID unresolved');
      Need((ElementType(la) = etMainRecord) and (ElementType(lb) = etMainRecord), labelText + ': counterpart not a record');
      Need(SameRecord(la, lb), labelText + ': resolved FormID changed; left=' + RecordIdentity(la) + '; right=' + RecordIdentity(lb));
      Exit;
  end;
  if (CTDAVariableParameter(a) <> 0) or (CTDAVariableParameter(b) <> 0) then begin
    AssertCTDAVariable(a, b, CTDAVariableParameter(b), labelText);
    Exit;
  end;
  typeA := VarType(GetNativeValue(a)); typeB := VarType(GetNativeValue(b));
  if (typeA = 8209) or (typeB = 8209) then begin
    AssertNativeByteVector(a, b, labelText);
    Exit;
  end;
  NeedLeaf(((typeA and $2000) = 0) and ((typeB and $2000) = 0),
    labelText + ': unsupported non-byte native Variant array', a, b);
  if (DefType(a) = dtByteArray) or (DefType(b) = dtByteArray) then begin
    NeedLeaf(False, labelText + ': byte-array definition returned unexpected native Variant type', a, b);
    Exit;
  end;
  if (DefType(a) = dtLString) or (DefType(a) = dtString) or (DefType(a) = dtLenString) then begin
    NeedLeaf(GetEditValue(a) = GetEditValue(b), labelText + ': resolved text changed', a, b);
    Exit;
  end;
  NeedLeaf(typeA = typeB, labelText + ': scalar native Variant type changed', a, b);
  if typeA = 0 then begin
    if DefType(a) = dtEmpty then begin
      NeedLeaf((GetEditValue(a) = '') and (GetEditValue(b) = ''), labelText + ': nonempty Empty definition', a, b);
      Exit;
    end;
    NeedLeaf((DefType(a) = dtFloat) or (DefType(a) = dtUnion), labelText + ': unsupported unassigned native value', a, b);
    // Exact FloatDef.ToNativeValue clears the Variant only for NaN. A union
    // must resolve to that float member and expose its exact NaN edit token.
    NeedLeaf((GetEditValue(a) = 'NaN') and (GetEditValue(b) = 'NaN'), labelText + ': unassigned native value is not a typed NaN', a, b);
    Exit;
  end;
  try equalNative := GetNativeValue(a) = GetNativeValue(b);
  except
    Need(False, labelText + ': native comparison is not scalar; left=' + LeafTrace(a) + '; right=' + LeafTrace(b));
    Exit;
  end;
  NeedLeaf(equalNative, labelText + ': exact native value changed', a, b);
end;

function AuditClean(s: string): string;
begin
  Result := StringReplace(s, #9, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #13, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #10, ' ', [rfReplaceAll]);
end;

procedure AuditComparatorLeaf(e: IInterface; rec: string);
var kind, p, trace: string; idx: Integer;
begin
  selfAuditLeaves := selfAuditLeaves + 1;
  p := '<path unavailable>'; trace := '<trace unavailable>';
  try
    p := AuditClean(Path(e));
    trace := AuditClean(LeafTrace(e));
    kind := IntToStr(DefType(e)) + '/' + DefTypeAsText(e) + #9 +
      IntToStr(ElementType(e)) + '/' + ElementTypeAsText(e) + #9 +
      IntToStr(VarType(GetNativeValue(e))) + '/' + VarTypeAsText(GetNativeValue(e));
    if IsDefinedEmptyContainer(e) then kind := kind + #9 + 'defined-empty-container';
    idx := selfAuditKinds.IndexOf(kind);
    if idx < 0 then begin
      Need(selfAuditKinds.Count < 8192, 'Self-audit kind capacity exceeded');
      idx := selfAuditKinds.Add(kind); selfAuditKindCounts[idx] := 0;
      AddMessage('COMPARATOR_SELF_KIND_SAMPLE' + #9 + kind + #9 + rec + #9 + p + #9 + trace);
    end;
    selfAuditKindCounts[idx] := selfAuditKindCounts[idx] + 1;
    AssertTree(e, e, 'Comparator self-audit ' + rec + '/' + p);
  except
    selfAuditFailures := selfAuditFailures + 1;
    AddMessage('COMPARATOR_SELF_UNSUPPORTED' + #9 + rec + #9 + p + #9 + trace);
  end;
end;

procedure AuditComparatorTree(e: IInterface; rec: string);
var i, n: Integer; child: IInterface;
begin
  try n := ElementCount(e);
  except
    selfAuditFailures := selfAuditFailures + 1;
    AddMessage('COMPARATOR_SELF_TRAVERSAL_EXCEPTION' + #9 + rec + #9 + 'ElementCount');
    Exit;
  end;
  if n = 0 then begin AuditComparatorLeaf(e, rec); Exit; end;
  for i := 0 to n - 1 do begin
    child := nil;
    try child := ElementByIndex(e, i);
    except
      selfAuditFailures := selfAuditFailures + 1;
      AddMessage('COMPARATOR_SELF_TRAVERSAL_EXCEPTION' + #9 + rec + #9 + 'ElementByIndex ' + IntToStr(i));
    end;
    if Assigned(child) then AuditComparatorTree(child, rec)
    else begin
      selfAuditFailures := selfAuditFailures + 1;
      AddMessage('COMPARATOR_SELF_TRAVERSAL_EXCEPTION' + #9 + rec + #9 + 'nil child ' + IntToStr(i));
    end;
  end;
end;

procedure AuditLoadedRecord(r: IInterface; context: string);
var key: string;
begin
  Need(Assigned(r), 'Comparator source record absent: ' + context);
  key := RecordIdentity(r) + '/' + Signature(r);
  if selfAuditSeen.IndexOf(key) >= 0 then Exit;
  selfAuditSeen.Add(key); selfAuditRecords := selfAuditRecords + 1;
  AddMessage('COMPARATOR_SELF_RECORD' + #9 + AuditClean(key) + #9 + AuditClean(context));
  AuditComparatorTree(r, AuditClean(key));
end;

procedure AuditExactSource(n, origin: string; id: Integer);
begin
  try AuditLoadedRecord(InFile(n, OriginRecord(origin, id)), n + ' exact source');
  except
    selfAuditFailures := selfAuditFailures + 1;
    AddMessage('COMPARATOR_SELF_RECORD_EXCEPTION' + #9 + n + #9 + origin + '|' + IntToHex(id, 6));
  end;
end;

procedure AuditVisibleSourceParent(n, origin: string; id: Integer);
var f, r, master: IInterface;
begin
  try
    f := ReqFile(n); master := OriginRecord(origin, id);
    r := RecordByFormID(f, LoadOrderFormIDtoFileFormID(f, GetLoadOrderFormID(master)), True);
    AuditLoadedRecord(r, n + ' visible source parent');
  except
    selfAuditFailures := selfAuditFailures + 1;
    AddMessage('COMPARATOR_SELF_PARENT_EXCEPTION' + #9 + n + #9 + origin + '|' + IntToHex(id, 6));
  end;
end;

procedure RunComparatorSelfAudit;
var i: Integer;
begin
  selfAuditRecords := 0; selfAuditLeaves := 0; selfAuditFailures := 0;
  selfAuditSeen := TStringList.Create; selfAuditKinds := TStringList.Create;
  try
    AddMessage('COMPARATOR_SELF_AUDIT_BEGIN');
@@COMPARATOR_SCOPE@@
    for i := 0 to selfAuditKinds.Count - 1 do
      AddMessage('COMPARATOR_SELF_KIND_COUNT' + #9 + selfAuditKinds[i] + #9 + IntToStr(selfAuditKindCounts[i]));
    AddMessage('COMPARATOR_SELF_AUDIT_COMPLETED' + #9 + IntToStr(selfAuditRecords) + #9 +
      IntToStr(selfAuditLeaves) + #9 + IntToStr(selfAuditFailures));
  finally selfAuditKinds.Free; selfAuditSeen.Free; end;
  Need(selfAuditFailures = 0, 'Comparator self-audit rejected ' + IntToStr(selfAuditFailures) +
    ' fields/records across full source scope; no patch was created');
end;

procedure RemapRefs(dst, src: IInterface; labelText: string);
var
  i: Integer;
  linked: IInterface;
begin
  Need(ElementCount(dst) = ElementCount(src), labelText + ': copy shape changed');
  if ElementCount(src) > 0 then begin
    for i := 0 to ElementCount(src) - 1 do
      RemapRefs(ElementByIndex(dst, i), ElementByIndex(src, i), labelText + '/' + IntToStr(i));
    Exit;
  end;
  linked := LinksTo(src);
  if Assigned(linked) then
    if ElementType(linked) = etMainRecord then
      // Input is a RESOLVED load-order FormID. xEdit writes the destination
      // plugin's namespace. Never copy source-file master-index bytes.
      SetEditValue(dst, IntToHex(GetLoadOrderFormID(linked), 8));
end;

function Token(e: IInterface): string;
begin
  Result := Signature(e);
  if Result = '' then Result := BaseName(e);
end;

function IsRecordHeader(e: IInterface): Boolean;
begin
  Result := BaseName(e) = 'Record Header';
end;

function Top(r: IInterface; tokenText: string): IInterface;
var
  i: Integer;
  e: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(r) - 1 do begin
    e := ElementByIndex(r, i);
    if not IsRecordHeader(e) then if Token(e) = tokenText then begin
      Need(not Assigned(Result), 'Duplicate top-level token: ' + tokenText);
      Result := e;
    end;
  end;
end;

function OutputRecord(origin: string; id: Integer): IInterface;
begin
  Result := InFile(PATCH_NAME, OriginRecord(origin, id));
end;

procedure RequireNormalDefinitions;
var nav, triangles, triangle, vertices, vertex: IInterface;
begin
  // This exact stock NAVM was independently probed under both settings.
  // MHDT remains strict when present, but it is optional and not a mode probe.
  nav := OriginRecord('Skyrim.esm', $108AB4);
  Need(Signature(nav) = 'NAVM', 'Pinned stock schema-probe identity changed');
  triangles := Req(nav, 'NVNM\Triangles');
  Need(ElementCount(triangles) = 321, 'Pinned stock NAVM triangle count changed');
  triangle := ElementByIndex(triangles, 50);
  Need((DefType(triangle) = dtStruct) and (ElementCount(triangle) = 8),
    'Normal xEdit definitions required: use private SimpleRecords=0; NAVM triangle is not typed');
  Req(triangle, 'Vertex 0'); Req(triangle, 'Vertex 1'); Req(triangle, 'Vertex 2');
  Req(triangle, 'Edge 0-1'); Req(triangle, 'Edge 1-2'); Req(triangle, 'Edge 2-0');
  Req(triangle, 'Flags'); Req(triangle, 'Cover Flags');
  vertices := Req(nav, 'NVNM\Vertices');
  Need(ElementCount(vertices) = 269, 'Pinned stock NAVM vertex count changed');
  vertex := ElementByIndex(vertices, 0);
  Need((DefType(vertex) = dtStruct) and (ElementCount(vertex) = 3), 'Normal XYZ vertex schema absent');
  Need((DefType(Req(vertex, 'X')) = dtFloat) and (DefType(Req(vertex, 'Y')) = dtFloat) and
    (DefType(Req(vertex, 'Z')) = dtFloat), 'Pinned normal XYZ vertex definitions changed');
  AddMessage('FEATURE_COMPARATOR_NORMAL_SCHEMA' + #9 + 'Skyrim.esm|108AB4' + #9 +
    IntToStr(ElementCount(triangles)) + #9 + IntToStr(ElementCount(triangle)) + #9 + IntToStr(ElementCount(vertex)));
end;

function IgnoredGenerated(r, field: IInterface): Boolean;
var
  t: string;
begin
  t := Token(field);
  Result := (Signature(r) = 'DIAL') and (t = 'TIFC');
  if (Signature(r) = 'DIAL') and ((t = 'INOM') or (t = 'INOA')) then begin
    Need(DefType(field) = dtArray, 'Unexpected exact-tag editor INFO-order definition: ' + t);
    // These two lists are dynamically reconstructed from this file's visible
    // masters/overrides and may be absent, empty or repopulated after copies.
    // Exact 4.1.5f flags them InternalEditOnly/DontAssign/DontSave. They never
    // enter serialized gameplay payload; binary verifiers reject stored tags.
    Result := True;
  end;
  // DIAL response count and interior XCLW are cpIgnore derived values.
  if (Signature(r) = 'CELL') and (t = 'XCLW') then
    if (GetNativeValue(Req(r, 'DATA')) and 1) <> 0 then Result := True;
end;

function AllowedOmission(r, field: IInterface): Boolean;
var t: string;
begin
  t := Token(field);
  Result := (Signature(r) = 'WRLD') and ((t = 'RNAM') or (t = 'Large References') or (t = 'OFST'));
  // Exact 4.1.5f: WRLD RNAM/OFST are no-copy-as-override; MHDT is strict.
  // Only omission is allowed for these serialized no-copy-as-override tables.
  // Present tables remain exact. DIAL INOM/INOA are separate unsaved caches.
end;

procedure AssertPreservedField(dst, src, field: IInterface; labelText: string);
var other: IInterface;
begin
  if IgnoredGenerated(src, field) then Exit;
  other := Top(dst, Token(field));
  if not Assigned(other) then
    if AllowedOmission(src, field) then Exit;
  AssertTree(other, field, labelText);
end;

procedure AssertHeader(dst, src: IInterface; labelText: string; newOwn: Boolean; expectedFlags: Integer);
var
  a, b, x, y: IInterface;
  i: Integer;
  n: string;
begin
  labelText := labelText + ' src=' + RecordIdentity(src) + ' dst=' + RecordIdentity(dst);
  a := Req(dst, 'Record Header');
  b := Req(src, 'Record Header');
  Need(ElementCount(a) = 7, labelText + ': unexpected destination 4.1.5f header shape');
  Need(ElementCount(b) = 7, labelText + ': unexpected source 4.1.5f header shape');
  if newOwn then begin
    Need(Signature(dst) = 'PACK', labelText + ': only the explicit PACK clone may acquire new identity');
    Need(SameText(GetFileName(GetFile(MasterOrSelf(dst))), PATCH_NAME), labelText + ': new PACK not owned by patch');
    Need(not SameRecord(dst, src), labelText + ': PACK clone retained original identity');
    Need((FormID(dst) and $FFFFFF) >= $800, labelText + ': new own ID below safe range');
    Need((FormID(dst) and $FFFFFF) <= $FFF, labelText + ': new own ID above safe range');
  end else Need(SameRecord(dst, src), labelText + ': canonical FormID mapping differs');
  for i := 0 to 6 do begin
    x := ElementByIndex(a, i); y := ElementByIndex(b, i);
    n := BaseName(y);
    Need(BaseName(x) = n, labelText + ': header member definition changed');
    if n = 'Data Size' then begin
      // Serialized payload size changes when schemaNoCopy tables are omitted.
    end else if n = 'FormID' then begin
      // File-local master indices differ; canonical mapping checked above.
    end else if n = 'Version Control Info 1' then
      Need(GetFormVCS1(dst) = GetFormVCS1(src), labelText + ': exact VCS1 differs; dst=' + IntToHex(GetFormVCS1(dst), 8) + '; src=' + IntToHex(GetFormVCS1(src), 8))
    else if n = 'Version Control Info 2' then
      Need(GetFormVCS2(dst) = GetFormVCS2(src), labelText + ': exact VCS2 differs; dst=' + IntToHex(GetFormVCS2(dst), 4) + '; src=' + IntToHex(GetFormVCS2(src), 4))
    else if n = 'Record Flags' then
      Need(GetNativeValue(x) = expectedFlags, labelText + ': flags differ; left=' + LeafTrace(x) + '; expected=' + IntToHex(expectedFlags, 8))
    else AssertTree(x, y, labelText + '/' + n);
  end;
  Need(GetFormVersion(dst) = GetFormVersion(src), labelText + ': FormVersion API differs');
  Need(GetFormVCS1(dst) = GetFormVCS1(src), labelText + ': VCS1 API differs');
  Need(GetFormVCS2(dst) = GetFormVCS2(src), labelText + ': VCS2 API differs');
end;

procedure AssertPayloadInner(dst, src: IInterface; labelText: string; newOwn: Boolean);
var
  i: Integer;
  e: IInterface;
begin
  Need(Signature(dst) = Signature(src), labelText + ': signature changed');
  AssertHeader(dst, src, labelText, newOwn, GetNativeValue(Req(src, 'Record Header\Record Flags')));
  labelText := labelText + ' src=' + RecordIdentity(src);
  for i := 0 to ElementCount(src) - 1 do begin
    e := ElementByIndex(src, i);
    if not IsRecordHeader(e) then
      AssertPreservedField(dst, src, e, labelText + '/' + Token(e));
  end;
  for i := 0 to ElementCount(dst) - 1 do begin
    e := ElementByIndex(dst, i);
    if not IsRecordHeader(e) and not IgnoredGenerated(dst, e) then
      Need(Assigned(Top(src, Token(e))), labelText + ': unexpected field ' + Token(e));
  end;
end;

procedure AssertPayload(dst, src: IInterface; labelText: string);
begin
  AssertPayloadInner(dst, src, labelText, False);
end;

procedure RestoreSourceHeaderMetadata(dst, src: IInterface);
begin
  Need(SameText(GetFileName(GetFile(dst)), PATCH_NAME), 'Metadata restore refused outside the new patch');
  // 4.1.5f typed AddCopy resets VCS2. Preserve the exact source metadata,
  // then retain strict verification; never exempt differing VCS bytes.
  SetFormVersion(dst, GetFormVersion(src));
  SetFormVCS1(dst, GetFormVCS1(src));
  SetFormVCS2(dst, GetFormVCS2(src));
end;

procedure RestoreSeedMetadata(origin: string; id: Integer; owner: string);
begin
  RestoreSourceHeaderMetadata(OutputRecord(origin, id), InFile(owner, OriginRecord(origin, id)));
end;

procedure Seed(origin: string; id: Integer; sig, owner: string);
var
  r, base, copied: IInterface;
begin
  r := OriginRecord(origin, id);
  base := BaseWinner(r);
  Need(SameText(GetFileName(GetFile(base)), owner), 'Base winner changed at ' + origin + '|' + IntToHex(id, 6) + ': ' + GetFileName(GetFile(base)));
  Need(Signature(base) = sig, 'Base signature changed: ' + origin + '|' + IntToHex(id, 6));
  if VERIFY_ONLY then begin
    OutputRecord(origin, id);
  end else begin
    Need(AddRequiredElementMasters(base, patchFile, False, True), 'Base required masters failed');
    // This API calls File.AddCopy on the MAIN RECORD. Deep=True assigns its
    // payload; unlike Element.CopyInto it does not select the ChildGroup.
    // All WRLD/CELL/DIAL ancestors are explicitly seeded before descendants.
    copied := wbCopyElementToFile(base, patchFile, False, True);
    Need(Assigned(copied), 'Base copy failed');
    RestoreSourceHeaderMetadata(copied, base);
    AssertPayload(copied, base, 'Initial exact typed base copy');
  end;
  Inc(seedCount);
end;

procedure ForwardField(donor, origin: string; id: Integer; fieldText: string);
var
  src, dst, s, d, c: IInterface;
begin
  src := InFile(donor, OriginRecord(origin, id));
  dst := OutputRecord(origin, id);
  s := Top(src, fieldText);
  Need(Assigned(s), 'Donor field absent: ' + donor + '/' + fieldText);
  Need(AddRequiredElementMasters(s, patchFile, False, True), 'Field required masters failed: ' + fieldText);
  d := Top(dst, fieldText);
  if Assigned(d) then Remove(d);
  c := wbCopyElementToRecord(s, dst, False, True);
  Need(Assigned(c), 'Typed field copy failed: ' + fieldText);
  d := Top(dst, fieldText);
  Need(Assigned(d), 'Copied field absent: ' + fieldText);
  RemapRefs(d, s, 'Typed copied field ' + fieldText);
  AssertTree(d, s, 'Copied field ' + fieldText);
end;

procedure AssertForwarded(donor, origin: string; id: Integer; fieldText: string);
begin
  AssertTree(Top(OutputRecord(origin, id), fieldText),
    Top(InFile(donor, OriginRecord(origin, id)), fieldText), donor + '/' + IntToHex(id, 6) + '/' + fieldText);
end;

procedure SetPersistentBit(origin: string; id: Integer);
begin
  SetIsPersistent(OutputRecord(origin, id), True);
end;

procedure ReferenceContext(r: IInterface; var cell, world: IInterface; var childType: Integer);
var g, owner: IInterface; depth: Integer;
begin
  cell := nil; world := nil;
  Need((Signature(r) = 'REFR') or (Signature(r) = 'ACHR'), 'Reference context requested for non-reference');
  g := GetContainer(r);
  Need(Assigned(g), 'Reference has no physical parent group: ' + RecordIdentity(r));
  Need(ElementType(g) = etGroupRecord, 'Reference parent is not a group');
  childType := GroupType(g);
  Need((childType = 8) or (childType = 9) or (childType = 10), 'Unexpected reference physical child group');
  owner := ChildrenOf(g);
  g := GetContainer(g);
  Need(Assigned(g) and (ElementType(g) = etGroupRecord), 'Reference has no CELL Children group');
  Need(GroupType(g) = 6, 'Reference grandparent is not CELL Children group6');
  cell := ChildrenOf(g);
  Need(Assigned(cell), 'Physical CELL Children owner unresolved');
  Need(Signature(cell) = 'CELL', 'Physical reference owner is not CELL');
  Need(SameRecord(owner, cell), 'Reference subgroup and CELL Children labels disagree');
  depth := 0;
  while Assigned(g) do begin
    if ElementType(g) = etGroupRecord then
      if GroupType(g) = 1 then begin
        world := ChildrenOf(g);
        Need(Assigned(world), 'Physical world owner unresolved');
        Need(Signature(world) = 'WRLD', 'Physical world owner has wrong type');
      end;
    g := GetContainer(g); depth := depth + 1;
    Need(depth < 32, 'Unexpected/cyclic physical reference group chain');
  end;
end;

procedure AssertVirtualCell(r, cell: IInterface);
var e: IInterface;
begin
  e := Top(r, 'Cell');
  if not Assigned(e) then Exit;
  Need((Signature(e) = '') and (BaseName(e) = 'Cell') and (DefType(e) = dtInteger) and
    (ElementType(e) = etValue) and (ElementCount(e) = 0), 'Unexpected synthetic Cell definition');
  Need(SameRecord(ContainingMainRecord(e), r), 'Synthetic Cell is not owned by the validated reference');
  Need(SameRecord(LinksTo(e), cell), 'Synthetic Cell disagrees with physical GRUP owner');
end;

procedure AssertReferencePlacement(base, dst: IInterface; sourceOrigin: string; sourceID: Integer;
  targetOrigin: string; targetID: Integer; worldOrigin: string; worldID, sourceKind, targetKind: Integer);
var sourceCell, targetCell, sourceWorld, targetWorld, expected: IInterface; a, b: Integer;
begin
  ReferenceContext(base, sourceCell, sourceWorld, a);
  ReferenceContext(dst, targetCell, targetWorld, b);
  Need(a = sourceKind, 'Frozen source reference group changed: ' + RecordIdentity(base));
  Need(b = targetKind, 'Reference output physical group type changed: ' + RecordIdentity(dst));
  Need(SameRecord(sourceCell, OriginRecord(sourceOrigin, sourceID)), 'Frozen source CELL changed');
  Need(SameRecord(targetCell, OriginRecord(targetOrigin, targetID)), 'Reference moved to an unplanned CELL');
  if worldOrigin = '' then
    Need((not Assigned(sourceWorld)) and (not Assigned(targetWorld)), 'Interior reference gained a WRLD parent')
  else begin
    expected := OriginRecord(worldOrigin, worldID);
    Need(SameRecord(sourceWorld, expected) and SameRecord(targetWorld, expected), 'Reference crossed its frozen WRLD');
  end;
  AssertVirtualCell(base, sourceCell); AssertVirtualCell(dst, targetCell);
  Need(Assigned(Top(base, 'Cell')) = Assigned(Top(dst, 'Cell')), 'Synthetic Cell presence changed');
  // DATA coordinates/rotation stay exact at typed leaves and in the separate
  // binary verifier. Only the18 authored Persistent transformations relocate.
  AssertTree(Top(dst, 'DATA'), Top(base, 'DATA'), 'Reference placement DATA ' + RecordIdentity(base));
end;

procedure AssertPlannedReferencePlacement(origin: string; id: Integer; base, dst: IInterface; persistent: Boolean);
var matched: Boolean;
begin
  if (Signature(base) <> 'REFR') and (Signature(base) <> 'ACHR') then Exit;
  matched := False;
@@REF_PLACEMENT_DISPATCH@@
  Need(matched, 'Reference has no frozen physical placement contract: ' + origin + '|' + IntToHex(id, 6));
end;

procedure AssertMerged(origin: string; id: Integer; owner, allowed: string; persistent: Boolean);
var
  base, dst, a, b: IInterface;
  i, expected: Integer;
  t: string;
begin
  base := InFile(owner, OriginRecord(origin, id));
  dst := OutputRecord(origin, id);
  Need(SameRecord(dst, base), 'Output identity mismatch');
  Need(Signature(dst) = Signature(base), 'Output signature mismatch');
  expected := GetNativeValue(Req(base, 'Record Header\Record Flags'));
  if persistent then expected := expected or $400;
  AssertHeader(dst, base, 'Merged header', False, expected);
  AssertPlannedReferencePlacement(origin, id, base, dst, persistent);
  for i := 0 to ElementCount(base) - 1 do begin
    a := ElementByIndex(base, i);
    t := Token(a);
    if not IsRecordHeader(a) and (Pos('|' + t + '|', allowed) = 0) then
      if not (persistent and (t = 'Cell') and (Signature(a) = '')) then
        AssertPreservedField(dst, base, a, 'Preserved base ' + IntToHex(id, 6) + '/' + t);
  end;
  for i := 0 to ElementCount(dst) - 1 do begin
    b := ElementByIndex(dst, i);
    t := Token(b);
    if not IsRecordHeader(b) and (Pos('|' + t + '|', allowed) = 0) and not IgnoredGenerated(dst, b) then
      Need(Assigned(Top(base, t)), 'Unexpected added field: ' + t);
  end;
end;

procedure PostBegin;
begin
  Inc(postChecks);
  lastNeedFailure := '';
end;

procedure PostFailure(context: string);
begin
  Inc(postFailures);
  if lastNeedFailure = '' then
    lastNeedFailure := 'Unexpected runtime exception during this assertion; not accepted';
  AddMessage('FEATURE_POST_ASSERTION_FAILURE' + #9 + AuditClean(context) + #9 + AuditClean(lastNeedFailure));
end;

procedure PostMerged(origin: string; id: Integer; owner, allowed: string; persistent: Boolean);
var base, dst, a, b: IInterface; i, expected: Integer; t, context: string;
begin
  context := origin + '|' + IntToHex(id, 6) + ' [' + owner + ']';
  PostBegin;
  try
    base := InFile(owner, OriginRecord(origin, id));
    dst := OutputRecord(origin, id);
    Need(SameRecord(dst, base), 'Output identity mismatch');
    Need(Signature(dst) = Signature(base), 'Output signature mismatch');
    expected := GetNativeValue(Req(base, 'Record Header\Record Flags'));
    if persistent then expected := expected or $400;
  except PostFailure(context + '/resolution'); Exit; end;
  PostBegin;
  try AssertHeader(dst, base, 'Merged header', False, expected);
  except PostFailure(context + '/Record Header'); end;
  PostBegin;
  try AssertPlannedReferencePlacement(origin, id, base, dst, persistent);
  except PostFailure(context + '/physical placement'); end;
  // Each source top-level field has its own exception boundary. A mismatch
  // never silently returns success or prevents auditing subsequent fields.
  for i := 0 to ElementCount(base) - 1 do begin
    a := ElementByIndex(base, i); t := Token(a);
    if not IsRecordHeader(a) and (Pos('|' + t + '|', allowed) = 0) then
      if not (persistent and (t = 'Cell') and (Signature(a) = '')) then begin
        PostBegin;
        try AssertPreservedField(dst, base, a, 'Preserved base ' + IntToHex(id, 6) + '/' + t);
        except PostFailure(context + '/' + t); end;
      end;
  end;
  for i := 0 to ElementCount(dst) - 1 do begin
    b := ElementByIndex(dst, i); t := Token(b);
    if not IsRecordHeader(b) and (Pos('|' + t + '|', allowed) = 0) and not IgnoredGenerated(dst, b) then begin
      PostBegin;
      try Need(Assigned(Top(base, t)), 'Unexpected added field: ' + t);
      except PostFailure(context + '/added/' + t); end;
    end;
  end;
end;

procedure PostForwarded(donor, origin: string; id: Integer; fieldText: string);
begin
  PostBegin;
  try AssertForwarded(donor, origin, id, fieldText);
  except PostFailure(origin + '|' + IntToHex(id, 6) + '/forward/' + fieldText + ' [' + donor + ']'); end;
end;

procedure PostExactSource(owner, origin: string; id: Integer);
begin
  PostBegin;
  try AssertPayload(OutputRecord(origin, id), InFile(owner, OriginRecord(origin, id)), 'Preserved source-authored record');
  except PostFailure(origin + '|' + IntToHex(id, 6) + '/source-authored [' + owner + ']'); end;
end;

procedure FinishPostAssertions;
begin
  AddMessage('FEATURE_POST_ASSERTIONS_COMPLETED' + #9 + IntToStr(postChecks) + #9 + IntToStr(postFailures));
  Need(postFailures = 0, 'Post-merge assertions failed: ' + IntToStr(postFailures) + '; candidate export prohibited');
end;

function FindListItem(list, target: IInterface): IInterface;
var
  i: Integer;
  e: IInterface;
begin
  Result := nil;
  for i := 0 to ElementCount(list) - 1 do begin
    e := ElementByIndex(list, i);
    if SameRecord(LinksTo(e), target) then begin
      Need(not Assigned(Result), 'Duplicate FLST item');
      Result := e;
    end;
  end;
end;

procedure HothVoiceUnion;
var
  baseList, dstList, sourceList, item, added, hoth, erin: IInterface;
  i, expected: Integer;
begin
  baseList := Req(InFile('ErinRace.esm', OriginRecord('Skyrim.esm', $03B4A5)), 'FormIDs');
  dstList := Req(OutputRecord('Skyrim.esm', $03B4A5), 'FormIDs');
  sourceList := Req(InFile('HothFollower.esp', OriginRecord('Skyrim.esm', $03B4A5)), 'FormIDs');
  hoth := OriginRecord('HothFollower.esp', $00333C);
  erin := OriginRecord('ErinRace.esm', $001040);
  Need(Signature(hoth) = 'VTYP', 'Hoth appended voice signature changed');
  Need(Signature(erin) = 'VTYP', 'Erin base voice signature changed');
  Need(Assigned(FindListItem(baseList, erin)), 'Expected Erin voice absent in base');
  item := FindListItem(sourceList, hoth);
  Need(Assigned(item), 'Hoth voice absent in donor list');
  Need(not Assigned(FindListItem(baseList, hoth)), 'Base already includes Hoth: re-evaluate plan');
  if (not VERIFY_ONLY) and (not postVerificationPhase) then begin
    Need(not Assigned(FindListItem(dstList, hoth)), 'Hoth already present before union');
    Need(AddRequiredElementMasters(item, patchFile, False, True), 'Hoth voice required master failed');
    added := ElementAssign(dstList, HighInteger, item, False);
    Need(Assigned(added), 'Typed voice append failed');
    SetEditValue(added, IntToHex(GetLoadOrderFormID(hoth), 8));
  end;
  Need(ElementCount(dstList) = ElementCount(baseList) + 1, 'Voice union cardinality mismatch');
  for i := 0 to ElementCount(baseList) - 1 do begin
    item := ElementByIndex(baseList, i);
    added := FindListItem(dstList, LinksTo(item));
    Need(Assigned(added), 'Voice union lost a base entry');
    AssertTree(item, added, 'Preserved base voice');
  end;
  Need(Assigned(FindListItem(dstList, erin)), 'Erin voice lost');
  Need(Assigned(FindListItem(dstList, hoth)), 'Hoth voice absent after union');
end;

function HorseAliasPackage(q, expectedPack: IInterface): IInterface;
var
  aliases, a, packages, p: IInterface;
  i, j, countAlias, countPackage: Integer;
begin
  Result := nil;
  countAlias := 0;
  countPackage := 0;
  aliases := Req(q, 'Aliases');
  for i := 0 to ElementCount(aliases) - 1 do begin
    a := ElementByIndex(aliases, i);
    if Assigned(ElementByPath(a, 'ALST')) then
      if GetNativeValue(Req(a, 'ALST')) = 1 then begin
        Inc(countAlias);
        Need(GetEditValue(Req(a, 'ALID')) = 'SofiaHorse', 'Alias 1 is no longer SofiaHorse');
        packages := Req(a, 'Alias Package Data');
        for j := 0 to ElementCount(packages) - 1 do begin
          p := ElementByIndex(packages, j);
          Need(Signature(p) = 'ALPC', 'Unexpected alias package field');
          if SameRecord(LinksTo(p), expectedPack) then begin
            Inc(countPackage);
            Result := p;
          end;
        end;
      end;
  end;
  Need(countAlias = 1, 'Expected exactly one Alias 1');
  Need(countPackage = 1, 'Expected exactly one Alias 1 ALPC target');
end;

procedure AssertQuestRedirect(src, dst, oldPack, newPack: IInterface; var redirects: Integer);
var
  i: Integer;
  linked: IInterface;
begin
  Need(BaseName(src) = BaseName(dst), 'Quest field definition changed');
  Need(ElementCount(src) = ElementCount(dst), 'Quest copy shape changed');
  if ElementCount(src) > 0 then begin
    for i := 0 to ElementCount(src) - 1 do
      AssertQuestRedirect(ElementByIndex(src, i), ElementByIndex(dst, i), oldPack, newPack, redirects);
    Exit;
  end;
  linked := LinksTo(src);
  if Assigned(linked) then
    if ElementType(linked) = etMainRecord then
      if SameRecord(linked, oldPack) then begin
        Need(Signature(src) = 'ALPC', 'Unexpected non-ALPC use of global PACK in source quest');
        Need(SameRecord(LinksTo(dst), newPack), 'Quest package redirection failed');
        Inc(redirects);
        Exit;
      end;
  AssertTree(src, dst, 'Unchanged source quest leaf');
end;

procedure CountSourcePackUses(e, recordOwner, oldPack, expectedQuest: IInterface; var total: Integer);
var
  i: Integer;
  linked: IInterface;
begin
  if ElementCount(e) > 0 then begin
    for i := 0 to ElementCount(e) - 1 do
      CountSourcePackUses(ElementByIndex(e, i), recordOwner, oldPack, expectedQuest, total);
    Exit;
  end;
  linked := LinksTo(e);
  if Assigned(linked) then
    if ElementType(linked) = etMainRecord then
      if SameRecord(linked, oldPack) then begin
        Need(SameRecord(recordOwner, expectedQuest), 'Additional typed source consumer of global PACK: ' + Name(recordOwner));
        Need(Signature(e) = 'ALPC', 'Unexpected typed source use of global PACK');
        Inc(total);
      end;
end;

procedure AssertOnlySourcePackConsumer(f, oldPack, expectedQuest: IInterface);
var
  i, j, total: Integer;
  r: IInterface;
begin
  total := 0;
  for i := 0 to RecordCount(f) - 1 do begin
    r := RecordByIndex(f, i);
    if Signature(r) <> 'TES4' then
      // Skip header identity: an override's FormID is not a payload consumer.
      for j := 0 to ElementCount(r) - 1 do
        if not IsRecordHeader(ElementByIndex(r, j)) then
          CountSourcePackUses(ElementByIndex(r, j), r, oldPack, expectedQuest, total);
  end;
  Need(total = 1, 'Expected exactly one typed payload use of global PACK across the entire Sofia plugin');
end;

procedure SofiaHorseIsolation;
var
  globalPack, donorPack, aliasLeaf, p: IInterface;
  redirects, i, ownPacks: Integer;
begin
  globalPack := OriginRecord('Skyrim.esm', $09845C);
  donorPack := InFile('SofiaFollower.esp', globalPack);
  Need(EditorID(globalPack) = 'PlayerHorseStayPut', 'Stock PACK editor ID changed');
  Need(EditorID(donorPack) = 'SofiaHorseStayPut', 'Source PACK editor ID changed');
  Need(ElementCount(Req(globalPack, 'Conditions')) = 2, 'Stock PACK condition count changed');
  Need(not Assigned(ElementByPath(donorPack, 'Conditions')), 'Source PACK unexpectedly has Conditions');
  sourceQuest := OriginRecord('SofiaFollower.esp', $00AA58);
  Need(EditorID(sourceQuest) = 'JJSofiaScripts', 'Sofia quest EDID changed');
  Need(SameText(GetFileName(GetFile(BaseWinner(sourceQuest))), 'SofiaFollower.esp'), 'Unreviewed Sofia quest override');
  HorseAliasPackage(sourceQuest, globalPack);
  AssertOnlySourcePackConsumer(ReqFile('SofiaFollower.esp'), globalPack, sourceQuest);
  if VERIFY_ONLY or postVerificationPhase then begin
    ownPacks := 0;
    for i := 0 to RecordCount(patchFile) - 1 do begin
      p := RecordByIndex(patchFile, i);
      if SameText(GetFileName(GetFile(MasterOrSelf(p))), PATCH_NAME) then
        if Signature(p) <> 'TES4' then begin
          Need(Signature(p) = 'PACK', 'Unexpected new own record in output');
          clonePack := p;
          Inc(ownPacks);
        end;
    end;
    Need(ownPacks = 1, 'Expected exactly one new own PACK');
    copiedQuest := InFile(PATCH_NAME, sourceQuest);
  end else begin
    Need(AddRequiredElementMasters(donorPack, patchFile, False, True), 'Source PACK required masters failed');
    Need(AddRequiredElementMasters(sourceQuest, patchFile, False, True), 'Sofia quest required masters failed');
    clonePack := wbCopyElementToFile(donorPack, patchFile, True, True);
    Need(Assigned(clonePack), 'New PACK clone failed');
    RestoreSourceHeaderMetadata(clonePack, donorPack);
    copiedQuest := wbCopyElementToFile(sourceQuest, patchFile, False, True);
    Need(Assigned(copiedQuest), 'Sofia quest typed copy failed');
    RestoreSourceHeaderMetadata(copiedQuest, sourceQuest);
    AssertPayload(copiedQuest, sourceQuest, 'Initial Sofia quest');
    aliasLeaf := HorseAliasPackage(copiedQuest, globalPack);
    SetEditValue(aliasLeaf, IntToHex(GetLoadOrderFormID(clonePack), 8));
    RestoreSourceHeaderMetadata(copiedQuest, sourceQuest);
  end;
  Need(Signature(clonePack) = 'PACK', 'Clone signature changed');
  Need((FormID(clonePack) and $FFFFFF) >= $800, 'New own object ID below ESL safe range');
  Need((FormID(clonePack) and $FFFFFF) <= $FFF, 'New own object ID exceeds ESL safe range');
  AssertPayloadInner(clonePack, donorPack, 'Exact source PACK clone', True);
  HorseAliasPackage(copiedQuest, clonePack);
  redirects := 0;
  Need(ElementCount(sourceQuest) = ElementCount(copiedQuest), 'Quest top-level fields changed');
  for i := 0 to ElementCount(sourceQuest) - 1 do
    if not IsRecordHeader(ElementByIndex(sourceQuest, i)) then
      AssertQuestRedirect(ElementByIndex(sourceQuest, i), Top(copiedQuest, Token(ElementByIndex(sourceQuest, i))), globalPack, clonePack, redirects);
  AssertHeader(copiedQuest, sourceQuest, 'Sofia quest redirected header', False, GetNativeValue(Req(sourceQuest, 'Record Header\Record Flags')));
  Need(redirects = 1, 'Expected exactly one redirected FormID leaf in the entire quest');
  AssertPayload(OutputRecord('Skyrim.esm', $09845C), globalPack, 'Restored global player-horse PACK');
end;

procedure AssertRecordSet;
var
  i, countPayload, ownCount: Integer;
  r: IInterface;
begin
  countPayload := 0;
  ownCount := 0;
  for i := 0 to RecordCount(patchFile) - 1 do begin
    r := RecordByIndex(patchFile, i);
    if Signature(r) <> 'TES4' then begin
      Inc(countPayload);
      Need((Signature(r) <> 'NAVI') and (Signature(r) <> 'NAVM'), 'Unexpected navigation record in this bounded patch');
      if SameText(GetFileName(GetFile(MasterOrSelf(r))), PATCH_NAME) then begin
        Inc(ownCount);
        Need(SameRecord(r, clonePack), 'Unexpected new own record');
      end;
      Need(Check(r) = '', 'Native Check failed: ' + Name(r) + ' | ' + Check(r));
    end;
  end;
  Need(countPayload = @@RECORD_COUNT@@, 'Unexpected output payload record count');
  Need(ownCount = 1, 'Expected exactly one new own record');
  Need(MasterCount(patchFile) <= 253, 'Conservative master limit exceeded');
end;

procedure PostSpecials;
begin
  PostBegin;
  try HothVoiceUnion;
  except PostFailure('Skyrim.esm|03B4A5/Hoth exact voice union'); end;
  PostBegin;
  try SofiaHorseIsolation;
  except PostFailure('Sofia exact PACK clone, unique Alias1 redirect and global PACK restore'); end;
end;

procedure PostRecordSet;
begin
  PostBegin;
  try AssertRecordSet;
  except PostFailure('Exact output record set and native Check'); end;
end;

function Initialize: Integer;
var
  stream: TFileStream;
begin
  Result := 1;
  seedCount := 0;
  postChecks := 0; postFailures := 0; postVerificationPhase := False;
@@GUARDS@@
  RequireNormalDefinitions;
  RunComparatorSelfAudit;
  if VERIFY_ONLY then
    patchFile := ReqFile(PATCH_NAME)
  else begin
    Need(not Assigned(FileByName(PATCH_NAME)), 'Patch already loaded; refuse overwrite');
    Need(not FileExists(DataPath + PATCH_NAME), 'Patch already present in VFS; refuse overwrite');
    Need(not FileExists(OUTPUT_FILE), 'Candidate output already exists; refuse overwrite');
    patchFile := AddNewFileName(PATCH_NAME);
    Need(Assigned(patchFile), 'Could not create a new in-memory plugin');
  end;
@@SEEDS@@
  if not VERIFY_ONLY then begin
@@APPLY@@
@@PERSISTENT@@
  end;
  if not VERIFY_ONLY then begin
    HothVoiceUnion;
    SofiaHorseIsolation;
  end;
  if not VERIFY_ONLY then begin
    SortMasters(patchFile);
    SetIsESL(patchFile, True);
@@RESTORE_METADATA@@
    RestoreSourceHeaderMetadata(copiedQuest, sourceQuest);
    RestoreSourceHeaderMetadata(clonePack, InFile('SofiaFollower.esp', OriginRecord('Skyrim.esm', $09845C)));
  end;
  postVerificationPhase := True;
@@VERIFY@@
@@VERIFY_FIELDS@@
  PostSpecials;
  PostRecordSet;
  FinishPostAssertions;
  if not VERIFY_ONLY then begin
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));
    stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
    try
      // rmNo: mode 1 triggers a known xEdit GRUP reset-modified assertion.
      FileWriteToStream(patchFile, stream, 0);
    finally
      stream.Free;
    end;
    AddMessage('FEATURE_COMPAT_CANDIDATE_EXPORTED|' + OUTPUT_FILE);
  end;
  if VERIFY_ONLY then
    AddMessage('FEATURE_COMPAT_RELOAD_TYPED_PASS|SEEDS=' + IntToStr(seedCount) + '|OWN_PACK=1|SOFIA_ALIAS_REDIRECT=1')
  else
    AddMessage('FEATURE_COMPAT_INMEMORY_TYPED_PASS|SEEDS=' + IntToStr(seedCount) + '|OWN_PACK=1|SOFIA_ALIAS_REDIRECT=1');
  Result := 0;
end;

end.
