"""Independent read-only check of the 27-record quest metadata extension."""
from pathlib import Path
import argparse
import collections
import copy
import hashlib
import json
import struct
import sys

sys.dont_write_bytecode = True
from analyze_fields import OUT, scan, canonical, candidate_condition_storage_issues, candidate_editor_metadata_issues
from build_compat_plan import file_guard, sha
from placement_contract import check_physical_groups, encode_groups


def stream_sha256(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file-map', type=Path)
    ap.add_argument('--candidate', type=Path)
    ap.add_argument('--report', type=Path, default=OUT / 'quest_extension_preflight.json')
    args = ap.parse_args()
    if not args.report.resolve().is_relative_to(OUT.resolve()):
        raise ValueError('Report must remain in feature_conflicts')
    plan = json.loads((OUT / 'quest_extension_plan.json').read_text(encoding='utf-8'))
    mapped = json.loads(args.file_map.read_text(encoding='utf-8-sig')) if args.file_map else {}
    mapped = {k.casefold(): v for k, v in mapped.items()}
    files = {}
    errors = []
    guards = []
    for g in plan['input_file_guards']:
        name = g['filename'].casefold()
        if args.file_map and name not in mapped: errors.append('Missing resolved path: ' + name)
        p = Path(mapped.get(name, g['path']))
        check = file_guard(p)
        ok = check['sha256'] == g['sha256'] and check['crc32'] == g['crc32']
        guards.append(check | {'matches': ok})
        if not ok: errors.append('Input changed: ' + name)
        files[name] = p
    keys = collections.defaultdict(set)
    for r in plan['rows']:
        k = (r['origin'], int(r['object_id'], 16))
        keys[r['seed_file'].casefold()].add(k)
        if r['field_source']: keys[r['field_source'].casefold()].add(k)
    parsed = {n: scan(files[n], wanted=ks)[0] for n, ks in keys.items()}
    expected = {}
    for r in plan['rows']:
        k = (r['origin'], int(r['object_id'], 16))
        value = canonical(parsed[r['seed_file'].casefold()][k])
        if sha(value) != r['seed_semantic_sha256']: errors.append('Seed canonical changed: ' + str(k))
        if r['field_source']:
            donor = canonical(parsed[r['field_source'].casefold()][k])
            for tag in ('CTDA', 'CIS1', 'CIS2'):
                if tag in donor: value[tag] = copy.deepcopy(donor[tag])
                else: value.pop(tag, None)
        expected[k] = value
    checks = []
    placement_checks=[]
    placement=json.loads((OUT/'physical_placement_contract.json').read_text(encoding='utf-8'))
    candidate_sha256_before=stream_sha256(args.candidate) if args.candidate else None
    candidate_sha256_after=None
    if args.candidate:
        rs, _, _ = scan(args.candidate)
        for key,record in rs.items():
            for issue in candidate_condition_storage_issues(record):errors.append('Candidate CTDA variable storage: '+str(key)+' '+str(issue))
            for issue in candidate_editor_metadata_issues(record):errors.append('Candidate editor metadata: '+str(key)+' '+str(issue))
            expected_placement=placement['rows'].get(f'{key[0]}|{key[1]:06X}')
            if expected_placement:
                issues=check_physical_groups(record,expected_placement)
                placement_checks.append({'record':f'{key[0]}|{key[1]:06X}','matching':not issues,
                    'expected_groups':expected_placement['expected_groups'],'actual_groups':encode_groups(record['groups']),'issues':issues})
                for issue in issues:errors.append('Candidate physical placement: '+str(key)+' '+str(issue))
            else:errors.append('Candidate record lacks physical placement contract: '+str(key))
        if set(rs) != set(expected):
            errors.append('Unexpected record set: missing=' + str(set(expected) - set(rs)) + '; extra=' + str(set(rs) - set(expected)))
        for k, value in expected.items():
            if k not in rs: continue
            actual = canonical(rs[k])
            fields = sorted(t for t in set(value) | set(actual) if value.get(t) != actual.get(t))
            checks.append({'record': f'{k[0]}|{k[1]:06X}', 'matching': not fields, 'different_fields': fields,
                           'expected_sha256': sha(value), 'actual_sha256': sha(actual)})
            if fields: errors.append('Candidate canonical differs: ' + str(k) + ' fields=' + ','.join(fields))
        with args.candidate.open('rb') as f:
            flags = struct.unpack_from('<I', f.read(24), 8)[0]
        if not flags & 0x200: errors.append('Candidate is not ESL flagged')
        candidate_sha256_after=stream_sha256(args.candidate)
        if candidate_sha256_before!=candidate_sha256_after:errors.append('Candidate bytes changed during verification')
    result = {'input_scope': 'resolved-file-map' if args.file_map else 'authoring-source-paths',
              'file_guards': guards, 'seed_records': len(expected), 'candidate': str(args.candidate) if args.candidate else None,
              'candidate_sha256':candidate_sha256_after if candidate_sha256_before==candidate_sha256_after else None,
              'candidate_sha256_before':candidate_sha256_before,'candidate_sha256_after':candidate_sha256_after,
              'candidate_unchanged_during_verification':candidate_sha256_before==candidate_sha256_after if args.candidate else None,
              'physical_placement_contract_sha256':stream_sha256(OUT/'physical_placement_contract.json'),
              'physical_placement_checks':placement_checks,
              'candidate_checks': checks, 'errors': errors, 'passed': not errors,
              'limits': 'Limited binary normalizer; fresh final-VFS xEdit recursive typed leaf reload verification and full profile checks remain required. No game/runtime validation.'}
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Quest extension:', 'PASS' if not errors else 'FAIL', len(guards), 'guards,', len(expected), 'records,', len(errors), 'errors')
    for e in errors: print(e)
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__': main()
