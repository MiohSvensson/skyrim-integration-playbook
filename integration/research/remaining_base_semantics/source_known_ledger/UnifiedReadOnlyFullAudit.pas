unit UnifiedReadOnlyFullAudit;

// Read-only full selection audit. No plugin creation, assignment, or saving API.
// Select every active file. The parser rejects any missing file/record coverage.
// FULL_AUDIT_COMPLETED means Finalize ran; it is not a zero-diagnostic claim.
var
  files, prefixes: TStringList;
  counts, bad, fields, expected: array[0..8191] of integer;
  total, diagnostics, exceptions: integer;

function Clean(s: string): string;
begin
  Result := StringReplace(s, #9, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #13, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #10, ' ', [rfReplaceAll]);
end;

function IsPlugin(fn: string): boolean;
var ext: string;
begin
  ext := ExtractFileExt(fn);
  Result := SameText(ext, '.esm') or SameText(ext, '.esp') or SameText(ext, '.esl');
end;

function IDPrefix(hex: string): string;
begin
  if Copy(hex, 1, 2) = 'FE' then Result := Copy(hex, 1, 5)
  else Result := Copy(hex, 1, 2);
end;

function ObjectID(hex: string): string;
begin
  if Copy(hex, 1, 2) = 'FE' then Result := '000' + Copy(hex, 6, 3)
  else Result := Copy(hex, 3, 6);
end;

function OwnerFor(hex: string): string;
var idx: integer;
begin
  idx := prefixes.IndexOf(IDPrefix(hex));
  if idx < 0 then Result := 'UNMAPPED:' + hex else Result := files[idx];
end;

procedure AuditException(fn, rec, owner, obj, sig, p, operation: string);
begin
  exceptions := exceptions + 1;
  AddMessage('UNIFIED_EXCEPTION' + #9 + Clean(fn) + #9 + Clean(rec) + #9 +
    Clean(p) + #9 + Clean(operation) + #9 + Clean(owner) + #9 + obj + #9 + sig);
end;

procedure ElementException(e: IInterface; fn, rec, owner, obj, sig, operation: string);
var p: string;
begin
  p := '<Path unavailable>';
  try p := Clean(Path(e)); except end;
  AuditException(fn, rec, owner, obj, sig, p, operation);
end;

function CheckTree(e: IInterface; fn, rec, owner, obj, sig: string): integer;
var i, n: integer; s, p, fp: string; child: IInterface;
begin
  Result := 0;
  try
    s := Check(e);
    if s <> '' then begin
      p := '<Path unavailable>'; fp := '<FullPath unavailable>';
      try p := Clean(Path(e));
      except AuditException(fn, rec, owner, obj, sig, p, 'Path'); end;
      try fp := Clean(FullPath(e));
      except AuditException(fn, rec, owner, obj, sig, p, 'FullPath'); end;
      Result := Result + 1; diagnostics := diagnostics + 1;
      AddMessage('UNIFIED_DETAIL' + #9 + Clean(fn) + #9 + Clean(rec) + #9 +
        p + #9 + Clean(s) + #9 + Clean(owner) + #9 + obj + #9 + sig + #9 + fp);
    end;
  except ElementException(e, fn, rec, owner, obj, sig, 'Check'); end;
  n := 0;
  try n := ElementCount(e);
  except ElementException(e, fn, rec, owner, obj, sig, 'ElementCount'); end;
  for i := 0 to n - 1 do begin
    child := nil;
    try child := ElementByIndex(e, i);
    except ElementException(e, fn, rec, owner, obj, sig, 'ElementByIndex ' + IntToStr(i)); end;
    if Assigned(child) then
      Result := Result + CheckTree(child, fn, rec, owner, obj, sig);
  end;
end;

function Initialize: integer;
var i, idx: integer; f: IInterface; fn, hex: string;
begin
  Result := 0; total := 0; diagnostics := 0; exceptions := 0;
  files := TStringList.Create; prefixes := TStringList.Create;
  files.CaseSensitive := False; prefixes.CaseSensitive := False;
  AddMessage('UNIFIED_BEGIN' + #9 + '2' + #9 + IntToStr(FileCount));
  for i := 0 to FileCount - 1 do begin
    f := FileByIndex(i); fn := GetFileName(f);
    if IsPlugin(fn) then begin
      idx := files.Count;
      if idx >= 8192 then raise Exception.Create('FULL_AUDIT_STOP: file array capacity exceeded');
      files.Add(fn);
      hex := IntToHex(FileFormIDtoLoadOrderFormID(f, (MasterCount(f) shl 24) or $800), 8);
      if prefixes.IndexOf(IDPrefix(hex)) >= 0 then
        raise Exception.Create('FULL_AUDIT_STOP: duplicate runtime file prefix ' + hex);
      prefixes.Add(IDPrefix(hex));
      counts[idx] := 0; bad[idx] := 0; fields[idx] := 0;
      // Exact 4.1.5f AddMainRecord indexes only non-null FormIDs, so the
      // TES4 header is excluded from File.RecordCount but included by Process.
      expected[idx] := RecordCount(f) + 1;
      AddMessage('UNIFIED_FILE' + #9 + Clean(fn) + #9 + hex + #9 + IntToStr(expected[idx]));
    end else AddMessage('UNIFIED_IGNORED' + #9 + Clean(fn));
  end;
  AddMessage('UNIFIED_SCOPE' + #9 + IntToStr(files.Count));
end;

function Process(e: IInterface): integer;
var idx, n, before: integer; fn, rec, hex, owner, obj, sig: string;
begin
  Result := 0; fn := GetFileName(GetFile(e)); idx := files.IndexOf(fn);
  if idx < 0 then Exit;
  total := total + 1; counts[idx] := counts[idx] + 1;
  rec := '<record name unavailable>'; owner := '<owner unavailable>';
  obj := '000000'; sig := '????'; before := exceptions;
  try
    rec := Clean(Name(e)); sig := Signature(e);
    if sig = 'TES4' then begin owner := fn; obj := '000000'; end
    else begin
      hex := IntToHex(GetLoadOrderFormID(e), 8);
      owner := OwnerFor(hex); obj := ObjectID(hex);
    end;
    n := CheckTree(e, fn, rec, owner, obj, sig);
    fields[idx] := fields[idx] + n;
    if (n > 0) or (before <> exceptions) then bad[idx] := bad[idx] + 1;
  except
    bad[idx] := bad[idx] + 1;
    AuditException(fn, rec, owner, obj, sig, '<record>', 'Process record');
  end;
end;

function Finalize: integer;
var i: integer;
begin
  Result := 0;
  for i := 0 to files.Count - 1 do
    AddMessage('UNIFIED_PLUGIN' + #9 + Clean(files[i]) + #9 + IntToStr(counts[i]) + #9 +
      IntToStr(bad[i]) + #9 + IntToStr(fields[i]) + #9 + IntToStr(expected[i]));
  AddMessage('UNIFIED_COMPLETE' + #9 + IntToStr(total) + #9 + IntToStr(exceptions) + #9 +
    IntToStr(diagnostics) + #9 + IntToStr(files.Count));
  AddMessage('FULL_AUDIT_COMPLETED' + #9 + '2' + #9 + IntToStr(total) + #9 +
    IntToStr(diagnostics) + #9 + IntToStr(exceptions));
  files.Free; prefixes.Free;
end;
end.
