"""Generate the second bounded metadata patch; navigation stays separately owned."""
from pathlib import Path
import collections
import json
import sys

sys.dont_write_bytecode = True
from analyze_fields import BASE, OUT, scan, canonical
from build_compat_plan import file_guard, quote, sha
from comparator_scope import current_scope, statements as comparator_statements
from placement_contract import build as build_placement_contract, pascal_dispatch

PATCH = 'Database Quest Feature Compatibility.esp'
NAV_PATCH = 'Database Forgotten City USSEP Navigation.esp'


def main():
    raw = json.loads((OUT / 'raw_field_comparison.json').read_text(encoding='utf-8'))
    priority = json.loads((OUT / 'compat_patch_plan.json').read_text(encoding='utf-8'))
    fc = next(f for f in raw['features'] if f['plugin'] == 'ForgottenCity.esp')
    zero = next(f for f in raw['features'] if f['plugin'] == '[LongShou]WorldInPainting_ZeroHall.esp')
    all_features = {f['plugin']: f for f in raw['features']}
    rows = []
    files = {}
    for name in ('ForgottenCity.esp', 'Forgotten City Music Fix.esp', '[LongShou]WorldInPainting_ZeroHall.esp', '[longshou]UF6.esp'):
        g = file_guard(all_features[name]['path'])
        files[g['filename'].casefold()] = g
    for f in (fc, zero):
        for r in f['override_records']:
            if r['signature'] in ('NAVI', 'NAVM'): continue
            k = (r['origin'], int(r['object_id'], 16))
            assert r['base_record']
            source_authored = f is fc and r['signature'] in ('REFR', 'ARMA', 'HDPT', 'FLST') and r['object_id'] != '071A05'
            if source_authored:
                # All these source-authored global records compete only with
                # their exact coherent-stock origin, not another TuLED edit.
                assert not r['canonical_base_from_vanilla'], (r['object_id'], r['canonical_base_from_vanilla'])
            path = f['path'] if source_authored else r['base_record']['path']
            p, _, _ = scan(path, wanted={k})
            rows.append({'origin': k[0], 'object_id': r['object_id'], 'signature': r['signature'],
                         'mode': 'source_authored_record' if source_authored else 'base_record',
                         'base_file': r['base_record']['plugin'], 'seed_file': f['plugin'] if source_authored else r['base_record']['plugin'],
                         'seed_path': path, 'seed_semantic_sha256': sha(canonical(p[k])),
                         'allowed_fields': ['Conditions'] if r['signature'] == 'INFO' else [],
                         'field_source': 'ForgottenCity.esp' if r['signature'] == 'INFO' else None})
            g = file_guard(path); files[g['filename'].casefold()] = g
            g = file_guard(r['base_record']['path']); files[g['filename'].casefold()] = g
    rank = {'WRLD': 0, 'CELL': 1, 'DIAL': 2}
    rows.sort(key=lambda r: (rank.get(r['signature'], 3), r['origin'], r['object_id']))
    assert len(rows) == 27 and sum(r['mode'] == 'source_authored_record' for r in rows) == 11
    excluded = sorted(set(priority['excluded_from_base_winner_search']) | {PATCH, NAV_PATCH}, key=str.casefold)
    plan = {'patch': PATCH, 'status': 'field-audited draft, not xEdit executed', 'record_count': len(rows), 'own_records': 0,
            'rows': rows, 'input_file_guards': sorted(files.values(), key=lambda g: g['filename'].casefold()),
            'excluded_from_base_winner_search': excluded,
            'preserve_source_untouched': ['all feature-own records, including repaired UF6 override of ZeroHall|000D68',
                'UF6 deletion of Dragonborn|03A741 empty stock stub; no evidence it is an active Dragonborn door, so do not invent a fix or undelete it'],
            'required_separate_navigation': str(BASE / 'integration/research/forgotten_city_navigation/README.md'),
            'order': 'After all source plugins and the priority metadata patch; before bounded Forgotten City navigation builder so it can forward the final CELL 007644 metadata.',
            'scope': '16 base-preserving records plus 11 source-authored global records with no TuLED field opponent; FC INFO merges source Conditions with base VMAD/text/PNAM. No NAVM/NAVI or new own records.'}
    comparator=current_scope(priority=priority,quest=plan)
    plan['input_file_guards']=comparator['input_file_guards']
    plan['comparator_self_audit']={'scope':str(OUT/'comparator_self_audit_scope.json'),'exact_scope_rows':len(comparator['exact_records']),
        'visible_parent_rows':len(comparator['visible_source_parents']),'rule':'Audit all source leaves e-vs-e before any patch creation; report every unsupported leaf then fail one summary.'}
    (OUT / 'quest_extension_plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    template = (OUT / 'compatibility_template.pas').read_text(encoding='utf-8')
    helper = template[:template.index('function FindListItem(')]
    helper = helper.replace('@@PATCH@@', PATCH).replace('@@OUTPUT@@', str(OUT / 'candidate' / PATCH))
    helper = helper.replace('@@COMPARATOR_SCOPE@@',comparator_statements(comparator,quote))
    helper = helper.replace('@@REF_PLACEMENT_DISPATCH@@',pascal_dispatch(build_placement_contract(priority,plan),quote))
    helper = helper.replace('@@EXCLUDED@@', '\n'.join('    SameText(n, ' + quote(n) + ') or' for n in excluded) + '\n    False')
    helper += '''
procedure SeedSource(origin: string; id: Integer; sig, baseOwner, sourceOwner: string);
var r, base, src, dst: IInterface;
begin
  r := OriginRecord(origin, id);
  base := BaseWinner(r);
  Need(SameText(GetFileName(GetFile(base)), baseOwner), 'Source-only record has an unreviewed base opponent: ' + IntToHex(id, 6));
  src := InFile(sourceOwner, r);
  Need(Signature(src) = sig, 'Source signature changed');
  if VERIFY_ONLY then dst := OutputRecord(origin, id)
  else begin
    Need(AddRequiredElementMasters(src, patchFile, False, True), 'Source required masters failed');
    dst := wbCopyElementToFile(src, patchFile, False, True);
    Need(Assigned(dst), 'Source-only typed copy failed');
    RestoreSourceHeaderMetadata(dst, src);
  end;
  AssertPayload(dst, src, 'Exact source-authored record');
  Inc(seedCount);
end;

procedure AssertRecordSet;
var i, payloadCount: Integer; r: IInterface;
begin
  payloadCount := 0;
  for i := 0 to RecordCount(patchFile) - 1 do begin
    r := RecordByIndex(patchFile, i);
    if Signature(r) <> 'TES4' then begin
      Inc(payloadCount);
      Need(not SameText(GetFileName(GetFile(MasterOrSelf(r))), PATCH_NAME), 'Unexpected own record');
      Need((Signature(r) <> 'NAVM') and (Signature(r) <> 'NAVI'), 'Unexpected navigation record');
      Need(Check(r) = '', 'Native Check failed: ' + Name(r) + ' | ' + Check(r));
    end;
  end;
  Need(payloadCount = 27, 'Unexpected output record count');
  Need(MasterCount(patchFile) <= 253, 'Conservative master limit exceeded');
end;

procedure PostRecordSet;
begin
  PostBegin;
  try AssertRecordSet;
  except PostFailure('Exact output record set and native Check'); end;
end;

function Initialize: Integer;
var stream: TFileStream;
begin
  Result := 1;
  seedCount := 0;
  postChecks := 0; postFailures := 0; postVerificationPhase := False;
'''
    for g in plan['input_file_guards']:
        helper += f"  GuardFile({quote(g['filename'])}, {quote(g['crc32'])});\n"
    for n in priority['must_not_be_loaded']:
        helper += f"  Need(not Assigned(FileByName({quote(n)})), {quote('Excluded plugin loaded: ' + n)});\n"
    helper += '  RequireNormalDefinitions;\n  RunComparatorSelfAudit;\n'
    helper += '''  if VERIFY_ONLY then patchFile := ReqFile(PATCH_NAME)
  else begin
    Need(not Assigned(FileByName(PATCH_NAME)), 'Patch already loaded');
    Need(not FileExists(DataPath + PATCH_NAME), 'Patch exists in VFS; refuse overwrite');
    Need(not FileExists(OUTPUT_FILE), 'Candidate exists; refuse overwrite');
    patchFile := AddNewFileName(PATCH_NAME);
    Need(Assigned(patchFile), 'New in-memory plugin failed');
  end;
'''
    for r in rows:
        args = f"{quote(r['origin'])}, ${r['object_id']}, {quote(r['signature'])}, {quote(r['base_file'])}"
        if r['mode'] == 'source_authored_record':
            helper += f"  SeedSource({args}, {quote(r['seed_file'])});\n"
        else:
            helper += f"  Seed({args});\n"
    helper += "  if not VERIFY_ONLY then ForwardField('ForgottenCity.esp', 'skyrim.esm', $071440, 'Conditions');\n"
    helper += "  if not VERIFY_ONLY then begin\n    SortMasters(patchFile);\n    SetIsESL(patchFile, True);\n"
    for r in rows:
        helper += f"    RestoreSeedMetadata({quote(r['origin'])}, ${r['object_id']}, {quote(r['seed_file'])});\n"
    helper += "  end;\n"
    helper += "  postVerificationPhase := True;\n"
    for r in rows:
        if r['mode'] == 'source_authored_record':
            helper += f"  PostExactSource({quote(r['seed_file'])}, {quote(r['origin'])}, ${r['object_id']});\n"
        else:
            allow = '|' + '|'.join(r['allowed_fields']) + '|'
            helper += f"  PostMerged({quote(r['origin'])}, ${r['object_id']}, {quote(r['base_file'])}, {quote(allow)}, False);\n"
    helper += '''  PostForwarded('ForgottenCity.esp', 'skyrim.esm', $071440, 'Conditions');
  PostRecordSet;
  FinishPostAssertions;
  if not VERIFY_ONLY then begin
    ForceDirectories(ExtractFilePath(OUTPUT_FILE));
    stream := TFileStream.Create(OUTPUT_FILE, fmCreate);
    try FileWriteToStream(patchFile, stream, 0);
    finally stream.Free; end;
    AddMessage('QUEST_FEATURE_CANDIDATE_EXPORTED|' + OUTPUT_FILE);
  end;
  if VERIFY_ONLY then AddMessage('QUEST_FEATURE_RELOAD_TYPED_PASS|RECORDS=27|OWN=0|NAVIGATION=0')
  else AddMessage('QUEST_FEATURE_INMEMORY_TYPED_PASS|RECORDS=27|OWN=0|NAVIGATION=0');
  Result := 0;
end;
end.
'''
    assert '@@' not in helper
    (OUT / 'DatabaseQuestFeatureCompatibilityDraft.pas').write_text(helper, encoding='utf-8')
    (OUT / 'DatabaseVerifyQuestFeatureCompatibilityDraft.pas').write_text(helper.replace('VERIFY_ONLY = False;', 'VERIFY_ONLY = True;', 1), encoding='utf-8')
    print('Quest extension: 27 existing overrides, 0 own records,', len(plan['input_file_guards']), 'file guards')


if __name__ == '__main__': main()
