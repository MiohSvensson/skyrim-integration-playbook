unit UserScript;
const
  PROGRESS_FILE = '';
  SOURCE_FILE = 'E:\stock\Skyrim collection\Database\integration\research\synthesis_final\DatabaseSynthesisInputModelsV2.source.txt';

procedure Need(ok: Boolean; messageText: string);
begin
  if not ok then raise Exception.Create('BOUNDED_INPUT_MODEL_STOP: ' + messageText);
end;

procedure NativePhase(value: string);
var rows: TStringList;
begin
  rows := TStringList.Create;
  try rows.Add(value); rows.SaveToFile(PROGRESS_FILE);
  finally rows.Free; end;
end;

function Initialize: Integer;
var f, r, model, filename: IInterface;
    rows, parts: TStringList;
    i, j: Integer;
    modelPath, tag: string;
begin
  Result := 1;
  Need(not Assigned(FileByName('Synthesis - Patch.esp')), 'A Synthesis output is active in the input profile');
  AddMessage('SYNTHESIS_INPUT_NO_SYNTHESIS');
  rows := TStringList.Create;
  parts := TStringList.Create;
  try
    rows.LoadFromFile(SOURCE_FILE);
    Need(rows.Count = 275, 'Input source count differs from the reviewed delta');
    parts.Delimiter := ':';
    parts.StrictDelimiter := True;
    for i := 0 to rows.Count - 1 do begin
      parts.DelimitedText := rows[i];
      Need(parts.Count = 2, 'Invalid source key: ' + rows[i]);
      f := FileByName(parts[0]);
      Need(Assigned(f), 'Missing input master: ' + parts[0]);
      r := RecordByFormID(f, (MasterCount(f) shl 24) or StrToInt('$' + parts[1]), False);
      Need(Assigned(r), 'Missing source ARMA: ' + rows[i]);
      r := WinningOverride(r);
      Need(Assigned(r) and (Signature(r) = 'ARMA'), 'Invalid winning input ARMA: ' + rows[i]);
      for j := 0 to 3 do begin
        tag := 'MOD' + IntToStr(j + 2);
        model := ElementBySignature(r, tag);
        modelPath := '';
        if Assigned(model) then begin
          filename := ElementByIndex(model, 0);
          if Assigned(filename) then modelPath := GetEditValue(filename);
        end;
        AddMessage('SYNTHESIS_INPUT_MODEL|' + rows[i] + '|' + tag + '|' + modelPath);
      end;
    end;
    AddMessage('SYNTHESIS_INPUT_MODELS_COMPLETE');
    NativePhase('SYNTHESIS_INPUT_MODELS_COMPLETE');
    Result := 0;
  finally
    parts.Free;
    rows.Free;
  end;
end;

end.
