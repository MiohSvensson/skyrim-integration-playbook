"""Install only the audited Hoth cloak mesh and its exact texture dependencies."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
import install_igraine_material as installer

MANIFEST = HERE / 'hoth_cloak_manifest.json'
LAYER = 'ZZ83 Verified generated item and quest assets'


def install_hoth(job=None, copier=None):
    report = json.loads(MANIFEST.read_text('utf-8'))
    expected = {Path(row['destination']).relative_to(mat.BASE / 'UnifiedSkyrim/mods' / LAYER).as_posix()
                for row in report['private_resource_mapping']}
    return installer.install(MANIFEST, job or HERE / 'hoth_cloak_r1', copier,
                             unit='hoth_cloak_v1', manifest_sha256=mat.sha(MANIFEST), expected=expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job')
    args = parser.parse_args()
    install_hoth(args.job)
