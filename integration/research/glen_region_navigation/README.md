# Glenmoril bounded navigation composition

Status: exact-source static composition and source preflight passed. The Pascal builder and verifier are frozen drafts for xEdit 4.1.5f normal definitions; they have not been compiled or executed here. No plugin was created by this research task. No game, GUI, MO2, source plugin, or shared script directory was opened for writing.

The current PAS files are the **v6 exact-source orphan-guard revision**, pinned by `../plugin_integration/navi_unresolved_audit/stock_orphan_lookup_fix_manifest_v6.json`. `generate_drafts.py` and the older header/native-vector receipts are historical baseline evidence only. Do not rerun that generator over the current drafts; it would remove the v4–v6 fixes. Start any further revision from the v6 frozen copies.

This **single candidate supersedes the earlier AK-only candidate** in `../navmesh_patch`. Do not enable both. It adds four authored door connections across three NAVMs:

| Skyrim NAVM | Selected final base | Exact Glen face -> base face | Authored Glen door |
|---|---|---|---|
| 016F5D | AKSkyrimUnderground.esm | 502 -> 502 | 0122F4 |
| 0EC466 | AncientLand2.esp | 34 -> 34 | 014C1D |
| 0EC469 | RedBag's Falkreath.esp | 116 -> 116 | 0073D4 |
| 0EC469 | RedBag's Falkreath.esp | 325 -> **86** | 017737 |

Every mapped face has exactly the same three IEEE-754 coordinates and winding, with one unique destination face. **Do not forward Glen triangle 325 as ordinal 325 into RedBag.** The retained base face is 86. Entire base vertices, internal and external adjacency, cover, grid, pathing and all other flags remain unchanged. Only Door bit 1024 is ORed onto the four mapped faces. Complete typed Glen Door Triangle entries are transferred with their authored CRC and resolved REFR, changing only the mapped triangle ordinal.

The selected components contain 532/349/312 faces, all reachable from their door faces through internally reciprocal shared geometric edges. Their retained base exits are respectively 2 existing doors / 16 external portals / 17 external portals. There are no deleted or water faces in these components. This proves preservation of existing static connectivity; it does not prove in-game collision, actor movement or quest execution.

For each target NVMI, retain the complete selected base NVMI and append only the relevant authored Glen Door Links. RedBag's 0EC469 has four retained neighboring NAVMs; Glen's older seven-neighbor NVMI must not replace it. Coordinates, preferred merge, island geometry and CRCs are copied from the relevant author data, never invented. All unrelated final-winning NVMI entries, NVPP and NVSI are preserved.

The candidate is ESL-flagged but contains **zero own records**. Eight existing Skyrim overrides are expected: three NAVM, three parent CELL (`016D72`, `009CA3`, `009CA0`), one final-winning Tamriel WRLD `00003C`, and NAVI `012FB4`. Copying the exterior hierarchy necessarily creates WRLD/CELL containers; current final gameplay payloads are explicitly forwarded. `CopyOverride` uses `wbCopyElementToFile(..., False, True)` because deep-copy=False creates an empty main-record shell. xEdit's separate child groups are not copied by its main-record field assignment. Source VCS1, VCS2 and FormVersion are restored because xEdit assignment otherwise resets the author stamps.

The exact 4.1.5f schema marks WRLD RNAM/Large References and OFST as `dfNoCopyAsOverride`, so those two generated tables may be omitted by the copy; if present they must equal the original typed data. **MHDT is not marked no-copy in 4.1.5f and is compared strictly.** The latest-main schema is different and must not supply this exception list. Interior CELL XCLW alone is excluded under the exact `wbCELLXCLWGetConflictPriority` condition (DATA Interior bit 1), because the game does not use interior water height; exterior XCLW remains strict. No other missing, extra or changed parent payload is accepted.

## Execution and evidence chain

1. Re-run `python verify_navigation_candidate.py`. Optional `--vanilla`, `--glen`, `--ak`, `--ancientland`, `--redbag` permit source paths relocated into the private final instance, but SHA-256 must remain equal to `comparison.json`. A mismatched source stops the process.
2. The final profile must place Glenmoril.esm **before AKSkyrimUnderground.esm** and preserve AncientLand/RedBag order. The three pre-patch NAVM winners must be AK, AncientLand, RedBag respectively. Another winner stops the builder. Glen only masters Skyrim, Update, Dawnguard and Dragonborn. Source and destination Glen door REFR payloads must also remain exactly as authored, and their teleport pair must be reciprocal.
3. Finish the broad feature compatibility patch first. If using the FC navigation patch, build/install it, then do its fresh xEdit reload and independent check **before** Glen. The Glen builder copies that final NAVI and preserves its FC entries.
4. In private xEdit 4.1.5f, ensure app-side `SSEEdit.ini` has `[Options] SimpleRecords=false` (or its documented `plugins.sseviewsettings` fallback only when app INI is absent). The `-I` argument is Skyrim.ini and does not control this setting. Do not use QuickClean to force schema.
5. Load the **complete final** profile through the isolated MO2 environment, without the old AK-only patch or this new candidate present. Run `DatabaseGlenmorilNavigationDraft.pas`. It fails closed before creation on geometry/source-order issues and exports only the named candidate under this research directory. Do not save an incomplete in-memory patch after any error. Close xEdit without saving source plugins.
6. Verify the exported candidate's filename and move/copy it into a dedicated private output mod. Enable it after the FC navigation patch and after every other patch touching NAVI or these targets. Reload the complete profile in a new xEdit process, then run `DatabaseVerifyGlenmorilNavigationDraft.pas`. Keep the full log, including `GLEN_NAV_CELL_SOURCE`, `GLEN_NAV_NAVI_SOURCE`, `GLEN_NAV_WRLD_SOURCE` and `GLEN_NAV_RELOAD_TYPED_PASS|NAVM=3|DOORS_ADDED=4|OWN=0`.
7. Independently check it: `python verify_navigation_candidate.py --candidate <candidate> --navi-winning <builder-logged prior NAVI source plugin> --typed-log <fresh log> --output <report under this research directory>`. The checker validates the exact eight-record whitelist, ESL flag/no new own records, all three independently parsed NVNM models and triangle tuples, base header stamps, canonical NAVI references and the whole prior NAVI except the three bounded entries. Typed fresh reload additionally proves unchanged CELL/WRLD canonical payloads and xEdit's Check diagnostics. The candidate cannot serve as its own NAVI witness.

The FC verifier requires FC to be the final NAVI winner, so its original winner assertion must be checked before installing Glen. Afterward the evidence chain is FC fresh verification followed by Glen's complete preservation of every other final-winning NVMI/NVPP/NVSI. Re-run the Glen fresh verification and independent checker whenever any load order, source, parent CELL/WRLD or later NAVI patch changes.

## Files

- `comparison.json`: exact original source SHA-256, profile witness, face coordinates/bytes, all mappings, complete component proofs, expected triangle hashes, expected Door Triangles and source/base NVMI.
- `analyze.py`: source-only repeatable comparison; writes only its research report.
- `source_preflight.json`: independent file hashes, face mappings and component proof repeated successfully.
- `DatabaseGlenmorilNavigationDraft.pas`: standalone builder draft.
- `DatabaseVerifyGlenmorilNavigationDraft.pas`: standalone fresh-reload verifier draft.
- `verify_navigation_candidate.py`: read-only source/candidate checker; does not construct binary plugins.
- `draft_manifest.json`: draft file SHA-256 and common helper provenance.

Exact schema/API evidence is pinned in `../navmesh_patch/source_4_1_5f/` at xedit-4.1.5f commit `f5c00f3fa3ee39511185515802647246c807f759`. Normal Door Triangle fields are `Triangle before door`, `CRC Hash`, `Door Ref`; `XTEL\Door` is the registered typed teleport field. No binary offsets are used to mutate a plugin, and no raw local FormID is blindly copied across plugin namespaces.
