"""Preserve exact v12 and author scoped FLST/post-assertion collection changes."""
from pathlib import Path
import hashlib
import json
import shutil

OUT = Path(__file__).resolve().parent


def replace_once(text, old, new):
    assert text.count(old) == 1, (old[:100], text.count(old))
    return text.replace(old, new, 1)


def main():
    manifest = json.loads((OUT / 'draft_version_manifest.v12.json').read_text())
    archive = OUT / 'version_freezes/v12'
    archive.mkdir(exist_ok=True)
    entries = []
    for row in manifest['files'][:4]:
        source = Path(row['path'])
        assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
        target = archive / source.name
        if target.exists():
            assert target.read_bytes() == source.read_bytes()
        else:
            shutil.copyfile(source, target)
        entries.append({'path': str(target), 'sha256': row['sha256']})
    shutil.copyfile(OUT / 'draft_version_manifest.v12.json', archive / 'draft_version_manifest.v12.json')
    (archive / 'manifest.v12.json').write_text(json.dumps({'version': 'v12', 'files': entries,
        'status': 'Exact prior dispatched source, not current authoring files'}, indent=2) + '\n')

    path = OUT / 'compatibility_template.pas'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, '  seedCount: Integer;', '''  seedCount: Integer;
  lastNeedFailure: string;
  postChecks, postFailures: Integer;
  postVerificationPhase: Boolean;''')
    text = replace_once(text, "  if not ok then raise Exception.Create('FEATURE_COMPAT_STOP: ' + messageText);", """  if not ok then begin
    lastNeedFailure := messageText;
    raise Exception.Create('FEATURE_COMPAT_STOP: ' + messageText);
  end;""")
    collector = '''procedure PostBegin;
begin
  Inc(postChecks);
  lastNeedFailure := '';
end;

procedure PostFailure(context: string);
begin
  Inc(postFailures);
  if lastNeedFailure = '' then
    lastNeedFailure := 'Unexpected runtime exception during this assertion; not accepted';
  AddMessage('FEATURE_POST_ASSERTION_FAILURE' + #9 + AuditClean(context) + #9 + AuditClean(lastNeedFailure));
end;

procedure PostMerged(origin: string; id: Integer; owner, allowed: string; persistent: Boolean);
var base, dst, a, b: IInterface; i, expected: Integer; t, context: string;
begin
  context := origin + '|' + IntToHex(id, 6) + ' [' + owner + ']';
  PostBegin;
  try
    base := InFile(owner, OriginRecord(origin, id));
    dst := OutputRecord(origin, id);
    Need(SameRecord(dst, base), 'Output identity mismatch');
    Need(Signature(dst) = Signature(base), 'Output signature mismatch');
    expected := GetNativeValue(Req(base, 'Record Header\\Record Flags'));
    if persistent then expected := expected or $400;
  except PostFailure(context + '/resolution'); Exit; end;
  PostBegin;
  try AssertHeader(dst, base, 'Merged header', False, expected);
  except PostFailure(context + '/Record Header'); end;
  PostBegin;
  try AssertPlannedReferencePlacement(origin, id, base, dst, persistent);
  except PostFailure(context + '/physical placement'); end;
  // Each source top-level field has its own exception boundary. A mismatch
  // never silently returns success or prevents auditing subsequent fields.
  for i := 0 to ElementCount(base) - 1 do begin
    a := ElementByIndex(base, i); t := Token(a);
    if not IsRecordHeader(a) and (Pos('|' + t + '|', allowed) = 0) then
      if not (persistent and (t = 'Cell') and (Signature(a) = '')) then begin
        PostBegin;
        try AssertPreservedField(dst, base, a, 'Preserved base ' + IntToHex(id, 6) + '/' + t);
        except PostFailure(context + '/' + t); end;
      end;
  end;
  for i := 0 to ElementCount(dst) - 1 do begin
    b := ElementByIndex(dst, i); t := Token(b);
    if not IsRecordHeader(b) and (Pos('|' + t + '|', allowed) = 0) and not IgnoredGenerated(dst, b) then begin
      PostBegin;
      try Need(Assigned(Top(base, t)), 'Unexpected added field: ' + t);
      except PostFailure(context + '/added/' + t); end;
    end;
  end;
end;

procedure PostForwarded(donor, origin: string; id: Integer; fieldText: string);
begin
  PostBegin;
  try AssertForwarded(donor, origin, id, fieldText);
  except PostFailure(origin + '|' + IntToHex(id, 6) + '/forward/' + fieldText + ' [' + donor + ']'); end;
end;

procedure PostExactSource(owner, origin: string; id: Integer);
begin
  PostBegin;
  try AssertPayload(OutputRecord(origin, id), InFile(owner, OriginRecord(origin, id)), 'Preserved source-authored record');
  except PostFailure(origin + '|' + IntToHex(id, 6) + '/source-authored [' + owner + ']'); end;
end;

procedure FinishPostAssertions;
begin
  AddMessage('FEATURE_POST_ASSERTIONS_COMPLETED' + #9 + IntToStr(postChecks) + #9 + IntToStr(postFailures));
  Need(postFailures = 0, 'Post-merge assertions failed: ' + IntToStr(postFailures) + '; candidate export prohibited');
end;

'''
    text = replace_once(text, 'function FindListItem(', collector + 'function FindListItem(')
    text = replace_once(text, "  if not VERIFY_ONLY then begin\n    Need(not Assigned(FindListItem(dstList, hoth))", "  if (not VERIFY_ONLY) and (not postVerificationPhase) then begin\n    Need(not Assigned(FindListItem(dstList, hoth))")
    text = replace_once(text, '  if VERIFY_ONLY then begin\n    ownPacks := 0;', '  if VERIFY_ONLY or postVerificationPhase then begin\n    ownPacks := 0;')
    specials = '''procedure PostSpecials;
begin
  PostBegin;
  try HothVoiceUnion;
  except PostFailure('Skyrim.esm|03B4A5/Hoth exact voice union'); end;
  PostBegin;
  try SofiaHorseIsolation;
  except PostFailure('Sofia exact PACK clone, unique Alias1 redirect and global PACK restore'); end;
end;

procedure PostRecordSet;
begin
  PostBegin;
  try AssertRecordSet;
  except PostFailure('Exact output record set and native Check'); end;
end;

'''
    text = replace_once(text, 'function Initialize: Integer;', specials + 'function Initialize: Integer;')
    text = replace_once(text, '  seedCount := 0;', '  seedCount := 0;\n  postChecks := 0; postFailures := 0; postVerificationPhase := False;')
    text = replace_once(text, '  HothVoiceUnion;\n  SofiaHorseIsolation;', '  if not VERIFY_ONLY then begin\n    HothVoiceUnion;\n    SofiaHorseIsolation;\n  end;')
    text = replace_once(text, '@@VERIFY@@\n@@VERIFY_FIELDS@@\n  AssertRecordSet;', '''  postVerificationPhase := True;
@@VERIFY@@
@@VERIFY_FIELDS@@
  PostSpecials;
  PostRecordSet;
  FinishPostAssertions;''')
    path.write_text(text, encoding='utf-8')

    path = OUT / 'build_compat_plan.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, "old['allowed_fields'].add('FormIDs')", "old['allowed_fields'].update(('FormIDs', 'LNAM'))  # exact FLST RArray signature in pinned 4.1.5f")
    text = text.replace('f"  AssertMerged(', 'f"  PostMerged(').replace('f"  AssertForwarded(', 'f"  PostForwarded(')
    path.write_text(text, encoding='utf-8')

    path = OUT / 'build_quest_extension.py'
    text = path.read_text(encoding='utf-8')
    text = replace_once(text, 'function Initialize: Integer;', '''procedure PostRecordSet;
begin
  PostBegin;
  try AssertRecordSet;
  except PostFailure('Exact output record set and native Check'); end;
end;

function Initialize: Integer;''')
    text = replace_once(text, '  seedCount := 0;', '  seedCount := 0;\n  postChecks := 0; postFailures := 0; postVerificationPhase := False;')
    text = replace_once(text, '    for r in rows:\n        if r[\'mode\'] == \'base_record\':\n            allow =', '    helper += "  postVerificationPhase := True;\\n"\n    for r in rows:\n        if r[\'mode\'] == \'source_authored_record\':\n            helper += f"  PostExactSource({quote(r[\'seed_file\'])}, {quote(r[\'origin\'])}, ${r[\'object_id\']});\\n"\n        else:\n            allow =')
    text = text.replace('f"  AssertMerged(', 'f"  PostMerged(')
    text = replace_once(text, "helper += '''  AssertForwarded('ForgottenCity.esp', 'skyrim.esm', $071440, 'Conditions');\n  AssertRecordSet;", "helper += '''  PostForwarded('ForgottenCity.esp', 'skyrim.esm', $071440, 'Conditions');\n  PostRecordSet;\n  FinishPostAssertions;")
    path.write_text(text, encoding='utf-8')

    path = OUT / 'freeze_draft_manifest.py'
    text = path.read_text(encoding='utf-8').replace("VERSION='v12'", "VERSION='v13'")
    text = text.replace("version_freezes/v9, v10 and v11.", "version_freezes/v9, v10, v11 and v12.")
    text = replace_once(text, "'change': 'Only the normal-schema gate changes from v11: optional MHDT is replaced by pinned stock NAVM108AB4, 321triangles/269vertices, Triangle50 dtStruct8 and XYZ vertex dtStruct3. Existing strict MHDT handling,18 dedicated persistent placement contracts, all43guards/fullsource audit and four-output baseline exclusions are unchanged.',", "'change': 'Only Hoth exact FLST03B4A5 allows the pinned RArray signature LNAM alongside FormIDs. Final merged base fields, forwarded fields, source-authored quest records and special union/redirect/record-set assertions collect all scoped failures and require one zero-failure summary before export. Source/copy/mutation preconditions, strict MHDT, normal-schema gate, all43guards and18 physical placement contracts remain unchanged.',")
    text = text.replace("('v9','v10','v11')", "('v9','v10','v11','v12')")
    path.write_text(text, encoding='utf-8')
    print('v12 preserved; v13 authoring sources updated')


if __name__ == '__main__':
    main()
