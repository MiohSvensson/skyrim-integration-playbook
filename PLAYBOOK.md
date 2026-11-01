# Integration continuation playbook

Last reviewed: 2026-11-01. Base: TuLED. Work remains active; static integration is not complete and no game testing has been performed.

## Current checkpoint

- Final profile: 1,082 plugins; 147 full and 935 light.
- Build profile: 1,080 plugins; 145 full and 935 light.
- Physical resolution reports no missing plugins or masters and remains within slot limits.
- Feature, quest, FC, Glen, and God of War format compatibility patches have independent binary and fresh typed-reload acceptance.
- The 6,495-row source catalog is refreshed as work in progress, with zero stale rows and zero linkage issues; 1,721 alternatives remain pending.
- FC v12 and Glen v7 are accepted for static integration. Production Synthesis is accepted after fresh native and scoped installed-VFS validation; inherited gaps and final generation remain open.
- Native pre-Synthesis capture covers 275 ARMA records and 1,100 model fields. Every model path changed by Synthesis resolves. A 23-file exact resource supplement is installed and VFS-verified. The reviewed plugin and captured Experience sidecar are deployed. PG containment and final LOD remain pending.

A pre-navigation MO2 child proved actual `usvfs_x64` injection and all 411,248 current runtime-path FileID/size winners in `pre_navigation_vfs_r2_probe_files.json`. That run is not an aggregate pass: MO2 moved its generated `modlist.txt` comment, and two Igraine hand textures remain unresolved. `mo2_controls.py` now canonicalizes only that exact comment with journal backup/rollback; no final all-resource VFS or in-game proof exists.

`run_mo2_child.py` and `prepare_xedit_producer.py` normalize the selected profile before freezing its controls. Keep all child script arguments absolute; the wrapper also resolves `integration/...` arguments to avoid the pre-injection launch failure seen with a relative child path. The wrapper propagates a logged child's nonzero exit even when MO2 itself returns zero.

MO2 may discover installed diagnostic mods that a cloned profile omitted. It adds them disabled. The producer admits only explicitly allowlisted disabled additions in their exact expected order; any enabled-mod or plugin/loadorder change fails. Use `--allow-mo2-disabled-mod "ZZ90 FC diagnostic 2" --allow-mo2-disabled-mod "ZZ90 FC diagnostic"` only for those existing diagnostic layers, not as a general bypass. See `integration/research/plugin_integration/xedit_settings/control_audit_proof_v1.json`.

## Authoritative handoff files

Use these current sources rather than older status labels:

- `integration/state.json`
- `integration/research/forgotten_city_navigation/navigation_v12_manifest.json`
- `integration/research/verified_patch_install/installer_tools_frozen_rev4.json`
- `integration/research/lod_update/delivery_manifest.json`
- `integration/research/feature_generation/PG_delivery.json`
- `integration/research/feature_conflicts/draft_version_manifest.v13.json` for the feature producer
- `integration/research/feature_conflicts/verify_compatibility_v14.py` for the current feature candidate

Do not:

- rerun the baseline FC/Glen `generate_drafts.py` over current v6 scripts;
- use the old `terrain_wyrm_preview_001` batch;
- use frozen v13 `verify_compatibility.py` for the accepted feature candidate;
- run `catalog.py --final` before final generation and validation;
- activate old generated output merely because a replacement is blocked.

## Required safety rules

- Keep all task-owned data inside `Database`; keep the original packs read-only.
- Use fresh task/run/batch names and preserve prior receipts.
- Require exact source hashes, private writable inputs, and actual MO2 VFS checks for producers.
- Installation is not acceptance: every candidate needs independent binary verification and a fresh installed-VFS typed reload.
- Stop on unexpected records, missing masters, changed load order, altered source winners, or unclassified resource paths.
- Maintain the 32 GiB reserve. Do not launch the game.

Installer rev4 passes 29 fixture checks, including actual child-process interruptions before and after copies and replacement recovery. For a rev4 `install_started.json` without a terminal receipt, use `install_verified_patch.py recover --prepared <job/prepared.json>` only after its installer process has exited. It refuses external changes and restores the original bytes and journal rows. Legacy rev3 interrupted attempts still require manual inspection.

The MO2/xEdit harness proves the complete native plugin sequence, including xEdit's `SkyrimSE.exe` pseudo-plugin—not a game launch. It permits only the exact Module Selection dialog, uses phase evidence for short scripts, and closes normally after the intended script. Nil-parent lookup, edge removal, NAVI append/remap, full NAVI preservation, and parent preservation probes pass; see `integration/research/plugin_integration/xedit_settings/native_harness_proof_manifest.json`.

## 1. Forgotten City navigation

FC v12 is accepted for static integration, with final VFS/resource checks still pending. Its producer exports the bounded patch without deep post-mutation inspection. Independent binary checks and fresh-process typed verifiers retain the full acceptance checks, avoiding xEdit's stale interface destruction when mutation and deep comparison share a process.

1. Run the corrected source preflight documented in `integration/research/forgotten_city_navigation/README.md`.
2. Prepare a fresh xEdit producer against `Unified Build` and execute it through the actual MO2 VFS.
3. Independently verify the exported candidate, using the builder-logged prior NAVI winner as witness.
4. Prepare/install with installer rev4.
5. Run the main read-only verifier and `DatabaseTriangleLocalProbe.pas` in separate fresh MO2/xEdit processes. Both must consume the installed candidate in the same native plugin order.
6. Accept only after exact candidate SHA, four-record whitelist, 16/16 reciprocal portals, all 324 triangle flag/edge checks, NAVI preservation, and both-profile closure pass. Use `accept --aux-reload-task <triangle-task>`; acceptance rejects a missing FC companion result.

Stop if any source, NAVM winner, parent CELL/WRLD, NAVI witness, or record set changes unexpectedly.

## 2. Glenmoril navigation

Glen v7 is accepted for static integration after the same producer → binary → install → fresh reload → accept chain. See `integration/research/glen_region_navigation/navigation_v7_manifest.json` and `integration/research/verified_patch_install/runs/glen_v7/accepted.json`.

- FC and all unrelated NAVI/NVPP/NVSI entries are preserved.
- Three NAVMs, four added door connections, eight existing overrides, and zero own records are verified.
- The combined checker reports `STATIC_BINARY_AND_TYPED_RELOAD_PASS`; final VFS/resource checks and in-game validation remain separate.
- Do not enable the superseded AK-only candidate.

God of War prerequisite: the first Synthesis replay stopped on two MGEF records using unsupported VMAD object format 0. `integration/research/god_of_war_script_format/format_v3_manifest.json` records the accepted 780-byte, two-record patch that changes only object format 0 to 2, preserving spell references, script/property data, metadata, and the source empty keyword array. The raw VFS producer, independent binary check, rev4 installation, and fresh typed reload all pass. Earlier failed candidates and the failed replay were not deployed.

## 3. Close bounded resource questions

Resolve or explicitly disposition every known gap before final resource closure:

- nine grass-source gaps;
- Forgotten City response-motif sound;
- Glen female `DwarvenSoldier.nif` and `shaderbox.nif`;
- Moon and Star BS82 asset contract and 35 affected LAND records.
- Igraine hand material is closed by two private files in the existing ZZ83 layer: the exact author mask and stock-identical environment cubemap. `integration/research/vfs_validation/igraine_material_r1/accepted.json` records actual MO2 FileID/hash proof, unchanged mesh/controls, and rollback-tested installation. This is targeted closure, not a full resource graph or in-game material test.

Use author assets or typed evidence. Do not invent resources or delete references only to suppress diagnostics. `integration/research/supplemental_import/resource_limitations_manifest.json` records the current dispositions: nine exact grass omissions, an unrepaired FC motif, Glen's statically unused female-model branch and stock material stub, and two retained Moon and Star BS82 meshes. The typed full-context audit has eight male Glen NPCs, no female consumer, and a non-player race; raw source payloads and the FC response's sound FormID match exactly. These are explicit source limitations, not a zero-gap or in-game claim. Recheck them during final QEX, VFS, and whole-world grass/LOD.

## 4. Final Synthesis

Run after all gameplay/navigation patches are accepted.

- Use `integration/research/synthesis_final/replay_tools_frozen_rev3.json` and the six-stage order evidence.
- Run the missing-gender-world-model patcher before PG because their ARMA semantics overlap.
- Capture the Experience sidecar, install the final private copy, then disable temporary `ZZ88` workspace.
- Replace old generated layers only after native checks, master/slot validation, and known-exception comparison.
- Keep generated plugins after the compatibility block.

Current validated candidate: `final_v8`, SHA-256 `5f8f491fc086631868ecd78fb4f19c09b76e9a8a4e3b0cb20d5156611cfc64a8`, 19,214 records, 240 masters, full plugin, no own records. Its native Check reported zero diagnostics. `synthesis_v8_arma_delta_manifest.json` identifies 275 affected ARMA records by source plugin and object ID, avoiding raw FormID renumbering after master insertion. `synthesis_input_models_manifest.json` binds the winning pre-Synthesis model context from `synthesis_input_models_v3`: 275 records and 1,100 fields, with no Synthesis plugin active in that input profile.

The per-field audit finds no missing model path changed by Synthesis. `generated_mesh_manifest_v3.json` adds 23 exact stock/author files with rollback and crash-recovery coverage; `generated_mesh_resources_r1/accepted.json` verifies their actual MO2 FileIDs, hashes and mesh material closure. `install/runs/production_v2/accepted.json` and `synthesis_acceptance_manifest.json` record production Synthesis acceptance after a fresh native Check, actual installed-plugin/sidecar VFS proof and both-profile closure. The inherited-only census remains open for final consumer/resource disposition, including Hoodu's copied PG duplicate; do not alias gender/weight variants or treat inherited gaps as newly generated dependencies.

## 5. PG containment and generation

Formal PG is blocked while Windows/NVIDIA may write an OS driver cache outside `Database`. An earlier unsupported change removed that launch block; `prepare_pg_run.py` now restores it, and `pg_child.py` refuses a true block. `PG_delivery_final.json` is not accepted as authority while containment is unproven.

First implement and verify per-process containment inside the run. Never change global GPU/security/privacy settings. If containment cannot be proven, leave PG blocked and do not weaken the guard.

A bounded D3D11 initialization probe passed inside a private debug-MO2 tool tree, with the main MO2 config unchanged. Its actual usvfs log captured no D3D cache write, but no shader dispatch or full PG workload was exercised. Kernel ETW was refused for insufficient privileges; no elevation was attempted. See `cache_containment/probe_v1/usvfs_trace_analysis_manifest.json`. This is not a supported cache-root override or permission to run formal PG.

After containment and final Synthesis:

1. Prepare a fresh incoming-only run with old DynDOLOD/TexGen outputs disabled.
2. Freeze effective input NIFs privately.
3. Run PG.
4. Verify typed ESP changes, NIF geometry/skinning, TXST references, and DDS/resource closure.
5. Deploy only after every check passes.

## 6. Terrain, grass, LOD, and occlusion

Use fresh isolated batches from `integration/research/lod_update/prepare_lod_batch.py`.

1. Generate required terrain for new worlds.
2. Run TexGen after disabling old TexGen output.
3. Generate whole-world grass caches for every affected world; the two-cell smoke test is not enough.
4. Update DynDOLOD with the required existing private DynDOLOD plugins active.
5. Generate occlusion last, after terrain/object outputs are installed.

Validate and install each batch before preparing the next. Preserve unselected-world assets and final CELL/WRLD gameplay fields. Keep all outputs in new private layers under `Database`.

## 7. Final acceptance

Require all of the following:

- full native xEdit Check and QEX with normal 4.1.5f definitions;
- actual all-path MO2 VFS verification and resource/archive closure;
- final-load-order rechecks of every compatibility patch;
- master topology, full/light slot limits, and x64 SKSE DLL checks;
- original-control hashes and current configuration-path scan;
- SQLite integrity/orphan checks and disk reserve;
- final machine-readable receipts for every generated layer.

Only then finalize the catalog, launchers, maintenance documentation, and `integration/state.json`. The handoff must still say that no in-game test was performed.

## Repeatable review commands

Run from `Database` on Windows with the existing local toolchain:

```powershell
python integration/research/verified_patch_install/validate_installer.py
python integration/research/catalog_decision_review/audit_catalog.py
python integration/research/catalog_decision_review/audit_configuration_postapply.py
python integration/research/feature_conflicts/verify_compatibility_v14.py --file-map "UnifiedSkyrim/validation/feature_reload_v13/file_map.json" --candidate "UnifiedSkyrim/mods/ZZ87 Verified compatibility patches/Database Feature Compatibility.esp" --report candidate/review_recheck_v14.json
```

Validators may create local receipts or fixtures. Review them before committing; never force-add generated data.
