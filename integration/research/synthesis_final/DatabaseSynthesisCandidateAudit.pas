unit UserScript;
// Read-only full native Check of the generated Synthesis candidate.
const
  VERIFY_ONLY = True;
  PATCH_NAME = 'Synthesis - Patch.esp';
  PROGRESS_FILE = '';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('BOUNDED_SYNTHESIS_STOP: ' + messageText);
end;

procedure NativePhase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try rows.Add(value); rows.SaveToFile(PROGRESS_FILE);
  finally rows.Free; end;
end;

function Initialize: Integer;
var patchFile, r: IInterface;
    i, checked, errors: Integer;
    messageText: string;
begin
  Result := 1;
  patchFile := FileByName(PATCH_NAME);
  Need(Assigned(patchFile), 'Synthesis candidate is not loaded');
  Need(not GetIsESL(patchFile), 'Synthesis group must remain a full plugin');
  Need(MasterCount(patchFile) <= 253, 'Synthesis master budget exceeded');
  errors := 0;
  checked := 0;
  for i := 0 to RecordCount(patchFile) - 1 do begin
    r := RecordByIndex(patchFile, i);
    messageText := Check(r);
    if messageText <> '' then begin
      Inc(errors);
      AddMessage('SYNTHESIS_DIAGNOSTIC|' + Signature(r) + '|' + IntToHex(GetLoadOrderFormID(r), 8) + '|' + messageText);
      if errors >= 20 then Break;
    end;
    Inc(checked);
  end;
  AddMessage('SYNTHESIS_NATIVE_CHECKED|' + IntToStr(checked) + '|ERRORS=' + IntToStr(errors));
  Need(errors = 0, 'Unexpected generated Synthesis diagnostics');
  AddMessage('SYNTHESIS_NATIVE_CHECK_PASS');
  NativePhase('SYNTHESIS_NATIVE_CHECK_PASS');
  Result := 0;
end;

end.
