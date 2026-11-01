unit UserScript;

const
  PATCH_NAME = 'Database Triangle Flag Probe.esp';
  PROGRESS_FILE = '';

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

function CopyOverride(sourceRecord, targetFile: IInterface): IInterface;
begin
  Result := wbCopyElementToFile(sourceRecord, targetFile, False, True);
  Need(Assigned(Result), 'Main-record payload copy failed');
  SetFormVCS1(Result, GetFormVCS1(sourceRecord));
  SetFormVCS2(Result, GetFormVCS2(sourceRecord));
  SetFormVersion(Result, GetFormVersion(sourceRecord));
end;

function Triangle(r: IInterface; index: Integer): IInterface;
var a: IInterface;
begin
  a := Req(r, 'NVNM\Triangles');
  Need((index >= 0) and (index < ElementCount(a)), 'Triangle index outside record');
  Result := ElementByIndex(a, index);
  Need(ElementCount(Result) = 8, 'Normal 4.1.5f triangle fields required');
end;

function Initialize: Integer;
var stock, usFile, masterNav, usNav, patchFile, navCopy, a, b: IInterface;
    flags: Integer;
begin
  Result := 1;
  stock := ReqFile('Skyrim.esm');
  usFile := ReqFile('Unofficial Skyrim Special Edition Patch.esp');
  masterNav := RecordByFormID(stock, $00108AB4, False);
  usNav := RecordByFormID(usFile, LoadOrderFormIDtoFileFormID(usFile, GetLoadOrderFormID(masterNav)), True);
  Need(not Assigned(FileByName(PATCH_NAME)), 'Probe patch already loaded');
  patchFile := AddNewFileName(PATCH_NAME);
  Need(Assigned(patchFile), 'Probe patch creation failed');
  Need(AddRequiredElementMasters(usNav, patchFile, False, True), 'NAVM masters failed');
  SortMasters(patchFile);
  navCopy := CopyOverride(usNav, patchFile);
  Need(Assigned(navCopy), 'NAVM copy failed');
  RemoveByIndex(Req(navCopy, 'NVNM\Edge Links'), 6, True);
  SetIsESL(patchFile, True);
  a := Triangle(navCopy, 323);
  NativePhase('triangle_assigned');
  b := Req(a, 'Flags');
  NativePhase('flag_assigned');
  flags := GetNativeValue(b);
  AddMessage('TRIANGLE_FLAG_NATIVE|' + IntToStr(flags));
  NativePhase('flag_native_read');
  b := nil;
  NativePhase('flag_released');
  a := nil;
  NativePhase('triangle_released');
  AddMessage('TRIANGLE_FLAG_LIFETIME_PASS');
  NativePhase('TRIANGLE_FLAG_LIFETIME_PASS');
  Result := 0;
end;

end.
