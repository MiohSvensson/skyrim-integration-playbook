Private incoming-only ParallaxGen preparation (not executed here)

Use a fresh run after the final compatibility patches are accepted. Disable old
DynDOLOD and TexGen output layers in the generation profile, as required by the
pinned PG author workflow, then run `prepare_pg_run.py --profile "Unified Build"
--run-name incoming_002` (or another unused name). This only prepares private
tool/config files and never activates output. `incoming_001` is a research
snapshot with a known old TexGen warning and is not a formal run.

The root launches `pg_child.py --manifest <new run>/manifest.json --run-tool`
through `integration/logged_child.py` as an actual MO2 child. The child checks
all frozen plugin SHA/FileIDs, shader-rule SHA, actual KnownFolder INI/plugin
redirection, private single-link tool files, empty output and the 32 GiB free
space reserve. Normal Windows security refusal is a fatal stop. The unsigned
PGMutagen namespace-only edit and original DLL are fully preserved in
`PGMutagen_namespace_ledger.json`; no global settings are changed.

Before launching the actual tool, run `pg_nif_validate.py freeze --run <new
run>`. This resolves the real final loose/logical archive winner for every
permitted input mesh and saves private copies by SHA under `<run>/nif_inputs`.
The copies are independent, never hardlinked. A 32 GiB reserve is enforced.
After the successful tool child, run `pg_nif_validate.py verify --run <new
run>`. The official PyNifly CPU API compares all actual output vertices,
triangles, normals, UVs, node transforms/parents, skin bones/weights/transforms
and partitions against these frozen originals. It refuses shape removal,
unknown stream conversion or any unproven geometry change. It records every
shader/texture change and requires a later material/TXST/resource closure.
Unknown collision/controller/particle block changes are rejected, including
unproven block-index relocations; no broad bypass is used. The actual
multi-shape source freeze and identity/mutation fixtures passed, including
skinned stream83 and100 identity comparisons. This is not a PG generation run.

The input list is 3,843 effective incoming NIFs. The single geometry-delete
hazard `architecture/revenant/castle/slumn/whgrayquarter04.nif` is blocked. Only
TruePBR with texture-existence checks is enabled. No CM/parallax conversion,
FixSSS or hairflowmap texture processing is enabled. Missing 31 optional
rule-target texture paths stay ordinary shaders; no fake textures are made.
The one copied DDS permitted is the author's fixed black cubemap. The real
`textures/black.dds` source was separately verified against the actual
ZZ80 Consistent stock data BSA provider in `black_texture_actual.json`.

PG 0.9.9.5 unconditionally initializes hardware D3D11 and an alpha-count compute
shader. Its own cfg/log/temp/cache/output and .NET paths are inside Database, but
Windows/NVIDIA may maintain an OS-owned shader driver cache outside Database and
the author exposes no switch to relocate it. The current requirement is stricter:
**all task data must remain inside Database**. Therefore `pg_child.py --run-tool`
is blocked while this boundary is unproven. Preparation, read-only research and
non-generating preflight may continue. Resume formal PG only after implementing
and verifying per-process containment inside the run; never change global
GPU/security/privacy settings or treat an OS cache exception as implied consent.

After a successful child result, run `prepare_pg_verifier.py --run <new run>`.
It pins every output and every source plugin, independently computes the last
source winner for each override, and creates
`typed_verifier/DatabasePGMetadataVerifier.pas`. The parent loads the frozen
source plugins plus all DB output plugins in xEdit 4.1.5f and applies that
read-only script. Its artifact is `audit.tsv`; a final PASS line with exact
counts is required. The preparer fixture passed; no xEdit compile or actual
PG result is claimed by this preparation.

The verifier allows only existing model filenames and alternate texture
metadata to change. All remaining fields are recursively compared using
canonical resolved FormIDs, native scalar values and complete native byte
vectors. Localized strings compare exact resolved text. Unknown payload or
unsupported arrays stop. Model-information derived cache may be omitted;
if present, it must remain exact. Headers preserve identity, form version and
all flags except storage compression; VCS author stamp changes are logged.
New records belong only to DBPatcher.esp and must be TXST; DB_n.esp files
contain existing modeled-record overrides only. Original PGPatcher.esp and
PG_1.esp remain input records and never share the new namespace.

Typed record verification is followed by typed NIF geometry/skinning and
alternate-shape-index checks, and closure of every newly referenced TXST/DDS
path against actual final providers. Nothing is deployed on a partial pass.
All evidence is static; no game or rendering test has been performed.
