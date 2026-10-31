"""Generate one self-contained four-door/three-NAVM composition draft."""
import hashlib,json
from pathlib import Path

OUT=Path(__file__).resolve().parent
COMMON=OUT.parent/'navmesh_patch/DatabaseBoundedNavmeshDraft.pas'

def part(text,start,end):return text[text.index(start):text.index(end)]

BODY=r'''
function TargetID(c: Integer): Integer;
begin case c of 0:Result:=$016F5D;1:Result:=$0EC466;2:Result:=$0EC469;else Need(False,'Bad case');end;end;
function ParentID(c: Integer): Integer;
begin case c of 0:Result:=$016D72;1:Result:=$009CA3;2:Result:=$009CA0;else Need(False,'Bad case');end;end;
function BaseNameFor(c: Integer): string;
begin case c of 0:Result:='AKSkyrimUnderground.esm';1:Result:='AncientLand2.esp';2:Result:='RedBag''s Falkreath.esp';else Need(False,'Bad case');end;end;
function NewDoorCount(c: Integer): Integer;
begin if c=2 then Result:=2 else Result:=1;end;
function OldDoorCount(c: Integer): Integer;
begin if c=0 then Result:=2 else Result:=0;end;
function SourceTriangle(c,d: Integer): Integer;
begin case c of 0:Result:=502;1:Result:=34;2:if d=0 then Result:=116 else Result:=325;else Need(False,'Bad case');end;end;
function PlannedTriangle(c,d: Integer): Integer;
begin Result:=SourceTriangle(c,d);if (c=2) and (d=1) then Result:=86;end;
function DoorObject(c,d: Integer): Integer;
begin case c of 0:Result:=$0122F4;1:Result:=$014C1D;2:if d=0 then Result:=$0073D4 else Result:=$017737;else Need(False,'Bad case');end;end;
function ExpectedFaceCount(c: Integer): Integer;
begin case c of 0:Result:=532;1:Result:=349;2:Result:=312;else Need(False,'Bad case');end;end;
function ExpectedPorts(c: Integer): Integer;
begin case c of 0:Result:=0;1:Result:=16;2:Result:=17;else Need(False,'Bad case');end;end;
function EdgeName(side: Integer): string;
begin case side of 0:Result:='Edge 0-1';1:Result:='Edge 1-2';2:Result:='Edge 2-0';else Need(False,'Bad side');end;end;
function VertexName(side: Integer): string;
begin Result:='Vertex '+IntToStr(side);end;
function Tri(r: IInterface;i: Integer): IInterface;
var a:IInterface;
begin a:=Req(r,'NVNM\Triangles');Need((i>=0) and (i<ElementCount(a)),'Triangle out of bounds');Result:=ElementByIndex(a,i);Need(ElementCount(Result)=8,'Normal 4.1.5f triangle schema required');end;
function Vertex(r,t:IInterface;j:Integer):IInterface;
begin Result:=ElementByIndex(Req(r,'NVNM\Vertices'),GetNativeValue(Req(t,VertexName(j))));Need(Assigned(Result),'Vertex out of bounds');end;
function VertexEqual(a,b:IInterface):Boolean;
begin Result:=(GetNativeValue(Req(a,'X'))=GetNativeValue(Req(b,'X'))) and
 (GetNativeValue(Req(a,'Y'))=GetNativeValue(Req(b,'Y'))) and (GetNativeValue(Req(a,'Z'))=GetNativeValue(Req(b,'Z')));end;
function FaceEqual(source,st,base,bt:IInterface;rotation:Integer):Boolean;
var j:Integer;
begin Result:=True;for j:=0 to 2 do if not VertexEqual(Vertex(source,st,j),Vertex(base,bt,(j+rotation) mod 3)) then Result:=False;end;
function UniqueFace(source,base:IInterface;c,d:Integer):Integer;
var i,j,count:Integer;st,bt:IInterface;
begin
 Result:=-1;count:=0;st:=Tri(source,SourceTriangle(c,d));
 for i:=0 to ElementCount(Req(base,'NVNM\Triangles'))-1 do begin
  bt:=Tri(base,i);
  for j:=0 to 2 do if FaceEqual(source,st,base,bt,j) then begin Result:=i;Inc(count);end;
 end;
 Need(count=1,'Door face missing/ambiguous or winding reversed');
 Need(Result=PlannedTriangle(c,d),'Unique face mapping changed from audited plan');
 Need((GetNativeValue(Req(Tri(base,Result),'Flags')) and (8 or 512 or 1024))=0,'Base door face deleted/water/already bound');
end;
function EdgeFor(r,t:IInterface;side:Integer):IInterface;
var i:Integer;a:IInterface;
begin i:=GetNativeValue(Req(t,EdgeName(side)));a:=Req(r,'NVNM\Edge Links');Need((i>=0) and (i<ElementCount(a)),'External link index invalid');Result:=ElementByIndex(a,i);end;
function SourceDoor(source:IInterface;c,d:Integer):IInterface;
var a,e,r:IInterface;i,count:Integer;
begin
 Result:=nil;count:=0;a:=Req(source,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin
  e:=ElementByIndex(a,i);
  if GetNativeValue(Req(e,'Triangle before door'))=SourceTriangle(c,d) then begin
   r:=LinksTo(Req(e,'Door Ref'));Need(Assigned(r),'Glen Door Ref unresolved');r:=MasterOrSelf(r);
   if SameText(GetFileName(GetFile(r)),'Glenmoril.esm') then begin
    Need((GetLoadOrderFormID(r) and $00FFFFFF)=DoorObject(c,d),'Authored door identity changed');
    Need(Signature(r)='REFR','Door Ref is not REFR');
    Need(IntToHex(GetNativeValue(Req(e,'CRC Hash')),8)='E48B73F3','Authored CRC changed');
    Result:=e;Inc(count);
   end;
  end;
 end;
 Need(count=1,'Authored Door Triangle absent or ambiguous');
end;
procedure AssertAuthoredDoorReferences(entry:IInterface);
var r,destination:IInterface;
begin
 r:=LinksTo(Req(entry,'Door Ref'));Need(Assigned(r),'Authored door missing');r:=MasterOrSelf(r);
 AssertUnchangedRecord(WinningOverride(r),r,'Unreviewed final authored door REFR change');
 destination:=LinksTo(Req(r,'XTEL\Door'));Need(Assigned(destination),'Authored teleport destination missing');destination:=MasterOrSelf(destination);
 Need(SameText(GetFileName(GetFile(destination)),'Glenmoril.esm'),'Teleport destination source changed');
 AssertUnchangedRecord(WinningOverride(destination),destination,'Unreviewed final destination door REFR change');
 Need(SameRecord(LinksTo(Req(destination,'XTEL\Door')),r),'Authored teleport pair is not reciprocal');
end;
procedure CompareOtherNVNM(a,b:IInterface;ignoreEdgeLinks:Boolean);
var ga,gb,x,y:IInterface;i:Integer;n:string;
begin
 ga:=Req(a,'NVNM');gb:=Req(b,'NVNM');Need(ElementCount(ga)=ElementCount(gb),'NVNM schema changed');
 for i:=0 to ElementCount(ga)-1 do begin
  x:=ElementByIndex(ga,i);y:=ElementByIndex(gb,i);n:=BaseName(x);Need(n=BaseName(y),'NVNM field order changed');
  if (n<>'Triangles') and (n<>'Door Triangles') and not(ignoreEdgeLinks and (n='Edge Links')) then AssertTree(x,y,'preserved NVNM/'+n);
 end;
end;
function IsSourceDoorTriangle(c,index:Integer):Boolean;
var d:Integer;
begin Result:=False;for d:=0 to NewDoorCount(c)-1 do if index=SourceTriangle(c,d) then Result:=True;end;
procedure AssertAuthoredDelta(source,vanilla:IInterface;c:Integer);
var i,j,flags,expected:Integer;a,b:IInterface;
begin
 CompareOtherNVNM(source,vanilla,True);
 Need(ElementCount(Req(source,'NVNM\Triangles'))=ElementCount(Req(vanilla,'NVNM\Triangles')),'Glen changed triangle count');
 for i:=0 to ElementCount(Req(vanilla,'NVNM\Triangles'))-1 do begin
  a:=Tri(source,i);b:=Tri(vanilla,i);
  for j:=0 to 2 do AssertTree(Req(a,VertexName(j)),Req(b,VertexName(j)),'authored vertex ordinal');
  AssertTree(Req(a,'Cover Flags'),Req(b,'Cover Flags'),'authored cover flags');
  flags:=GetNativeValue(Req(b,'Flags'));expected:=flags;if IsSourceDoorTriangle(c,i) then expected:=expected or 1024;
  Need(GetNativeValue(Req(a,'Flags'))=expected,'Glen delta exceeds the authored Door bit');
  for j:=0 to 2 do begin
   if (flags and (1 shl j))<>0 then AssertTree(EdgeFor(source,a,j),EdgeFor(vanilla,b,j),'authored logical external link')
   else AssertTree(Req(a,EdgeName(j)),Req(b,EdgeName(j)),'authored internal adjacency');
  end;
 end;
end;
procedure AssertConnected(base:IInterface;c:Integer);
var seen,queue:TStringList;position,i,j,k,n,flags,otherFlags,ports,shared,doors:Integer;
    t,other,a:IInterface;back:Boolean;
begin
 seen:=TStringList.Create;queue:=TStringList.Create;
 try
  seen.Sorted:=True;i:=PlannedTriangle(c,0);seen.Add(IntToStr(i));queue.Add(IntToStr(i));position:=0;ports:=0;doors:=0;
  while position<queue.Count do begin
   i:=StrToInt(queue[position]);Inc(position);t:=Tri(base,i);flags:=GetNativeValue(Req(t,'Flags'));
   Need((flags and (8 or 512))=0,'Base component deleted or underwater');
   for j:=0 to 2 do begin
    n:=GetNativeValue(Req(t,EdgeName(j)));
    if (flags and (1 shl j))<>0 then begin EdgeFor(base,t,j);Inc(ports);end
    else if n<>-1 then begin
     other:=Tri(base,n);otherFlags:=GetNativeValue(Req(other,'Flags'));back:=False;
     for k:=0 to 2 do if ((otherFlags and (1 shl k))=0) and (GetNativeValue(Req(other,EdgeName(k)))=i) then back:=True;
     Need(back,'Base internal adjacency is not reciprocal');shared:=0;
     for k:=0 to 2 do begin
      a:=Vertex(base,t,k);
      if VertexEqual(a,Vertex(base,other,0)) or VertexEqual(a,Vertex(base,other,1)) or VertexEqual(a,Vertex(base,other,2)) then Inc(shared);
     end;
     Need(shared>=2,'Base internal neighbors do not share an exact geometric edge');
     if (otherFlags and 8)=0 then if seen.IndexOf(IntToStr(n))<0 then begin seen.Add(IntToStr(n));queue.Add(IntToStr(n));end;
    end;
   end;
  end;
  a:=Req(base,'NVNM\Door Triangles');
  for i:=0 to ElementCount(a)-1 do if seen.IndexOf(IntToStr(GetNativeValue(Req(ElementByIndex(a,i),'Triangle before door'))))>=0 then Inc(doors);
  Need(seen.Count=ExpectedFaceCount(c),'Base connected component changed');
  Need(ports=ExpectedPorts(c),'Base component external exits changed');
  Need(doors=OldDoorCount(c),'Base component door exits changed');
  Need((ports>0) or (doors>0),'Door face has no existing reachable topological exit');
 finally seen.Free;queue.Free;end;
end;
function TargetDoor(copyNav,refRecord:IInterface;triangleIndex:Integer):IInterface;
var a,e:IInterface;i,count:Integer;
begin Result:=nil;count:=0;a:=Req(copyNav,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin e:=ElementByIndex(a,i);
  if (GetNativeValue(Req(e,'Triangle before door'))=triangleIndex) and SameRecord(LinksTo(Req(e,'Door Ref')),refRecord) then begin Result:=e;Inc(count);end;
 end;Need(count=1,'Expected mapped Door Triangle absent or duplicated');end;
procedure AssertDoorState(copyNav,base,source:IInterface;c:Integer);
var i,j,d,expected:Integer;a,b,x,y,srcDoor,refRecord:IInterface;
begin
 AssertRecordHeader(copyNav,base,'Preserve NAVM header');
 Need(ElementCount(copyNav)=ElementCount(base),'NAVM top-level fields changed');
 for i:=0 to ElementCount(base)-1 do begin
  b:=ElementByIndex(base,i);
  if BaseName(b)<>'Record Header' then begin
   a:=UniqueTop(copyNav,FieldToken(b));Need(Assigned(a),'NAVM field missing'+ComparisonContext(a,b));
   if BaseName(b)<>'NVNM' then AssertTree(a,b,'Preserve NAVM non-NVNM field');
  end;
 end;
 CompareOtherNVNM(copyNav,base,False);
 Need(ElementCount(Req(copyNav,'NVNM\Triangles'))=ExpectedFaceCount(c),'Base triangle count changed');
 for i:=0 to ExpectedFaceCount(c)-1 do begin
  a:=Tri(copyNav,i);b:=Tri(base,i);
  for j:=0 to 7 do begin
   x:=ElementByIndex(a,j);y:=ElementByIndex(b,j);
   if BaseName(x)='Flags' then begin
    expected:=GetNativeValue(y);
    for d:=0 to NewDoorCount(c)-1 do if i=PlannedTriangle(c,d) then expected:=expected or 1024;
    Need(GetNativeValue(x)=expected,'Unexpected post-copy triangle flags');
   end else AssertTree(x,y,'unchanged base triangle field');
  end;
 end;
 Need(ElementCount(Req(copyNav,'NVNM\Door Triangles'))=OldDoorCount(c)+NewDoorCount(c),'Door count changed unexpectedly');
 a:=Req(base,'NVNM\Door Triangles');
 for i:=0 to ElementCount(a)-1 do begin
  srcDoor:=ElementByIndex(a,i);refRecord:=LinksTo(Req(srcDoor,'Door Ref'));
  b:=TargetDoor(copyNav,refRecord,GetNativeValue(Req(srcDoor,'Triangle before door')));AssertTree(b,srcDoor,'preserve base door');
 end;
 for d:=0 to NewDoorCount(c)-1 do begin
  srcDoor:=SourceDoor(source,c,d);refRecord:=LinksTo(Req(srcDoor,'Door Ref'));
  b:=TargetDoor(copyNav,refRecord,PlannedTriangle(c,d));
  AssertTree(Req(b,'CRC Hash'),Req(srcDoor,'CRC Hash'),'preserve authored CRC');
  Need(SameRecord(LinksTo(Req(b,'Door Ref')),refRecord),'Door Ref namespace translation failed');
 end;
end;
function ParentCell(r:IInterface;expected:Integer):IInterface;
var e,p:IInterface;
begin
 Result:=nil;e:=GetContainer(r);
 while Assigned(e) do begin
  if ElementType(e)=etGroupRecord then begin p:=ChildrenOf(e);if Assigned(p) then if Signature(p)='CELL' then begin Result:=MasterOrSelf(p);Break;end;end;
  e:=GetContainer(e);
 end;
 Need(Assigned(Result),'CELL container not found');
 Need(SameText(GetFileName(GetFile(Result)),'Skyrim.esm') and ((GetLoadOrderFormID(Result) and $00FFFFFF)=expected),'CELL container changed');
end;
function EffectiveInfoBefore(naviMaster,navMaster:IInterface):IInterface;
var i:Integer;r,item:IInterface;
begin
 Result:=InfoFor(naviMaster,navMaster);
 for i:=0 to OverrideCount(naviMaster)-1 do begin r:=OverrideByIndex(naviMaster,i);
  if not SameText(GetFileName(GetFile(r)),PATCH_NAME) then begin item:=InfoFor(r,navMaster);
   if Assigned(item) then begin if not Assigned(Result) then Result:=item else if GetLoadOrder(GetFile(item))>GetLoadOrder(GetFile(Result)) then Result:=item;end;
  end;
 end;Need(Assigned(Result),'Effective prior NVMI absent');
end;
function IsTargetInfo(info:IInterface):Boolean;
var r:IInterface;i:Integer;
begin Result:=False;r:=LinksTo(Req(info,'Navmesh'));Need(Assigned(r),'NAVI key unresolved');r:=MasterOrSelf(r);
 if not SameText(GetFileName(GetFile(r)),'Skyrim.esm') then Exit;
 for i:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=TargetID(i) then Result:=True;
end;
procedure AssertOtherInfos(copyNavi,sourceNavi:IInterface);
var a,b,x,y:IInterface;i,j:Integer;
begin
 a:=Req(copyNavi,'Navmesh Infos');b:=Req(sourceNavi,'Navmesh Infos');i:=0;j:=0;
 while j<ElementCount(b) do begin y:=ElementByIndex(b,j);
  if not IsTargetInfo(y) then begin
   while i<ElementCount(a) do begin x:=ElementByIndex(a,i);if not IsTargetInfo(x) then Break;Inc(i);end;
   Need(i<ElementCount(a),'Unrelated NVMI removed');AssertTree(ElementByIndex(a,i),y,'unchanged other NVMI');Inc(i);
  end;Inc(j);
 end;
 while i<ElementCount(a) do begin Need(IsTargetInfo(ElementByIndex(a,i)),'New unrelated NVMI');Inc(i);end;
end;
procedure AssertInfoDoorState(copyInfo,baseInfo,sourceInfo,sourceNav:IInterface;c:Integer);
var a,b,entry,refRecord:IInterface;i,d:Integer;
begin
 AssertInfoOther(copyInfo,baseInfo);
 Need(ElementCount(Req(copyInfo,'Door Links'))=OldDoorCount(c)+NewDoorCount(c),'NVMI Door Link count changed');
 a:=Req(baseInfo,'Door Links');
 for i:=0 to ElementCount(a)-1 do begin entry:=ElementByIndex(a,i);refRecord:=LinksTo(Req(entry,'Door Ref'));b:=InfoDoor(copyInfo,refRecord);AssertTree(b,entry,'preserve base NVMI door');end;
 for d:=0 to NewDoorCount(c)-1 do begin entry:=SourceDoor(sourceNav,c,d);refRecord:=LinksTo(Req(entry,'Door Ref'));a:=InfoDoor(sourceInfo,refRecord);b:=InfoDoor(copyInfo,refRecord);AssertTree(b,a,'exact authored NVMI door');end;
end;
procedure AssertAllowedRecords(patchFile,worldMaster,naviMaster:IInterface);
var i,j,n,c,w,v:Integer;r:IInterface;sig:string;known:Boolean;
begin n:=0;c:=0;w:=0;v:=0;
 for i:=0 to RecordCount(patchFile)-1 do begin r:=RecordByIndex(patchFile,i);sig:=Signature(r);
  if sig<>'TES4' then begin
   Need(SameText(GetFileName(GetFile(MasterOrSelf(r))),'Skyrim.esm'),'Own/new records forbidden');
   if sig='NAVM' then begin known:=False;for j:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=TargetID(j) then known:=True;Need(known,'Unexpected NAVM');Inc(n);end
   else if sig='CELL' then begin known:=False;for j:=0 to 2 do if (GetLoadOrderFormID(r) and $00FFFFFF)=ParentID(j) then known:=True;Need(known,'Unexpected CELL');Inc(c);end
   else if sig='WRLD' then begin Need(SameRecord(r,worldMaster),'Unexpected WRLD');Inc(w);end
   else if sig='NAVI' then begin Need(SameRecord(r,naviMaster),'Unexpected NAVI');Inc(v);end
   else Need(False,'Unexpected record type '+sig);
  end;
 end;Need((n=3) and (c=3) and (w=1) and (v=1),'Expected 3 NAVM + 3 CELL + WRLD + NAVI existing overrides');Need(GetIsESL(patchFile),'ESL flag missing');
end;
function Initialize:Integer;
var stock,glen,patchFile,naviMaster,glenNavi,naviSource,naviCopy,worldMaster,worldSource,worldCopy:IInterface;
    baseFile,masterNav,vanilla,sourceNav,baseNav,cellMaster,cellSource,cellCopy,navCopy:IInterface;
    baseNavi,baseInfo,sourceInfo,copyInfo,e,entry,refRecord,t,existing:IInterface;
    c,d,i,mapped,flags:Integer;expectedOwner:string;stream:TFileStream;
begin
 Result:=1;Need(Pos('e:\stock\skyrim collection\database\',LowerCase(DataPath))=1,'Database-owned Data required');
 stock:=ReqFile('Skyrim.esm');glen:=ReqFile('Glenmoril.esm');Need(not GetIsESL(glen),'Glen must remain a full master');
 naviMaster:=RecordByFormID(stock,$012FB4,False);naviSource:=WinnerExcludingPatch(naviMaster);
 glenNavi:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(naviMaster)),True);
 worldMaster:=RecordByFormID(stock,$00003C,False);worldSource:=WinnerExcludingPatch(worldMaster);
 Req(naviSource,'Navmesh Infos');
 // Entire preflight before creation; source file SHA checks are a separate prerequisite.
 for c:=0 to 2 do begin
  baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);vanilla:=masterNav;
  sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
  baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
  Need(SameText(GetFileName(GetFile(sourceNav)),'Glenmoril.esm'),'Glen override absent');
  Need(SameText(GetFileName(GetFile(baseNav)),BaseNameFor(c)),'Selected base override absent');
  expectedOwner:=BaseNameFor(c);if VERIFY_ONLY then expectedOwner:=PATCH_NAME;
  Need(SameText(GetFileName(GetFile(WinningOverride(masterNav))),expectedOwner),'Unexpected final NAVM winner/order');
  AssertAuthoredDelta(sourceNav,vanilla,c);AssertConnected(baseNav,c);ParentCell(baseNav,ParentID(c));
  baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);
  baseInfo:=InfoFor(baseNavi,masterNav);Need(Assigned(baseInfo),'Selected base NVMI absent');
  existing:=EffectiveInfoBefore(naviMaster,masterNav);AssertTree(existing,baseInfo,'Unreviewed final effective base NVMI');
  Need(ElementCount(Req(baseNav,'NVNM\Door Triangles'))=OldDoorCount(c),'Base Door Triangles changed');
  Need(ElementCount(Req(baseInfo,'Door Links'))=OldDoorCount(c),'Base NVMI Door Links changed');
  AssertNoTargetPath(ElementByPath(naviSource,'NVPP'),masterNav);AssertNoTargetPath(ElementByPath(naviSource,'NVSI'),masterNav);
  for d:=0 to NewDoorCount(c)-1 do begin mapped:=UniqueFace(sourceNav,baseNav,c,d);entry:=SourceDoor(sourceNav,c,d);AssertAuthoredDoorReferences(entry);end;
 end;
 if VERIFY_ONLY then begin Need(FileExists(DataPath+PATCH_NAME),'Installed candidate required for fresh reload');patchFile:=ReqFile(PATCH_NAME);end
 else begin
  Need(not Assigned(FileByName(PATCH_NAME)),'Patch already loaded');Need(not FileExists(DataPath+PATCH_NAME),'Patch already in VFS');Need(not FileExists(OUTPUT_FILE),'Candidate output exists');
  patchFile:=AddNewFileName(PATCH_NAME);Need(Assigned(patchFile),'Patch creation failed');
  AddMasterIfMissing(patchFile,'Skyrim.esm');AddMasterIfMissing(patchFile,'Glenmoril.esm');
  AddMasterIfMissing(patchFile,GetFileName(GetFile(naviSource)));AddMasterIfMissing(patchFile,GetFileName(GetFile(worldSource)));
  Need(AddRequiredElementMasters(naviSource,patchFile,False,True),'NAVI masters failed');Need(AddRequiredElementMasters(worldSource,patchFile,False,True),'WRLD masters failed');
  for c:=0 to 2 do begin
   baseFile:=ReqFile(BaseNameFor(c));AddMasterIfMissing(patchFile,BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
   baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
   cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);
   AddMasterIfMissing(patchFile,GetFileName(GetFile(cellSource)));
   Need(AddRequiredElementMasters(baseNav,patchFile,False,True),'NAVM masters failed');Need(AddRequiredElementMasters(cellSource,patchFile,False,True),'CELL masters failed');
   baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);
   Need(AddRequiredElementMasters(baseInfo,patchFile,False,True),'NVMI masters failed');
  end;
  SortMasters(patchFile);Need(MasterCount(patchFile)<=253,'Master budget exceeded');
  worldCopy:=CopyOverride(worldSource,patchFile);naviCopy:=CopyOverride(naviSource,patchFile);
  AssertUnchangedRecord(worldCopy,worldSource,'Initial exact final WRLD');AssertUnchangedRecord(naviCopy,naviSource,'Initial exact final NAVI');
  for c:=0 to 2 do begin
   baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
   sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
   baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
   cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);cellCopy:=CopyOverride(cellSource,patchFile);
   navCopy:=CopyOverride(baseNav,patchFile);AssertUnchangedRecord(navCopy,baseNav,'Initial exact selected base NAVM');
   baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);sourceInfo:=InfoFor(glenNavi,masterNav);
   existing:=InfoFor(naviCopy,masterNav);if Assigned(existing) then Remove(existing);
   copyInfo:=ElementAssign(Req(naviCopy,'Navmesh Infos'),HighInteger,baseInfo,False);Need(Assigned(copyInfo),'Base NVMI forwarding failed');RemapInfoReferences(copyInfo,baseInfo);
   for d:=0 to NewDoorCount(c)-1 do begin
    mapped:=UniqueFace(sourceNav,baseNav,c,d);entry:=SourceDoor(sourceNav,c,d);refRecord:=LinksTo(Req(entry,'Door Ref'));
    e:=ElementAssign(Req(navCopy,'NVNM\Door Triangles'),HighInteger,entry,False);Need(Assigned(e),'Door Triangle append failed');
    SetNativeValue(Req(e,'Triangle before door'),mapped);SetEditValue(Req(e,'Door Ref'),IntToHex(GetLoadOrderFormID(refRecord),8));
    t:=Tri(navCopy,mapped);flags:=GetNativeValue(Req(t,'Flags'));SetNativeValue(Req(t,'Flags'),flags or 1024);
    entry:=InfoDoor(sourceInfo,refRecord);e:=ElementAssign(Req(copyInfo,'Door Links'),HighInteger,entry,False);Need(Assigned(e),'NAVI Door Link append failed');SetEditValue(Req(e,'Door Ref'),IntToHex(GetLoadOrderFormID(refRecord),8));
   end;
  end;SetIsESL(patchFile,True);
 end;
 naviCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(naviMaster)),True);
 worldCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(worldMaster)),True);
 for c:=0 to 2 do begin
  baseFile:=ReqFile(BaseNameFor(c));masterNav:=RecordByFormID(stock,TargetID(c),False);
  sourceNav:=RecordByFormID(glen,LoadOrderFormIDtoFileFormID(glen,GetLoadOrderFormID(masterNav)),True);
  baseNav:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(masterNav)),True);
  navCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(masterNav)),True);
  cellMaster:=ParentCell(baseNav,ParentID(c));cellSource:=WinnerExcludingPatch(cellMaster);
  cellCopy:=RecordByFormID(patchFile,LoadOrderFormIDtoFileFormID(patchFile,GetLoadOrderFormID(cellMaster)),True);
  AddMessage('GLEN_NAV_CELL_SOURCE|'+IntToHex(ParentID(c),6)+'|'+GetFileName(GetFile(cellSource)));
  AssertUnchangedRecord(cellCopy,cellSource,'Preserve final parent CELL');AssertDoorState(navCopy,baseNav,sourceNav,c);
  baseNavi:=RecordByFormID(baseFile,LoadOrderFormIDtoFileFormID(baseFile,GetLoadOrderFormID(naviMaster)),True);baseInfo:=InfoFor(baseNavi,masterNav);sourceInfo:=InfoFor(glenNavi,masterNav);copyInfo:=InfoFor(naviCopy,masterNav);
  AssertInfoDoorState(copyInfo,baseInfo,sourceInfo,sourceNav,c);
  Need(Check(navCopy)='','NAVM diagnostics: '+Check(navCopy));Need(Check(cellCopy)='','CELL diagnostics: '+Check(cellCopy));
 end;
 AssertUnchangedRecord(worldCopy,worldSource,'Preserve final WRLD');AssertNaviRest(naviCopy,naviSource);AssertOtherInfos(naviCopy,naviSource);AssertAllowedRecords(patchFile,worldMaster,naviMaster);
 Need(Check(naviCopy)='','NAVI diagnostics: '+Check(naviCopy));Need(Check(worldCopy)='','WRLD diagnostics: '+Check(worldCopy));
 AddMessage('GLEN_NAV_NAVI_SOURCE|'+GetFileName(GetFile(naviSource)));AddMessage('GLEN_NAV_WRLD_SOURCE|'+GetFileName(GetFile(worldSource)));
 if VERIFY_ONLY then Need(SameText(GetFileName(GetFile(WinningOverride(naviMaster))),PATCH_NAME),'Patch is not final NAVI winner')
 else begin ForceDirectories(ExtractFilePath(OUTPUT_FILE));stream:=TFileStream.Create(OUTPUT_FILE,fmCreate);try FileWriteToStream(patchFile,stream,0);finally stream.Free;end;AddMessage('GLEN_NAV_CANDIDATE_EXPORTED|'+OUTPUT_FILE);end;
 if VERIFY_ONLY then AddMessage('GLEN_NAV_RELOAD_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0') else AddMessage('GLEN_NAV_INMEMORY_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0');Result:=0;
end;
end.
'''

def main():
 text=COMMON.read_text(encoding='utf-8')
 helpers=part(text,'procedure Need(','procedure AssertOneNVNM(')
 helpers+=part(text,'function WinnerExcludingPatch(','procedure AssertInfoOther(')
 helpers+=part(text,'procedure AssertInfoOther(','function InfoDoor(')
 helpers+=part(text,'function InfoDoor(','procedure AssertInfoDoors(')
 helpers+=part(text,'procedure AssertNoTargetPath(','procedure AssertOtherInfos(')
 helpers+=part(text,'procedure AssertNaviRest(','procedure AssertOnlyExistingOverrides(')
 header="""unit UserScript;
// DRAFT: requires exact-source preflight and normal xEdit4.1.5f definitions.
// Supersedes the earlier AK-only draft; do not load both candidates together.
const
 VERIFY_ONLY = False;
 PATCH_NAME = 'Database Glenmoril Navigation Compatibility.esp';
 OUTPUT_FILE = 'E:\\stock\\Skyrim collection\\Database\\integration\\research\\glen_region_navigation\\candidate\\Database Glenmoril Navigation Compatibility.esp';

"""
 result=header+helpers+BODY
 paths=[OUT/'DatabaseGlenmorilNavigationDraft.pas',OUT/'DatabaseVerifyGlenmorilNavigationDraft.pas']
 paths[0].write_text(result,encoding='utf-8');paths[1].write_text(result.replace('VERIFY_ONLY = False;','VERIFY_ONLY = True;',1),encoding='utf-8')
 (OUT/'draft_manifest.json').write_text(json.dumps({'status':'DRAFT_NOT_XEDIT_COMPILED_OR_EXECUTED','helper_source':str(COMMON),
  'helper_sha256':hashlib.sha256(COMMON.read_bytes()).hexdigest(),'files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]},indent=2)+'\n',encoding='utf-8')
 print('Standalone combined Glen drafts generated:',len(result.splitlines()),'lines; no ESP written')

if __name__=='__main__':main()
