unit UserScript;
// Read-only verifier for the bounded VMAD format patch.
const
  VERIFY_ONLY = True;
  PATCH_NAME = 'Database God of War Script Format.esp';
  PROGRESS_FILE = '';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\god_of_war_script_format\candidate\Database God of War Script Format.esp';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('BOUNDED_GOW_STOP: ' + messageText);
end;

procedure NativePhase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try rows.Add(value); rows.SaveToFile(PROGRESS_FILE);
  finally rows.Free; end;
end;

function ReqFile(fileName: string): IInterface;
begin
  Result := FileByName(fileName);
  Need(Assigned(Result), 'Required file absent: ' + fileName);
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Required field absent: ' + path);
end;

function Initialize: Integer;
var source, patchFile, sourceRec, r: IInterface;
    i, id, count: Integer;
begin
  Result := 1;
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1, 'Database-owned Data required');
  source := ReqFile('God of War.esp');
  Need(FileExists(DataPath + PATCH_NAME), 'Installed candidate required');
  patchFile := ReqFile(PATCH_NAME);
  count := 0;
  for i := 0 to 1 do begin
    if i = 0 then id := $03000881 else id := $030008A7;
    sourceRec := RecordByFormID(source, id, True);
    Need(Assigned(sourceRec), 'Expected source MGEF absent');
    Need(GetNativeValue(Req(sourceRec, 'VMAD\Object Format')) = 0, 'Expected source object format 0');
    r := RecordByFormID(patchFile, LoadOrderFormIDtoFileFormID(patchFile, GetLoadOrderFormID(sourceRec)), True);
    Need(Assigned(r), 'Expected MGEF override absent');
    Need(GetNativeValue(Req(r, 'VMAD\Object Format')) = 2, 'Object format 2 not established');
    Need(Check(r) = '', 'MGEF diagnostics: ' + Check(r));
    Inc(count);
  end;
  Need(count = 2, 'Expected exactly two MGEF overrides');
  Need(RecordCount(patchFile) = 2, 'Only two MGEF records are allowed');
  for i := 0 to RecordCount(patchFile) - 1 do begin
    r := RecordByIndex(patchFile, i);
    if Signature(r) <> 'TES4' then begin
      Need(Signature(r) = 'MGEF', 'Unexpected record signature');
      Need(SameText(GetFileName(GetFile(MasterOrSelf(r))), 'God of War.esp'), 'Own records forbidden');
    end;
  end;
  Need(GetIsESL(patchFile), 'ESL flag missing');
  NativePhase('GOW_SCRIPT_FORMAT_RELOAD_TYPED_PASS');
  AddMessage('GOW_SCRIPT_FORMAT_RELOAD_TYPED_PASS');
  Result := 0;
end;

end.
