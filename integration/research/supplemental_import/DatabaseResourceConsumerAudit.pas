unit UserScript;

const
  VERIFY_ONLY = True;
  PROGRESS_FILE = '';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then
    raise Exception.Create('BOUNDED_RESOURCE_STOP: ' + messageText);
end;

procedure NativePhase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try
    rows.Add(value);
    rows.SaveToFile(PROGRESS_FILE);
  finally rows.Free; end;
end;

function ReqFile(fileName: string): IInterface;
begin
  Result := FileByName(fileName);
  Need(Assigned(Result), 'Required source plugin absent: ' + fileName);
end;

function Req(e: IInterface; path: string): IInterface;
begin
  Result := ElementByPath(e, path);
  Need(Assigned(Result), 'Required typed field absent: ' + path);
end;

function SameRecord(a, b: IInterface): Boolean;
begin
  Result := False;
  if not Assigned(a) then Exit;
  if not Assigned(b) then Exit;
  Result := GetLoadOrderFormID(MasterOrSelf(a)) = GetLoadOrderFormID(MasterOrSelf(b));
end;

procedure RequireWinner(r: IInterface; expectedFile: string);
begin
  Need(SameText(GetFileName(GetFile(WinningOverride(r))), expectedFile),
    'Winning source record changed: ' + expectedFile);
end;

function RaceForNPC(r, targetRace: IInterface): Boolean;
var current, linked: IInterface; depth: Integer;
begin
  Result := False;
  current := r;
  for depth := 0 to 7 do begin
    linked := LinksTo(ElementByPath(current, 'RNAM - Race'));
    if Assigned(linked) then begin
      Result := SameRecord(linked, targetRace);
      Exit;
    end;
    linked := LinksTo(ElementByPath(current, 'TPLT - Template'));
    if not Assigned(linked) then Exit;
    current := WinningOverride(MasterOrSelf(linked));
  end;
  Need(False, 'NPC template chain exceeded the bounded depth');
end;

function Initialize: Integer;
var glen, fc, skin, targetRace, arma, mato, sndr, response: IInterface;
    f, r, linked, npc, g: IInterface;
    i, fileIndex, raceConsumers, npcConsumers, femaleConsumers: Integer;
    flags: Cardinal;
    seen: TStringList;
    key: string;
begin
  Result := 1;
  glen := ReqFile('Glenmoril.esm');
  fc := ReqFile('ForgottenCity.esp');
  skin := RecordByFormID(glen, $0400F5E1, True);
  targetRace := RecordByFormID(glen, $0400F5DD, True);
  arma := RecordByFormID(glen, $0400F5DF, True);
  mato := RecordByFormID(glen, $0400C8CD, True);
  sndr := RecordByFormID(fc, $010E2673, True);
  response := RecordByFormID(fc, $010C38B4, True);
  RequireWinner(skin, 'Glenmoril.esm');
  RequireWinner(targetRace, 'Glenmoril.esm');
  RequireWinner(arma, 'Glenmoril.esm');
  RequireWinner(mato, 'Glenmoril.esm');
  RequireWinner(sndr, 'ForgottenCity.esp');
  RequireWinner(response, 'ForgottenCity.esp');
  Need(ElementCount(Req(skin, 'MODL')) = 1, 'Glen armor has an unexpected additional armature');
  Need(SameRecord(LinksTo(ElementByIndex(Req(skin, 'MODL'), 0)), arma), 'Glen armor-to-arma link changed');
  Need(SameText(GetEditValue(Req(arma, 'MOD3\MOD3 - Model FileName')), 'actors\WitchHunt\EtonNir\DwarvenSoldier.nif'),
    'Glen female model declaration changed');
  Need((Signature(mato) = 'MATO') and (Signature(sndr) = 'SNDR') and (Signature(response) = 'INFO'),
    'Resource consumer record signatures changed');
  AddMessage('OPAQUE_MISSING_DECLARATIONS_REQUIRE_RAW_GUARD|MATO_MODL|SNDR_ANAM|INFO_TRDT');
  flags := GetNativeValue(Req(targetRace, 'DATA\Flags'));
  Need((flags and 1) = 0, 'Glen race is player-bound; female model gap requires a real repair');
  NativePhase('source_and_response_guards_passed');
  seen := TStringList.Create;
  raceConsumers := 0;
  npcConsumers := 0;
  femaleConsumers := 0;
  try
    for fileIndex := 0 to FileCount - 1 do begin
      f := FileByIndex(fileIndex);
      g := GroupBySignature(f, 'RACE');
      for i := 0 to ElementCount(g) - 1 do begin
        r := ElementByIndex(g, i);
        linked := LinksTo(ElementByPath(r, 'WNAM - Skin'));
        if SameRecord(linked, skin) then begin
          Need(SameRecord(r, targetRace), 'An additional race consumes Glen skin');
          Inc(raceConsumers);
        end;
      end;
      g := GroupBySignature(f, 'NPC_');
      for i := 0 to ElementCount(g) - 1 do begin
        r := ElementByIndex(g, i);
        npc := WinningOverride(MasterOrSelf(r));
        key := LowerCase(GetFileName(GetFile(npc))) + '|' + IntToHex(GetLoadOrderFormID(npc), 8);
        if seen.IndexOf(key) < 0 then begin
          seen.Add(key);
          if RaceForNPC(npc, targetRace) then begin
            Inc(npcConsumers);
            flags := GetNativeValue(Req(npc, 'ACBS\Flags'));
            if (flags and 1) <> 0 then begin
              Inc(femaleConsumers);
              AddMessage('GLEN_FEMALE_CONSUMER_REQUIRES_REPAIR|' + key);
            end;
          end;
        end;
      end;
    end;
  finally seen.Free; end;
  Need(raceConsumers = 1, 'Unexpected number of Glen skin race consumers');
  Need(npcConsumers = 8, 'Unexpected number of Glen race NPC consumers');
  Need(femaleConsumers = 0, 'Female Glen NPC requires the missing female model');
  NativePhase('typed_consumers_passed');
  AddMessage('RESOURCE_STATIC_CONSUMERS_PASS|RACE=1|MALE_NPC=8|FEMALE_NPC=0|MATO_STUB=1|FC_MOTIF_SOURCE_LIMIT=1');
  NativePhase('RESOURCE_STATIC_CONSUMERS_PASS');
  Result := 0;
end;

end.
