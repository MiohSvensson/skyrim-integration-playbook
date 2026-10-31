"""Keep exact source Single bits; add diagnostics for xEdit native rounding.

Only four research authoring PAS are changed. v3 dispatched scripts/results and
the original guarded sources are retained. No runtime/profile/plugin edit.
"""
from datetime import datetime,timezone
import difflib
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[3]

SINGLE_HELPERS=r'''function StockFieldContext(e: IInterface; expectedText: string): string;
begin
  Result := ' | record=' + CanonicalRecordText(e) + ' path=' + FullPath(e) +
    ' actualNative=' + NativeText(e) + ' edit=' + GetEditValue(e) +
    ' nativeVarType=' + IntToStr(VarType(GetNativeValue(e))) +
    ' definition=' + IntToStr(Ord(DefType(e))) +
    ' element=' + IntToStr(Ord(ElementType(e))) + ' expected=' + expectedText;
end;

function StockSingleLE(value: Variant; seedElement: IInterface): string;
var stream: TBytesStream; writer: TBinaryWriter; reader: TBinaryReader; i: Integer;
begin
  Result := '';
  Need(VarType(GetNativeValue(seedElement)) = 8209, 'Single witness seed is not native Array Byte');
  stream := TBytesStream.Create(GetNativeValue(seedElement));
  try
    Need(stream.Size = 4, 'Single witness seed size is not4');
    stream.Position := 0; writer := TBinaryWriter.Create(stream);
    try
      // Exact4.1.5f binding xejviScriptAdapterMisc:793-795 /2077:
      // WriteSingle explicitly casts to IEEE754 Single; no decimal tolerance.
      writer.WriteSingle(value);
      Need(stream.Size = 4, 'Single witness serialized size is not4');
      stream.Position := 0; reader := TBinaryReader.Create(stream);
      try
        for i := 0 to 3 do Result := Result + IntToHex(reader.ReadByte, 2);
        Need(stream.Position = 4, 'Single witness read incomplete');
      finally reader.Free; end;
    finally writer.Free; end;
  finally stream.Free; end;
end;

procedure AssertStockSingle(info: IInterface; fieldName: string;
  expectedLiteral: Variant; expectedLE: string);
var e,seed: IInterface; actualLE,literalLE,literalText,contextText: string;
begin
  e := Req(info, fieldName); seed := Req(info, 'Preferred Merges Flag');
  literalText := expectedLiteral;
  contextText := StockFieldContext(e, expectedLE) + ' literal=' + literalText +
    ' literalVarType=' + IntToStr(VarType(expectedLiteral));
  AddMessage('NAVMI_ORPHAN_FLOAT_INPUT|' + fieldName + contextText);
  Need(DefType(e) = dtFloat, 'Known stock orphan float definition changed' + contextText);
  Need(VarType(GetNativeValue(e)) = 5, 'Known stock orphan float native Variant is not Double' + contextText);
  actualLE := StockSingleLE(GetNativeValue(e), seed);
  literalLE := StockSingleLE(expectedLiteral, seed);
  AddMessage('NAVMI_ORPHAN_FLOAT_SINGLE|' + fieldName + '|actualLE=' + actualLE +
    '|literalLE=' + literalLE + '|expectedLE=' + expectedLE + contextText);
  // wbInterface:71/16324-16332/16643-16647/16689-16703 round native
  // Single fields to6decimal places. Decimal literal equality is not a raw
  // serialized-Single test. Require every source Single byte here instead.
  Need(SameText(actualLE, expectedLE), 'Known stock orphan ' + fieldName +
    ' serialized Single bytes changed actual=' + actualLE + ' expected=' + expectedLE + contextText);
end;

'''


def pin(path):
    path=Path(path).resolve();return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    old_manifest=OWN/'stock_orphan_lookup_fix_manifest.json'
    previous=json.loads(old_manifest.read_text('utf-8'))
    archive=OWN/'frozen/stock_orphan_v3'
    assert not archive.exists(),'Already prepared; inspect immutable v4 manifest'
    archive.mkdir(parents=True)
    for p in [old_manifest,OWN/'stock_orphan_fix_static_verification.json']:
        (archive/(p.name+'.frozen.txt')).write_bytes(p.read_bytes())
    rows=[];diffs=[]
    for row in previous['after']:
        path=Path(row['path']);assert pin(path)['sha256']==row['sha256']
        old=path.read_text('utf-8');backup=archive/(path.name+'.frozen.txt');backup.write_bytes(path.read_bytes())
        new=old.replace('function IsKnownStockOrphan(info: IInterface): Boolean;',SINGLE_HELPERS+'function IsKnownStockOrphan(info: IInterface): Boolean;',1)
        assert new.count('function StockSingleLE(')==1
        for name,literal,bits in [('X','-3391.8515625','A0FD53C5'),('Y','285.758941650390625','25E18E43'),('Z','239.091033935546875','4E176F43')]:
            a=f"  Need(GetNativeValue(Req(info, '{name}')) = {literal}, 'Known stock orphan {name} changed');"
            b=f"  AssertStockSingle(info, '{name}', {literal}, '{bits}');"
            assert new.count(a)==1;new=new.replace(a,b)
        new=new.replace('NAVMI_KNOWN_STOCK_ORPHAN_LOOKUP_ONLY|','NAVMI_KNOWN_STOCK_ORPHAN_CRC_GUARD_ONLY|',1)
        # Every remaining scalar guard retains exact equality and gains native
        # type/definition/path diagnostics rather than a generic stop message.
        replacements={
          "'Known stock orphan category changed'":"'Known stock orphan category changed' + StockFieldContext(Req(info, 'Category'), '0')",
          "'Known stock orphan island changed'":"'Known stock orphan island changed' + StockFieldContext(Req(info, 'Is Island'), '0')",
          "'Known stock orphan path CRC changed'":"'Known stock orphan path CRC changed' + StockFieldContext(Req(info, 'PathingCell\\CRC Hash'), 'A5E9A03C')",
          "'Known stock orphan world changed'":"'Known stock orphan world changed' + StockFieldContext(Req(info, 'PathingCell\\Parent Worldspace'), '0')",
          "'Known stock orphan parent cell changed'":"'Known stock orphan parent cell changed' + StockFieldContext(parentElement, '00028E34')",
        }
        for a,b in replacements.items():assert new.count(a)==1;new=new.replace(a,b)
        a="  Result := True;\nend;\n\nfunction InfoFor"
        b="  AddMessage('NAVMI_KNOWN_STOCK_ORPHAN_FULL_TYPED_GUARD_PASS|Skyrim.esm|028E37');\n  Result := True;\nend;\n\nfunction InfoFor"
        assert new.count(a)==1;new=new.replace(a,b)
        before=old[old.index('procedure AssertNativeByteVector'):old.index('procedure AssertTree')]
        after=new[new.index('procedure AssertNativeByteVector'):new.index('procedure AssertTree')]
        assert before==after
        path.write_text(new,encoding='utf-8',newline='\n')
        rows.append({'before':row,'frozen_before':pin(backup),'after':pin(path)})
        diffs.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=str(backup),tofile=str(path)))
    diff=OWN/'stock_orphan_single_witness_v4.diff';diff.write_text(''.join(diffs),encoding='utf-8',newline='\n')
    x=[(-3391.8515625,'a0fd53c5'),(285.758941650390625,'25e18e43'),(239.091033935546875,'4e176f43')]
    witnesses=[]
    for value,bits in x:
        rounded=round(value,6)
        assert rounded!=value and struct.pack('<f',rounded).hex()==bits==struct.pack('<f',value).hex()
        witnesses.append({'original_f32':value,'original_as_integer_ratio':list(value.as_integer_ratio()),
                          'rounded_native_model':rounded,'native_equals_original_literal':rounded==value,
                          'strict_WriteSingle_LE_hex':bits,'same_exact_serialized_Single':True})
    report={'schema':'skyrim.bounded_navi_orphan_lookup_fix.v2','utc':datetime.now(timezone.utc).isoformat(),
            'revision':4,'status':'AUTHORING_V4_EXACT_SINGLE_WITNESS_AND_DIAGNOSTICS_NATIVE_EXECUTION_PENDING',
            'previous_manifest':pin(old_manifest),'source_orphan_audit':pin(OWN/'final_navi_key_audit.json'),
            'files':rows,'patcher':pin(__file__),'diff':pin(diff),
            'pinned_source_evidence':[
                {'path':str(BASE/'integration/research/feature_conflicts/source_4_1_5f/wbInterface.pas'),'lines':[71,16324,16329,16643,16645,16689,16703],
                 'finding':'Default wbFloatDigits6 substituted for negative default digits; ToNativeValue returns ToValue after RoundToEx.'},
                {'path':str(BASE/'integration/research/feature_conflicts/source_4_1_5f/xejviScriptAdapterMisc.pas'),'lines':[793,795,2077],
                 'finding':'Author-provided WriteSingle casts Variant to Single then writes4bytes; explicitly registered in actual4.1.5f script API.'}],
            'exact_single_witnesses':witnesses,'native_vector_comparators_unchanged':True,
            'unchanged_constraints':['Exact source Skyrim.esm SHA+injected VFS CRC, originalNAVICanonicalID, soleorphanNativeID, all12NVMI fields/counts/merge bytes/pathing values, no output copy allowance.','Other nil keys/duplicate targets/missing requested targets remain fatal.','Full nontarget NAVI binary/typed preservation and Check diagnostics still required.'],
            'diagnostic_policy':'Log native value/display/Variant/DefType/ElementType/canonical record/fullpath and decimal-literal Variant, then exact actual/literal/expected Single bytes. CRC-only and full-typed-pass messages are distinct.',
            'limits':['No v3 dispatched/runtime/profile/plugin/source-float bytes changed.','Jv literal VarType is not inferred until actual v4 log. Source-native rounding is independently present in pinned code; direct literal checks are replaced by strict serialized-Single-byte checks with zero tolerance.','Root must fresh-run builder, independent binary after-check and installed fresh typed reload.']}
    for row in report['pinned_source_evidence']:row['sha256']=pin(row['path'])['sha256']
    path=OWN/'stock_orphan_lookup_fix_manifest_v4.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(pin(path),indent=2))


if __name__=='__main__':main()
