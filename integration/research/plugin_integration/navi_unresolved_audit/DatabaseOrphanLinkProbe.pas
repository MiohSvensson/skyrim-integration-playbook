unit UserScript;
const
  PROGRESS = 'E:\stock\Skyrim collection\Database\integration\research\plugin_integration\navi_unresolved_audit\orphan_link_probe_v1_progress.txt';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('ORPHAN_LINK_PROBE_STOP: ' + messageText);
end;

procedure Phase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try
    rows.Add(value);
    rows.SaveToFile(PROGRESS);
  finally rows.Free; end;
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Missing typed field: ' + path);
end;

function Initialize: Integer;
var stock, navi, infos, info, key, parent, linked: IInterface;
    i: Integer;
begin
  Result := 1;
  Need(not FileExists(PROGRESS), 'Fresh probe progress path required');
  Phase('entered|files=' + IntToStr(FileCount));
  Need(Pos('e:\stock\skyrim collection\database\', LowerCase(DataPath)) = 1, 'Database Data path required');
  stock := FileByName('Skyrim.esm');
  Need(Assigned(stock), 'Skyrim.esm not loaded');
  Need(SameText(IntToHex(wbCRC32File(DataPath + 'Skyrim.esm'), 8), '66212483'), 'Stock SHA/CRC context changed');
  Phase('stock_crc_passed');
  navi := RecordByFormID(stock, $00012FB4, False);
  Need(Assigned(navi), 'Stock NAVI absent');
  infos := Req(navi, 'Navmesh Infos');
  info := nil;
  for i := 0 to ElementCount(infos) - 1 do begin
    key := Req(ElementByIndex(infos, i), 'Navmesh');
    if GetNativeValue(key) = $00028E37 then begin
      info := ElementByIndex(infos, i);
      Break;
    end;
  end;
  Need(Assigned(info), 'Exact stock orphan absent');
  Phase('orphan_key_found');
  parent := Req(info, 'PathingCell\Parent');
  Need(DefType(parent) = dtUnion, 'Parent is not union');
  Need(ElementType(parent) = etUnion, 'Parent is not etUnion');
  Need(ElementCount(parent) = 0, 'Parent union unexpectedly has children');
  Need(GetNativeValue(parent) = $00028E34, 'Parent scalar changed');
  Phase('before_nil_parent_links_to');
  linked := LinksTo(parent);
  if Assigned(linked) then Phase('after_nil_parent_links_to|link_present')
  else Phase('after_nil_parent_links_to|link_nil');
  Need(not Assigned(linked), 'Nil parent unexpectedly resolved');
  AddMessage('ORPHAN_LINK_PROBE_PASS');
  Phase('ORPHAN_LINK_PROBE_PASS');
  Result := 0;
end;

end.
