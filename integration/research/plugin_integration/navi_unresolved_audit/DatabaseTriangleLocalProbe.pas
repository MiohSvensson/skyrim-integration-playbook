unit UserScript;

const
  VERIFY_ONLY = True;
  PATCH_NAME = 'Database Forgotten City USSEP Navigation.esp';
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

function Triangle(r: IInterface; index: Integer): IInterface;
var a: IInterface;
begin
  a := Req(r, 'NVNM\Triangles');
  Need((index >= 0) and (index < ElementCount(a)), 'Triangle index outside record');
  Result := ElementByIndex(a, index);
  Need(ElementCount(Result) = 8, 'Normal 4.1.5f triangle fields required');
end;

function EdgeName(side: Integer): string;
begin
  case side of
    0: Result := 'Edge 0-1';
    1: Result := 'Edge 1-2';
    2: Result := 'Edge 2-0';
  else Need(False, 'Bad triangle side'); end;
end;

function Initialize: Integer;
var stock, usFile, patchFile, masterNav, usNav, navCopy, a, b: IInterface;
    i, side, flags, edge, expected: Integer;
begin
  Result := 1;
  stock := ReqFile('Skyrim.esm');
  usFile := ReqFile('Unofficial Skyrim Special Edition Patch.esp');
  masterNav := RecordByFormID(stock, $00108AB4, False);
  usNav := RecordByFormID(usFile, LoadOrderFormIDtoFileFormID(usFile, GetLoadOrderFormID(masterNav)), True);
  Need(FileExists(DataPath + PATCH_NAME), 'Installed candidate required');
  patchFile := ReqFile(PATCH_NAME);
  navCopy := RecordByFormID(patchFile, LoadOrderFormIDtoFileFormID(patchFile, GetLoadOrderFormID(masterNav)), True);
  for i := 0 to 323 do begin
    a := Triangle(navCopy, i);
    b := Triangle(usNav, i);
    flags := GetNativeValue(Req(b, 'Flags'));
    expected := flags;
    if i = 50 then begin Need(flags = 2052, 'USSEP triangle50 flags changed'); expected := 2048; end;
    Need(GetNativeValue(Req(a, 'Flags')) = expected, 'Unexpected composed flags');
    for side := 0 to 2 do begin
      edge := GetNativeValue(Req(b, EdgeName(side)));
      expected := edge;
      if (flags and (1 shl side)) <> 0 then begin
        if edge = 6 then begin Need((i = 50) and (side = 2), 'More than one portal uses deleted entry'); expected := -1; end
        else if edge > 6 then expected := edge - 1;
      end;
      Need(GetNativeValue(Req(a, EdgeName(side))) = expected, 'Unexpected edge remap');
    end;
    a := nil;
    b := nil;
  end;
  NativePhase('triangle_locals_released');
  AddMessage('FC_NAV_TRIANGLE_TYPED_PASS');
  NativePhase('FC_NAV_TRIANGLE_TYPED_PASS');
  Result := 0;
end;

end.
