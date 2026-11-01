"""Recover an interrupted new-file private-resource installation after its PID exits."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
import install_igraine_material as installer
from research.verified_patch_install.install_verified_patch import pid_running


def recover(job):
    job = Path(job).resolve(strict=True)
    mat.within(job, HERE)
    if any((job / name).exists() for name in ('installed.json', 'accepted.json', 'failed.json', 'recovered.json', 'recovered_attempt.json')):
        raise ValueError('Installation already has a terminal receipt; do not recover it again')
    started_path = job / 'install_started.json'
    started = json.loads(started_path.read_text('utf-8'))
    if started.get('schema') != 'skyrim.private_resource_install.started.v1':
        raise ValueError('Unsupported private-resource recovery receipt')
    if not isinstance(started.get('pid'), int) or isinstance(started['pid'], bool) or pid_running(started['pid']):
        raise ValueError('Installer is still active; recovery cannot proceed')
    unit = started.get('unit')
    if unit not in installer.RESOURCE_SCHEMAS:
        raise ValueError('Unexpected private-resource unit')
    manifest_path = Path(started['manifest']['path']).resolve(strict=True)
    if mat.sha(manifest_path) != started['manifest']['sha256']:
        raise ValueError('Resource manifest changed during interruption')
    report = json.loads(manifest_path.read_text('utf-8'))
    if report.get('schema') != installer.RESOURCE_SCHEMAS[unit] or report.get('status') != 'READY_FOR_PRIVATE_RESOURCE_INSTALL':
        raise ValueError('Recovery source proof does not match the unit')
    reviewed = {}
    layer = mat.BASE / 'UnifiedSkyrim/mods' / installer.LAYER
    for row in report['private_resource_mapping']:
        source = Path(row['source']['path']).resolve(strict=True)
        destination = Path(row['destination']).resolve()
        relative = destination.relative_to(layer).as_posix()
        reviewed[f'mods/{installer.LAYER}/{relative}'] = (source, row['source']['sha256'], row['source']['bytes'])
    if set(reviewed) != {row['destination'] for row in started['files']} or len(started['files']) != len(reviewed) or not reviewed:
        raise ValueError('Interrupted file set differs from the reviewed manifest')
    mat.assert_owned_tree()
    if installer.control_pins() != started['controls']:
        raise ValueError('Profile controls changed during interruption')
    for row in started['files']:
        source, digest, size = reviewed[row['destination']]
        if row['sha256'] != digest or row['bytes'] != size or mat.sha(source) != digest or source.stat().st_size != size:
            raise ValueError('Interrupted source differs from its review')
        target = mat.guard_destination(mat.TARGET / row['destination'])
        if target.exists() and (target.stat().st_nlink != 1 or mat.sha(target) != digest):
            raise ValueError('Unexpected destination prevents recovery: ' + str(target))
    connection = mat.connect()
    try:
        expected = {mat.key(destination) for destination in reviewed}
        rows = [dict(row) for row in connection.execute('select * from files where unit_id=?', (unit,))]
        if any(mat.key(row['destination']) not in expected for row in rows):
            raise ValueError('Interrupted unit contains an unexpected journal destination')
        for destination in reviewed:
            target = mat.guard_destination(mat.TARGET / destination)
            if target.exists():
                target.unlink()
        connection.execute('begin immediate')
        rows = [dict(row) for row in connection.execute('select * from files where unit_id=?', (unit,))]
        if any(mat.key(row['destination']) not in expected for row in rows):
            raise ValueError('Journal changed during recovery')
        connection.execute('delete from files where unit_id=?', (unit,))
        connection.execute('delete from units where id=?', (unit,))
        receipt = {'schema': 'skyrim.private_resource_install.recovery.v1', 'status': 'INTERRUPTED_RESOURCE_INSTALL_RECOVERED_NOT_ACCEPTED',
                   'accepted': False, 'unit': unit, 'manifest': installer.pin(manifest_path),
                   'removed_files': list(reviewed), 'controls_unchanged': True, 'journal_rows_removed': len(rows),
                   'original_packs_modified': False, 'game_launched': False}
        connection.execute('insert into events values(?,?,?)', (mat.utc(), 'private_resource_interrupted_install_recovered', json.dumps(receipt)))
        connection.commit()
        if connection.execute('pragma integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Journal integrity check failed')
        (job / 'recovered.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        started_path.rename(job / 'recovered_attempt.json')
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return receipt
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    recover(args.job)
