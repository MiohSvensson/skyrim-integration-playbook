"""Install exactly the two audited Igraine resources with private-copy rollback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat

MANIFEST = HERE / 'igraine_material_manifest.json'
MANIFEST_SHA256 = '1b82bac88148ad43a887b8e16b4cf2fc80a8604216e75cc445fced2b45d22f9d'
UNIT = 'igraine_material_v1'
LAYER = 'ZZ83 Verified generated item and quest assets'
EXPECTED = {
    'textures/SC/4_Ports/21_Order1886/Igraine/Knight/Hands_F_m.dds',
    'textures/SC/4_Ports/21_Order1886/Igraine/Knight/quicksilver_e.dds',
}


def pin(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': mat.sha(path), 'bytes': path.stat().st_size}


def control_pins():
    return {f'profiles/{profile}/{name}': mat.sha(mat.TARGET / 'profiles' / profile / name)
            for profile in ['Unified Skyrim', 'Unified Build']
            for name in ['modlist.txt', 'plugins.txt', 'loadorder.txt']}


def install(manifest_path=MANIFEST, job=None, copier=None):
    copier = copier or mat.make_private
    manifest_path = Path(manifest_path).resolve(strict=True)
    if mat.sha(manifest_path) != MANIFEST_SHA256:
        raise ValueError('Reviewed Igraine manifest changed')
    report = json.loads(manifest_path.read_text('utf-8'))
    if report.get('schema') != 'skyrim.igraine_material_audit.v1' or report.get('status') != 'READY_FOR_PRIVATE_RESOURCE_INSTALL':
        raise ValueError('Typed Igraine source proof required')
    layer = mat.BASE / 'UnifiedSkyrim/mods' / LAYER
    mappings = []
    for row in report['private_resource_mapping']:
        source = Path(row['source']['path']).resolve(strict=True)
        destination = Path(row['destination']).resolve()
        if not source.is_file() or not destination.is_relative_to(layer):
            raise ValueError('Unexpected Igraine source or destination')
        relative = destination.relative_to(layer).as_posix()
        if relative not in EXPECTED or mat.sha(source) != row['source']['sha256'] or source.stat().st_size != row['source']['bytes']:
            raise ValueError('Igraine source or target differs from the typed review')
        mappings.append({'source': source, 'relative': relative,
                         'destination': f'mods/{LAYER}/{relative}', 'bytes': source.stat().st_size,
                         'sha256': row['source']['sha256']})
    if {row['relative'] for row in mappings} != EXPECTED or len(mappings) != 2:
        raise ValueError('Exactly two reviewed Igraine resources are required')
    job = Path(job).resolve() if job else HERE / 'igraine_material_r1'
    mat.within(job, HERE)
    if job.exists():
        raise FileExistsError('Use a fresh Igraine installation receipt directory')
    mat.assert_owned_tree()
    for row in mappings:
        target = mat.guard_destination(mat.TARGET / row['destination'])
        if target.exists():
            raise FileExistsError('Refusing to replace an existing Igraine resource: ' + str(target))
    if shutil.disk_usage(mat.BASE).free < mat.RESERVE + sum(row['bytes'] for row in mappings) + 65536:
        raise RuntimeError('Disk reserve would be crossed')
    controls = control_pins()
    job.mkdir(parents=True)
    (job / 'install_started.json').write_text(json.dumps({'manifest': pin(manifest_path), 'controls': controls,
                                                         'pid': os.getpid(), 'files': mappings}, ensure_ascii=False, indent=2, default=str) + '\n', encoding='utf-8')
    c = mat.connect()
    installed = []
    try:
        mat.add_file_mapping(c, UNIT, [{'source': str(row['source']), 'destination': row['destination'],
                                       'storage': 'private', 'bytes': row['bytes']} for row in mappings],
                             'Two typed Igraine hand-material resources; private copies only')
        for row in mappings:
            target = mat.guard_destination(mat.TARGET / row['destination'])
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = copier(row['source'], target, row['source'].stat())
            if digest != row['sha256'] or target.stat().st_nlink != 1:
                raise RuntimeError('Private resource copy differs from its reviewed source')
            c.execute("update files set status='materialized',sha256=? where unit_id=? and dest_key=?",
                      (digest, UNIT, mat.key(row['destination'])))
            c.commit()
            installed.append(pin(target))
        if control_pins() != controls:
            raise RuntimeError('Profile controls changed during resource installation')
        if c.execute('pragma integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Journal integrity check failed')
        receipt = {'schema': 'skyrim.igraine_material_install.v1', 'utc': mat.utc(),
                   'status': 'INSTALLED_PENDING_ACTUAL_VFS', 'accepted': False, 'unit': UNIT,
                   'manifest': pin(manifest_path), 'files': installed, 'controls': controls,
                   'original_packs_modified': False, 'game_launched': False}
        (job / 'installed.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        c.execute('insert into events values(?,?,?)', (mat.utc(), 'igraine_material_installed_pending_vfs', json.dumps(receipt)))
        c.commit()
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        return receipt
    except BaseException as exc:
        for row in mappings:
            target = mat.guard_destination(mat.TARGET / row['destination'])
            if target.exists():
                if mat.sha(target) != row['sha256']:
                    raise RuntimeError('Rollback refuses an unexpected destination: ' + str(target))
                target.unlink()
        c.execute('delete from files where unit_id=?', (UNIT,))
        c.execute('delete from units where id=?', (UNIT,))
        c.commit()
        (job / 'failed.json').write_text(json.dumps({'status': 'INSTALL_FAILED_ROLLED_BACK', 'error': repr(exc)}, indent=2) + '\n', encoding='utf-8')
        raise
    finally:
        c.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', default=MANIFEST)
    parser.add_argument('--job')
    args = parser.parse_args()
    install(args.manifest, args.job)
