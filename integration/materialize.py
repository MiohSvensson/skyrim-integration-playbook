"""Journaled staging into the one Database-owned integration tree.

Assets remain shared NTFS files. This is deliberately not a process sandbox.
Third-party writers must use private inputs or a fresh, explicit output folder.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TARGET = BASE / 'UnifiedSkyrim'
DB = BASE / 'integration/files.sqlite'
RESERVE = 32 * 1024**3
SHARED_EXTENSIONS = {
    '.dds', '.nif', '.bsa', '.bto', '.btr', '.tri', '.osd', '.wav', '.fuz',
    '.xwm', '.hkx', '.bik', '.cgid', '.lip', '.pdb', '.psd', '.mp4', '.ogg',
    '.tga', '.png', '.jpg', '.jpeg', '.tif', '.tiff', '.7z', '.zip', '.rar',
}
WRITABLE_TREES = {'nemesis_engine', 'pandora_engine', 'cache', 'logs', 'temp', 'tmp'}


def utc():
    return datetime.now(timezone.utc).isoformat()


def key(value):
    return unicodedata.normalize('NFC', str(value).replace('\\', '/')).casefold()


def lp(path):
    value = os.path.abspath(path)
    return value if value.startswith('\\\\?\\') else '\\\\?\\' + value


def sha(path):
    with open(lp(path), 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def within(path, root):
    path, root = Path(path).resolve(), Path(root).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f'Path is not a child of task root: {path}')
    return path


def storage(relative, destination):
    parts = key(relative).split('/')
    # Game root binaries/settings and every third-party tool writable tree stay private.
    if str(destination).replace('\\', '/') == 'Game' and len(parts) == 1:
        return 'private'
    if any(p in WRITABLE_TREES for p in parts[:-1]) or 'root' in parts[:-1]:
        return 'private'
    suffix = Path(parts[-1].removesuffix('.mohidden')).suffix
    return 'shared' if suffix in SHARED_EXTENSIONS else 'private'


def connect():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('pragma journal_mode=wal')
    c.executescript('''
      create table if not exists units(
        id text primary key,source text not null,destination text not null,
        reason text not null,planned_utc text not null);
      create table if not exists files(
        id integer primary key,unit_id text not null,relative_path text not null,
        destination text not null,dest_key text not null unique,
        size_bytes integer not null,mtime_ns integer not null,storage text not null,
        status text not null default 'planned',sha256 text,error text);
      create index if not exists files_status on files(status,id);
      create index if not exists files_unit on files(unit_id);
      create table if not exists events(utc text,event text,detail text);
    ''')
    return c


def assert_owned_tree():
    within(TARGET, BASE)
    for path in [BASE, TARGET]:
        if path.exists() and getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Reparse task root: {path}')
    if TARGET.exists():
        marker = TARGET / '.integration-managed.json'
        guard_destination(marker)
        if not marker.exists():
            raise ValueError('Existing target lacks the integration ownership marker')
        for folder, dirs, files in os.walk(lp(TARGET), followlinks=False):
            for name in dirs + files:
                path = Path(folder) / name
                if getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
                    raise ValueError(f'Reparse directory in destination: {path}')


def guard_destination(path):
    path = Path(path).absolute()
    within(path, TARGET)
    current = path
    while current != TARGET:
        try:
            info = current.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Reparse destination item: {current}')
        if current.parent == current:
            raise ValueError('Destination has no task-root ancestor')
        current = current.parent
    if TARGET.exists() and getattr(TARGET.lstat(), 'st_file_attributes', 0) & 0x400:
        raise ValueError('Reparse task root')
    return path


def add_unit(c, unit_id, source, destination, reason, replace_planned=False):
    source = Path(source).resolve(strict=True)
    if not source.is_relative_to(BASE.parent):
        raise ValueError(f'Source outside explicitly authorized collection: {source}')
    destination = Path(destination)
    if destination.is_absolute() or '..' in destination.parts:
        raise ValueError(f'Invalid destination: {destination}')
    within(TARGET / destination, TARGET)
    prior = c.execute('select * from units where id=?', (unit_id,)).fetchone()
    if prior:
        raise ValueError(f'Unit already planned: {unit_id}')
    c.execute('insert into units values(?,?,?,?,?)', (unit_id, str(source), destination.as_posix(), reason, utc()))
    stack = [(str(source), '')]
    count = 0
    while stack:
        folder, relative_folder = stack.pop()
        with os.scandir(lp(folder)) as entries:
            for entry in entries:
                relative = (Path(relative_folder) / entry.name).as_posix()
                st = entry.stat(follow_symlinks=False)
                if getattr(st, 'st_file_attributes', 0) & 0x400:
                    raise ValueError(f'Source reparse item needs explicit resolution: {source / relative}')
                if entry.is_dir(follow_symlinks=False):
                    stack.append((str(source / relative), relative))
                    continue
                if not entry.is_file(follow_symlinks=False):
                    raise ValueError(f'Non-regular source file: {source / relative}')
                dest = (destination / relative).as_posix()
                existing = c.execute('select id,status from files where dest_key=?', (key(dest),)).fetchone()
                if existing:
                    if not replace_planned or existing['status'] != 'planned':
                        raise ValueError(f'Destination collision: {dest}')
                    c.execute('delete from files where id=?', (existing['id'],))
                c.execute('''insert into files(unit_id,relative_path,destination,dest_key,size_bytes,mtime_ns,storage)
                    values(?,?,?,?,?,?,?)''', (unit_id, relative, dest, key(dest), st.st_size, st.st_mtime_ns,
                                               storage(relative, destination)))
                count += 1
    c.execute('insert into events values(?,?,?)', (utc(), 'planned_unit', json.dumps({'id': unit_id, 'files': count})))
    c.commit()
    return count


def add_file_mapping(c, unit_id, mappings, reason, replace_planned=False):
    """Plan reviewed individual files (game/root payloads or bounded asset closures)."""
    source_root = BASE.parent.resolve()
    if c.execute('select 1 from units where id=?', (unit_id,)).fetchone():
        raise ValueError(f'Unit already planned: {unit_id}')
    c.execute('insert into units values(?,?,?,?,?)', (unit_id, str(source_root), '[per-file mapping]', reason, utc()))
    count = 0
    for item in mappings:
        source = Path(item['source']).resolve(strict=True)
        within(source, source_root)
        dest = Path(item['destination'])
        if dest.is_absolute() or '..' in dest.parts:
            raise ValueError(f'Invalid mapped destination: {dest}')
        within(TARGET / dest, TARGET)
        st = source.stat()
        if getattr(st, 'st_file_attributes', 0) & 0x400 or not source.is_file():
            raise ValueError(f'Non-regular mapped file: {source}')
        if item.get('bytes') is not None and st.st_size != item['bytes']:
            raise ValueError(f'Mapped source length differs from reviewed plan: {source}')
        existing = c.execute('select id,status from files where dest_key=?', (key(dest),)).fetchone()
        if existing:
            if not replace_planned or existing['status'] != 'planned':
                raise ValueError(f'Mapped destination collision: {dest}')
            c.execute('delete from files where id=?', (existing['id'],))
        c.execute('''insert into files(unit_id,relative_path,destination,dest_key,size_bytes,mtime_ns,storage)
            values(?,?,?,?,?,?,?)''', (unit_id, source.relative_to(source_root).as_posix(), dest.as_posix(),
            key(dest), st.st_size, st.st_mtime_ns, item.get('storage', 'private')))
        count += 1
    c.execute('insert into events values(?,?,?)', (utc(), 'planned_mapping', json.dumps({'id': unit_id, 'files': count})))
    c.commit()
    return count


def budget(c):
    counts = [dict(r) for r in c.execute('select storage,status,count(*) files,sum(size_bytes) bytes from files group by storage,status')]
    private_remaining = c.execute("select coalesce(sum(size_bytes),0) from files where storage='private' and status='planned'").fetchone()[0]
    pending = c.execute("select count(*) from files where status='planned'").fetchone()[0]
    free = shutil.disk_usage(BASE).free
    return {'utc': utc(), 'free_bytes': free, 'reserve_bytes': RESERVE,
            'pending_private_bytes': private_remaining, 'pending_files': pending,
            'metadata_allowance_bytes': pending * 4096,
            'fits_preflight': private_remaining + pending * 4096 + RESERVE <= free,
            'rows': counts}


def make_private(source, dest, expected_stat):
    temp = dest.with_name(dest.name + '.stage-' + uuid.uuid4().hex)
    guard_destination(temp)
    expected_hash = sha(source)
    try:
        with open(lp(source), 'rb') as original, open(lp(temp), 'xb') as output:
            shutil.copyfileobj(original, output, 1024 * 1024)
        if sha(temp) != expected_hash:
            raise RuntimeError(f'Private copy SHA mismatch: {dest}')
        current = os.stat(lp(source))
        if (current.st_size, current.st_mtime_ns) != (expected_stat.st_size, expected_stat.st_mtime_ns):
            raise RuntimeError(f'Source changed while copying: {source}')
        os.utime(lp(temp), ns=(expected_stat.st_atime_ns, expected_stat.st_mtime_ns))
        os.replace(lp(temp), lp(dest))
        if os.stat(lp(dest)).st_nlink != 1 or os.path.samefile(lp(source), lp(dest)):
            raise RuntimeError(f'Private copy is still shared: {dest}')
        return expected_hash
    finally:
        if os.path.exists(lp(temp)):
            os.unlink(lp(temp))


def build(c, limit=None):
    if limit is not None and limit <= 0:
        raise ValueError('File limit must be positive')
    assert_owned_tree()
    check = budget(c)
    if not check['fits_preflight']:
        raise RuntimeError('Insufficient disk space for private files, metadata allowance and reserve')
    TARGET.mkdir(exist_ok=True)
    marker = TARGET / '.integration-managed.json'
    if not marker.exists():
        marker.write_text(json.dumps({'created_utc': utc(), 'journal': str(DB), 'source_assets_are_shared': True}, indent=2), encoding='utf-8')
    start = time.monotonic()
    total = 0
    while True:
        batch = c.execute('''select f.*,u.source from files f join units u on u.id=f.unit_id
          where f.status='planned' order by f.id limit ?''', (min(500, limit - total) if limit else 500,)).fetchall()
        if not batch:
            break
        if shutil.disk_usage(BASE).free < RESERVE + len(batch)*4096 + sum(r['size_bytes'] for r in batch if r['storage'] == 'private'):
            raise RuntimeError('Disk reserve reached before next batch')
        for row in batch:
            source = Path(row['source']) / row['relative_path']
            dest = guard_destination(TARGET / row['destination'])
            st = os.stat(lp(source))
            if (st.st_size, st.st_mtime_ns) != (row['size_bytes'], row['mtime_ns']):
                raise RuntimeError(f'Source metadata drift: {source}')
            os.makedirs(lp(dest.parent), exist_ok=True)
            content_hash = None
            if row['storage'] == 'shared':
                if os.path.exists(lp(dest)):
                    if not os.path.samefile(lp(source), lp(dest)):
                        raise FileExistsError(f'Unexpected existing asset: {dest}')
                else:
                    os.link(lp(source), lp(dest))
                if not os.path.samefile(lp(source), lp(dest)):
                    raise RuntimeError(f'Hard-link identity mismatch: {dest}')
            else:
                if os.path.exists(lp(dest)):
                    if os.stat(lp(dest)).st_nlink != 1 or sha(dest) != sha(source):
                        raise FileExistsError(f'Unexpected existing writable file: {dest}')
                    content_hash = sha(dest)
                else:
                    content_hash = make_private(source, dest, st)
            c.execute("update files set status='materialized',sha256=? where id=?", (content_hash, row['id']))
            total += 1
        c.commit()
        print(json.dumps({'materialized_this_run': total, 'seconds': round(time.monotonic()-start, 1),
                          'free_gib': round(shutil.disk_usage(BASE).free/1024**3, 2)}, ensure_ascii=False), flush=True)
        if limit and total >= limit:
            break
    c.execute('insert into events values(?,?,?)', (utc(), 'materialized_run', json.dumps({'count': total})))
    c.commit()
    return budget(c)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['add', 'budget', 'build'])
    parser.add_argument('--id')
    parser.add_argument('--source')
    parser.add_argument('--destination')
    parser.add_argument('--reason', default='Selected source')
    parser.add_argument('--replace-planned', action='store_true')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    c = connect()
    if args.action == 'add':
        print('planned', add_unit(c, args.id, args.source, args.destination, args.reason, args.replace_planned))
        result = budget(c)
    elif args.action == 'build':
        result = build(c, args.limit)
    else:
        result = budget(c)
    c.close()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
