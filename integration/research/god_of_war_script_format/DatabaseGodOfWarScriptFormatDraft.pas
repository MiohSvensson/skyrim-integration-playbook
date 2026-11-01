unit UserScript;
// Bounded producer: only VMAD object format is changed; fresh verification is required.
const
  VERIFY_ONLY = False;
  PATCH_NAME = 'Database God of War Script Format.esp';
  PROGRESS_FILE = '';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\god_of_war_script_format\candidate_v2\Database God of War Script Format.esp';

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

function CopyOverride(sourceRecord, targetFile: IInterface): IInterface;
begin
  Result := wbCopyElementToFile(sourceRecord, targetFile, False, True);
  Need(Assigned(Result), 'MGEF copy failed');
  SetFormVCS1(Result, GetFormVCS1(sourceRecord));
  SetFormVCS2(Result, GetFormVCS2(sourceRecord));
  SetFormVersion(Result, GetFormVersion(sourceRecord));
end;

function Initialize: Integer;
var source, patchFile, sourceRec, r: IInterface;
    i, id, count: Integer;
    stream: TFileStream;
begin
  Result := 1;
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1, 'Database-owned Data required');
  source := ReqFile('God of War.esp');
  if VERIFY_ONLY then begin
    Need(FileExists(DataPath + PATCH_NAME), 'Installed candidate required');
    patchFile := ReqFile(PATCH_NAME);
  end else begin
    Need(not Assigned(FileByName(PATCH_NAME)), 'Patch already loaded');
    Need(not FileExists(OUTPUT_FILE), 'Candidate already exists');
    patchFile := AddNewFileName(PATCH_NAME);
    Need(Assigned(patchFile), 'Patch creation failed');
    AddMasterIfMissing(patchFile, 'Skyrim.esm');
    AddMasterIfMissing(patchFile, 'Dawnguard.esm');
    AddMasterIfMissing(patchFile, 'Dragonborn.esm');
    AddMasterIfMissing(patchFile, 'God of War.esp');
    SortMasters(patchFile);
  end;
  count := 0;
  for i := 0 to 1 do begin
    if i = 0 then id := $03000881 else id := $030008A7;
    sourceRec := RecordByFormID(source, id, True);
    Need(Assigned(sourceRec), 'Expected source MGEF absent');
    Need(SameText(GetFileName(GetFile(WinningOverride(sourceRec))), 'God of War.esp'), 'Unexpected MGEF winner');
    Need(GetNativeValue(Req(sourceRec, 'VMAD\Object Format')) = 0, 'Expected source object format 0');
    if VERIFY_ONLY then
      r := RecordByFormID(patchFile, LoadOrderFormIDtoFileFormID(patchFile, GetLoadOrderFormID(sourceRec)), True)
    else begin
      Need(AddRequiredElementMasters(sourceRec, patchFile, False, True), 'MGEF masters failed');
      r := CopyOverride(sourceRec, patchFile);
      if not Assigned(ElementByPath(sourceRec, 'FULL')) and Assigned(ElementByPath(r, 'FULL')) then begin
        Need(GetEditValue(ElementByPath(r, 'FULL')) = '', 'Unexpected added FULL content');
        Remove(ElementByPath(r, 'FULL'));
      end;
    end;
    Need(Assigned(r), 'Expected MGEF override absent');
    if not VERIFY_ONLY then begin
      Need(GetNativeValue(Req(r, 'VMAD\Object Format')) = 0, 'Copy changed object format before editing');
      SetNativeValue(Req(r, 'VMAD\Object Format'), 2);
    end;
    Need(GetNativeValue(Req(r, 'VMAD\Object Format')) = 2, 'Object format 2 not established');
    if VERIFY_ONLY then Need(Check(r) = '', 'MGEF diagnostics: ' + Check(r));
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
  if not VERIFY_ONLY then SetIsESL(patchFile, True);
  Need(GetIsESL(patchFile), 'ESL flag missing');
  if not VERIFY_ONLY then begin
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));
    stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
    try FileWriteToStream(patchFile, stream, 0);
    finally stream.Free; end;
    NativePhase('GOW_SCRIPT_FORMAT_PRODUCER_PASS');
    AddMessage('GOW_SCRIPT_FORMAT_PRODUCER_PASS');
  end else begin
    NativePhase('GOW_SCRIPT_FORMAT_RELOAD_PASS');
    AddMessage('GOW_SCRIPT_FORMAT_RELOAD_PASS');
  end;
  Result := 0;
end;

end.
