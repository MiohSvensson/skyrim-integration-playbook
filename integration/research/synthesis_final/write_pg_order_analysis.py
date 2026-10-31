"""Read-only source audit: exact six pinned patchers -> fresh PG -> final LOD.

Writes only this research directory. Does not launch a producer or edit a profile.
"""
import datetime
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
RESEARCH = OUT.parent
CATALOGUE = OUT / 'official_replay_catalogue.json'
PG = RESEARCH / 'feature_generation'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin(path, expected=None):
    p = Path(path)
    actual = sha(p)
    if expected is not None:
        assert actual == expected, (str(p), expected, actual)
    return {'path': str(p), 'sha256': actual, 'bytes': p.stat().st_size}


def evidence(file, start, end):
    p = Path(file)
    lines = p.read_text(encoding='utf-8-sig').splitlines()
    excerpt = '\n'.join(lines[start-1:end])
    assert excerpt
    return {**pin(p), 'line_start': start, 'line_end': end,
            'excerpt_sha256_utf8_lf': hashlib.sha256(excerpt.encode('utf-8')).hexdigest()}


def main():
    catalogue = json.loads(CATALOGUE.read_text())
    assert sha(CATALOGUE) == '9bf91162371e3ed183e44f44311be403eee22a411774377427532ba2dd6e74ee'
    assert len(catalogue['drivers']) == 6
    driver_audits = []
    specs = [
        {
            'index': 1, 'verdict': 'READY',
            'active_settings': {'mode': 'All'},
            'reads': ['Input ModKeys', 'Winning LSCR canonical FormKey owner'],
            'writes': ['LSCR.Conditions: replace with GetRandomPercent == -1'],
            'model_dependency': 'None in the active All branch. Smart mode STAT/LSCR counts are not executed.',
            'pg_interaction': 'PG output signature allowlist excludes LSCR. PG may change a STAT model referenced by an LSCR, but cannot restore or replace the Synthesis conditions.',
            'evidence_ranges': [('Program.cs', 137, 191)],
        },
        {
            'index': 2, 'verdict': 'READY',
            'active_settings': {'PatchArmors': True, 'PatchWeapons': True, 'PatchSoulGems': True, 'PatchMagicEffects': True},
            'reads': ['AOS/ISC ModKey presence', 'MGEF.Projectile/Explosion canonical links',
                      'SLGM.Keywords', 'WEAP.Template/Keywords/Data.Flags',
                      'ARMO.Keywords/Armature', 'ARMA.FootstepSound nullness'],
            'writes': ['MGEF.Projectile/Explosion', 'SLGM.PickUpSound/PutDownSound',
                       'WEAP.ImpactDataSet/EquipSound/UnequipSound/AttackFailSound',
                       'ARMO.PickUpSound/PutDownSound', 'ARMA.FootstepSound'],
            'model_dependency': 'No model filename, NIF, geometry, texture path or ALTTexture input is read.',
            'pg_interaction': 'PG can later override ARMO/ARMA/WEAP/SLGM for model changes, so disjoint assignments alone are insufficient. Fresh PG must DeepCopy the current winning Synthesis record; its typed verifier must prove every sound/impact link and all other nonmodel fields remain canonical-equal. MGEF is outside PG output signatures.',
            'evidence_ranges': [('Program.cs', 30, 58), ('Program.cs', 62, 97), ('Program.cs', 108, 119), ('Program.cs', 131, 183), ('Program.cs', 195, 233)],
        },
        {
            'index': 3, 'verdict': 'READY_ASYMMETRIC_ORDER_ONLY',
            'active_settings_summary': 'Five stock winning ARMO ModKeys ignored; exact pinned 14 keyword/template maps retained.',
            'reads': ['Winning ARMO context.ModKey (IgnoreMods predicate)',
                      'ARMO.NonPlayable/Shield flags, BodyTemplate, Keywords, Armature',
                      'Resolved ARMA.EditorID/BodyTemplate/Race',
                      'ARMA.WorldModel container and per-sex null/whitespace File',
                      'Template ARMA male/female WorldModel.File nonempty strings'],
            'writes': ['ARMA.WorldModel.Male or Female only when absent/empty; hair rule copies the opposite Model object, otherwise constructs Model with template File'],
            'model_dependency': 'Overlaps PG model surface. Tests null/empty model presence, not NIF physical existence. Existing nonempty model paths are not replaced.',
            'pg_interaction': 'Run AA first. Fresh PG sees any newly populated sex model, preserves that nonempty presence and every nonmodel Synthesis field, then may retarget the existing File/ALT data. This is not a commutativity result: PG-first changes winning ARMO context.ModKey and may change template/opposite model and ALT values before AA; the original reverse order is not asserted equivalent.',
            'evidence_ranges': [('Program.cs', 80, 112), ('Program.cs', 127, 166), ('Program.cs', 173, 188)],
        },
        {
            'index': 4, 'verdict': 'READY_WITH_EXISTING_PRIVATE_SIDECAR_PROTOCOL',
            'reads': ['Winning RACE.Starting.Values[0] health', 'RACE.EditorID/Name/FormKey.ID',
                      'Last/original resolved RACE context.ModKey; exclude stock owners'],
            'writes': ['SKSE/Plugins/Experience/Races/GeneratedExperiencePatch.ini; XP = Floor(health/10 + 0.5)',
                       'No payload record authored by this driver; normal sequential seed is forwarded'],
            'model_dependency': 'None; no model or texture data is consulted.',
            'pg_interaction': 'PG excludes RACE and cannot change the health/name/origin values. Replay still must use the existing exact private winner FileID proof, backup, capture, finally restore and fresh output sidecar protocol. No permission to write the original/base sidecar.',
            'evidence_ranges': [('Program.cs', 25, 32), ('Program.cs', 40, 72)],
        },
        {
            'index': 5, 'verdict': 'READY',
            'active_settings': {'ignoreIdenticalToWinningOverride': False, 'WaterForEnbModName': 'Water for ENB (Shades of Skyrim).esp', 'ModsToSkip': 'DynDOLOD.esm;Occlusion.esp;Synthesis.esp;Requiem for the Indifferent.esp;Bashed patch, 0.esp'},
            'reads': ['Water for ENB.esm + configured Shades plugin and their directly dependent input mods',
                      'Source CELL.WaterEnvironmentMap/Flags.HasWater/Water', 'Source WRLD.LodWater',
                      'Winning CELL/WRLD full records for GetOrAddAsOverride'],
            'writes': ['CELL.WaterEnvironmentMap', 'CELL.Flags.HasWater set true when source true',
                       'CELL.Water', 'WRLD.LodWater; all other copied fields come from current winning context'],
            'model_dependency': 'None. WaterEnvironmentMap is water data, not a PG model surface.',
            'pg_interaction': 'PG emits neither CELL nor WRLD. New PG masters alone do not make it a producer of water records. Existing six-driver combined seed protocol must be retained, including later LAND hierarchical parent carryover checks.',
            'evidence_ranges': [('Program.cs', 49, 57), ('Program.cs', 77, 108), ('LoadOrderUtilities.cs', 1, 90)],
        },
        {
            'index': 6, 'verdict': 'READY',
            'active_settings_summary': 'removeAllVertexVertexColors=false; snow RGB Pow(channel/255,0.1)*255; standard RGB Pow(channel/255,0.5)*255.',
            'reads': ['Winning LAND.Flags.VertexColors, VertexColors and Layers opacity/quadrant/base/alpha texture links',
                      'Resolved LTEX.Flags == IsSnow', 'Pinned formula settings'],
            'writes': ['LAND.VertexColors only in this active false branch; hierarchical parent copies may accompany output serialization'],
            'model_dependency': 'No NIF model/path input. Landscape texture snow flags are not PG new TXST texture records.',
            'pg_interaction': 'PG emits no LAND/LTEX/CELL/WRLD and cannot overwrite these colors or water parent state. Keep native combined stage order and independently inspect generated hierarchical parent/water semantics; this report does not authorize independent-group fallback.',
            'evidence_ranges': [('Program.cs', 29, 67), ('LandscapeGrid.cs', 46, 96), ('LandscapeGrid.cs', 141, 171)],
        },
    ]
    for d, spec in zip(catalogue['drivers'], specs):
        assert d['index'] == spec['index']
        sources = [pin(s['path'], s['sha256']) for s in d['source_code_files']]
        settings = [pin(s['path'], s['sha256']) for s in d['settings_files']]
        exe = next(s for s in d['compiled_runtime_files'] if s['path'].casefold() == d['Build_metadata']['ExecutablePath'].casefold())
        ranges = spec.pop('evidence_ranges')
        ev = [evidence(next(s['path'] for s in sources if Path(s['path']).name == name), a, b) for name, a, b in ranges]
        driver_audits.append({**spec, 'name': d['name'], 'source_commit': d['source_commit'],
                              'primary_author_repository': d['repository'], 'sources_verified': sources,
                              'compiled_driver_verified': pin(exe['path'], exe['sha256']),
                              'settings_verified': settings, 'evidence': ev})
    pgsource = PG / 'primary_sources/PGPatcher-source/PGPatcher-bf2333af2077384102bd250969ede87eb4c99367/PGMutagen/PGMutagen.cs'
    delivery = json.loads((PG / 'PG_delivery.json').read_text())
    for basename in ['prepare_pg_run.py', 'pg_child.py', 'prepare_pg_verifier.py', 'pg_metadata_verifier_body.pas', 'PGMutagen_namespace_ledger.json']:
        p = PG / basename
        pin(p, delivery['artifacts'][str(p)])
    pg_ev = [evidence(pgsource, a, b) for a, b in [(172, 247), (300, 320), (868, 940), (944, 1075), (1097, 1139), (1142, 1245), (1287, 1322)]]
    verifier = PG / 'pg_metadata_verifier_body.pas'
    report = {
        'schema': 'skyrim.derived_producer_order_source_audit.v1',
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'verdict': 'READY',
        'meaning': 'Source-backed permission to schedule the exact six-stage Synthesis first, then a fresh PG built from the enabled fresh Synthesis winning context, then all LOD generation. Execution and artifact acceptance remain pending.',
        'order': ['Complete and accept feature, quest, Forgotten City NAVI and Glen NAVI compatibility in Unified Build',
                  'Freeze final active gameplay inputs minus original group blacklist and old derived outputs',
                  'Replay pinned six drivers with fresh empty seed and original sequential SourcePath chain',
                  'Independently validate/accept fresh Synthesis plugin and Experience sidecar, then enable that output after gameplay/compatibility',
                  'Prepare and execute NEW private PG run against this post-Synthesis winning context',
                  'Validate PG NIF/material/TXST closure and exact current-source typed preservation, then enable every new DB output after fresh Synthesis',
                  'Generate and accept new TexGen/DynDOLOD/Occlusion/grass-related applicable outputs from this final context',
                  'Fresh final Unified Skyrim QEX, xEdit and VFS graph after all enabled names/SHAs are fixed'],
        'scope_change': {'authorized_inputs': catalogue['final_scope_authorization'],
                         'original_blacklist_retained': catalogue['original_blacklist'],
                         'new_explicit_change': 'Fresh PG output is placed after the new Synthesis. The previous PG-before-Synthesis proposal and any pre-Synthesis PG plugin output are not used as final output.',
                         'original_base_PG_layers': 'Existing base PGPatcher/PG_n remain ordinary earlier baseline inputs. New DB namespace only is the final post-Synthesis material layer.',
                         'not_commutative': True},
        'source_catalogue': pin(CATALOGUE),
        'replay_frozen_contract': pin(OUT / 'replay_tools_frozen_rev3.json', '707406f95a8652f774c046d43e29887bca026f40458926d16c99b7a1bd26d0fc'),
        'six_driver_matrix': driver_audits,
        'pg_contract': {
            'author_source_commit': 'bf2333af2077384102bd250969ede87eb4c99367',
            'source': pin(pgsource), 'namespace_ledger': pin(PG / 'PGMutagen_namespace_ledger.json'),
            'managed_binary_change': 'Only four bytes of equal-length output namespace strings; all other bytes pinned by namespace ledger.',
            'reads': ['Actual post-Synthesis load order and master-closed input records', 'Winning existing model record and submodel', 'Existing model filename/nonempty presence, weight-slider endpoint, ALT texture identities', 'Incoming allowed NIF/PBR/material/texture assets'],
            'writes': ['Existing model File -> generated allowed mesh path', 'Existing ALT texture entry index/new TXST link or subset removal', 'Own DBPatcher TXST records; split DB_n overrides', 'Derived Model Information cache may be omitted; typed gameplay flags/payload remain unchanged'],
            'must_preserve': ['Every original nonempty model container/member presence', 'All nonmodel payload fields canonical/typed-equal to the final source winner, including sound/footstep/impact values from fresh Synthesis', 'Canonical record identity, Form Version and gameplay flags; only compression/VCS metadata exceptions explicitly logged by verifier'],
            'source_evidence': pg_ev,
            'frozen_verifier': pin(verifier, 'ff487beb429b1dc688b3a742cb0ba1755112b72d13d9d55cfd690cda2a548cb7'),
            'verifier_evidence': [evidence(verifier, a, b) for a, b in [(25, 71), (74, 163), (167, 183)]],
            'preparer': pin(PG / 'prepare_pg_verifier.py', '74fd299c56252410b6ec5be1265513cdebc0a2555c47995e7df4743e412235ee'),
            'explicit_order_required': 'DB outputs must follow fresh Synthesis even if Synthesis is not in their master lists: copying an override of an older canonical owner does not imply a dependency on the source winner plugin.'},
        'acceptance_gates': [
            {'gate': 'Source and settings identity', 'status': 'PASS', 'detail': 'All listed driver sources/settings/primary DLLs and frozen PG core tools verified by SHA in this audit.'},
            {'gate': 'Gameplay compatibility final and accepted', 'status': 'PENDING_PARENT', 'detail': 'Four compatibility outputs must be final before preparing Synthesis, including both navigation patches.'},
            {'gate': 'Six-stage runtime execution', 'status': 'PENDING', 'detail': 'Actual MO2 Python child with usvfs, fresh output, stage SHA/master closure/own-ID inspection; unexpected split/limit stops remain.'},
            {'gate': 'Synthesis field semantics and stage carryover', 'status': 'PENDING', 'detail': 'Inspect exact intended deltas and full record carryover; AA filled model presence, AOS sound links, Water parent fields, LAND output and Experience sidecar must pass. No alternative group fallback is authorized.'},
            {'gate': 'Fresh PG input includes accepted Synthesis', 'status': 'PENDING', 'detail': 'Reprepare current profile manifest; prove fresh Synthesis is present/not skipped by PG load/master gate. Never reuse old PG input manifest or generated plugin.'},
            {'gate': 'PG output against current winning context', 'status': 'PENDING', 'detail': 'Regenerate ExpectedSources after fresh Synthesis, freeze actual generated NIF allowlist; run existing typed body. Any changed nonmodel Synthesis field is fatal.'},
            {'gate': 'PG asset proof coverage', 'status': 'PENDING', 'detail': 'Research preflight CPU snapshots can be reused only per identical asset path+SHA+provider+reader pins. AA may add model uses; fresh final model-use mapping and any newly introduced NIFs need coverage. Old frozen profile proof does not become final by renaming.'},
            {'gate': 'Final LOD and all graph consumers', 'status': 'PENDING', 'detail': 'All LOD after accepted post-Synthesis PG. Fresh final QEX/resource graph must use the exact final enabled plugin SHA set; no pre-Synthesis bounded consumer evidence can stand in for it.'}],
        'limitations': ['This is source analysis, not producer execution, in-game validation, or completed final artifact acceptance.',
                        'No proof that running these producers in arbitrary orders is equivalent. AA is an explicit overlapping model writer and mandates the new asymmetric order.',
                        'Any driver/settings/PG implementation change invalidates this narrow matrix.',
                        'The existing incoming mesh allowlist remains in force. A newly filled template model outside it is retained from Synthesis; expanding PG processing scope requires separate asset evidence.'],
        'changes_performed': {'research_report_only': True, 'runtime': False, 'profiles': False, 'frozen_producer_tools': False, 'game_started': False},
        'generator': pin(__file__),
    }
    dest = OUT / 'pg_order_analysis.json'
    assert not dest.exists(), 'Do not overwrite an earlier audit; version it.'
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    md = OUT / 'pg_order_analysis.md'
    assert not md.exists()
    md.write_text('''READY: final gameplay/compatibility → six-stage Synthesis → fresh PG → new LOD.

This is a source-backed scheduling decision. Runtime output acceptance remains pending.

| Patcher | Reads | Writes | Post-Synthesis PG condition |
|---|---|---|---|
| Disable loading screens (All) | ModKeys, LSCR owner | LSCR conditions | PG emits no LSCR |
| AOS/ISC | Keywords, sound/impact/projectile links, armor armature | Sound/impact/projectile links and ARMA footsteps | Fresh winning-record copy and typed nonmodel equality |
| Missing gender world model | ARMO winning ModKey; ARMA null/empty sex model; templates | Missing male/female ARMA model | Overlapping writer: run it first; preserve populated model and validate fresh PG |
| Experience | RACE health/name/origin | Captured generated INI | PG emits no RACE; retain private sidecar finally-restore protocol |
| Water for ENB | CELL/WRLD water and dependencies | CELL water/env map/flag, WRLD LOD water | PG emits no CELL/WRLD |
| Landscape vertex color | LAND colors/layers; LTEX snow | LAND vertex colors | PG emits no LAND/LTEX/CELL/WRLD |

Do not reuse pre-Synthesis PG plugins or ExpectedSources. Prepare and execute PG against the accepted fresh Synthesis context, install DB outputs after it explicitly, and run the frozen typed verifier. Masters alone do not enforce this order. Preflight NIF snapshots are reusable only for the exact asset path, bytes, provider and reader pins; newly added model uses still require final coverage. Generate LOD last, then repeat final QEX and VFS on the final plugin SHA set.

The opposite order is not asserted equivalent. The AA driver tests winning ARMO ModKey and fills missing model containers; these predicates overlap PG output semantics. Full evidence, source hashes, line ranges and pending gates are in pg_order_analysis.json.
''', encoding='utf-8')
    print(json.dumps({'verdict': report['verdict'], 'report': str(dest), 'sha256': sha(dest),
                      'drivers_verified': len(driver_audits), 'source_files_verified': sum(len(d['sources_verified']) for d in driver_audits),
                      'pending_acceptance_gates': sum(g['status'] != 'PASS' for g in report['acceptance_gates'])}))


if __name__ == '__main__':
    main()
