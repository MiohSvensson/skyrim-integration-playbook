"""Add complete first-call typed NVMI diagnostics and exact scalar-union guard.

The original scalar Parent Cell union has zero child elements in4.1.5f. Its
resolved native value and LinksTo are read directly from the union. No format
fallback, raw-offset editing, dispatched script, or runtime change is made.
"""
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[3]

DUMP=r'''procedure DumpStockOrphanTree(e: IInterface; depth: Integer; var nodes: Integer);
var i,n: Integer; linked: IInterface; nativeTypeText,editText,linksText: string;
begin
  Need(Assigned(e), 'Orphan full-tree diagnostic encountered missing element');
  Inc(nodes); Need((depth <= 12) and (nodes <= 128), 'Orphan full-tree diagnostic exceeded bounded source scope');
  n := ElementCount(e);
  nativeTypeText := '<unavailable>'; editText := '<unavailable>'; linksText := '<none>';
  try nativeTypeText := IntToStr(VarType(GetNativeValue(e))); except end;
  try editText := GetEditValue(e); except end;
  linked := LinksTo(e);
  if Assigned(linked) then begin
    if ElementType(linked) = etMainRecord then linksText := CanonicalRecordText(linked)
    else linksText := '<non-record> ' + Name(linked);
  end;
  AddMessage('NAVMI_ORPHAN_TREE|depth=' + IntToStr(depth) + '|name=' + Name(e) +
    '|base=' + BaseName(e) + '|definition=' + IntToStr(Ord(DefType(e))) +
    '|element=' + IntToStr(Ord(ElementType(e))) + '|children=' + IntToStr(n) +
    '|nativeVarType=' + nativeTypeText + '|native=' + NativeText(e) +
    '|edit=' + editText + '|record=' + CanonicalRecordText(e) +
    '|links=' + linksText + '|path=' + FullPath(e));
  for i := 0 to n - 1 do DumpStockOrphanTree(ElementByIndex(e, i), depth + 1, nodes);
end;

'''

PARENT=r'''  parentElement := Req(info, 'PathingCell\Parent');
  // Exact4.1.5f wbNAVIParentDecider: null Parent Worldspace selects the
  // scalar Parent Cell definition. UnionDoInit does NOT allocate a child
  // for scalar unions; NativeValue/LinksTo delegate to the resolved scalar.
  Need(DefType(parentElement) = dtUnion, 'Known stock orphan parent union definition changed' + StockFieldContext(parentElement, 'dtUnion/zero-child scalar CELL'));
  Need(ElementType(parentElement) = etUnion, 'Known stock orphan parent element type changed' + StockFieldContext(parentElement, 'etUnion'));
  Need(ElementCount(parentElement) = 0, 'Known stock orphan parent scalar union gained children' + StockFieldContext(parentElement, '0children'));
  Need(GetNativeValue(parentElement) = $00028E34, 'Known stock orphan parent cell native value changed' + StockFieldContext(parentElement, '00028E34'));
  parentCell := LinksTo(parentElement);
  Need(Assigned(parentCell), 'Known stock orphan parent Cell link unresolved' + StockFieldContext(parentElement, 'Skyrim.esm|028E34'));
  Need(ElementType(parentCell) = etMainRecord, 'Known stock orphan parent link is not a record');
  Need(Signature(parentCell) = 'CELL', 'Known stock orphan parent link is not CELL');
  parentCell := MasterOrSelf(parentCell);
  Need(SameText(GetFileName(GetFile(parentCell)), 'Skyrim.esm') and
    (GetLoadOrderFormID(parentCell) = $00028E34),
    'Known stock orphan parent canonical identity changed: ' + CanonicalRecordText(parentCell));
'''


def pin(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    old_manifest=OWN/'stock_orphan_lookup_fix_manifest_v4.json'
    prior=json.loads(old_manifest.read_text('utf-8'))
    archive=OWN/'frozen/stock_orphan_v4_before_v5'
    assert not archive.exists(),'Already authored; inspect immutable v5 manifest'
    archive.mkdir(parents=True)
    (archive/(old_manifest.name+'.frozen.txt')).write_bytes(old_manifest.read_bytes())
    rows=[];diffs=[]
    for row in prior['files']:
        p=Path(row['after']['path']);assert pin(p)['sha256']==row['after']['sha256']
        old=p.read_text('utf-8');backup=archive/(p.name+'.frozen.txt');backup.write_bytes(p.read_bytes())
        new=old.replace('var stockOrphanGuardChecked: Boolean;',
                        'var stockOrphanGuardChecked, stockOrphanTreeDumped: Boolean;',1)
        new=new.replace('function IsKnownStockOrphan(info: IInterface): Boolean;',DUMP+'function IsKnownStockOrphan(info: IInterface): Boolean;',1)
        new=new.replace('  owner, recordElement, keyElement, mergeElement, parentElement: IInterface;',
                        '  owner, recordElement, keyElement, mergeElement, parentElement, parentCell: IInterface;',1)
        at=new.index('function IsKnownStockOrphan')
        tail=new[at:];assert tail.count('  i: Integer;')>=1
        tail=tail.replace('  i: Integer;','  i, dumpNodes: Integer;',1);new=new[:at]+tail
        needle='  // All fields of the original49-byte NVMI are checked, not its ordinal.'
        insertion="""  if not stockOrphanTreeDumped then begin
    AddMessage('NAVMI_ORPHAN_TREE_BEGIN|Skyrim.esm|028E37|ALL12FIELDS_BEFORE_GUARDS');
    dumpNodes := 0; DumpStockOrphanTree(info, 0, dumpNodes);
    AddMessage('NAVMI_ORPHAN_TREE_COMPLETE|NODES=' + IntToStr(dumpNodes));
    stockOrphanTreeDumped := True;
  end;
"""
        assert new.count(needle)==1;new=new.replace(needle,insertion+needle,1)
        start=new.index("  parentElement := Req(info, 'PathingCell\\Parent');")
        end=new.index("  AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_FULL_TYPED_GUARD_PASS",start)
        new=new[:start]+PARENT+new[end:]
        needle='  stockOrphanGuardChecked := False;'
        assert new.count(needle)==1;new=new.replace(needle,needle+' stockOrphanTreeDumped := False;',1)
        for a,b in [('procedure AssertNativeByteVector','procedure AssertTree'),
                    ('function StockSingleLE','function IsKnownStockOrphan')]:
            # v5 only inserts the diagnostic walker after the Single helpers.
            old_piece=old[old.index(a):old.index(b)]
            if a=='function StockSingleLE':new_piece=new[new.index(a):new.index('procedure DumpStockOrphanTree')]
            else:new_piece=new[new.index(a):new.index(b)]
            assert old_piece==new_piece
        p.write_text(new,encoding='utf-8',newline='\n')
        rows.append({'before':row['after'],'frozen_before':pin(backup),'after':pin(p)})
        diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(backup),tofile=str(p)))
    diff=OWN/'stock_orphan_union_v5.diff';diff.write_text(''.join(diffs),encoding='utf-8',newline='\n')
    log=BASE/'UnifiedSkyrim/validation/fc_navigation_v4/logs/xedit.log'
    text=log.read_text('utf-8-sig')
    witnesses=[l for l in text.splitlines() if l.startswith('NAVMI_ORPHAN_FLOAT_SINGLE|')]
    assert len(witnesses)==3
    for line in witnesses:
        actual=re.search(r'actualLE=([0-9A-F]{8})',line).group(1)
        expected=re.search(r'expectedLE=([0-9A-F]{8})',line).group(1)
        assert actual==expected
    report={'schema':'skyrim.bounded_navi_orphan_lookup_fix.v3','utc':datetime.now(timezone.utc).isoformat(),
            'revision':5,'status':'AUTHORING_V5_COMPLETE_SUBTREE_DUMP_EXACT_SCALAR_UNION_NATIVE_EXECUTION_PENDING',
            'previous_manifest':pin(old_manifest),'files':rows,'patcher':pin(__file__),'diff':pin(diff),
            'v4_actual_single_witness':{'log':pin(log),'rows':witnesses,
                'result':'All3 actual native and literal VarType5; their Double values differ, but WriteSingle produces exact original4bytes. No Jv literal type coercion is inferred.'},
            'source_semantics':[
                {'path':str(BASE/'integration/research/feature_conflicts/source_4_1_5f/wbDefinitionsTES5.pas'),'lines':[1922,1945,8215,8220],
                 'fact':'Null Parent Worldspace resolves Parent union to scalar CELL FormID.'},
                {'path':str(BASE/'integration/research/feature_conflicts/source_4_1_5f/wbImplementation.pas'),'lines':[21595,21631],
                 'fact':'UnionDoInit creates no child element for a scalar resolved definition; it delegates to ValueDoInit.'},
                {'path':str(BASE/'integration/research/feature_conflicts/source_4_1_5f/wbInterface.pas'),'lines':[20117,20126,20330,20336],
                 'fact':'Resolved union directly delegates LinksTo and NativeValue to its selected scalar definition.'}],
            'diagnostic_scope':'First matching original source orphan only, before12field guards, recursive bounded full subtree; Name/BaseName/DefType/ElementType/count/VarType/native/edit/canonicalLinks/record/path for every node.',
            'unchanged_guards':['All12 exact typed NVMI fields still reconstruct original49bytes; 3 strict Single byte checks unchanged.','Source SkyrimSHA+actualVFSCRC, NAVI/key/owner guard, rawvalue028E34 and now resolved canonical CELL target, all other nil/duplicate/target guards remain strict.','No0-or1 union fallback: require exact dtUnion etUnion zero-child scalar layout from pinned source.','Full nontarget binary/typed NAVI preservation and Check diagnostics remain mandatory.'],
            'limits':['v4 dispatched PAS/log/result untouched; only four research authoring files changed.','No runtime/profile/plugin or rev9 edit; native v5 execution still required.']}
    for r in report['source_semantics']:r['sha256']=pin(r['path'])['sha256']
    manifest=OWN/'stock_orphan_lookup_fix_manifest_v5.json'
    manifest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    freeze=OWN/'frozen/stock_orphan_v5';freeze.mkdir(parents=True)
    frozen=[]
    for p in [Path(r['after']['path']) for r in rows]+[manifest,Path(__file__)]:
        copy=freeze/(p.name+'.frozen.txt');copy.write_bytes(p.read_bytes());frozen.append(pin(p)|{'frozen_source_copy':str(copy)})
    index=OWN/'stock_orphan_v5_tools_frozen.json';index.write_text(json.dumps({'status':report['status'],'files':frozen},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'manifest':pin(manifest),'freeze':pin(index)},indent=2))


if __name__=='__main__':main()
