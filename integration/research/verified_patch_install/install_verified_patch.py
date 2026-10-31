"""Guarded, journaled installation of an exported compatibility candidate.

prepare is read-only with respect to UnifiedSkyrim. install writes only reviewed
private destinations. Installation never constitutes acceptance: accept requires
a later successful, fresh MO2/xEdit typed reload of the installed VFS winner.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
import msvcrt
import os
import re
import shutil
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
INTEGRATION = HERE.parents[1]
sys.path.insert(0, str(INTEGRATION))
import materialize as mat
import runtime_inventory as runtime
sys.path.insert(0, str(mat.BASE / 'rootcause'))
import plugin_binary

LAYER = 'ZZ87 Verified compatibility patches'
PROFILES = ('Unified Skyrim', 'Unified Build')
CONTROLS = ('modlist.txt', 'plugins.txt', 'loadorder.txt', 'Skyrim.ini',
            'SkyrimCustom.ini', 'initweaks.ini', 'archives.txt', 'settings.ini')
DERIVED = {'synthesis - patch.esp', 'dyndolod.esp', 'occlusion.esp'}
COMPATIBILITY_PRIORITY = {
    'database feature compatibility.esp': 10,
    'database quest feature compatibility.esp': 20,
    'database forgotten city ussep navigation.esp': 30,
    'database glenmoril underground door compatibility.esp': 40,
    'database glenmoril navigation compatibility.esp': 50,
}
BINARY_STATUSES = {'BINARY_PASS_TYPED_RELOAD_REQUIRED', 'STATIC_BINARY_AND_TYPED_RELOAD_PASS'}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha_bytes(blob):
    return hashlib.sha256(blob).hexdigest()


def load(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def research_path(path, existing=True):
    p = Path(path).resolve(strict=existing)
    mat.within(p, mat.BASE / 'integration/research')
    return p


def regular(path):
    p = Path(path)
    st = p.lstat()
    need(p.is_file() and not (getattr(st, 'st_file_attributes', 0) & 0x400),
         'Not a plain non-reparse file: ' + str(p))
    return st


def pin(path):
    p = Path(path).resolve(strict=True)
    st = regular(p)
    return {'path': str(p), 'sha256': mat.sha(p), 'size_bytes': st.st_size}


def check_pin(row):
    st = regular(row['path'])
    need(st.st_size == row['size_bytes'] and mat.sha(row['path']) == row['sha256'],
         'Frozen evidence or source changed: ' + row['path'])


def save_new(path, value):
    p = research_path(path, existing=False)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def producer_gate(task, expected_candidate=None):
    task = Path(task).resolve(strict=True)
    mat.within(task, mat.TARGET / 'validation')
    prepared, result = load(task / 'prepared.json'), load(task / 'result.json')
    need(result.get('status') == 'PASS' and result.get('usvfs') is True,
         'Producer did not explicitly PASS in the real MO2 VFS')
    need(result.get('return_code') == 0 and result.get('marker_seen') is True,
         'Producer completion or process gate failed')
    need(result.get('changed_input_plugins') == [] and result.get('changed_profile_controls') == [],
         'Producer inputs changed')
    need(prepared.get('game_not_selected') is True, 'Producer was not restricted to xEdit')
    need(result.get('pass_marker') == prepared.get('pass_marker') and prepared.get('pass_marker'),
         'Producer marker mismatch')
    log = task / 'logs/xedit.log'
    need(mat.sha(log) == result.get('log_sha256'), 'Producer log SHA mismatch')
    need(prepared['pass_marker'] in log.read_text('utf-8-sig', errors='replace'),
         'Producer marker absent from pinned log')
    need(mat.sha(prepared['script']) == prepared['script_sha256'], 'Executed script changed')
    if expected_candidate is not None:
        need(prepared.get('candidate') and Path(prepared['candidate']).resolve() == expected_candidate,
             'Producer candidate path mismatch')
        need(result.get('candidate_sha256') == mat.sha(expected_candidate),
             'Producer candidate SHA mismatch')
    return prepared, result


def binary_gate(report, candidate, candidate_sha):
    need(report.get('errors', []) == [], 'Independent binary report contains errors')
    candidate_field = report.get('candidate')
    if isinstance(candidate_field, dict):
        path = candidate_field.get('path')
        digest = candidate_field.get('sha256')
    else:
        path = candidate_field
        digest = report.get('candidate_sha256')
    need(path and Path(path).resolve() == candidate, 'Binary report has no matching candidate')
    need(digest == candidate_sha, 'Binary report does not bind the exact candidate SHA')
    if 'passed' in report:
        need(report['passed'] is True, 'Binary report did not explicitly pass')
        checks = report.get('candidate_checks')
        need(isinstance(checks, list) and checks, 'Source-only preflight cannot authorize installation')
        need(all(c.get('matching') is True and c.get('different_fields') == [] for c in checks),
             'Binary candidate checks are incomplete or failed')
        guards = report.get('file_checks', report.get('file_guards'))
        need(isinstance(guards, list) and guards, 'Binary report lacks source SHA guards')
        for guard in guards:
            need(guard.get('matches') is True and guard.get('path') and guard.get('sha256'),
                 'Binary report has an incomplete source guard')
            need(mat.sha(guard['path']) == guard['sha256'], 'Binary verifier source changed')
    else:
        need(report.get('status') in BINARY_STATUSES, 'Unrecognized binary candidate pass status')
        need(isinstance(candidate_field, dict) and candidate_field.get('records'),
             'Navigation report lacks an actual candidate record set')


def candidate_header(candidate):
    h = runtime.header(candidate)
    need(candidate.suffix.casefold() == '.esp' and not h['is_master'],
         'This installer supports ordinary compatibility ESPs only')
    masters, records = plugin_binary.read(candidate)
    need(records and records[0]['sig'] == 'TES4', 'Missing TES4 header')
    need(len(masters) < 254 and len({mat.key(m) for m in masters}) == len(masters),
         'Duplicate or excessive masters')
    own = []
    seen = set()
    for r in records[1:]:
        index, object_id = r['fid'] >> 24, r['fid'] & 0xFFFFFF
        need(index <= len(masters), 'Record uses an out-of-range local master index')
        need((r['sig'], r['fid']) not in seen, 'Duplicate candidate record identity')
        seen.add((r['sig'], r['fid']))
        if index == len(masters):
            own.append(object_id)
    if h['is_light']:
        need(all(0x800 <= x <= 0xFFF for x in own), 'Own IDs are not ESL-safe without compaction')
    return h | {'records': len(records) - 1, 'own_records': len(own),
                'own_object_ids': [f'{x:06X}' for x in own]}


class Lines:
    """Keep BOM, line terminators, comments, disabled stars and untouched bytes."""
    def __init__(self, blob):
        self.bom = b'\xef\xbb\xbf' if blob.startswith(b'\xef\xbb\xbf') else b''
        raw = blob[len(self.bom):]
        raw.decode('utf-8', errors='strict')
        self.rows = []
        for chunk in raw.splitlines(keepends=True):
            eol = b'\r\n' if chunk.endswith(b'\r\n') else chunk[-1:] if chunk.endswith((b'\r', b'\n')) else b''
            self.rows.append((chunk[:-len(eol)] if eol else chunk, eol))
        self.newline = next((e for _, e in self.rows if e), b'\n')

    def names(self, modlist=False):
        out = []
        for body, _ in self.rows:
            text = body.decode('utf-8')
            if not text or text.startswith('#'):
                continue
            name = text[1:] if text.startswith(('*', '+', '-')) else text
            if modlist:
                need(text.startswith(('+', '-')) or text.startswith(('*DLC: ', '*Unmanaged: ')),
                     'Malformed modlist row: ' + text)
            need(name == name.strip() and name, 'Malformed control filename')
            out.append((mat.key(name), name, text[:1]))
        need(len({x[0] for x in out}) == len(out), 'Duplicate explicit control entries')
        return out

    def blob(self):
        return self.bom + b''.join(b + e for b, e in self.rows)

    def append(self, body, old_eol=None):
        if self.rows and not self.rows[-1][1]:
            self.rows[-1] = (self.rows[-1][0], self.newline)
        self.rows.append((body, old_eol or self.newline))


def edit_plugin_order(blob, candidate_name, derived, starred, compat_active=()):
    doc = Lines(blob)
    doc.names()
    compatible = {mat.key(candidate_name), *compat_active}
    move = compatible | derived
    kept, suffix, compat_rows = [], [], {}
    for body, eol in doc.rows:
        text = body.decode('utf-8')
        n = mat.key(text[1:] if text.startswith('*') else text)
        if n == mat.key(candidate_name):
            compat_rows[n] = ((('*' if starred else '') + candidate_name).encode('utf-8'), eol)
        elif n in compatible and (not starred or text.startswith('*')):
            compat_rows[n] = (body, eol)
        elif n in move and (not starred or text.startswith('*')):
            suffix.append((body, eol))
        else:
            kept.append((body, eol))
    doc.rows = kept
    compat_rows.setdefault(mat.key(candidate_name),
                           ((('*' if starred else '') + candidate_name).encode('utf-8'), doc.newline))
    for name in sorted(compat_rows, key=lambda n: (COMPATIBILITY_PRIORITY.get(n, 1000), n)):
        doc.append(*compat_rows[name])
    for row in suffix:
        doc.append(*row)
    return doc.blob()


def edit_modlist(blob):
    doc = Lines(blob)
    doc.names(modlist=True)
    retained, eol = [], doc.newline
    for body, ending in doc.rows:
        if mat.key(body.decode('utf-8')[1:]) == mat.key(LAYER) and body[:1] in (b'+', b'-'):
            eol = ending or doc.newline
        else:
            retained.append((body, ending))
    at = 0
    while at < len(retained) and (not retained[at][0] or retained[at][0].startswith(b'#')):
        at += 1
    if at and not retained[at-1][1]:
        retained[at-1] = (retained[at-1][0], doc.newline)
    retained.insert(at, (('+' + LAYER).encode('utf-8'), eol))
    doc.rows = retained
    return doc.blob()


def active_names(plugins_blob, mods):
    root = {}
    for name, folder in mods + [('Game/Data', mat.TARGET / 'Game/Data')]:
        if not folder.is_dir():
            continue
        with os.scandir(mat.lp(folder)) as entries:
            for entry in entries:
                if entry.is_file(follow_symlinks=False):
                    root.setdefault(mat.key(entry.name), (name, folder / entry.name))
    names = ['Skyrim.esm', 'Update.esm', 'Dawnguard.esm', 'HearthFires.esm', 'Dragonborn.esm']
    ccc = mat.TARGET / 'Game/Skyrim.ccc'
    if ccc.is_file():
        names += [n.strip() for n in ccc.read_text('utf-8-sig').splitlines()
                  if n.strip() and not n.startswith('#') and mat.key(n.strip()) in root]
    names += [name for _, name, prefix in Lines(plugins_blob).names() if prefix == '*']
    return list(dict((mat.key(n), n) for n in names).values()), root


def topo(names, headers):
    positions = {mat.key(n): i for i, n in enumerate(names)}
    need(len(positions) == len(names), 'Duplicate runtime plugin')
    for n in names:
        need(mat.key(n) in headers, 'Missing plugin: ' + n)
        for master in headers[mat.key(n)]['masters']:
            need(mat.key(master) in positions, f'Missing master {master} of {n}')
            need(positions[mat.key(master)] < positions[mat.key(n)], f'Topological violation: {n} before {master}')
    slots = {'full': sum(not headers[mat.key(n)]['is_light'] for n in names),
             'light': sum(headers[mat.key(n)]['is_light'] for n in names)}
    need(slots['full'] <= 254 and slots['light'] <= 4096, 'Plugin slots overflow')
    return slots


def profile_plan(name, candidate, header, replace_sha):
    folder = mat.TARGET / 'profiles' / name
    pins = {n: pin(folder / n) for n in CONTROLS if (folder / n).is_file()}
    need(all(n in pins for n in CONTROLS[:3]), 'Missing profile control file')
    controls = {n: (folder / n).read_bytes() for n in CONTROLS[:3]}
    mods_doc = Lines(controls['modlist.txt'])
    mods = [(n, mat.TARGET / 'mods' / n) for _, n, prefix in mods_doc.names(modlist=True) if prefix == '+']
    need(all(p.is_dir() for _, p in mods), 'Missing enabled mod directory')
    names, root = active_names(controls['plugins.txt'], mods)
    headers, inputs = {}, []
    for n in names:
        need(mat.key(n) in root, 'Missing active plugin ' + n)
        provider, path = root[mat.key(n)]
        h = runtime.header(path)
        if mat.key(n) == mat.key(candidate.name):
            need(provider == LAYER and replace_sha == h['sha256'],
                 'Candidate already active outside the explicitly pinned replacement')
        headers[mat.key(n)] = h
        inputs.append({'name': n, 'provider': provider, **pin(path), 'masters': h['masters']})
    topo(names, headers)
    collision = root.get(mat.key(candidate.name))
    if collision:
        need(collision[0] == LAYER and replace_sha == mat.sha(collision[1]),
             'Existing candidate winner is not the pinned own-layer replacement')
    derived = {mat.key(n) for n in names if mat.key(n) in DERIVED}
    while True:
        more = {mat.key(n) for n in names if mat.key(n) != 'dyndolod.esm' and
                any(mat.key(m) in derived for m in headers[mat.key(n)]['masters'])}
        if more <= derived:
            break
        derived |= more
    need(not any(mat.key(m) in derived for m in header['masters']),
         'Compatibility candidate depends on a downstream generated plugin')
    compat_active = {mat.key(n) for n in names if mat.key(n) in COMPATIBILITY_PRIORITY}
    new_controls = {'modlist.txt': edit_modlist(controls['modlist.txt']),
                    'plugins.txt': edit_plugin_order(controls['plugins.txt'], candidate.name, derived, True, compat_active),
                    'loadorder.txt': edit_plugin_order(controls['loadorder.txt'], candidate.name, derived, False, compat_active)}
    planned_names, _ = active_names(new_controls['plugins.txt'], mods)
    headers[mat.key(candidate.name)] = header
    slots = topo(planned_names, headers)
    load_names = [k for k, _, _ in Lines(new_controls['loadorder.txt']).names()]
    active_set = {mat.key(n) for n in planned_names}
    need([k for k in load_names if k in active_set] == [mat.key(n) for n in planned_names],
         'plugins.txt and loadorder.txt active order disagree')
    return {'profile': name, 'control_pins': pins, 'inputs': inputs, 'slots': slots,
            'new_active_order': planned_names, 'relocated_derived_suffix': sorted(derived),
            'compatibility_order': [n for n in planned_names if mat.key(n) in COMPATIBILITY_PRIORITY]}, new_controls


def prepare(args):
    candidate = research_path(args.candidate)
    need(Path(candidate.name).name == candidate.name, 'Invalid plugin filename')
    need(mat.key(candidate.name) in COMPATIBILITY_PRIORITY, 'Candidate is outside the explicit compatibility name/priority table')
    prepared, result = producer_gate(args.producer, candidate)
    report_path = research_path(args.binary_report)
    binary_gate(load(report_path), candidate, result['candidate_sha256'])
    need(prepared.get('patch_name') == candidate.name, 'Patch name differs from exported filename')
    header = candidate_header(candidate)
    need(header['sha256'] == result['candidate_sha256'], 'Candidate changed during preflight')
    job = research_path(args.output, existing=False)
    need(not job.exists(), 'Use a fresh immutable preparation directory')
    plans = []
    staged = {}
    for name in PROFILES:
        p, files = profile_plan(name, candidate, header, args.replace_sha256)
        plans.append(p)
        staged[name] = files
    build_plan = next(p for p in plans if p['profile'] == 'Unified Build')
    need(Path(prepared['profile']).resolve() == mat.TARGET / 'profiles/Unified Build', 'Unexpected producer profile')
    for name, digest in prepared['profile_controls'].items():
        need(build_plan['control_pins'][name]['sha256'] == digest, 'Build profile changed after producer: ' + name)
    producer_inputs = load(Path(args.producer) / 'input_inventory.json')['plugins']
    current = {mat.key(r['name']): r['sha256'] for r in build_plan['inputs']}
    old = {mat.key(r['name']): r['sha256'] for r in producer_inputs}
    need(current == old, 'Current Build inputs differ from producer full context')
    marker = load(mat.TARGET / '.integration-managed.json')
    need(Path(marker['journal']).resolve() == mat.DB, 'Ownership marker journal mismatch')
    job.mkdir(parents=True)
    copies, mappings = [], []
    source = job / 'candidate' / candidate.name
    source.parent.mkdir()
    source.write_bytes(candidate.read_bytes())
    need(mat.sha(source) == header['sha256'], 'Candidate snapshot mismatch')
    copies.append(pin(source))
    mappings.append({'source': str(source), 'destination': f'mods/{LAYER}/{candidate.name}',
                     'storage': 'private', 'bytes': source.stat().st_size})
    for name in PROFILES:
        for filename, blob in staged[name].items():
            source = job / 'controls' / name / filename
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(blob)
            copies.append(pin(source))
            mappings.append({'source': str(source), 'destination': f'profiles/{name}/{filename}',
                             'storage': 'private', 'bytes': len(blob)})
    frozen = [pin(candidate), pin(report_path)]
    task = Path(args.producer).resolve()
    frozen += [pin(task / n) for n in ['prepared.json', 'result.json', 'input_inventory.json', 'logs/xedit.log']]
    frozen.append(pin(prepared['script']))
    frozen += [pin(mat.TARGET / '.integration-managed.json'), pin(mat.__file__), pin(runtime.__file__),
               pin(plugin_binary.__file__)]
    plan = {'schema': 'skyrim.verified_patch_install.v1', 'utc': mat.utc(),
            'status': 'PREPARED_INSTALL_ONLY_NOT_ACCEPTED', 'installer': pin(__file__),
            'layer': LAYER, 'candidate_name': candidate.name, 'candidate_sha256': header['sha256'],
            'candidate_header': header, 'producer_task': str(task), 'binary_report': str(report_path),
            'source_pins': frozen, 'staged_pins': copies, 'profiles': plans, 'mappings': mappings,
            'replace_sha256': args.replace_sha256,
            'compatibility_priority': COMPATIBILITY_PRIORITY,
            'acceptance': 'Fresh installed-VFS xEdit typed reload required. Neither installation nor binary export is acceptance.',
            'ordering': 'Preserve gameplay relative order; known compatibility patches have fixed feature/quest/FC/Underground/Glen priority independent of installation order, then generated output/dependent suffix. DynDOLOD.esm retains original master position.'}
    save_new(job / 'prepared.json', plan)
    print(json.dumps({'status': plan['status'], 'prepared': str(job / 'prepared.json'),
                      'sha256': mat.sha(job / 'prepared.json'), 'profiles': [{k: p[k] for k in ('profile', 'slots', 'relocated_derived_suffix')} for p in plans]}, indent=2))


def check_plan(plan, verify_current=True):
    need(plan['schema'] == 'skyrim.verified_patch_install.v1' and plan['layer'] == LAYER, 'Wrong plan schema/layer')
    need(plan.get('compatibility_priority') == COMPATIBILITY_PRIORITY, 'Compatibility priority policy changed')
    need(Path(plan['installer']['path']).resolve() == Path(__file__).resolve(), 'Wrong installer source')
    for row in [plan['installer'], *plan['source_pins'], *plan['staged_pins']]:
        check_pin(row)
    producer_gate(plan['producer_task'], Path(plan['source_pins'][0]['path']))
    binary_gate(load(plan['binary_report']), Path(plan['source_pins'][0]['path']), plan['candidate_sha256'])
    if verify_current:
        for profile in plan['profiles']:
            for row in profile['control_pins'].values():
                check_pin(row)
            for row in profile['inputs']:
                check_pin(row)
    need([p['profile'] for p in plan['profiles']] == list(PROFILES), 'Unexpected profile set/order')
    source_pins = {str(Path(p['path']).resolve()): p for p in plan['staged_pins']}
    need(len(source_pins) == len(plan['mappings']), 'Incomplete staged source set')
    for mapping in plan['mappings']:
        source = str(Path(mapping['source']).resolve())
        need(source in source_pins and source_pins[source]['size_bytes'] == mapping['bytes'] and
             mapping.get('storage') == 'private', 'Unpinned or non-private mapping')
    header = candidate_header(Path(plan['source_pins'][0]['path']))
    need(header == plan['candidate_header'], 'Candidate structure changed')
    if verify_current:
        # Recalculate from current controls, so the staged text is not trusted merely
        # because its hash occurs in a JSON plan.
        for profile in plan['profiles']:
            current, expected = profile_plan(profile['profile'], Path(plan['source_pins'][0]['path']),
                                             header, plan['replace_sha256'])
            need(current == profile, 'Current active-input or ordering plan differs')
            for filename, blob in expected.items():
                destination = f'profiles/{profile["profile"]}/{filename}'
                matches = [m for m in plan['mappings'] if m['destination'] == destination]
                need(len(matches) == 1 and Path(matches[0]['source']).read_bytes() == blob,
                     'Staged control file differs from recomputed ordering')


def install_unlocked(args):
    path = research_path(args.prepared)
    plan = load(path)
    check_plan(plan)
    job = path.parent
    need(not (job / 'installed.json').exists() and not (job / 'install_started.json').exists(),
         'Existing install attempt; inspect receipt/rollback rather than blindly retry')
    mappings = plan['mappings']
    allowed = {f'mods/{LAYER}/{plan["candidate_name"]}'} | {
        f'profiles/{p}/{n}' for p in PROFILES for n in CONTROLS[:3]}
    need({m['destination'] for m in mappings} == allowed and len(mappings) == len(allowed),
         'Unexpected or duplicate destination mapping')
    backups = {}
    for i, item in enumerate(mappings):
        destination = mat.guard_destination(mat.TARGET / item['destination'])
        if destination.exists():
            st = regular(destination)
            need(st.st_nlink == 1, 'Existing writable destination is shared')
            if item['destination'].startswith('mods/'):
                need(plan['replace_sha256'] and mat.sha(destination) == plan['replace_sha256'],
                     'Replacement SHA not explicitly pinned')
            backup = job / 'backups' / f'{i:02d}.bin'
            backup.parent.mkdir(exist_ok=True)
            backup.write_bytes(destination.read_bytes())
            backups[item['destination']] = pin(backup) | {'prior_sha256': mat.sha(destination)}
        else:
            backups[item['destination']] = None
    needed = sum(m['bytes'] for m in mappings) + 4096 * len(mappings)
    need(shutil.disk_usage(mat.BASE).free >= mat.RESERVE + needed, 'Disk reserve would be crossed')
    check_plan(plan)
    unit = 'verified_patch_' + uuid.uuid4().hex
    unit = 'verified_patch_' + uuid.uuid4().hex
    c = mat.connect()
    c.execute('begin immediate')
    old_rows = []
    for item in mappings:
        old = c.execute('select * from files where dest_key=?', (mat.key(item['destination']),)).fetchone()
        if old:
            need(old['status'] == 'materialized', 'Destination has unresolved journal work')
            old_rows.append(dict(old))
    save_new(job / 'install_started.json', {
        'schema': 'skyrim.verified_patch_install.started.v1', 'utc': mat.utc(), 'install_pid': os.getpid(),
        'plan': pin(path), 'unit': unit, 'backups': backups, 'original_file_rows': old_rows})
    touched = []
    try:
        # add_file_mapping owns the canonical source/destination validation and
        # planned journal records. Never call build(): it consumes unrelated work.
        for row in old_rows:
            c.execute('delete from files where id=?', (row['id'],))
        c.execute('insert into events values(?,?,?)', (mat.utc(), 'verified_patch_prior_rows', json.dumps({'unit': unit, 'rows': old_rows, 'backups': backups})))
        mat.add_file_mapping(c, unit, mappings, 'Independently verified exported compatibility candidate; acceptance pending fresh installed-VFS typed reload')
        for item in mappings:
            source = Path(item['source'])
            destination = mat.guard_destination(mat.TARGET / item['destination'])
            prior = backups[item['destination']]
            need((destination.exists() and mat.sha(destination) == prior['prior_sha256']) if prior else not destination.exists(),
                 'Destination drift before atomic replacement')
            os.makedirs(mat.lp(destination.parent), exist_ok=True)
            touched.append(item)
            digest = mat.make_private(source, destination, regular(source))
            need(digest == mat.sha(source), 'Private materialization SHA mismatch')
            c.execute("update files set status='materialized',sha256=? where unit_id=? and dest_key=?",
                      (digest, unit, mat.key(item['destination'])))
            c.commit()
        for row in plan['source_pins'] + plan['staged_pins']:
            check_pin(row)
        for profile in plan['profiles']:
            for row in profile['inputs']:
                if mat.key(row['name']) != mat.key(plan['candidate_name']):
                    check_pin(row)
            for filename, row in profile['control_pins'].items():
                if filename not in CONTROLS[:3]:
                    check_pin(row)
        for item in mappings:
            need(mat.sha(mat.TARGET / item['destination']) == mat.sha(item['source']),
                 'Installed destination changed before receipt')
        receipt = {'utc': mat.utc(), 'status': 'INSTALLED_PENDING_FRESH_TYPED_RELOAD',
                   'accepted': False, 'unit': unit, 'prepared': pin(path),
                   'candidate_name': plan['candidate_name'], 'candidate_sha256': plan['candidate_sha256'],
                   'files': [pin(mat.TARGET / m['destination']) for m in mappings],
                   'required_next_step': 'New MO2/xEdit process with installed candidate active; run exact typed reload verifier before accept.'}
        c.execute('insert into events values(?,?,?)', (mat.utc(), 'verified_patch_installed_pending_reload', json.dumps(receipt)))
        c.commit()
        save_new(job / 'installed.json', receipt)
        print(json.dumps(receipt, indent=2))
    except BaseException as exc:
        rollback_errors = []
        for item in reversed(touched):
            destination = mat.guard_destination(mat.TARGET / item['destination'])
            prior = backups[item['destination']]
            try:
                if destination.exists():
                    need(mat.sha(destination) in {mat.sha(item['source']), prior['prior_sha256'] if prior else ''},
                         'Concurrent destination change prevents automatic rollback')
                if prior:
                    check_pin(prior)
                    source = Path(prior['path'])
                    mat.make_private(source, destination, regular(source))
                elif destination.exists():
                    need(destination.stat().st_nlink == 1, 'Rollback target became shared')
                    destination.unlink()
            except BaseException as rollback_exc:
                rollback_errors.append({'destination': str(destination), 'error': repr(rollback_exc)})
        if not rollback_errors:
            c.execute('delete from files where unit_id=?', (unit,))
            c.execute('delete from units where id=?', (unit,))
            for row in old_rows:
                columns = ','.join(row)
                c.execute(f'insert into files({columns}) values({",".join("?" for _ in row)})', tuple(row.values()))
        failure = {'utc': mat.utc(), 'status': 'INSTALL_FAILED_ROLLED_BACK' if not rollback_errors else 'INSTALL_FAILED_ROLLBACK_INCOMPLETE',
                   'error': repr(exc), 'rollback_errors': rollback_errors, 'unit': unit, 'accepted': False}
        c.execute('insert into events values(?,?,?)', (mat.utc(), 'verified_patch_install_failed', json.dumps(failure)))
        c.commit()
        save_new(job / 'install_failure.json', failure)
        raise
    finally:
        c.close()


def locked_operation(args, action, recovery=False):
    path = HERE / 'install.lock'
    existed = path.exists()
    acquired = False
    lock = path.open('a+b')
    try:
        if lock.tell() == 0:
            lock.write(b'\n')
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        acquired = True
        lock.seek(0)
        content = lock.read().decode('utf-8').strip()
        prior = json.loads(content) if content else None
        if prior:
            need(isinstance(prior.get('pid'), int) and not pid_running(prior['pid']),
                 'A live installer holds the operation lock')
        need(recovery or not existed or (prior or {}).get('operation_finished') is True,
             'Unfinished lock requires explicit recovery of its prepared attempt')
        if recovery and prior:
            need(Path(prior['prepared']).resolve() == research_path(args.prepared),
                 'Lock belongs to a different prepared attempt')
        lock.seek(0)
        lock.truncate()
        lock.write((json.dumps({'utc': mat.utc(), 'pid': os.getpid(), 'prepared': args.prepared,
                                'recovery': recovery}) + '\n').encode('utf-8'))
        lock.flush()
        action(args)
    finally:
        if acquired:
            lock.seek(0)
            lock.truncate()
            lock.write((json.dumps({'utc': mat.utc(), 'pid': os.getpid(), 'prepared': args.prepared,
                                    'recovery': recovery, 'operation_finished': True}) + '\n').encode('utf-8'))
            lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        lock.close()


def install(args):
    locked_operation(args, install_unlocked)


def pid_running(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        if error == 5:
            return True
        if error == 87:
            return False
        raise ctypes.WinError(error)
    try:
        code = wintypes.DWORD()
        need(kernel.GetExitCodeProcess(handle, ctypes.byref(code)), 'Cannot inspect installer process')
        return code.value == 259
    finally:
        kernel.CloseHandle(handle)


def check_recovery_journal(c, unit, mappings, old_rows):
    expected = {r['id']: r for r in old_rows}
    keys = [mat.key(m['destination']) for m in mappings]
    placeholders = ','.join('?' for _ in keys)
    actual = [dict(r) for r in c.execute(
        f'select * from files where dest_key in ({placeholders}) or unit_id=?', (*keys, unit))]
    for row in actual:
        if row['unit_id'] == unit:
            need(mat.key(row['destination']) in keys, 'Interrupted unit has an unexpected destination')
        else:
            need(row['id'] in expected and dict(row) == expected[row['id']],
                 'An unrelated journal row occupies a recovery destination')
    return actual


def recover_unlocked(args):
    path = research_path(args.prepared)
    plan = load(path)
    check_plan(plan, verify_current=False)
    job = path.parent
    need(not any((job / name).exists() for name in (
        'installed.json', 'accepted.json', 'install_failure.json', 'recovered.json', 'recovered_attempt.json')),
         'Attempt already has a terminal receipt; do not recover it again')
    started = load(job / 'install_started.json')
    need(started.get('schema') == 'skyrim.verified_patch_install.started.v1',
         'Legacy interrupted attempts lack complete original journal rows; inspect them manually')
    need(started['plan']['path'] == str(path) and started['plan']['sha256'] == mat.sha(path),
         'Interrupted attempt belongs to a different preparation')
    unit = started['unit']
    need(re.fullmatch(r'verified_patch_[0-9a-f]{32}', unit), 'Unexpected interrupted unit')
    need(isinstance(started.get('install_pid'), int) and not pid_running(started['install_pid']),
         'Installer is still running; recovery cannot proceed')
    mappings = plan['mappings']
    allowed = {f'mods/{LAYER}/{plan["candidate_name"]}'} | {
        f'profiles/{p}/{n}' for p in PROFILES for n in CONTROLS[:3]}
    need({m['destination'] for m in mappings} == allowed and len(mappings) == len(allowed),
         'Unexpected or duplicate recovery destination')
    backups = started['backups']
    need(set(backups) == allowed, 'Incomplete interrupted backup set')
    old_rows = started['original_file_rows']
    old_by_key = {mat.key(r['destination']): r for r in old_rows}
    need(len(old_by_key) == len(old_rows) and
         set(old_by_key) == {mat.key(k) for k, v in backups.items() if v},
         'Duplicate or incomplete original journal destination')
    for item in mappings:
        destination = item['destination']
        prior = backups[destination]
        old = old_by_key.get(mat.key(destination))
        if prior:
            check_pin(prior)
            need(old is not None and old['status'] == 'materialized' and old['storage'] == 'private' and
                 old['sha256'] == prior['prior_sha256'] and old['destination'] == destination and
                 old['unit_id'] != unit,
                 'Original journal row does not match its backup')
            for profile in plan['profiles']:
                control = profile['control_pins'].get(Path(destination).name)
                if control and f'profiles/{profile["profile"]}/' + Path(destination).name == destination:
                    need(control['sha256'] == prior['prior_sha256'], 'Control backup does not match the frozen plan')
        else:
            need(old is None and destination == f'mods/{LAYER}/{plan["candidate_name"]}',
                 'A missing original is only valid for the new candidate')
        target = mat.guard_destination(mat.TARGET / destination)
        actual = mat.sha(target) if target.exists() else None
        expected = {mat.sha(item['source']), prior['prior_sha256'] if prior else None}
        need(actual in expected, 'External file change prevents recovery: ' + destination)
        if actual is not None:
            need(regular(target).st_nlink == 1, 'Recovery destination became shared')
    c = mat.connect()
    try:
        check_recovery_journal(c, unit, mappings, old_rows)
        for event in c.execute("select detail from events where event='verified_patch_prior_rows'"):
            detail = json.loads(event['detail'])
            if detail.get('unit') == unit:
                need(detail['rows'] == old_rows and detail['backups'] == backups,
                     'Journal event disagrees with interrupted-attempt snapshot')
        for item in reversed(mappings):
            target = mat.guard_destination(mat.TARGET / item['destination'])
            prior = backups[item['destination']]
            if prior:
                source = Path(prior['path'])
                mat.make_private(source, target, regular(source))
            elif target.exists():
                target.unlink()
        for item in mappings:
            target = mat.guard_destination(mat.TARGET / item['destination'])
            prior = backups[item['destination']]
            need((mat.sha(target) == prior['prior_sha256']) if prior else not target.exists(),
                 'Restored file failed verification: ' + item['destination'])
        c.execute('begin immediate')
        before = check_recovery_journal(c, unit, mappings, old_rows)
        c.execute('delete from files where unit_id=?', (unit,))
        c.execute('delete from units where id=?', (unit,))
        for row in old_rows:
            columns = ','.join(row)
            c.execute(f'insert into files({columns}) values({",".join("?" for _ in row)})', tuple(row.values()))
        receipt = {'utc': mat.utc(), 'status': 'INTERRUPTED_INSTALL_RECOVERED_NOT_ACCEPTED', 'accepted': False,
                   'unit': unit, 'prepared': pin(path), 'interrupted_attempt': pin(job / 'install_started.json'),
                   'restored_files': [pin(mat.TARGET / m['destination']) for m in mappings if backups[m['destination']]],
                   'removed_new_files': [m['destination'] for m in mappings if not backups[m['destination']]],
                   'restored_journal_rows': old_rows, 'rows_before_recovery': before,
                   'required_next_step': 'Re-run preparation and installation from unchanged inputs; do not reuse this interrupted attempt.'}
        c.execute('insert into events values(?,?,?)', (mat.utc(), 'verified_patch_interrupted_install_recovered', json.dumps(receipt)))
        c.commit()
        after = check_recovery_journal(c, unit, mappings, old_rows)
        need(len(after) == len(old_rows) and not c.execute('select 1 from units where id=?', (unit,)).fetchone(),
             'Recovered journal verification failed')
        save_new(job / 'recovered.json', receipt)
        (job / 'install_started.json').rename(job / 'recovered_attempt.json')
        print(json.dumps(receipt, indent=2))
    finally:
        c.close()


def recover(args):
    locked_operation(args, recover_unlocked, recovery=True)


def accept(args):
    path = research_path(args.prepared)
    plan, receipt = load(path), load(path.parent / 'installed.json')
    need(receipt.get('status') == 'INSTALLED_PENDING_FRESH_TYPED_RELOAD' and receipt.get('accepted') is False,
         'No pending verified installation')
    need(receipt['prepared']['sha256'] == mat.sha(path), 'Installed preparation changed')
    installed = mat.TARGET / 'mods' / LAYER / plan['candidate_name']
    need(mat.sha(installed) == plan['candidate_sha256'], 'Installed candidate changed')
    prepared, result = producer_gate(args.reload_task)
    need(prepared.get('candidate') is None and 'RELOAD_TYPED_PASS' in prepared['pass_marker'],
         'Acceptance requires a fresh read-only typed reload job, not a builder')
    need(prepared.get('patch_name') == plan['candidate_name'], 'Reload verifier targets another patch')
    need(re.search(r'\bVERIFY_ONLY\s*=\s*True\s*;', Path(prepared['script']).read_text('utf-8'), re.I),
         'Reload script does not explicitly select read-only verification')
    need(datetime.fromisoformat(prepared['utc']) > datetime.fromisoformat(receipt['utc']),
         'Reload job predates installation')
    need(Path(prepared['profile']).resolve() == mat.TARGET / 'profiles/Unified Build', 'Wrong reload profile')
    task = Path(args.reload_task).resolve()
    inventory = load(task / 'input_inventory.json')['plugins']
    rows = [r for r in inventory if mat.key(r['name']) == mat.key(plan['candidate_name'])]
    need(len(rows) == 1 and rows[0]['sha256'] == plan['candidate_sha256'] and Path(rows[0]['path']).resolve() == installed,
         'Reload did not consume the installed exact VFS winner')
    for row in inventory:
        need(mat.sha(row['path']) == row['sha256'], 'Input changed after typed reload: ' + row['name'])
    for filename, digest in prepared['profile_controls'].items():
        need(mat.sha(Path(prepared['profile']) / filename) == digest, 'Controls changed after reload')
    current = runtime.PROFILE
    try:
        for name in PROFILES:
            runtime.PROFILE = mat.TARGET / 'profiles' / name
            controls = {n: (runtime.PROFILE / n).read_bytes() for n in CONTROLS[:3]}
            Lines(controls['modlist.txt']).names(modlist=True)
            Lines(controls['plugins.txt']).names()
            order = [k for k, _, _ in Lines(controls['loadorder.txt']).names()]
            inv = runtime.inventory()
            need(not inv['missing_plugins'] and not inv['missing_masters'] and inv['within_slot_limits'], 'Final profile closure failed')
            candidate_rows = [r for r in inv['plugins'] if mat.key(r['name']) == mat.key(plan['candidate_name'])]
            need(len(candidate_rows) == 1 and candidate_rows[0]['sha256'] == plan['candidate_sha256'] and candidate_rows[0]['provider'] == LAYER,
                 'Candidate not activated as exact winner in both profiles')
            topo([r['name'] for r in inv['plugins']], {mat.key(r['name']): r for r in inv['plugins']})
            ranks = [COMPATIBILITY_PRIORITY[mat.key(r['name'])] for r in inv['plugins']
                     if mat.key(r['name']) in COMPATIBILITY_PRIORITY]
            need(ranks == sorted(ranks), 'Final compatibility priority order changed')
            active = {mat.key(r['name']) for r in inv['plugins']}
            need([n for n in order if n in active] == [mat.key(r['name']) for r in inv['plugins']],
                 'Final loadorder and activation order disagree')
    finally:
        runtime.PROFILE = current
    accepted = {'utc': mat.utc(), 'status': 'ACCEPTED_STATIC_TYPED_RELOAD_FINAL_VFS_PENDING',
                'accepted': True, 'candidate': pin(installed), 'installation': pin(path.parent / 'installed.json'),
                'reload_task': str(task), 'reload_result': pin(task / 'result.json'),
                'limits': 'Static typed reload acceptance only. Final full VFS/resource/Synthesis/LOD audits remain separate; no game launch.'}
    save_new(path.parent / 'accepted.json', accepted)
    c = mat.connect()
    c.execute('insert into events values(?,?,?)', (mat.utc(), 'verified_patch_static_typed_reload_accepted', json.dumps(accepted)))
    c.commit()
    c.close()
    print(json.dumps(accepted, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--candidate', required=True)
    p.add_argument('--producer', required=True)
    p.add_argument('--binary-report', required=True)
    p.add_argument('--output', required=True, help='Fresh directory under integration/research')
    p.add_argument('--replace-sha256', help='Exact previous own-layer plugin SHA, only for an intentional replacement')
    p.set_defaults(function=prepare)
    p = sub.add_parser('install')
    p.add_argument('--prepared', required=True)
    p.set_defaults(function=install)
    p = sub.add_parser('recover', help='Restore a process-interrupted rev4 installation after verifying that its PID has exited')
    p.add_argument('--prepared', required=True)
    p.set_defaults(function=recover)
    p = sub.add_parser('accept')
    p.add_argument('--prepared', required=True)
    p.add_argument('--reload-task', required=True)
    p.set_defaults(function=accept)
    args = ap.parse_args()
    if hasattr(args, 'replace_sha256') and args.replace_sha256:
        need(re.fullmatch('[0-9a-f]{64}', args.replace_sha256), 'Invalid replacement SHA')
    args.function(args)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
