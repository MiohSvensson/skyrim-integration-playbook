"""Run the bounded D3D11 hardware/cache probe, never PGPatcher or Skyrim."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / 'vfs_validation'))
import vfs_common as vfs


def main():
    assert vfs.injected(), 'The probe must run inside the actual MO2 VFS'
    executable = HERE / 'D3D11Probe.exe'
    source = HERE / 'D3D11Probe.cs'
    assert executable.is_file() and source.is_file()
    environment = os.environ.copy()
    for name in ['APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP']:
        assert Path(environment[name]).is_relative_to(vfs.BASE), name + ' escaped Database'
    process = subprocess.Popen([str(executable)], cwd=HERE, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    output, _ = process.communicate(timeout=90)
    text = output.decode('utf-8', errors='replace')
    result = {'schema': 'skyrim.pg_cache_probe.native.v1', 'pid': process.pid,
              'return_code': process.returncode, 'stdout': text,
              'executable_sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'usvfs_in_python_child': True, 'game_launched': False, 'pg_launched': False}
    (HERE / 'native_result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if process.returncode != 0 or 'D3D11_HARDWARE_COMPUTE_SHADER_PASS' not in text or 'D3D11_PROBE_USVFS_PRESENT' not in text:
        raise RuntimeError('D3D11 hardware/VFS probe failed')


if __name__ == '__main__':
    main()
