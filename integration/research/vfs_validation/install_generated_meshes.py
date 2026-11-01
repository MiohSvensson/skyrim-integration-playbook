"""Install the exact 23-file Synthesis-related resource supplement."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import materialize as mat
import install_igraine_material as installer

MANIFEST = HERE / 'generated_mesh_manifest_v3.json'
MANIFEST_SHA256 = '8a69dd6717c554317080c5e692d92e51f2fe3d8805e05c54aeae6e5a0c0bc9d4'
UNIT = 'generated_mesh_resources_v1'
CANDIDATE_SHA256 = '5f8f491fc086631868ecd78fb4f19c09b76e9a8a4e3b0cb20d5156611cfc64a8'


def install_generated(job=None, copier=None):
    if mat.sha(MANIFEST) != MANIFEST_SHA256:
        raise ValueError('Reviewed generated mesh manifest changed')
    report = json.loads(MANIFEST.read_text('utf-8'))
    assert report['candidate']['sha256'] == CANDIDATE_SHA256
    assert report['affected_record_count'] == 275
    assert report['missing_model_count'] == 8 and report['resource_count'] == 23
    assert report['arma_delta']['sha256'] == '71cb18f6c671070a53e3544a14e493f16c02a97f25b8c730e06dd06aa1123527'
    assert report['input_models']['sha256'] == '3a846400b3ae045e0bedd767e56a56b1877931d93d07876eb75f435daae51cc7'
    assert len(report['inherited_source_gaps']) == 1
    gap = report['inherited_source_gaps'][0]
    assert gap['path'] == 'meshes/_pgpatcher_dups/1/clothing/hoodu/setarmors_1.nif'
    assert gap['source_key'] == 'hoodu_follower.esp:00084F' and gap['field'] == 'MOD3'
    assert gap['disposition'] == 'INHERITED_UNCHANGED_SOURCE_GAP_RETAINED_NO_ALIAS'
    expected = {Path(row['destination']).relative_to(mat.BASE / 'UnifiedSkyrim/mods' / installer.LAYER).as_posix()
                for row in report['private_resource_mapping']}
    return installer.install(MANIFEST, job or HERE / 'generated_mesh_resources_r1', copier,
                             unit=UNIT, manifest_sha256=MANIFEST_SHA256, expected=expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job')
    args = parser.parse_args()
    install_generated(args.job)
