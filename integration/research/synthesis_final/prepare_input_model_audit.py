"""Generate a bounded native capture of winning pre-Synthesis ARMA model paths."""
import argparse
import hashlib
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arma-delta', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    delta_path = Path(args.arma_delta).resolve(strict=True)
    delta = json.loads(delta_path.read_text('utf-8'))
    assert delta['status'] == 'ARMA_DELTA_READY_FOR_SCOPED_RUNTIME_AUDIT'
    keys = sorted(set(delta['affected_source_keys']))
    rows = []
    for key in keys:
        plugin, object_id = key.rsplit(':', 1)
        rows.append((key, plugin.replace("'", "''"), int(object_id, 16)))
    text = """unit UserScript;
const
  PROGRESS_FILE = '';
  SOURCE_FILE = '%s';

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
    Need(rows.Count = %d, 'Input source count differs from the reviewed delta');
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
"""
    output = Path(args.output).resolve()
    if not output.is_relative_to(HERE):
        raise ValueError('Generated script must stay in synthesis_final')
    source_path = output.with_suffix('.source.txt')
    source_text = '\n'.join(row[0] for row in rows) + '\n'
    with source_path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(source_text)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(text % (str(source_path).replace("'", "''"), len(rows)))
    print(json.dumps({'status': 'INPUT_MODEL_AUDIT_SCRIPT_READY', 'source_records': len(rows),
                      'delta_sha256': hashlib.sha256(delta_path.read_bytes()).hexdigest(),
                      'source_file': str(source_path), 'script': str(output)}, indent=2))


if __name__ == '__main__':
    main()
