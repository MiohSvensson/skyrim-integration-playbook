"""Install the reviewed Synthesis plugin and captured sidecar with rev4 rollback."""
import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parents[1]
sys.path.insert(0, str(INTEGRATION))
import materialize as mat
import runtime_inventory as runtime
from research.verified_patch_install import install_verified_patch as base

LAYER = 'T5861 Synthesis Patch (1.01)'
PATCH = 'Synthesis - Patch.esp'
SIDECAR = 'SKSE/Plugins/Experience/Races/GeneratedExperiencePatch.ini'
CANDIDATE_SHA256 = '5f8f491fc086631868ecd78fb4f19c09b76e9a8a4e3b0cb20d5156611cfc64a8'
SIDECAR_SHA256 = '2eec837296da38c4e69c2927cc7293918a325fb61120f87bf743044b8ed12417'
INPUT_SHA256 = '3a846400b3ae045e0bedd767e56a56b1877931d93d07876eb75f435daae51cc7'
DELTA_SHA256 = '71cb18f6c671070a53e3544a14e493f16c02a97f25b8c730e06dd06aa1123527'
base.LAYER = LAYER
original_edit_modlist = base.edit_modlist
original_check_plan = base.check_plan


def edit_modlist(blob):
    doc = base.Lines(original_edit_modlist(blob))
    for index, (body, ending) in enumerate(doc.rows):
        text = body.decode('utf-8')
        if body[:1] in (b'+', b'-') and mat.key(text[1:]).startswith('zz88'):
            doc.rows[index] = (b'-' + text[1:].encode('utf-8'), ending)
    return doc.blob()


base.edit_modlist = edit_modlist


def source_scope(proof):
    diagnostic_path = Path(proof['diagnostic_receipt']).resolve(strict=True)
    diagnostic = base.load(diagnostic_path)
    assert diagnostic['status'] == 'DIAGNOSTIC_PROFILE_READY_NOT_PRODUCTION_INSTALLATION'
    candidate = Path(diagnostic['candidate']['path']).resolve(strict=True)
    sidecar = Path(diagnostic['sidecar']['path']).resolve(strict=True)
    assert mat.sha(candidate) == diagnostic['candidate']['sha256'] == CANDIDATE_SHA256
    assert mat.sha(sidecar) == diagnostic['sidecar']['sha256'] == SIDECAR_SHA256
    replay_path = Path(diagnostic['replay_result']['path']).resolve(strict=True)
    assert mat.sha(replay_path) == diagnostic['replay_result']['sha256']
    replay = base.load(replay_path)
    assert replay['status'] == 'REPLAY_COMPLETED_OUTPUT_NOT_DEPLOYED_NEEDS_SEMANTIC_AND_XEDIT_VALIDATION'
    assert len(replay['stages']) == 6 and all(row['return_code'] == 0 for row in replay['stages'])
    assert replay['final_plugin_candidate']['sha256'] == CANDIDATE_SHA256
    assert replay['generated_sidecar']['sha256'] == SIDECAR_SHA256 and replay['private_sidecar_restored']
    prepared_replay = base.load(Path(replay['prepared']['path']).parent / 'prepared.json')
    original = Path(prepared_replay['private_sidecar']['path']).resolve(strict=True)
    assert mat.sha(original) == replay['original_sidecar_sha256']
    prepared, result = base.producer_gate(proof['producer_task'])
    assert prepared['patch_name'] == PATCH and result['native_loaded_context']['expected_profile_plugins'] == 1080
    assert result['native_loaded_context']['expected_native_entries'] == 1081
    header = base.candidate_header(candidate)
    assert header['sha256'] == CANDIDATE_SHA256 and header['own_records'] == 0
    validation_path = Path(proof['validation_report']).resolve(strict=True)
    validation = base.load(validation_path)
    assert validation['status'] == 'SYNTHESIS_CANDIDATE_SCOPED_STATIC_PASS_PENDING_INSTALLATION'
    assert validation['candidate']['sha256'] == CANDIDATE_SHA256
    assert validation['candidate']['records'] == header['records']
    assert validation['generated_missing_references'] == []
    assert validation['native_check']['diagnostics'] == 0
    assert validation['native_check']['result_sha256'] == mat.sha(Path(proof['producer_task']) / 'result.json')
    input_path = Path(proof['input_models']).resolve(strict=True)
    input_report = base.load(input_path)
    assert input_report['candidate_sha256'] == CANDIDATE_SHA256
    assert input_report['source_key_count'] == 275 and input_report['model_field_count'] == 1100
    assert validation['input_models']['sha256'] == INPUT_SHA256 == mat.sha(input_path)
    delta_path = Path(proof['arma_delta']).resolve(strict=True)
    assert validation['arma_delta_sha256'] == DELTA_SHA256 == mat.sha(delta_path)
    resource_path = Path(proof['resource_acceptance']).resolve(strict=True)
    resources = base.load(resource_path)
    assert resources['accepted'] is True and resources['status'] == 'GENERATED_MESH_RESOURCES_VERIFIED'
    assert mat.sha(resources['proof']['path']) == resources['proof']['sha256']
    assert len(resources['resources']) == 23
    for row in resources['resources']:
        assert mat.sha(mat.TARGET / 'mods/ZZ83 Verified generated item and quest assets' / row['path']) == row['sha256']
    return candidate, sidecar, header


def prepare(args):
    replay_path = base.research_path(args.replay)
    proof = {
        'producer_task': str(Path(args.producer).resolve(strict=True)),
        'diagnostic_receipt': str(base.research_path(args.diagnostic_receipt)),
        'validation_report': str(base.research_path(args.validation_report)),
        'input_models': str(base.research_path(args.input_models)),
        'arma_delta': str(base.research_path(args.arma_delta)),
        'resource_acceptance': str(base.research_path(args.resource_acceptance)),
    }
    candidate, sidecar, header = source_scope(proof)
    diagnostic = base.load(proof['diagnostic_receipt'])
    assert Path(diagnostic['replay_result']['path']).resolve() == replay_path
    old_plugin = mat.TARGET / 'mods' / LAYER / PATCH
    old_sidecar = mat.TARGET / 'mods' / LAYER / SIDECAR
    replace_sha = mat.sha(old_plugin)
    old_sidecar_sha = mat.sha(old_sidecar)
    plans = []
    staged = {}
    for name in base.PROFILES:
        plan, controls = base.profile_plan(name, candidate, header, replace_sha)
        plans.append(plan)
        staged[name] = controls
    mat.assert_owned_tree()
    job = base.research_path(args.output, existing=False)
    base.need(not job.exists(), 'Use a fresh Synthesis installation directory')
    old_bytes = old_plugin.stat().st_size + old_sidecar.stat().st_size
    new_bytes = candidate.stat().st_size + sidecar.stat().st_size
    base.need(shutil.disk_usage(mat.BASE).free >= mat.RESERVE + old_bytes + new_bytes + 1024 * 1024,
              'Disk reserve would be crossed')
    job.mkdir(parents=True)
    copies = []
    mappings = []
    for source, destination in [(candidate, f'mods/{LAYER}/{PATCH}'), (sidecar, f'mods/{LAYER}/{SIDECAR}')]:
        snapshot = job / 'candidate' / Path(destination).name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(source.read_bytes())
        assert mat.sha(snapshot) == mat.sha(source)
        copies.append(base.pin(snapshot))
        mappings.append({'source': str(snapshot), 'destination': destination,
                         'storage': 'private', 'bytes': snapshot.stat().st_size})
    for name in base.PROFILES:
        for filename, blob in staged[name].items():
            snapshot = job / 'controls' / name / filename
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(blob)
            copies.append(base.pin(snapshot))
            mappings.append({'source': str(snapshot), 'destination': f'profiles/{name}/{filename}',
                             'storage': 'private', 'bytes': len(blob)})
    task = Path(proof['producer_task'])
    prepared_native = base.load(task / 'prepared.json')
    frozen = [base.pin(candidate), base.pin(sidecar)]
    frozen += [base.pin(path) for path in [replay_path, proof['diagnostic_receipt'], proof['validation_report'],
                                          proof['input_models'], proof['arma_delta'], proof['resource_acceptance']]]
    frozen += [base.pin(task / name) for name in ['prepared.json', 'result.json', 'input_inventory.json', 'logs/xedit.log']]
    frozen += [base.pin(prepared_native['script']), base.pin(mat.__file__), base.pin(runtime.__file__),
               base.pin(base.plugin_binary.__file__), base.pin(base.__file__), base.pin(__file__)]
    plan = {
        'schema': 'skyrim.verified_patch_install.v1', 'utc': mat.utc(), 'status': 'PREPARED_INSTALL_ONLY_NOT_ACCEPTED',
        'installer': base.pin(__file__), 'installer_variants': [str(__file__)], 'layer': LAYER,
        'candidate_name': PATCH, 'candidate_sha256': CANDIDATE_SHA256, 'candidate_header': header,
        'producer_task': str(task), 'binary_report': proof['validation_report'],
        'source_pins': frozen, 'staged_pins': copies, 'profiles': plans, 'mappings': mappings,
        'replace_sha256': replace_sha,
        'extra_replacements': {f'mods/{LAYER}/{SIDECAR}': old_sidecar_sha},
        'sidecar_sha256': SIDECAR_SHA256, 'producer_candidate_required': False,
        'synthesis_proof': proof, 'compatibility_priority': base.COMPATIBILITY_PRIORITY,
        'acceptance': 'Fresh installed-VFS xEdit typed reload, captured sidecar, exact scoped model proof and both-profile closure required',
        'ordering': 'Preserve compatibility block before generated output; disable ZZ88 only after the captured sidecar is installed',
    }
    base.save_new(job / 'prepared.json', plan)
    print(json.dumps({'status': plan['status'], 'prepared': str(job / 'prepared.json'),
                      'profiles': [{k: row[k] for k in ('profile', 'slots')} for row in plans]}, indent=2))


def check_plan(plan, verify_current=True):
    original_check_plan(plan, verify_current=verify_current, binary_validation=False)
    source_scope(plan['synthesis_proof'])
    base.need(plan['candidate_sha256'] == CANDIDATE_SHA256 and plan['sidecar_sha256'] == SIDECAR_SHA256,
              'Synthesis candidate or sidecar policy changed')


def acceptance_guard(args, plan, receipt, installed):
    report_path = Path(args.validation_report).resolve(strict=True)
    report = base.load(report_path)
    base.need(report['status'] == 'SYNTHESIS_INSTALLED_SCOPED_STATIC_PASS_PENDING_ACCEPTANCE',
              'Production Synthesis scoped validation is missing')
    base.need(report['candidate']['sha256'] == plan['candidate_sha256'], 'Production candidate differs from review')
    base.need(report['sidecar']['sha256'] == plan['sidecar_sha256'], 'Production sidecar differs from capture')
    base.need(report['production_receipt']['sha256'] == mat.sha(Path(args.prepared).parent / 'installed.json'),
              'Production install receipt differs from validation')
    base.need(report['native_check']['task'] == str(Path(args.reload_task).resolve()), 'Wrong production native task')
    base.need(report['native_check']['result_sha256'] == mat.sha(Path(args.reload_task) / 'result.json'),
              'Production native result changed')
    base.need(report['generated_missing_references'] == [], 'Changed Synthesis model dependency remains missing')
    base.need(report['input_models']['sha256'] == INPUT_SHA256 and report['arma_delta_sha256'] == DELTA_SHA256,
              'Synthesis source context changed')
    assert mat.sha(mat.TARGET / 'mods' / LAYER / SIDECAR) == plan['sidecar_sha256']
    for profile in base.PROFILES:
        doc = base.Lines((mat.TARGET / 'profiles' / profile / 'modlist.txt').read_bytes())
        for name, _, prefix in doc.names(modlist=True):
            base.need(not ((name.startswith('zz88') or name == 'zz89 synthesis candidate') and prefix == '+'),
                      'Temporary Synthesis workspace remains active: ' + name)
    source_scope(plan['synthesis_proof'])


def accept(args):
    args.acceptance_guard = lambda plan, receipt, installed: acceptance_guard(args, plan, receipt, installed)
    base.accept(args)
    job = Path(args.prepared).parent
    context = {'schema': 'skyrim.synthesis_acceptance.v1', 'status': 'SYNTHESIS_SCOPED_STATIC_ACCEPTED_FINAL_RESOURCE_WORK_PENDING',
               'candidate': base.pin(mat.TARGET / 'mods' / LAYER / PATCH),
               'sidecar': base.pin(mat.TARGET / 'mods' / LAYER / SIDECAR),
               'validation_report': base.pin(args.validation_report),
               'proof': plan_proof(args.prepared),
               'inherited_resource_disposition_required': True, 'game_launched': False}
    base.save_new(job / 'synthesis_acceptance_manifest.json', context)
    print(json.dumps(context, indent=2))


def plan_proof(prepared):
    return base.load(prepared)['synthesis_proof']


def install(args):
    original = base.check_plan
    base.check_plan = check_plan
    try:
        base.install(args)
    finally:
        base.check_plan = original


def recover(args):
    original = base.check_plan
    base.check_plan = check_plan
    try:
        base.recover(args)
    finally:
        base.check_plan = original


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--replay', required=True)
    p.add_argument('--diagnostic-receipt', required=True)
    p.add_argument('--producer', required=True)
    p.add_argument('--validation-report', required=True)
    p.add_argument('--input-models', required=True)
    p.add_argument('--arma-delta', required=True)
    p.add_argument('--resource-acceptance', required=True)
    p.add_argument('--output', required=True)
    p.set_defaults(function=prepare)
    p = sub.add_parser('install')
    p.add_argument('--prepared', required=True)
    p.set_defaults(function=install)
    p = sub.add_parser('recover')
    p.add_argument('--prepared', required=True)
    p.set_defaults(function=recover)
    p = sub.add_parser('accept')
    p.add_argument('--prepared', required=True)
    p.add_argument('--reload-task', required=True)
    p.add_argument('--validation-report', required=True)
    p.set_defaults(function=accept)
    args = parser.parse_args()
    args.function(args)


if __name__ == '__main__':
    main()
