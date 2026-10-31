unit UserScript;
const
  PATCH_NAME = 'Database NAVM Removal Probe.esp';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\plugin_integration\navi_unresolved_audit\lifetime_navm_v2\Database NAVM Removal Probe.esp';
  PROGRESS = 'E:\stock\Skyrim collection\Database\integration\research\plugin_integration\navi_unresolved_audit\navm_removal_probe_v2_progress.txt';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('NAVM_REMOVAL_PROBE_STOP: ' + messageText);
end;

procedure Phase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try rows.Add(value); rows.SaveToFile(PROGRESS);
  finally rows.Free; end;
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Missing field: ' + path);
end;

function Initialize: Integer;
var stock, usFile, masterNav, patchFile, source, edge: IInterface;
    stream: TFileStream;
begin
  Result := 1;
  Need(not FileExists(PROGRESS), 'Fresh progress required');
  Phase('entered');
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1, 'Database Data path required');
  stock := FileByName('Skyrim.esm');
  usFile := FileByName('Unofficial Skyrim Special Edition Patch.esp');
  Need(Assigned(stock) and Assigned(usFile), 'Required sources absent');
  masterNav := RecordByFormID(stock, $00108AB4, False);
  source := RecordByFormID(usFile, LoadOrderFormIDtoFileFormID(usFile, GetLoadOrderFormID(masterNav)), True);
  Need(not Assigned(FileByName(PATCH_NAME)), 'Probe patch already loaded');
  Need(not FileExists(OUTPUT_FILE), 'Probe output already exists');
  patchFile := AddNewFileName(PATCH_NAME);
  Need(Assigned(patchFile), 'Probe patch creation failed');
  Need(AddRequiredElementMasters(source, patchFile, False, True), 'NAVM masters failed');
  SortMasters(patchFile);
  source := wbCopyElementToFile(source, patchFile, False, True);
  Need(Assigned(source), 'NAVM copy failed');
  Phase('copied');
  edge := ElementByIndex(Req(source, 'NVNM\Edge Links'), 6);
  Need(Assigned(edge), 'Target edge absent');
  Remove(edge);
  edge := nil;
  Phase('removed');
  SetIsESL(patchFile, True);
  ForceDirectories(ExtractFilePath(OUTPUT_FILE));
  stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
  try FileWriteToStream(patchFile, stream, 0);
  finally stream.Free; end;
  Phase('exported');
  AddMessage('NAVM_REMOVAL_PROBE_PASS');
  Phase('NAVM_REMOVAL_PROBE_PASS');
  Result := 0;
end;

end.
