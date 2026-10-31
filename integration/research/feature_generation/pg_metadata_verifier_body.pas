// Read-only metadata verifier. Appended after exact common canonical/native helpers.
var
  ExpectedSources,AllowedFiles,AllowedMeshes,OutputNames,Checked,Audit: TStringList;
  CheckedRecords,CheckedTXST,ChangedModels,ChangedAlternates: Integer;

function ModelKey(s: string): string;
begin
  s:=LowerCase(StringReplace(s,'/','\',[rfReplaceAll]));
  if Copy(s,1,7)<>'meshes\' then s:='meshes\'+s;
  Result:=s;
end;

function Child(e: IInterface; childName: string): IInterface;
var i: Integer; x: IInterface;
begin
  Result:=nil;
  for i:=0 to ElementCount(e)-1 do begin
    x:=ElementByIndex(e,i);
    if BaseName(x)=childName then begin
      Need(not Assigned(Result),'Duplicate exact child '+childName+ComparisonContext(x,Result));Result:=x;
    end;
  end;
end;

function IsOutput(fileName: string): Boolean;
begin Result:=OutputNames.IndexOf(LowerCase(fileName))>=0;end;

function SourceWinner(r: IInterface): IInterface;
var i: Integer; x,m: IInterface;
begin
  m:=MasterOrSelf(r);Result:=nil;
  if not IsOutput(GetFileName(GetFile(m))) then Result:=m;
  for i:=0 to OverrideCount(m)-1 do begin
    x:=OverrideByIndex(m,i);
    if not IsOutput(GetFileName(GetFile(x))) then Result:=x;
  end;
  Need(Assigned(Result),'No non-output source winner '+CanonicalRecordText(r));
end;

procedure Header(a,b: IInterface);
var x,y,ah,bh: IInterface; i: Integer; n: string; va,vb: Integer;
begin
  NeedCompared(Signature(a)=Signature(b),'Header signature changed',a,b);
  NeedCompared(SameRecord(a,b),'Canonical record identity changed',a,b);
  NeedCompared(GetFormVersion(a)=GetFormVersion(b),'Form Version changed',a,b);
  ah:=Req(a,'Record Header');bh:=Req(b,'Record Header');
  NeedCompared(ElementCount(ah)=ElementCount(bh),'Unknown header shape',ah,bh);
  for i:=0 to ElementCount(bh)-1 do begin
    y:=ElementByIndex(bh,i);n:=BaseName(y);x:=Child(ah,n);
    NeedCompared(Assigned(x),'Missing header member '+n,x,y);
    if n='Record Flags' then begin
      va:=GetNativeValue(x);vb:=GetNativeValue(y);
      // Compressed is a storage choice; every other flag remains exact.
      NeedCompared((va and $FFFBFFFF)=(vb and $FFFBFFFF),'Gameplay record flags changed',x,y);
      if va<>vb then Audit.Add('STORAGE_COMPRESSION'+#9+CanonicalRecordText(a)+#9+IntToHex(vb,8)+#9+IntToHex(va,8));
    end else if n='Version Control Info 1' then begin
      if GetFormVCS1(a)<>GetFormVCS1(b) then Audit.Add('AUTHOR_VCS1'+#9+CanonicalRecordText(a)+#9+IntToHex(GetFormVCS1(b),8)+#9+IntToHex(GetFormVCS1(a),8));
    end else if n='Version Control Info 2' then begin
      if GetFormVCS2(a)<>GetFormVCS2(b) then Audit.Add('AUTHOR_VCS2'+#9+CanonicalRecordText(a)+#9+IntToHex(GetFormVCS2(b),4)+#9+IntToHex(GetFormVCS2(a),4));
    end else if (n<>'Data Size') and (n<>'FormID') then AssertTree(x,y,'Header/'+n);
  end;
end;

function ModelContainer(r,e: IInterface): Boolean;
var n,s: string;
begin
  n:=BaseName(e);s:=Signature(r);Result:=False;
  if n='Model' then Result:=True;
  if s='ARMO' then Result:=(n='Model') or (n='Male World Model') or (n='Female World Model');
  if s='ARMA' then Result:=(n='Male Biped Model') or (n='Female Biped Model') or (n='Male 1st Person') or (n='Female 1st Person');
  if not Assigned(Child(e,'Model FileName')) then Result:=False;
end;

function NativeModelUse(r,e: IInterface): string;
var n,s: string;
begin
  n:=BaseName(e);s:=Signature(r);Result:='';
  if s='ARMO' then begin
    if n='Male World Model' then Result:='MALE';
    if n='Female World Model' then Result:='FEMALE';
  end else if s='ARMA' then begin
    if n='Male Biped Model' then Result:='MALE';
    if n='Female Biped Model' then Result:='FEMALE';
    if n='Male 1st Person' then Result:='1STMALE';
    if n='Female 1st Person' then Result:='1STFEMALE';
  end else if n='Model' then Result:='MODL';
  Need(Result<>'','Unmapped author PG model-use container '+s+'/'+n+ComparisonContext(e,r));
end;

procedure ModelInfo(a,b: IInterface; labelText: string);
var i: Integer;x,y,alts: IInterface;n,path: string;
begin
  Audit.Add('MODEL_BIND'+#9+CanonicalRecordText(a)+#9+NativeModelUse(ContainingMainRecord(a),a)+#9+ModelKey(GetEditValue(Req(b,'Model FileName')))+#9+ModelKey(GetEditValue(Req(a,'Model FileName')))+#9+labelText);
  // Exact 4.1.5f wbGenericModel and wbTexturedModel: only these children.
  for i:=0 to ElementCount(b)-1 do begin
    y:=ElementByIndex(b,i);n:=BaseName(y);x:=Child(a,n);
    if n='Model FileName' then begin
      NeedCompared(Assigned(x),'Missing model filename',x,y);
      if GetEditValue(x)<>GetEditValue(y) then begin
        path:=ModelKey(GetEditValue(x));
        Need(AllowedMeshes.IndexOf(path)>=0,'Changed model is not a real generated NIF: '+path+ComparisonContext(x,y));
        Inc(ChangedModels);Audit.Add('MODEL'+#9+CanonicalRecordText(a)+#9+labelText+#9+GetEditValue(y)+#9+GetEditValue(x));
      end;
    end else if n='Alternate Textures' then begin
      alts:=x;
      // Native author PG may remove existing alternatives or remap indices/TXST.
      // No arbitrary new 3D name is allowed; exact output NIF/shape mapping is
      // additionally verified by the post-output NIF reviewer.
      if Assigned(alts) then begin
        Need(ElementCount(alts)<=ElementCount(y),'Added alternate texture entries '+labelText);
      end;
    end else if n='Model Information' then begin
      // wbModelInfo is cpIgnore derived cache. A serializer may omit it;
      // if retained, every typed field/byte must remain exact.
      if Assigned(x) then AssertTree(x,y,labelText+'/Model Information');
    end else Need(False,'Unknown model container member '+n+ComparisonContext(x,y));
  end;
  for i:=0 to ElementCount(a)-1 do begin
    x:=ElementByIndex(a,i);n:=BaseName(x);
    Need((n='Model FileName') or (n='Alternate Textures') or (n='Model Information'),'Unexpected model member '+n);
    Need(Assigned(Child(b,n)),'New model member outside author deep-copy surface '+n+ComparisonContext(x,b));
  end;
end;

procedure Alternates(a,b: IInterface; labelText: string);
var i,j,found: Integer;x,y,z,link: IInterface;n,originalName: string;
begin
  if not Assigned(a) then begin
    if Assigned(b) then begin Inc(ChangedAlternates);Audit.Add('ALTERNATES_REMOVED'+#9+CanonicalRecordText(b)+#9+labelText);end;
    Exit;
  end;
  Need(Assigned(b),'New alternate array is outside author modification surface '+labelText);
  Need(ElementCount(a)<=ElementCount(b),'Added alternate entries '+labelText);
  for i:=0 to ElementCount(a)-1 do begin
    x:=ElementByIndex(a,i);Need(ElementCount(x)=3,'Unknown alternate texture schema '+FullPath(x));
    originalName:=GetEditValue(Req(x,'3D Name'));found:=0;y:=nil;
    for j:=0 to ElementCount(b)-1 do begin
      z:=ElementByIndex(b,j);
      if GetEditValue(Req(z,'3D Name'))=originalName then begin Inc(found);y:=z;end;
    end;
    Need(found=1,'Ambiguous/new 3D Name '+originalName+' '+labelText);
    AssertTree(Req(x,'3D Name'),Req(y,'3D Name'),labelText+'/3D Name');
    Need(GetNativeValue(Req(x,'3D Index'))>=0,'Negative 3D Index '+FullPath(x));
    link:=LinksTo(Req(x,'New Texture'));
    Need(Assigned(link),'Unresolved alternate TXST '+FullPath(x));
    Need(Signature(link)='TXST','Alternate texture does not resolve TXST '+FullPath(x));
    if not SameRecord(link,LinksTo(Req(y,'New Texture'))) then begin
      Need(LowerCase(GetFileName(GetFile(MasterOrSelf(link))))='dbpatcher.esp','Changed alternate texture is not a new DB owner TXST '+FullPath(x));
      Inc(ChangedAlternates);
    end;
    Audit.Add('ALT'+#9+CanonicalRecordText(a)+#9+labelText+#9+originalName+#9+GetEditValue(Req(y,'3D Index'))+#9+GetEditValue(Req(x,'3D Index'))+#9+CanonicalRecordText(link));
  end;
end;

procedure VerifyOverride(r: IInterface);
var src,x,y: IInterface;i: Integer;n,k: string;
begin
  k:=CanonicalRecordText(r);Need(Checked.IndexOf(k)<0,'Duplicate override across DB output splits '+k);Checked.Add(k);
  Need(Pos('|'+Signature(r)+'|','|ACTI|ADDN|AMMO|ANIO|ARMO|ARMA|ARTO|BPTD|BOOK|CAMS|CLMT|CONT|DOOR|EXPL|FLOR|FURN|GRAS|HAZD|HDPT|IDLM|IPCT|ALCH|INGR|KEYM|LVLN|LIGH|MATO|MISC|MSTT|PROJ|SCRL|SLGM|STAT|TACT|TREE|WEAP|')>0,'Signature outside pinned PG model enumeration '+Signature(r));
  src:=SourceWinner(r);
  Need(LowerCase(GetFileName(GetFile(src)))=ExpectedSources.Values[k],'Final source winner drift '+k+' actual='+GetFileName(GetFile(src))+' expected='+ExpectedSources.Values[k]);
  Header(r,src);
  for i:=0 to ElementCount(src)-1 do begin
    y:=ElementByIndex(src,i);n:=BaseName(y);
    if n<>'Record Header' then begin
      x:=Child(r,n);NeedCompared(Assigned(x),'Missing non-header payload '+n,x,y);
      if ModelContainer(src,y) then begin
        ModelInfo(x,y,k+'/'+n);Alternates(Child(x,'Alternate Textures'),Child(y,'Alternate Textures'),k+'/'+n);
      end else AssertTree(x,y,k+'/'+n);
    end;
  end;
  for i:=0 to ElementCount(r)-1 do begin
    x:=ElementByIndex(r,i);if BaseName(x)<>'Record Header' then Need(Assigned(Child(src,BaseName(x))),'Unexpected payload '+FullPath(x));
  end;
  Inc(CheckedRecords);Audit.Add('RECORD_PASS'+#9+k+#9+GetFileName(GetFile(src))+#9+GetFileName(GetFile(r)));
end;

procedure VerifyTXST(r: IInterface);
var i: Integer;x: IInterface;n,s: string;
begin
  Need(Signature(r)='TXST','DBPatcher owner contains a non-TXST record');
  Need(LowerCase(GetFileName(GetFile(MasterOrSelf(r))))='dbpatcher.esp','DBPatcher must contain only its own records');
  Need(not GetIsDeleted(r),'Deleted new TXST');
  Need(Copy(EditorID(r),1,3)='DB_','Unexpected new TXST namespace '+EditorID(r));
  for i:=0 to ElementCount(r)-1 do begin
    x:=ElementByIndex(r,i);n:=Signature(x);
    if (BaseName(x)<>'Record Header') then begin
      Need((n='EDID') or (n='OBND') or (n='TX00') or (n='TX01') or (n='TX02') or (n='TX03') or (n='TX04') or (n='TX05') or (n='TX06') or (n='TX07') or (n='DNAM'),'Unexpected new TXST field '+FullPath(x));
      if Copy(n,1,2)='TX' then begin
        s:=GetEditValue(x);if s<>'' then Audit.Add('TXST_TEXTURE'+#9+CanonicalRecordText(r)+#9+n+#9+s);
      end;
    end;
  end;
  Inc(CheckedTXST);Audit.Add('TXST_PASS'+#9+CanonicalRecordText(r));
end;

procedure Walk(e: IInterface; owner: Boolean);
var i: Integer;x: IInterface;
begin
  if ElementType(e)=etMainRecord then begin
    if Signature(e)='TES4' then Exit;
    if owner then VerifyTXST(e) else VerifyOverride(e);Exit;
  end;
  for i:=0 to ElementCount(e)-1 do begin x:=ElementByIndex(e,i);Walk(x,owner);end;
end;

function Initialize: Integer;
var i: Integer;f: IInterface;name: string;
begin
  Result:=1;ExpectedSources:=TStringList.Create;AllowedFiles:=TStringList.Create;AllowedMeshes:=TStringList.Create;
  OutputNames:=TStringList.Create;Checked:=TStringList.Create;Audit:=TStringList.Create;
  ExpectedSources.LoadFromFile(EXPECTED_SOURCE_FILE);AllowedFiles.LoadFromFile(ALLOWED_FILES_FILE);AllowedMeshes.LoadFromFile(ALLOWED_MESH_FILE);OutputNames.LoadFromFile(OUTPUT_NAMES_FILE);
  Need(FileCount=AllowedFiles.Count+OutputNames.Count,'Complete frozen source context plus all outputs must be loaded');
  for i:=0 to AllowedFiles.Count-1 do begin f:=ReqFile(AllowedFiles[i]);end;
  for i:=0 to FileCount-1 do begin
    f:=FileByIndex(i);name:=LowerCase(GetFileName(f));
    Need((AllowedFiles.IndexOf(name)>=0) or IsOutput(name),'Unfrozen loaded file '+name);
  end;
  for i:=0 to OutputNames.Count-1 do begin
    name:=OutputNames[i];f:=ReqFile(name);Walk(f,name='dbpatcher.esp');
  end;
  Need(CheckedRecords=EXPECTED_OVERRIDE_COUNT,'Override record count differs from pinned output inventory');
  Need(CheckedTXST=EXPECTED_TXST_COUNT,'New TXST count differs from pinned output inventory');
  Audit.Add('PASS_METADATA_ONLY'+#9+IntToStr(CheckedRecords)+#9+IntToStr(CheckedTXST)+#9+IntToStr(ChangedModels)+#9+IntToStr(ChangedAlternates));
  Audit.SaveToFile(AUDIT_FILE);AddMessage('PG_TYPED_METADATA_PASS overrides='+IntToStr(CheckedRecords)+' TXST='+IntToStr(CheckedTXST));
  Result:=0;
end;

function Finalize: Integer;
begin
  if Assigned(ExpectedSources) then ExpectedSources.Free;if Assigned(AllowedFiles) then AllowedFiles.Free;
  if Assigned(AllowedMeshes) then AllowedMeshes.Free;if Assigned(OutputNames) then OutputNames.Free;
  if Assigned(Checked) then Checked.Free;if Assigned(Audit) then Audit.Free;Result:=0;
end;
end.
