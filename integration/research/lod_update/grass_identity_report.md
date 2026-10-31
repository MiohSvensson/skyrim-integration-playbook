# Shipped grass cache identity and bounded regeneration

This research did not start MO2, a generator, a GUI or the game. The parent actually ran CPU smoke 003. Its result proves MO2 VFS access and two-cell output structure: the populated control placed 35,927 candidates, rejected 3,973 and wrote **31,954 blades in 41 groups**; the empty control wrote exactly `00000000`.

## What the cache ID does

FasterNGIO 1.6, pinned commit `5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40`, writes a four-byte **runtime** GRAS FormID after each group's model string and wave period. `src/Grass/NgioCacheWriter.cpp:30–44` and its header are the exact serialization evidence. Models and placement instance payloads are also stored in the cache; this is not an ID-only format.

The author's [NGIO source](https://github.com/DwemerEngineer/No-Grass-In-Objects-NG/tree/c2c5981a59a7d931c2327e830431660486dac338) immediately before the installed 1.5.11 release changes `.gid` to `.cgid`, fixes geometry writing and sets grass loading/creation options. `include/GrassControl/GidFileCache.h` delegates the read to the game, and detects the helper to avoid duplicating its filename hook. It does not translate the embedded GRAS identity using a stored plugin name. Its CMake version still says 1.5.9, so this is author-source evidence near the 1.5.11 release, **not a reproducible source/binary equivalence claim**. The installed DLL's PE version is exactly 1.5.11.0.

The installed Grass Cache Helper NG is **1.0.1.0**, not the current Nexus version. The [author's description](https://www.nexusmods.com/skyrimspecialedition/mods/101095) documents filename/season selection, world NoGrass changes and INI settings; it does not document GRAS-ID remapping. The local INI forces WhiterunWorld grass. A matching 1.0.1 source archive was not available locally; current source must not be substituted as exact proof of this installed DLL.

The packaged TuLED executable's relevant on-disk function bytes are encoded and cannot be meaningfully disassembled at the address-library targets. Static inspection of the **unexecuted Anno 1.5.97 reference image**, SHA `5666e1bddd01bcab31ecf11691ef1a3f22e1541af79f2bc0e55318533cfe5d12`, does permit analysis at the same pinned 1.5.97 library IDs. Reader 15206 reads model/wave/ID/flags and passes the group to 15214. The latter uses the ID plus cell coordinates as a cache key; the model is loaded from the path. No TESForm lookup of this serialized ID occurs in that traced path. Evidence: `grass_engine_anno_reference.json`. This is a matching-version static reference, **not execution or proof that the packaged image has identical runtime behavior**. Do not claim a shifted ID alone proves that the game will load the wrong grass model.

## What the shipped files actually contain

`grass_identity_audit.json` scanned every original TuLED Grass Cache file without changing it:

| Item | Count |
|---|---:|
| Files | 9,908 |
| Logical bytes | 1,764,769,194 |
| Groups in the first stream read by the engine | 161,983 |
| Files with additional complete streams | 446 |
| Complete streams, including appended data | 11,116 |
| Groups across every complete stream | 173,612 |

The files contain multiple historical load orders. `FE146` and `FE159` consistently describe Freak's Floral Fields; `FE145` and `FE158` consistently describe Waterplants. The current original TuLED plugins.txt alone leaves 142,464 first-stream groups unmapped. Adding only two full masters is therefore not the complete identity issue. For example, old OxEyeDaisy is `FE146828`, current original TuLED resolves it as `FE159828`, and the prepared final profile resolves it as `FE156828`.

Every one of the **380 distinct cached ID/model combinations** has exactly one match among final winning GRAS records when using full/light kind, object ID and exact normalized model path together. Every historical prefix maps consistently to exactly one owner; the corresponding original and final canonical GRAS full payload SHA is identical. No normalization creates a same-stream group-key collision. No guessed fixed prefix offset is used.

`grass_cache_remap_plan.json` therefore describes a bounded private overlay: copy **9,414 changed files / 1,746,418,639 bytes**, replacing exactly **162,257 four-byte ID fields**. All model names, wave data, flags, geometry, positions, instance data and appended streams are preserved byte-for-byte. Unchanged files can continue to resolve from the original cache provider. `grass_cache_remap.py` checks every source SHA, every old field, exact EOF, private output ownership, disk reserve and a SHA with only the listed ID fields masked. It checks each written file has one link and rechecks the original SHA. No file has been materialized or activated by this research agent.

The in-memory fixture tests both a normal file and an appended-stream file, validates all other bytes, and rejects truncation, unknown trailing bytes and implausible group counts. Result: `grass_remap_fixture.json` **PASS**. The ordinary strict new-cache verifier intentionally rejects appended streams; use this remapper's complete-stream verification for preserved original caches. Do not trim the originals to make another verifier pass.

After parent review, the executable creation command is:

```powershell
python Database/integration/research/lod_update/grass_cache_remap.py --materialize identity_001
```

It writes only under `research/lod_update/remap_runs/identity_001`. A profile drift stops it; refresh the audit and plan after plugin-order changes. Generated final-profile caches must win above this identity-only overlay for changed worlds. Identity normalization does not update placement for changed LAND or collision.

## Missing source models found during smoke review

The structurally successful smoke log reports 46 missing models representing 70 GRAS types. Three are actually referenced by the populated control's LTEX lists:

| Canonical GRAS | Model |
|---|---|
| `Freak's Floral Fields.esp|00082C` | `landscape\Grass\Dandelion02DrJ.nif` |
| `Freak's Floral Fields.esp|000A44` | `landscape\Grass\ComplexGrassDrJ15_D.nif` |
| `Freak's Floral Fields.esp|0008F5` | `landscape\Grass\TundraSedum_DrJ.nif` |

All three exact filenames are absent from the complete loose and BSA member indices of all three source packs, and absent from the models stored in the old caches. This is evidence of a pre-existing source resource gap, not proof of a FasterNGIO VFS bug. Similar filenames are only review candidates, not equivalent assets. Exact evidence and canonical payload hashes are in `smoke003_relevant_missing_grass.json`. Do not silently treat the smoke as proof of complete grass content.

## Complete-world CPU batch

`prepare_bulk_grass.py` pins the actual selected profile and all plugin hashes, recomputes runtime IDs, independently merges partial CELL data and selects each CELL's final LAND child slot. The current 1,074-plugin manifest selects only these eight worlds:

| World | Current runtime ID | Effective LAND cells |
|---|---|---:|
| Tamriel | 0000003C | 11,186 |
| WyrmstoothWorld | 18000D62 | 1,216 |
| Dimfrost | 180825E1 | 194 |
| zRevNamiraRealm | 19000D62 | 1,774 |
| zGHFelixRealm | 19009598 | 49 |
| zGHDunmerCampWorld | 19009DE8 | 105 |
| zGHCradleWoodsWorld | 1900AA1A | 140 |
| zRevDreamsleevesWorld | 19491B1A | 285 |

The IDs are observations in this manifest, never constants in the builder. Full Tamriel is selected because MoonAndStar alters 35 LAND records and new quest entrances alter collision; this avoids a guessed object-boundary radius. WhiterunWorld is excluded because FasterNGIO does not consume the Helper's ForceGrassWorlds option. Preserve its normalized original cache.

Use the actual-MO2 `integration/logged_child.py` bootstrap for every run. First run `faster_ngio_bulk_child.py --inspect-only`: it checks the generator CSV against the independent expected CELL, LAND and XY mapping and records every relevant `loadable=0` model across all eight worlds. Generation mode stops before generating a world with such a resource gap. It uses CPU/vanilla placement, explicit world IDs, fresh output, `--write-empty-cells`, four workers and one writer. It reserves 32 GiB plus an 8 GiB initial output allowance and monitors remaining space during generation.

Generated files are independently parsed, have exact per-world XY coverage including empty caches, and may not add blades beyond pre-rejection inspection. Global warnings and collision-missing counts remain in the result for parent review; successful creation does not automatically activate anything. Static collision cannot represent every later Papyrus/BOS world state, and no in-game verification is claimed.

Files and current hashes are frozen in `grass_identity_delivery.json`; regenerate that small delivery manifest after any child change.
