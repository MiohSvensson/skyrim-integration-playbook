"""Compare ARMA records by source identity, not renumbered load-order FormIDs."""
from pathlib import Path
import hashlib

MODEL_FIELDS = ('MOD2', 'MOD3', 'MOD4', 'MOD5')


def source_key(masters, record):
    index = record['fid'] >> 24
    if index >= len(masters):
        raise ValueError('ARMA record is not an override of a known source master')
    return f'{masters[index].casefold()}:{record["fid"] & 0xffffff:06X}'


def by_source(masters, records):
    result = {}
    for record in records:
        if record['sig'] != 'ARMA':
            continue
        key = source_key(masters, record)
        if key in result:
            raise ValueError('Duplicate ARMA source identity: ' + key)
        result[key] = record
    return result


def text(value):
    return value.rstrip(b'\0').decode('utf-8') if value else ''


def delta(before_masters, before_records, after_masters, after_records):
    before = by_source(before_masters, before_records)
    after = by_source(after_masters, after_records)
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    changes = []
    for key in sorted(after.keys() & before.keys()):
        old = dict(before[key]['fields'])
        new = dict(after[key]['fields'])
        for tag in MODEL_FIELDS:
            if old.get(tag) == new.get(tag):
                continue
            changes.append({'source_key': key, 'record': f'{after[key]["fid"]:08X}',
                            'editor_id': after[key].get('edid'), 'field': tag,
                            'old_path': text(old.get(tag)), 'new_path': text(new.get(tag))})
    for key in added:
        record = after[key]
        for tag, value in record['fields']:
            if tag in MODEL_FIELDS and value:
                changes.append({'source_key': key, 'record': f'{record["fid"]:08X}',
                                'editor_id': record.get('edid'), 'field': tag,
                                'old_path': None, 'new_path': text(value), 'new_override_record': True})
    affected = sorted(set(added) | {row['source_key'] for row in changes})
    return {'added_source_records': added, 'removed_source_records': removed,
            'model_changes': changes, 'affected_source_keys': affected}


def read_verified_stage(row, reader):
    path = Path(row['output']['path']).resolve(strict=True)
    if hashlib.sha256(path.read_bytes()).hexdigest() != row['output']['sha256']:
        raise ValueError('Stage output differs from the replay: ' + str(path))
    masters, records = reader(path)
    return path, masters, records
