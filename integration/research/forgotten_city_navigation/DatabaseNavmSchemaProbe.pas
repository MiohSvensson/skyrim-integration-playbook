unit UserScript;

procedure Dump(e: IInterface; depth: Integer);
var i, n: Integer;
begin
  if not Assigned(e) then begin AddMessage('NAVM_SCHEMA_MISSING'); Exit; end;
  AddMessage('NAVM_SCHEMA|' + IntToStr(depth) + '|' + Name(e) + '|' + BaseName(e) +
    '|elements=' + IntToStr(ElementCount(e)) + '|definition=' + IntToStr(Ord(DefType(e))) +
    '|element=' + IntToStr(Ord(ElementType(e))));
  if depth >= 2 then Exit;
  n := ElementCount(e); if n > 12 then n := 12;
  for i := 0 to n - 1 do Dump(ElementByIndex(e, i), depth + 1);
end;

function Initialize: Integer;
var f, r, a: IInterface;
begin
  Result := 1;
  f := FileByName('Skyrim.esm');
  r := RecordByFormID(f, $00108AB4, False);
  Dump(ElementByPath(r, 'NVNM'), 0);
  a := ElementByPath(r, 'NVNM\Triangles');
  if Assigned(a) then begin
    AddMessage('NAVM_TRIANGLES_COUNT|' + IntToStr(ElementCount(a)));
    Dump(ElementByIndex(a, 50), 0);
  end;
  AddMessage('NAVM_SCHEMA_PROBE_PASS');
  Result := 0;
end;
end.
