"""Generate standalone xEdit drafts; never executes xEdit or writes a plugin."""
import hashlib
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent
COMMON=OUT.parent/'navmesh_patch/DatabaseBoundedNavmeshDraft.pas'


def take(text,start,end):
    return text[text.index(start):text.index(end)]


BODY=r'''
function SharedID(i: Integer): Integer;
begin
  case i of
    0: Result := $10751B;
    1: Result := $107527;
    2: Result := $107528;
    3: Result := $107532;
    4: Result := $108AB4;
    5: Result := $108ABF;
    6: Result := $108BFA;
  else Need(False, 'Bad shared NAVM ordinal'); end;
end;

function IsSharedInfo(info: IInterface): Boolean;
var i: Integer; r: IInterface;
begin
  Result := False;
  r := LinksTo(Req(info, 'Navmesh'));
  Need(Assigned(r), 'Unresolved NVMI key');
  r := MasterOrSelf(r);
  if not SameText(GetFileName(GetFile(r)), 'Skyrim.esm') then Exit;
  for i := 0 to 6 do
    if (GetLoadOrderFormID(r) and $00FFFFFF) = SharedID(i) then Result := True;
end;

function EffectiveInfoBefore(naviMaster,navMaster: IInterface): IInterface;
var i: Integer; r,item: IInterface;
begin
  Result:=InfoFor(naviMaster,navMaster);
  for i:=0 to OverrideCount(naviMaster)-1 do begin
    r:=OverrideByIndex(naviMaster,i);
    if not SameText(GetFileName(GetFile(r)),PATCH_NAME) then begin
      item:=InfoFor(r,navMaster);
      if Assigned(item) then begin
        if not Assigned(Result) then Result:=item
        else if GetLoadOrder(GetFile(item))>GetLoadOrder(GetFile(Result)) then Result:=item;
      end;
    end;
  end;
  Need(Assigned(Result),'Effective prior NVMI absent');
end;

function EdgeName(side: Integer): string;
begin
  case side of
    0: Result := 'Edge 0-1';
    1: Result := 'Edge 1-2';
    2: Result := 'Edge 2-0';
  else Need(False, 'Bad triangle side'); end;
end;

function VertexName(side: Integer): string;
begin Result := 'Vertex ' + IntToStr(side); end;

function Triangle(r: IInterface; index: Integer): IInterface;
var a: IInterface;
begin
  a := Req(r, 'NVNM\Triangles');
  Need((index >= 0) and (index < ElementCount(a)), 'Triangle index outside record');
  Result := ElementByIndex(a, index);
  Need(ElementCount(Result) = 8, 'Normal 4.1.5f triangle fields required');
  Req(Result, 'Vertex 0');
  Req(Result, 'Flags');
end;

function EdgeFor(r, tri: IInterface; side: Integer): IInterface;
var index: Integer; a: IInterface;
begin
  index := GetNativeValue(Req(tri, EdgeName(side)));
  a := Req(r, 'NVNM\Edge Links');
  Need((index >= 0) and (index < ElementCount(a)), 'External link index outside Edge Links');
  Result := ElementByIndex(a, index);
end;

function LinkIs(edge, masterRecord: IInterface; triangleIndex: Integer): Boolean;
begin
  Result := SameRecord(LinksTo(Req(edge, 'Navmesh')), masterRecord) and
    (GetNativeValue(Req(edge, 'Triangle')) = triangleIndex);
end;

procedure AssertOtherNVNM(a,b: IInterface);
var ga,gb,x,y: IInterface; i: Integer; n: string;
begin
  ga := Req(a, 'NVNM'); gb := Req(b, 'NVNM');
  Need(ElementCount(ga) = ElementCount(gb), 'NVNM structure changed');
  for i := 0 to ElementCount(ga)-1 do begin
    x := ElementByIndex(ga,i); y := ElementByIndex(gb,i);
    n := BaseName(x); Need(n=BaseName(y), 'NVNM field order changed');
    if (n<>'Triangles') and (n<>'Edge Links') then AssertTree(x,y,'unchanged NVNM/'+n);
  end;
end;

procedure AssertAuthoredDelta(feature, vanilla, neighborMaster: IInterface);
var i,j,side,flagsA,flagsB: Integer; a,b: IInterface;
begin
  Need(ElementCount(Req(feature,'NVNM\Vertices'))=269, 'Feature vertex count changed');
  Need(ElementCount(Req(feature,'NVNM\Triangles'))=321, 'Feature triangle count changed');
  Need(ElementCount(Req(feature,'NVNM\Edge Links'))=28, 'Feature link count changed');
  Need(ElementCount(Req(vanilla,'NVNM\Edge Links'))=29, 'Vanilla link count changed');
  AssertOtherNVNM(feature,vanilla);
  for i := 0 to 320 do begin
    a := Triangle(feature,i); b := Triangle(vanilla,i);
    for j := 0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'author triangle vertices');
    AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'author cover flags');
    flagsA := GetNativeValue(Req(a,'Flags')); flagsB := GetNativeValue(Req(b,'Flags'));
    Need((flagsA and (not 7))=(flagsB and (not 7)), 'Author changed non-link triangle flags');
    for side := 0 to 2 do begin
      if (i=50) and (side=2) then begin
        Need(flagsB=2052, 'Vanilla triangle50 flags changed');
        Need(flagsA=2048, 'Feature triangle50 flags changed');
        Need(GetNativeValue(Req(a,EdgeName(side)))=-1, 'Author did not close expected edge');
        Need(LinkIs(EdgeFor(vanilla,b,side),neighborMaster,469), 'Authored removed target changed');
      end else begin
        Need((flagsA and (1 shl side))=(flagsB and (1 shl side)), 'Additional authored link-bit change');
        if (flagsB and (1 shl side))<>0 then
          AssertTree(EdgeFor(feature,a,side),EdgeFor(vanilla,b,side),'authored logical portal')
        else
          AssertTree(Req(a,EdgeName(side)),Req(b,EdgeName(side)),'authored internal adjacency');
      end;
    end;
  end;
end;

procedure AssertFaceSameAtIndex(a,b: IInterface; index: Integer);
var ta,tb,va,vb: IInterface; j,ia,ib: Integer;
begin
  ta := Triangle(a,index); tb := Triangle(b,index);
  for j := 0 to 2 do begin
    ia := GetNativeValue(Req(ta,VertexName(j)));
    ib := GetNativeValue(Req(tb,VertexName(j)));
    va := ElementByIndex(Req(a,'NVNM\Vertices'),ia);
    vb := ElementByIndex(Req(b,'NVNM\Vertices'),ib);
    AssertTree(va,vb,'exact unchanged ordered face vertex');
  end;
end;

function BackLink(r: IInterface; triIndex: Integer; targetMaster: IInterface; targetTriangle: Integer): Boolean;
var t: IInterface; side,flags: Integer;
begin
  Result := False; t := Triangle(r,triIndex); flags := GetNativeValue(Req(t,'Flags'));
  for side := 0 to 2 do
    if (flags and (1 shl side))<>0 then
      if LinkIs(EdgeFor(r,t,side),targetMaster,targetTriangle) then Result := True;
end;

procedure AssertReciprocal(primary,neighbor,vanPrimary,vanNeighbor,primaryMaster,neighborMaster: IInterface);
var i,side,flags,target,countA,countB: Integer; t,edge: IInterface;
begin
  countA := 0; countB := 0;
  for i := 0 to ElementCount(Req(primary,'NVNM\Triangles'))-1 do begin
    t := Triangle(primary,i); flags := GetNativeValue(Req(t,'Flags'));
    for side := 0 to 2 do if (flags and (1 shl side))<>0 then begin
      edge := EdgeFor(primary,t,side);
      if SameRecord(LinksTo(Req(edge,'Navmesh')),neighborMaster) then begin
        target := GetNativeValue(Req(edge,'Triangle'));
        Need(BackLink(neighbor,target,primaryMaster,i), 'Primary portal lacks authored reciprocal');
        AssertFaceSameAtIndex(neighbor,vanNeighbor,target);
        Inc(countA);
      end;
    end;
  end;
  for i := 0 to ElementCount(Req(neighbor,'NVNM\Triangles'))-1 do begin
    t := Triangle(neighbor,i); flags := GetNativeValue(Req(t,'Flags'));
    for side := 0 to 2 do if (flags and (1 shl side))<>0 then begin
      edge := EdgeFor(neighbor,t,side);
      if SameRecord(LinksTo(Req(edge,'Navmesh')),primaryMaster) then begin
        target := GetNativeValue(Req(edge,'Triangle'));
        Need(BackLink(primary,target,neighborMaster,i), 'Authored neighbor lacks primary reciprocal');
        AssertFaceSameAtIndex(primary,vanPrimary,target);
        Inc(countB);
      end;
    end;
  end;
  Need((countA=16) and (countB=16), 'Expected sixteen retained reciprocal ports');
end;

procedure AssertComposed(navCopy,usNav,neighborMaster: IInterface);
var i,j,side,flags,edge,expected: Integer; a,b,linksA,linksB: IInterface;
begin
  AssertRecordHeader(navCopy,usNav,'Preserve USSEP NAVM header');
  Need(ElementCount(navCopy)=ElementCount(usNav),'NAVM top-level member count changed');
  for i:=0 to ElementCount(usNav)-1 do begin
    b:=ElementByIndex(usNav,i);
    if BaseName(b)<>'Record Header' then begin
      a:=UniqueTop(navCopy,FieldToken(b));Need(Assigned(a),'NAVM field missing'+ComparisonContext(a,b));
      if BaseName(b)<>'NVNM' then AssertTree(a,b,'Preserve non-NVNM fields');
    end;
  end;
  Need(ElementCount(Req(navCopy,'NVNM\Vertices'))=271, 'USSEP vertices lost');
  Need(ElementCount(Req(navCopy,'NVNM\Triangles'))=324, 'USSEP triangles lost');
  Need(ElementCount(Req(usNav,'NVNM\Edge Links'))=30, 'USSEP Edge Links changed');
  Need(ElementCount(Req(navCopy,'NVNM\Edge Links'))=29, 'Expected one portal entry deletion');
  AssertOtherNVNM(navCopy,usNav);
  linksA := Req(navCopy,'NVNM\Edge Links'); linksB := Req(usNav,'NVNM\Edge Links');
  Need(LinkIs(ElementByIndex(linksB,6),neighborMaster,469), 'USSEP removed link no longer exact');
  for i := 0 to 28 do begin
    j := i; if i>=6 then Inc(j);
    AssertTree(ElementByIndex(linksA,i),ElementByIndex(linksB,j),'preserved external link');
  end;
  for i := 0 to 323 do begin
    a := Triangle(navCopy,i); b := Triangle(usNav,i);
    for j := 0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'preserved USSEP triangle vertices');
    AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'preserved USSEP cover flags');
    flags := GetNativeValue(Req(b,'Flags')); expected := flags;
    if i=50 then begin Need(flags=2052,'USSEP triangle50 flags changed'); expected := 2048; end;
    Need(GetNativeValue(Req(a,'Flags'))=expected,'Unexpected composed flags');
    for side := 0 to 2 do begin
      edge := GetNativeValue(Req(b,EdgeName(side))); expected := edge;
      if (flags and (1 shl side))<>0 then begin
        if edge=6 then begin Need((i=50) and (side=2),'More than one portal uses deleted entry'); expected := -1; end
        else if edge>6 then expected := edge-1;
      end;
      Need(GetNativeValue(Req(a,EdgeName(side)))=expected,'Unexpected composed adjacency/index remap');
    end;
  end;
end;

procedure AssertOtherInfosFC(copyNavi,sourceNavi: IInterface);
var a,b,x,y: IInterface; i,j: Integer;
begin
  a:=Req(copyNavi,'Navmesh Infos'); b:=Req(sourceNavi,'Navmesh Infos'); i:=0; j:=0;
  while j<ElementCount(b) do begin
    y:=ElementByIndex(b,j);
    if not IsSharedInfo(y) then begin
      while i<ElementCount(a) do begin x:=ElementByIndex(a,i); if not IsSharedInfo(x) then Break; Inc(i); end;
      Need(i<ElementCount(a),'Unrelated NVMI removed');
      AssertTree(ElementByIndex(a,i),y,'unchanged unrelated NVMI'); Inc(i);
    end;
    Inc(j);
  end;
  while i<ElementCount(a) do begin Need(IsSharedInfo(ElementByIndex(a,i)),'New unrelated NVMI'); Inc(i); end;
end;

procedure AssertRecords(patchFile,primaryMaster,cellMaster,naviMaster,worldMaster: IInterface);
var i,n,c,v,w: Integer; r: IInterface; sig: string;
begin
  n:=0;c:=0;v:=0;w:=0;
  for i:=0 to RecordCount(patchFile)-1 do begin
    r:=RecordByIndex(patchFile,i);sig:=Signature(r);
    if sig<>'TES4' then begin
      if sig='NAVM' then begin Need(SameRecord(r,primaryMaster),'Unexpected NAVM');Inc(n);end
      else if sig='CELL' then begin Need(SameRecord(r,cellMaster),'Unexpected CELL');Inc(c);end
      else if sig='NAVI' then begin Need(SameRecord(r,naviMaster),'Unexpected NAVI');Inc(v);end
      else if sig='WRLD' then begin Need(SameRecord(r,worldMaster),'Unexpected WRLD');Inc(w);end
      else Need(False,'Unexpected patch record: '+sig);
      Need(SameText(GetFileName(GetFile(MasterOrSelf(r))),'Skyrim.esm'),'Own records forbidden');
    end;
  end;
  Need((n=1) and (c=1) and (v=1) and (w=1),'Expected NAVM/CELL/NAVI/WRLD four existing overrides');
  Need(GetIsESL(patchFile),'ESL flag missing');
end;

function Initialize: Integer;
var stock,feature,usFile,patchFile: IInterface;
    masterNav,vanNeighbor,neighborMaster,vanNav,featureNav,usNav,featureNeighbor: IInterface;
    cellMaster,cellSource,cellCopy,naviMaster,naviSource,naviCopy,featureNavi,usNavi,navCopy: IInterface;
    worldMaster,worldSource,worldCopy: IInterface;
    m,desired,existing,newInfo,t,sourceTri,edgeArray: IInterface;
    i,j,side,flags,index: Integer; expectedOwner: string; stream: TFileStream;
begin
  Result:=1;
  Need(Pos('e:\stock\skyrim collection\database\',LowerCase(DataPath))=1,'Database-owned Data required');
  stock:=ReqFile('Skyrim.esm');feature:=ReqFile('ForgottenCity.esp');usFile:=ReqFile('Unofficial Skyrim Special Edition Patch.esp');
  masterNav:=RecordByFormID(stock,$00108AB4,False);vanNav:=masterNav;
  neighborMaster:=RecordByFormID(stock,$00107528,False);vanNeighbor:=neighborMaster;
  featureNav:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(masterNav)),True);
  usNav:=RecordByFormID(usFile,LoadOrderFormIDtoFileFormID(usFile,GetLoadOrderFormID(masterNav)),True);
  featureNeighbor:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(neighborMaster)),True);
  Need(SameText(GetFileName(GetFile(featureNav)),'ForgottenCity.esp'),'Feature NAVM override absent');
  Need(SameText(GetFileName(GetFile(usNav)),'Unofficial Skyrim Special Edition Patch.esp'),'USSEP NAVM override absent');
  Need(SameText(GetFileName(GetFile(featureNeighbor)),'ForgottenCity.esp'),'Authored neighbor override absent');
  AssertAuthoredDelta(featureNav,vanNav,neighborMaster);
  AssertFaceSameAtIndex(usNav,vanNav,50);
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 0'))=48,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 1'))=12,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Vertex 2'))=47,'USSEP target face changed');
  Need(GetNativeValue(Req(Triangle(usNav,50),'Edge 2-0'))=6,'USSEP target portal index changed');
  Need(LinkIs(EdgeFor(usNav,Triangle(usNav,50),2),neighborMaster,469),'USSEP target portal changed');
  Need(ElementCount(Req(featureNeighbor,'NVNM\Triangles'))=485,'Authored neighbor triangle count changed');
  cellMaster:=RecordByFormID(stock,$00007644,False);cellSource:=WinnerExcludingPatch(cellMaster);
  worldMaster:=RecordByFormID(stock,$0000003C,False);worldSource:=WinnerExcludingPatch(worldMaster);
  naviMaster:=RecordByFormID(stock,$00012FB4,False);naviSource:=WinnerExcludingPatch(naviMaster);
  featureNavi:=RecordByFormID(feature,LoadOrderFormIDtoFileFormID(feature,GetLoadOrderFormID(naviMaster)),True);
  usNavi:=RecordByFormID(usFile,LoadOrderFormIDtoFileFormID(usFile,GetLoadOrderFormID(naviMaster)),True);
  Req(naviSource,'Navmesh Infos');
  AddMessage('FC_NAV_CELL_SOURCE|'+GetFileName(GetFile(cellSource))+'|00007644');
  AddMessage('FC_NAV_NAVI_SOURCE|'+GetFileName(GetFile(naviSource))+'|00012FB4');
  AddMessage('FC_NAV_WRLD_SOURCE|'+GetFileName(GetFile(worldSource))+'|0000003C');
  for i:=0 to 6 do begin
    m:=RecordByFormID(stock,SharedID(i),False);Need(Assigned(m),'Shared master NAVM absent');
    expectedOwner:='ForgottenCity.esp';if VERIFY_ONLY and (SharedID(i)=$108AB4) then expectedOwner:=PATCH_NAME;
    Need(SameText(GetFileName(GetFile(WinningOverride(m))),expectedOwner),'Unreviewed final NAVM winner');
    AssertNoTargetPath(ElementByPath(naviSource,'NVPP'),m);
    AssertNoTargetPath(ElementByPath(naviSource,'NVSI'),m);
    existing:=EffectiveInfoBefore(naviMaster,m);desired:=InfoFor(featureNavi,m);
    Need(Assigned(desired),'Expected feature NVMI absent');
    AssertTree(existing,desired,'Unreviewed final effective NVMI change');
  end;
  if VERIFY_ONLY then begin
    Need(FileExists(DataPath+PATCH_NAME),'Installed candidate required for fresh reload');
    patchFile:=ReqFile(PATCH_NAME);
    navCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(masterNav)),True);
    cellCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(cellMaster)),True);
    naviCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(naviMaster)),True);
    worldCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(worldMaster)),True);
    Need(SameText(GetFileName(GetFile(WinningOverride(naviMaster))),PATCH_NAME),'Patch must be last NAVI winner');
  end else begin
    Need(not Assigned(FileByName(PATCH_NAME)),'Patch already loaded');
    Need(not FileExists(DataPath+PATCH_NAME),'Patch already exists in Data');
    Need(not FileExists(OUTPUT_FILE),'Candidate output exists');
    patchFile:=AddNewFileName(PATCH_NAME);Need(Assigned(patchFile),'Patch creation failed');
    AddMasterIfMissing(patchFile,'Skyrim.esm');AddMasterIfMissing(patchFile,'ForgottenCity.esp');
    AddMasterIfMissing(patchFile,'Unofficial Skyrim Special Edition Patch.esp');
    AddMasterIfMissing(patchFile,GetFileName(GetFile(cellSource)));
    AddMasterIfMissing(patchFile,GetFileName(GetFile(naviSource)));
    AddMasterIfMissing(patchFile,GetFileName(GetFile(worldSource)));
    Need(AddRequiredElementMasters(cellSource,patchFile,False,True),'CELL masters failed');
    Need(AddRequiredElementMasters(usNav,patchFile,False,True),'USSEP NAVM masters failed');
    Need(AddRequiredElementMasters(naviSource,patchFile,False,True),'Final NAVI masters failed');
    Need(AddRequiredElementMasters(worldSource,patchFile,False,True),'Final WRLD masters failed');
    for i:=0 to 6 do begin
      m:=RecordByFormID(stock,SharedID(i),False);
      if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
      Need(Assigned(desired),'Desired authored NVMI absent');
      Need(AddRequiredElementMasters(desired,patchFile,False,True),'NVMI masters failed');
    end;
    SortMasters(patchFile);Need(MasterCount(patchFile)<=253,'Master budget exceeded');
    worldCopy:=CopyOverride(worldSource,patchFile);
    cellCopy:=CopyOverride(cellSource,patchFile);
    navCopy:=CopyOverride(usNav,patchFile);
    Need(Assigned(cellCopy) and Assigned(navCopy),'Typed record copy failed');
    AssertTree(Req(navCopy,'NVNM'),Req(usNav,'NVNM'),'Initial exact USSEP copy');
    for i:=0 to 323 do begin
      sourceTri:=Triangle(usNav,i);t:=Triangle(navCopy,i);flags:=GetNativeValue(Req(sourceTri,'Flags'));
      for side:=0 to 2 do if (flags and (1 shl side))<>0 then begin
        index:=GetNativeValue(Req(sourceTri,EdgeName(side)));
        if index=6 then begin Need((i=50) and (side=2),'Deleted link has unexpected users');SetNativeValue(Req(t,EdgeName(side)),-1);end
        else if index>6 then SetNativeValue(Req(t,EdgeName(side)),index-1);
      end;
      if i=50 then SetNativeValue(Req(t,'Flags'),flags and (not 4));
    end;
    Remove(ElementByIndex(Req(navCopy,'NVNM\Edge Links'),6));
    naviCopy:=CopyOverride(naviSource,patchFile);Need(Assigned(naviCopy),'NAVI copy failed');
    AssertUnchangedRecord(naviCopy,naviSource,'Initial full final NAVI copy');
    for i:=0 to 6 do begin
      m:=RecordByFormID(stock,SharedID(i),False);
      if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
      existing:=InfoFor(naviCopy,m);if Assigned(existing) then Remove(existing);
      newInfo:=ElementAssign(Req(naviCopy,'Navmesh Infos'),HighInteger,desired,False);
      Need(Assigned(newInfo),'NVMI forwarding failed');RemapInfoReferences(newInfo,desired);
      AssertTree(newInfo,desired,'Exact selected NVMI forwarding');
    end;
    SetIsESL(patchFile,True);
  end;
  AssertComposed(navCopy,usNav,neighborMaster);
  AssertReciprocal(navCopy,featureNeighbor,vanNav,vanNeighbor,masterNav,neighborMaster);
  AssertUnchangedRecord(cellCopy,cellSource,'Preserve final parent CELL');
  AssertUnchangedRecord(worldCopy,worldSource,'Preserve final Tamriel WRLD');
  for i:=0 to 6 do begin
    m:=RecordByFormID(stock,SharedID(i),False);
    if SharedID(i)=$108AB4 then desired:=InfoFor(usNavi,m) else desired:=InfoFor(featureNavi,m);
    existing:=InfoFor(naviCopy,m);Need(Assigned(existing),'Forwarded NVMI missing');
    AssertTree(existing,desired,'Exact selected NVMI post-check');
  end;
  AssertOtherInfosFC(naviCopy,naviSource);AssertNaviRest(naviCopy,naviSource);
  AssertRecords(patchFile,masterNav,cellMaster,naviMaster,worldMaster);
  Need(Check(navCopy)='','NAVM diagnostics: '+Check(navCopy));
  Need(Check(cellCopy)='','CELL diagnostics: '+Check(cellCopy));
  Need(Check(naviCopy)='','NAVI diagnostics: '+Check(naviCopy));
  Need(Check(worldCopy)='','WRLD diagnostics: '+Check(worldCopy));
  if not VERIFY_ONLY then begin
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));stream:=TFileStream.Create(OUTPUT_FILE,fmCreate);
    try FileWriteToStream(patchFile,stream,0);finally stream.Free;end;
    AddMessage('FC_NAV_CANDIDATE_EXPORTED|'+OUTPUT_FILE);
  end;
  if VERIFY_ONLY then AddMessage('FC_NAV_RELOAD_TYPED_PASS|PORTS=16/16|OWN=0|NVMI=7')
  else AddMessage('FC_NAV_INMEMORY_TYPED_PASS|PORTS=16/16|OWN=0|NVMI=7');
  Result:=0;
end;

end.
'''


def main():
    text=COMMON.read_text(encoding='utf-8')
    helpers=take(text,'procedure Need(','procedure AssertOneNVNM(')
    helpers+=take(text,'function WinnerExcludingPatch(','procedure AssertInfoOther(')
    helpers+=take(text,'procedure RemapInfoReferences(','function InfoDoor(')
    helpers+=take(text,'procedure AssertNoTargetPath(','procedure AssertOtherInfos(')
    helpers+=take(text,'procedure AssertNaviRest(','procedure AssertOnlyExistingOverrides(')
    header="""unit UserScript;
// DRAFT ONLY. Same-version typed APIs verified; xEdit compile/run still required.
// Original records never edited. Requires normal definitions and source preflight.
const
  VERIFY_ONLY = False;
  PATCH_NAME = 'Database Forgotten City USSEP Navigation.esp';
  OUTPUT_FILE = 'E:\\stock\\Skyrim collection\\Database\\integration\\research\\forgotten_city_navigation\\candidate\\Database Forgotten City USSEP Navigation.esp';

"""
    result=header+helpers+BODY
    builder=OUT/'DatabaseForgottenCityNavigationDraft.pas'
    verifier=OUT/'DatabaseVerifyForgottenCityNavigationDraft.pas'
    builder.write_text(result,encoding='utf-8')
    verifier.write_text(result.replace('VERIFY_ONLY = False;','VERIFY_ONLY = True;',1),encoding='utf-8')
    manifest={'status':'DRAFT_NOT_XEDIT_COMPILED_OR_EXECUTED','common_helpers_source':str(COMMON),
        'common_helpers_sha256':hashlib.sha256(COMMON.read_bytes()).hexdigest(),
        'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (builder,verifier)]}
    (OUT/'draft_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('Standalone drafts generated:',len(result.splitlines()),'lines; no plugins written')


if __name__=='__main__':main()
