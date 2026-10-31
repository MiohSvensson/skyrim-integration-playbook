unit UserScript;
const
  PATCH_NAME = 'Database NAVI Append Probe.esp';
  OUTPUT_FILE = 'E:\stock\Skyrim collection\Database\integration\research\plugin_integration\navi_unresolved_audit\lifetime_navi_append_v2\Database NAVI Append Probe.esp';
  PROGRESS = 'E:\stock\Skyrim collection\Database\integration\research\plugin_integration\navi_unresolved_audit\navi_append_probe_v2_progress.txt';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('NAVI_APPEND_PROBE_STOP: ' + messageText);
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

function ReqFile(name: string): IInterface;
begin
  Result := FileByName(name);
  Need(Assigned(Result), 'Missing loaded file: ' + name);
end;

function InfoFor(navi, target: IInterface): IInterface;
var infos, item, linked: IInterface; i: Integer;
begin
  Result := nil;
  infos := Req(navi, 'Navmesh Infos');
  for i := 0 to ElementCount(infos) - 1 do begin
    item := ElementByIndex(infos, i);
    linked := LinksTo(Req(item, 'Navmesh'));
    if Assigned(linked) then
      if GetLoadOrderFormID(linked) = GetLoadOrderFormID(target) then begin
        Result := item;
        Exit;
      end;
  end;
end;

procedure RemapInfoReferences(copyInfo, sourceInfo: IInterface);
var i: Integer; linked: IInterface;
begin
  Need(BaseName(copyInfo) = BaseName(sourceInfo), 'NVMI shape mismatch');
  Need(ElementCount(copyInfo) = ElementCount(sourceInfo), 'NVMI count mismatch');
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

function WinnerExcludingPatch(master: IInterface): IInterface;
var i: Integer; candidate: IInterface;
begin
  Result := master;
  for i := 0 to OverrideCount(master) - 1 do begin
    candidate := OverrideByIndex(master, i);
    if not SameText(GetFileName(GetFile(candidate)), PATCH_NAME) then
      if GetLoadOrder(GetFile(candidate)) > GetLoadOrder(GetFile(Result)) then Result := candidate;
  end;
end;

function Initialize: Integer;
var stock, naviSource, usFile, usNavi, masterNavi, masterNav, patchFile: IInterface;
    source, desired, existing, newInfo: IInterface;
    stream: TFileStream;
begin
  Result := 1;
  Need(not FileExists(PROGRESS), 'Fresh progress required');
  Phase('entered');
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1, 'Database Data path required');
  stock := ReqFile('Skyrim.esm');
  naviSource := ReqFile('KuroneSoulTomb_EX3.esp');
  usFile := ReqFile('Unofficial Skyrim Special Edition Patch.esp');
  masterNavi := RecordByFormID(stock, $00012FB4, False);
  masterNav := RecordByFormID(stock, $00108AB4, False);
  source := WinnerExcludingPatch(masterNavi);
  Need(Assigned(source), 'Winning NAVI record absent');
  Need(SameText(GetFileName(GetFile(source)), 'KuroneSoulTomb_EX3.esp'), 'Winning NAVI source changed');
  Phase('source_resolved');
  usNavi := RecordByFormID(usFile, LoadOrderFormIDtoFileFormID(usFile, GetLoadOrderFormID(masterNavi)), True);
  Need(Assigned(usNavi), 'USSEP NAVI record absent');
  desired := InfoFor(usNavi, masterNav);
  Need(Assigned(desired), 'USSEP target NVMI absent');
  Need(not Assigned(FileByName(PATCH_NAME)), 'Probe patch already loaded');
  Need(not FileExists(OUTPUT_FILE), 'Probe output already exists');
  patchFile := AddNewFileName(PATCH_NAME);
  Need(Assigned(patchFile), 'Probe patch creation failed');
  Need(AddRequiredElementMasters(source, patchFile, False, True), 'Source NAVI masters failed');
  Need(AddRequiredElementMasters(desired, patchFile, False, True), 'USSEP NVMI masters failed');
  SortMasters(patchFile);
  source := wbCopyElementToFile(source, patchFile, False, True);
  Need(Assigned(source), 'NAVI copy failed');
  Phase('copied');
  existing := InfoFor(source, masterNav);
  if Assigned(existing) then begin Remove(existing); existing := nil; end;
  Phase('replacement_checked');
  newInfo := ElementAssign(Req(source, 'Navmesh Infos'), HighInteger, desired, False);
  Need(Assigned(newInfo), 'NVMI assignment failed');
  RemapInfoReferences(newInfo, desired);
  Phase('assigned');
  SetIsESL(patchFile, True);
  ForceDirectories(ExtractFilePath(OUTPUT_FILE));
  stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
  try FileWriteToStream(patchFile, stream, 0);
  finally stream.Free; end;
  Phase('exported');
  AddMessage('NAVI_APPEND_PROBE_PASS');
  Phase('NAVI_APPEND_PROBE_PASS');
  Result := 0;
end;

end.
