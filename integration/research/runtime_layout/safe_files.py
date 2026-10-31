"""Guarded file-level staging. Hard links remain shared until explicitly detached.

This helper does not sandbox third-party programs. Callers must redirect their
outputs and detach every shared file they might edit before launching them.
"""
import hashlib
import os
import shutil
import uuid
from pathlib import Path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def guarded_destination(path, allowed_root):
    root = Path(allowed_root).resolve(strict=True)
    path = Path(path).absolute()
    resolved = path.resolve(strict=False)
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError(f'Destination escapes task root: {path}')
    # Reject even in-root reparse traversal: a subsequent retarget could escape.
    current = path
    while current != root:
        if current.exists() and getattr(current.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError(f'Reparse destination is not permitted: {current}')
        if current.parent == current:
            raise ValueError('Destination has no allowed-root ancestor')
        current = current.parent
    return path


def stage_shared(source, destination, allowed_root):
    destination = guarded_destination(destination, allowed_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if os.path.samefile(source, destination):
            return 'existing_shared'
        raise FileExistsError(f'Refusing to replace existing destination: {destination}')
    os.link(source, destination)
    if not os.path.samefile(source, destination):
        raise RuntimeError('Hard-link file identity did not match')
    return 'created_shared'


def stage_private(source, destination, allowed_root):
    """Atomically replace the destination directory entry with an independent copy."""
    destination = guarded_destination(destination, allowed_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = guarded_destination(destination.with_name(destination.name + '.private-' + uuid.uuid4().hex), allowed_root)
    before = os.stat(source)
    expected_hash = digest(source)
    try:
        # Copy to a new path, never over an existing hard-link directory entry.
        with Path(source).open('rb') as src, temp.open('xb') as dst:
            shutil.copyfileobj(src, dst, length=1024*1024)
            dst.flush()
            os.fsync(dst.fileno())
        if digest(temp) != expected_hash:
            raise RuntimeError('Private copy hash mismatch')
        after = os.stat(source)
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
            raise RuntimeError('Source changed during private staging')
        os.replace(temp, destination)
        if os.stat(destination).st_nlink != 1:
            raise RuntimeError('Private destination still has additional hard links')
        return expected_hash
    finally:
        if temp.exists():
            temp.unlink()


def detach_for_write(path, allowed_root):
    path = guarded_destination(path, allowed_root)
    if os.stat(path).st_nlink > 1:
        return {'detached': True, 'sha256': stage_private(path, path, allowed_root)}
    return {'detached': False, 'sha256': digest(path)}


def assert_private(path, allowed_root):
    path = guarded_destination(path, allowed_root)
    if os.stat(path).st_nlink != 1:
        raise RuntimeError(f'Refusing known shared writable file: {path}')
    return path
