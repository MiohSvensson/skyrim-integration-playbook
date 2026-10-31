# Comparator source-type preflight

`DatabaseComparatorSelfAuditDraft.pas` is a standalone read-only script. It has
no patch name and no plugin creation, assignment, copy, save or export API.
Initialize directly enumerates the frozen scope; selecting records in the UI
does not restrict that scope. This research agent did not launch xEdit.

The scope is the union of both plans: 43 input guards, 239 exact base/donor/
Sofia quest and clone-PACK record rows, plus 107 source-visible WRLD/CELL/DIAL
parent rows. Visible parents may legitimately resolve to a master provider;
the actual provider and canonical identity are logged. Actual records are
deduplicated by canonical identity and provider. `comparator_self_audit_scope.json`
contains the complete machine-readable scope and source hashes.

Every source leaf, including a defined zero-child array or struct, is compared
with itself by the exact same AssertTree used in both builders/verifiers.
Failures are caught per leaf; traversal/lookup failures are separately logged.
The remaining records are still examined. The script reports all unsupported
cases, one sample and total counts for each DefType/ElementType/native VarType
combination, and the completed record/leaf/failure totals. A failure count above
zero produces a single final STOP after collecting the whole scope.

`COMPARATOR_SELF_AUDIT_COMPLETED` means traversal ended, not that it passed.
Only zero failures followed by `COMPARATOR_SELF_AUDIT_PASSED` is successful
comparator type coverage. It is not compatibility or game-runtime validation.

Both producer and reload-verifier Initialize functions run the same entire
preflight after all input CRC checks. The producer invokes it before
`AddNewFileName`, so an unsupported source kind cannot create an incomplete
patch. Existing assertions remain strict after copies and intended merges.

Zero-child containers are structurally compared after matching BaseName,
DefType, ElementType, signature and count. Only explicitly defined array,
struct and chapter containers qualify. A zero-child scalar or unknown union
does not acquire an exception. The real USSEP `Skyrim.esm|095123` empty
Properties array and exact source definitions are recorded in
`empty_container_evidence.json`.

The standalone script is generated from the producer's common helper block.
`comparator_self_audit_manifest.json` records its SHA and verifies all plugin
mutation/export calls are absent. API availability is statically checked in
`pascal_api_audit.json`; actual compilation and execution remain necessary.
