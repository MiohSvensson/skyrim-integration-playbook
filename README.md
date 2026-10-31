# Unified Skyrim integration playbook

Selective Git snapshot of the control plane for the Anno / Burida / TuLED integration. The working project remains under `E:\stock\Skyrim collection\Database`.

This repository is for continuity, review, and recovery of the workflow. It is **not** a downloadable Skyrim mod pack and is **not** a standalone reproducible build.

## What is tracked

- `PLAYBOOK.md`: ordered continuation procedure and stop gates.
- `integration/state.json`: current machine-readable handoff.
- Integration control scripts, decision overrides, catalog, and configuration.
- First-party Python and xEdit Pascal producers/verifiers.
- Current delivery manifests, frozen-tool indexes, source preflights, and selected acceptance receipts.
- Existing research notes that explain prior repairs and constraints.

The `.gitignore` is default-deny. Only explicitly allowed file types and paths can be staged.

## What stays local

- The three source packs and the `UnifiedSkyrim` runtime tree.
- ESP/ESM/ESL plugins, BSA/BA2 archives, NIF/DDS/HKX assets, BodySlide output, and generated patches.
- SQLite databases, caches, logs, temporary files, tool binaries, and generated LOD/PG/Synthesis output.
- Third-party source snapshots, large preflight/run directories, and installer fixtures.

Many scripts also have absolute paths and depend on local evidence and assets. Cloning this repository elsewhere provides the playbook and source code, not the missing data.

## Non-negotiable constraints

- Do not launch Skyrim from this workflow.
- Keep every task-owned output, cache, log, and generated file inside `Database`.
- Do not modify the original Anno, Burida, or TuLED packs.
- Preserve the 32 GiB disk-space reserve.
- Do not force-add ignored data to Git or GitHub.
- Formal PG remains blocked until OS driver-cache containment inside its run directory is proven.

## Normal Git workflow

From the local `Database` directory:

```powershell
git status --short
git add -A
git diff --cached --stat
git diff --cached --check
git status --short
```

Review the staged list before every commit. If a database, cache, log, plugin, asset, or generated batch appears, unstage it and repair `.gitignore` rather than uploading it.

Then use a scoped commit, for example:

```powershell
git commit -m "Update integration handoff"
git push
```

Do not use `git add -f`, and do not publish the repository without reviewing the local paths and evidence for sensitive material.

## Start here

1. Read `PLAYBOOK.md`.
2. Check `integration/state.json` and the authoritative manifests listed there.
3. Resume at the FC v6 navigation producer, not at Synthesis, PG, or LOD.
4. Treat static/xEdit validation and game runtime testing as separate claims.
