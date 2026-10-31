# Integration continuation playbook

Last reviewed: 2026-10-31. Base: TuLED. Work remains active; static integration is not complete and no game testing has been performed.

## Current checkpoint

- Final profile: 1,079 plugins; 147 full and 932 light.
- Build profile: 1,076 plugins; 144 full and 932 light.
- Physical resolution reports no missing plugins or masters and remains within slot limits.
- Feature and quest compatibility patches have independent binary and fresh typed-reload acceptance.
- The 6,495-row source catalog is refreshed as work in progress, with zero stale rows and zero linkage issues; 1,721 alternatives remain pending.
- FC and Glen navigation are at the v6 draft/source-preflight stage, not compiled or installed.
- Formal Synthesis, PG, and final LOD generation remain pending.

These are physical/static checks, not final MO2 VFS or in-game proof.

## Authoritative handoff files

Use these current sources rather than older status labels:

- `integration/state.json`
- `integration/research/plugin_integration/navi_unresolved_audit/stock_orphan_lookup_fix_manifest_v6.json`
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

## 1. Forgotten City navigation

Use the current v6 PAS scripts.

1. Run the corrected source preflight documented in `integration/research/forgotten_city_navigation/README.md`.
2. Prepare a fresh xEdit producer against `Unified Build` and execute it through the actual MO2 VFS.
3. Independently verify the exported candidate, using the builder-logged prior NAVI winner as witness.
4. Prepare/install with installer rev4.
5. Reload in a new MO2/xEdit process and run the read-only typed verifier.
6. Accept only after exact candidate SHA, four-record whitelist, 16/16 reciprocal portals, NAVI preservation, and both-profile closure pass.

Stop if any source, NAVM winner, parent CELL/WRLD, NAVI witness, or record set changes unexpectedly.

## 2. Glenmoril navigation

Repeat the same producer → binary → install → fresh reload → accept chain after FC acceptance.

- Preserve FC and all unrelated NAVI/NVPP/NVSI entries.
- Require three NAVMs, four added door connections, eight existing overrides, and zero own records.
- Do not enable the superseded AK-only candidate.

## 3. Close bounded resource questions

Resolve or explicitly disposition every known gap before final resource closure:

- nine grass-source gaps;
- Forgotten City response-motif sound;
- Glen female `DwarvenSoldier.nif` and `shaderbox.nif`;
- Moon and Star BS82 asset contract and 35 affected LAND records.

Use author assets or typed evidence. Do not invent resources or delete references only to suppress diagnostics.

## 4. Final Synthesis

Run after all gameplay/navigation patches are accepted.

- Use `integration/research/synthesis_final/replay_tools_frozen_rev3.json` and the six-stage order evidence.
- Run the missing-gender-world-model patcher before PG because their ARMA semantics overlap.
- Capture the Experience sidecar, install the final private copy, then disable temporary `ZZ88` workspace.
- Replace old generated layers only after native checks, master/slot validation, and known-exception comparison.
- Keep generated plugins after the compatibility block.

## 5. PG containment and generation

Formal PG is blocked while Windows/NVIDIA may write an OS driver cache outside `Database`.

First implement and verify per-process containment inside the run. Never change global GPU/security/privacy settings. If containment cannot be proven, leave PG blocked and do not weaken the guard.

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
