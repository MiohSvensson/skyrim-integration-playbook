unit BoundedQuestConsumerAudit;
var totalFiles, builtFiles, targetCount, failures: integer;
    resourceSeen: TStringList;

function Clean(s: string): string;
begin
  Result := StringReplace(s, #9, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #13, ' ', [rfReplaceAll]);
  Result := StringReplace(Result, #10, ' ', [rfReplaceAll]);
end;

procedure InspectNode(e: IInterface; depth: integer);
var m,w,r: IInterface; i,n: integer; identity: string;
begin
  if not Assigned(e) then Exit;
  m:=MasterOrSelf(e); w:=WinningOverride(m);
  identity:=LowerCase(GetFileName(GetFile(m)))+'|'+IntToHex(FixedFormID(m) and $FFFFFF,6);
  if resourceSeen.IndexOf(identity)>=0 then Exit;
  resourceSeen.Add(identity); n:=ReferencedByCount(m);
  AddMessage('RSRC_NODE'+#9+IntToStr(depth)+#9+identity+#9+Signature(m)+#9+
    GetFileName(GetFile(w))+#9+Clean(GetElementEditValues(w,'EDID'))+#9+IntToStr(n)+#9+
    Clean(GetElementEditValues(w,'ACBS\Flags'))+#9+Clean(GetElementEditValues(w,'ACBS\Template Flags'))+#9+
    Clean(GetElementEditValues(w,'TPLT'))+#9+Clean(GetElementEditValues(w,'RNAM'))+#9+Clean(GetElementEditValues(w,'WNAM')));
  for i:=0 to n-1 do begin
    r:=ReferencedByIndex(m,i);
    AddMessage('RSRC_EDGE'+#9+identity+#9+LowerCase(GetFileName(GetFile(MasterOrSelf(r))))+'|'+
      IntToHex(FixedFormID(MasterOrSelf(r)) and $FFFFFF,6)+#9+Signature(r)+#9+GetFileName(GetFile(r))+#9+
      Clean(Name(r)));
    if depth<4 then InspectNode(r,depth+1)
    else AddMessage('RSRC_DEPTH_BOUND'+#9+identity);
  end;
end;

procedure InspectResource(fn: string; id: cardinal; sig: string);
var f,e: IInterface;
begin
  f:=FileByName(fn);
  if not Assigned(f) then begin AddMessage('RSRC_ERROR'+#9+'missing_plugin'+#9+fn); Exit; end;
  e:=RecordByFormID(f,(MasterCount(f) shl 24) or id,False);
  if not Assigned(e) then begin AddMessage('RSRC_ERROR'+#9+'missing_record'+#9+fn+#9+IntToHex(id,6)); Exit; end;
  if Signature(e)<>sig then begin AddMessage('RSRC_ERROR'+#9+'wrong_signature'+#9+fn+#9+IntToHex(id,6)); Exit; end;
  AddMessage('RSRC_TARGET'+#9+fn+#9+IntToHex(id,6)+#9+sig);
  resourceSeen.Clear;
  InspectNode(e,0);
end;

procedure Target(fn: string; id: cardinal; sig: string);
var f,e,m,w,r: IInterface; i,n: integer;
begin
  f := FileByName(fn);
  if not Assigned(f) then begin
    Inc(failures); AddMessage('QEX_ERROR'+#9+'missing_plugin'+#9+fn); Exit;
  end;
  e := RecordByFormID(f, (MasterCount(f) shl 24) or id, False);
  if not Assigned(e) then begin
    Inc(failures); AddMessage('QEX_ERROR'+#9+'missing_record'+#9+fn+#9+IntToHex(id,6)); Exit;
  end;
  if Signature(e) <> sig then begin
    Inc(failures); AddMessage('QEX_ERROR'+#9+'wrong_signature'+#9+fn+#9+IntToHex(id,6)); Exit;
  end;
  m := MasterOrSelf(e); w := WinningOverride(m); n := ReferencedByCount(m);
  Inc(targetCount);
  AddMessage('QEX_TARGET'+#9+fn+#9+IntToHex(id,6)+#9+sig+#9+IntToStr(n)+#9+GetFileName(GetFile(w)));
  for i := 0 to n-1 do begin
    r := ReferencedByIndex(m,i);
    AddMessage('QEX_REF'+#9+fn+#9+IntToHex(id,6)+#9+GetFileName(GetFile(MasterOrSelf(r)))+#9+
      Signature(r)+#9+IntToHex(FixedFormID(MasterOrSelf(r)) and $FFFFFF,6)+#9+
      GetFileName(GetFile(r))+#9+Clean(Name(r)));
  end;
  if n <> 0 then Inc(failures);
end;

function Initialize: integer;
var i: integer; f: IInterface; fn: string;
begin
  failures:=0; builtFiles:=0; targetCount:=0; totalFiles:=0;
  resourceSeen:=TStringList.Create; resourceSeen.Sorted:=True; resourceSeen.CaseSensitive:=False;
  AddMessage('QEX_BEGIN'+#9+IntToStr(FileCount));
  for i:=0 to FileCount-1 do begin
    f:=FileByIndex(i); fn:=GetFileName(f);
    if Pos('.exe', LowerCase(fn))=0 then begin
      Inc(totalFiles);
      AddMessage('QEX_FILE'+#9+fn+#9+IntToStr(RecordCount(f)));
    end;
  end;
  for i:=0 to FileCount-1 do begin
    f:=FileByIndex(i); fn:=GetFileName(f);
    if Pos('.exe', LowerCase(fn))=0 then begin
      try
        BuildRef(f); Inc(builtFiles); AddMessage('QEX_BUILDREF'+#9+fn);
      except
        Inc(failures); AddMessage('QEX_ERROR'+#9+'buildref_exception'+#9+fn);
      end;
    end;
  end;
  Result:=0;
end;

function Process(e: IInterface): integer;
begin Result:=0; end;

function Finalize: integer;
begin
  Target('BenDoonSSE.esp', $04A1A3, 'PACK');
  Target('[longshou]UF6.esp', $000801, 'FURN');
  Target('[longshou]UF6.esp', $000802, 'FURN');
  Target('[longshou]UF6.esp', $000803, 'FURN');
  Target('[longshou]UF6.esp', $000804, 'FURN');
  Target('[longshou]UF6.esp', $000805, 'FURN');
  // Non-gating research appendix. These three new gaps are not exceptions.
  // Their typed references may legitimately be nonzero; inspect source assets
  // and actual NPC/template/response consumers before any disposition.
  InspectResource('Glenmoril.esm', $00F5DF, 'ARMA');
  InspectResource('Glenmoril.esm', $00C8CD, 'MATO');
  InspectResource('ForgottenCity.esp', $0E2673, 'SNDR');
  AddMessage('RSRC_APPENDIX_COMPLETE'); resourceSeen.Free;
  if (targetCount<>6) or (builtFiles<>totalFiles) then Inc(failures);
  AddMessage('QEX_COMPLETE'+#9+IntToStr(totalFiles)+#9+IntToStr(builtFiles)+#9+IntToStr(targetCount)+#9+IntToStr(failures));
  if failures=0 then AddMessage('QEX_PASS') else AddMessage('QEX_FAIL');
  Result:=0;
end;
end.
