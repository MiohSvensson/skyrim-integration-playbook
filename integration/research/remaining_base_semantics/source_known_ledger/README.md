# Read-only full active-plugin Check and exact diagnostic classification

`UnifiedReadOnlyFullAudit.pas` creates no plugin and calls no plugin assignment,
copy, modification or save API. Apply it to **all active loaded files** in a fresh
final-profile xEdit 4.1.5f session. The independent parser rejects selection gaps.
This agent did not compile or execute it in xEdit.

The engine's static `SkyrimSE.exe` pseudo-file is explicitly excluded from
the audit/plugin inventory and reported as `UNIFIED_IGNORED`. This is xEdit's
hardcoded-record definition source; it does not imply a game launch. The first
`UNIFIED_BEGIN` retains raw engine FileCount for traceability. `UNIFIED_SCOPE`,
per-plugin summaries and the final file count cover only real ESM/ESP/ESL files.

The initializer records each runtime file prefix with `UNIFIED_FILE`, computed
by xEdit's `FileFormIDtoLoadOrderFormID`, including light-slot indices. It reports
`RecordCount(f)+1`: exact 4.1.5f `TwbFile.AddMainRecord` indexes only non-null IDs,
so its record index excludes the TES4 header; the normal script Process traversal
and independent physical-file count include that header. Each diagnostic retains
the reporting file, readable context, Path, message, explicit canonical owner,
object ID, signature and FullPath. Each failing Check/field-traversal operation is
reported as an exception with record and field context.

`FULL_AUDIT_COMPLETED` means the Finalize function ran. It does not mean that
diagnostics are zero, that every file/record was selected, or that input hashes
matched. Final classification requires all those separate checks.

```powershell
python "E:\stock\Skyrim collection\Database\integration\research\remaining_base_semantics\source_known_ledger\classify_full_check.py" --log "<final-run>\logs\xedit.log" --input-inventory "<final-run>\input_inventory.json" --report "E:\stock\Skyrim collection\Database\integration\research\remaining_base_semantics\source_known_ledger\final_classification.json"
```

The inventory format is the existing generic producer format: a `plugins` array
of objects containing `name`, absolute physical provider `path`, and `sha256`.
The runtime file set must equal that inventory exactly. The parser rehashes every
provider and independently counts every physical main record, including TES4.
File-prefix maps, initializer/final counts, field and bad-record counts and final
markers must agree. Missing markers, exceptions, source changes, unloaded inputs,
extra files or incomplete record coverage block completion. Output files are
restricted to this research folder. Exit code 2 means the final check is blocked.

The ledger contains **1,845 exact historical cases, zero unresolved historical
identities**. Its case key is reporting plugin + canonical record owner/object
ID + signature + exact normalized field path + canonical diagnostic message.
The parser also requires the exact source-record fingerprint: ordered raw
decompressed subrecords, flags, VCS metadata, form version, master list and own
filename. A same-record label alone is insufficient. The fingerprint excludes
only serialized Data Size and compression encoding.

The historical 819-field coherent-stock TuLED run was replayed against this
classifier: **819/819** exact case and source-payload matches. It remained a
historical classification, never a final full-profile certification. Of those
historical fields, the policies identify 399 verified-repair/variant cases,
48 old generated cases, 29 excluded optional-plugin cases and 2 Rift stale
properties. The remaining categories stay distinct: 121 supported extensions,
213 other source-known semantic diagnoses, 6 alias-context cases and 1 navigation
case. These are counts from that historical run, not current final issues.

The ledger also records prior zero diagnostics with exact input hashes and
validation scope, including the actual equipment/core run of **63 targets and
4,598 records** whose per-file counts all equal physical record counts. Its log
SHA256 is `9967712df8d6f8372558bdd814199bd1f61cf80ab2a05a8907d5edfe78fbf573`.
It is not evidence that a later context or changed input remains clean.

New/unmatched errors, changed record payloads or namespace, excess diagnostic
multiplicity and repaired/disabled/generated regressions block completion.
Source-known unresolved, navigation and alias cases still require their explicit
semantic dispositions; supported extension cases remain separately identified.
No new error is broadly labelled upstream.

When a generated plugin such as Synthesis reports the same canonical record,
field and target/message as a source case, the parser separately identifies a
**possible forwarded known-field diagnostic**. It remains blocked until typed
canonical field/LinksTo comparison or a frozen builder/reload provenance proves
the exact forwarding operation. A different reporting filename is neither proof
of a new root cause nor permission to inherit a source exception.

Validation artifacts: `full_check_source_audit.json` checks only exact-tag API
availability and an explicit read-only API allowlist; `parser_validation_result.json`
tests six labelled fixtures using real plugin bytes (clean-complete acceptance;
missing marker, record gap, changed SHA, unmatched error, names-only prefix map
rejection). `parser_validation/historical_819_classification.json` records the
independent historical 819-field reconciliation. Fixtures are not xEdit runs.

Primary source is the frozen exact tag in
`research/feature_conflicts/source_4_1_5f/provenance.json`, commit
`f5c00f3fa3ee39511185515802647246c807f759`. Relevant code:
`xejviScriptAdapter.pas` 569–577 (Check), 1554–1570 (RecordCount/RecordByIndex),
1650–1656 (runtime FormID conversion); `wbImplementation.pas` 2316–2368
(only non-null IDs indexed), 4325–4328 (RecordCount); `xeMainForm.pas`
8300–8362 and 8448–8467 (Process selection and Finalize execution).

No game/runtime validation is claimed.
