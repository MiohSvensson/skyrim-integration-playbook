"""Read-only SHA preflight and post-export semantic verifier for bounded patch.

Default: verify authoring inputs. --file-map JSON: verify resolved physical VFS
winners, mapping plugin names to absolute physical paths. --candidate ESP:
verify exported record set and known typed canonical fields. xEdit's recursive
leaf LinksTo verifier remains required; this decoder is intentionally limited.
"""
from pathlib import Path
import argparse
import collections
import copy
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
from analyze_fields import OUT, candidate_condition_storage_issues, candidate_editor_metadata_issues, canonical, formvalue, scan
from build_compat_plan import encoded, file_guard, sha
from placement_contract import check_physical_groups, encode_groups


def payload_hash(r):
    return sha({'flags': r['flags'], 'fields': [(t, v.hex()) for t, v in r['fields']]})


def stream_sha256(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def identity(text):
    n, i = text.split('|')
    return n.casefold(), int(i, 16)


def quest_canonical(r):
    # Exact tags present in JJSofiaScripts; unsupported new fields are retained
    # opaque and therefore fail, rather than silently assumed to be FormIDs.
    result = []
    for tag, value in r['fields']:
        if tag in ('ALFR', 'ALPC', 'VTCK'):
            assert len(value) == 4
            v = formvalue(r, struct.unpack('<I', value)[0])
        elif tag in ('VMAD', 'FULL'):
            v = canonical(r)[tag]
            if tag == 'VMAD':
                from quest_vmad_tail import canonical_quest_tail
                from vmad_audit import parse_vmad
                parsed = parse_vmad(value, lambda fid: formvalue(r, fid))
                if parsed['version'] != 5:
                    raise ValueError('Unsupported Sofia VMAD script version')
                assert len(v) == 1
                v[0].pop('tail_hex')
                v[0]['typed_quest_tail'] = canonical_quest_tail(
                    bytes.fromhex(parsed['tail_hex']), parsed['object_format'], lambda fid: formvalue(r, fid))
        else:
            v = value.hex()
        result.append([tag, v])
    return {'flags': r['flags'], 'fields': result}


def pack_canonical(r):
    result = []
    for tag, value in r['fields']:
        if tag == 'PKCU':
            assert len(value) == 12
            n, template, version = struct.unpack('<III', value)
            v = [n, formvalue(r, template), version]
        elif tag == 'CTDA':
            # The clone has no conditions; this also handles the restored stock.
            from analyze_fields import condition
            v = condition(r, value)
        else:
            v = value.hex()
        result.append([tag, v])
    return {'flags': r['flags'], 'fields': result}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file-map', type=Path)
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--report', type=Path, default=OUT / 'preflight_result.json')
    args = ap.parse_args()
    if not args.report.resolve().is_relative_to(OUT.resolve()):
        raise ValueError('Report output must remain in feature_conflicts')
    plan = json.loads((OUT / 'compat_patch_plan.json').read_text(encoding='utf-8'))
    mapped = json.loads(args.file_map.read_text(encoding='utf-8-sig')) if args.file_map else {}
    mapped = {k.casefold(): v for k, v in mapped.items()}
    paths = {}
    checks = []
    errors = []
    for g in plan['input_file_guards']:
        key = g['filename'].casefold()
        path = Path(mapped.get(key, g['path']))
        if args.file_map and key not in mapped:
            errors.append('Resolved file map lacks ' + g['filename'])
        actual = file_guard(path)
        ok = actual['sha256'] == g['sha256'] and actual['crc32'] == g['crc32']
        checks.append({'filename': g['filename'], 'path': str(path), 'sha256': actual['sha256'], 'crc32': actual['crc32'], 'matches': ok})
        if not ok:
            errors.append('Input changed: ' + g['filename'])
        paths[key] = path
    grouped = collections.defaultdict(set)
    for s in plan['priority_seed_records']:
        grouped[s['base_file'].casefold()].add((s['origin'], int(s['object_id'], 16)))
    for o in plan['typed_field_operations']:
        grouped[o['source'].casefold()].add(identity(o['record']))
    grouped['sofiafollower.esp'] |= {('sofiafollower.esp', 0xAA58), ('skyrim.esm', 0x9845C)}
    parsed = {name: scan(paths[name], wanted=keys)[0] for name, keys in grouped.items()}
    expected = {}
    for s in plan['priority_seed_records']:
        key = (s['origin'], int(s['object_id'], 16))
        base = parsed[s['base_file'].casefold()][key]
        if payload_hash(base) != s['base_raw_payload_sha256']:
            errors.append('Base payload changed: ' + str(key))
        value = canonical(base)
        if s['persistent']:
            value['$FLAGS'] = [base['flags'] | 0x400]
        expected[key] = value
    for o in plan['typed_field_operations']:
        key = identity(o['record'])
        source = canonical(parsed[o['source'].casefold()][key])
        tags = ('CTDA', 'CIS1', 'CIS2') if o['field'] == 'Conditions' else (o['field'],)
        for tag in tags:
            if tag in source:
                expected[key][tag] = copy.deepcopy(source[tag])
            else:
                expected[key].pop(tag, None)
    voices = expected[('skyrim.esm', 0x3B4A5)]['LNAM']
    assert 'erinrace.esm|001040' in voices and 'hothfollower.esp|00333C' not in voices
    voices.append('hothfollower.esp|00333C')
    voices.sort()
    qsource = parsed['sofiafollower.esp'][('sofiafollower.esp', 0xAA58)]
    if payload_hash(qsource) != plan['source_quest']['raw_payload_sha256']:
        errors.append('Sofia quest payload changed')
    candidate_checks = []
    placement_checks=[]
    placement=json.loads((OUT/'physical_placement_contract.json').read_text(encoding='utf-8'))
    candidate_sha256_before=stream_sha256(args.candidate) if args.candidate else None
    candidate_sha256_after=None
    if args.candidate:
        rs, counts, own = scan(args.candidate)
        for key, record in rs.items():
            for issue in candidate_condition_storage_issues(record):errors.append('Candidate CTDA variable storage: '+str(key)+' '+str(issue))
            for issue in candidate_editor_metadata_issues(record):errors.append('Candidate editor metadata: '+str(key)+' '+str(issue))
            expected_placement=placement['rows'].get(f'{key[0]}|{key[1]:06X}')
            if key in expected:
                if not expected_placement:errors.append('Candidate base record lacks frozen physical placement contract: '+str(key))
                else:
                    issues=check_physical_groups(record,expected_placement)
                    placement_checks.append({'record':f'{key[0]}|{key[1]:06X}','matching':not issues,
                        'expected_groups':expected_placement['expected_groups'],'actual_groups':encode_groups(record['groups']),
                        'persistent_change':expected_placement['persistent_change'],'issues':issues})
                    for issue in issues:errors.append('Candidate physical placement: '+str(key)+' '+str(issue))
        own_packs = [(k, r) for k, r in rs.items() if k[0] == args.candidate.name.casefold()]
        if len(own_packs) != 1 or own_packs[0][1]['signature'] != 'PACK':
            errors.append('Expected exactly one new own PACK')
        else:
            pk, clone = own_packs[0]
            if not 0x800 <= pk[1] <= 0xFFF:
                errors.append('New own PACK object ID outside ESL-safe range')
            s = parsed['sofiafollower.esp'][('skyrim.esm', 0x9845C)]
            if pack_canonical(s) != pack_canonical(clone):
                errors.append('New PACK differs from authored Sofia package')
            for key,record,source in ((pk,clone,s),(('sofiafollower.esp',0xAA58),rs[('sofiafollower.esp',0xAA58)],qsource)):
                actual_groups=encode_groups(record['groups']);source_groups=encode_groups(source['groups'])
                ok=actual_groups==source_groups
                placement_checks.append({'record':f'{key[0]}|{key[1]:06X}','matching':ok,'expected_groups':source_groups,'actual_groups':actual_groups})
                if not ok:errors.append('Candidate quest/clone physical GRUP differs: '+str(key))
            qkey = ('sofiafollower.esp', 0xAA58)
            actual_q = quest_canonical(rs[qkey])
            expected_q = quest_canonical(qsource)
            target = f'{pk[0]}|{pk[1]:06X}'
            redirects = 0
            alias = None
            for pair in expected_q['fields']:
                if pair[0] == 'ALST': alias = int.from_bytes(bytes.fromhex(pair[1]), 'little')
                if pair == ['ALPC', 'skyrim.esm|09845C']:
                    assert alias == 1
                    pair[1] = target
                    redirects += 1
            if redirects != 1 or actual_q != expected_q:
                errors.append('Sofia quest has changes outside the single intended Alias 1 ALPC')
            expected_keys = set(expected) | {qkey, pk}
            if set(rs) != expected_keys:
                errors.append('Unexpected record set: missing=' + str(expected_keys - set(rs)) + '; extra=' + str(set(rs) - expected_keys))
            for k, value in expected.items():
                if k not in rs: continue
                actual = canonical(rs[k])
                changed = sorted(t for t in set(actual) | set(value) if actual.get(t) != value.get(t))
                candidate_checks.append({'record': f'{k[0]}|{k[1]:06X}', 'matching': not changed, 'different_fields': changed,
                                         'expected_sha256': sha(value), 'actual_sha256': sha(actual)})
                if changed:
                    errors.append('Candidate canonical difference: ' + str(k) + ' fields=' + ','.join(changed))
            with args.candidate.open('rb') as f:
                h = f.read(24)
            if not struct.unpack_from('<I', h, 8)[0] & 0x200:
                errors.append('Candidate is not ESL flagged')
        candidate_sha256_after=stream_sha256(args.candidate)
        if candidate_sha256_before!=candidate_sha256_after:errors.append('Candidate bytes changed during verification')
    result = {'input_scope': 'resolved-map' if args.file_map else 'authoring-source-paths', 'file_checks': checks,
              'priority_seed_records_verified': len(expected), 'candidate': str(args.candidate) if args.candidate else None,
              'candidate_sha256':candidate_sha256_after if candidate_sha256_before==candidate_sha256_after else None,
              'candidate_sha256_before':candidate_sha256_before,'candidate_sha256_after':candidate_sha256_after,
              'candidate_unchanged_during_verification':candidate_sha256_before==candidate_sha256_after if args.candidate else None,
              'physical_placement_contract_sha256':stream_sha256(OUT/'physical_placement_contract.json'),
              'physical_placement_checks':placement_checks,
              'candidate_checks': candidate_checks, 'errors': errors, 'passed': not errors,
              'limits': 'Limited binary normalizer. Fresh final-VFS xEdit typed leaf LinksTo reload verification and whole-profile checks are separately required. No game/runtime test.'}
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PASS' if not errors else 'FAIL', 'file guards', len(checks), 'base records', len(expected), 'candidate records', len(candidate_checks), 'errors', len(errors))
    for e in errors: print(e)
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
