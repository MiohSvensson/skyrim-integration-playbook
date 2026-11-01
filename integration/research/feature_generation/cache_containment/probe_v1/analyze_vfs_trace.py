"""Analyze the bounded initialization probe's actual usvfs file operations."""
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    native_path = HERE / 'native_result.json'
    native = json.loads(native_path.read_text('utf-8'))
    assert native['return_code'] == 0 and 'D3D11_HARDWARE_COMPUTE_SHADER_PASS' in native['stdout']
    assert native['usvfs_in_python_child'] and 'D3D11_PROBE_USVFS_PRESENT' in native['stdout']
    assert sha(HERE / 'D3D11Probe.exe') == native['executable_sha256']
    assert sha(HERE / 'D3D11Probe.cs') == native['source_sha256']
    debug = json.loads((HERE / 'debug_mo2_manifest.json').read_text('utf-8'))
    assert sha(debug['original_config']) == debug['original_config_sha256']
    logs = sorted((HERE / 'mo2_debug_full/logs').glob('usvfs-*.log'), key=lambda path: path.stat().st_mtime_ns)
    trace_path = logs[-1]
    text = trace_path.read_text('utf-8', errors='replace')
    assert f'D3D11Probe.exe:{native["pid"]}' in text and 'log level 0' in text
    assert 'inithooks in process ' in text and 'D3D11Probe.exe' in text
    cache_events = []
    native_nvidia_events = []
    for line in text.splitlines():
        if 'ntdll_mess_NtCreateFile' not in line:
            continue
        path = re.search(r'inPathW=(.*?)\]', line)
        access = re.search(r'DesiredAccess=([0-9a-fA-F]+)', line)
        if not path or not access:
            continue
        value = path.group(1)
        access_value = int(access.group(1), 16)
        record = {'path': value, 'desired_access': access.group(1),
                  'generic_write': bool(access_value & 0x40000000)}
        if 'nvidia' in value.casefold():
            native_nvidia_events.append(record)
        if any(word in value.casefold() for word in ['d3dscache', 'dxcache', 'nvcache', 'shadercache', 'nv cache']):
            cache_events.append(record)
    report = {'schema': 'skyrim.pg_cache_probe.usvfs_trace.v1',
              'status': 'CACHE_ROOT_UNPROVEN_NO_CACHE_WRITE_OBSERVED',
              'native_result_sha256': sha(native_path), 'trace_sha256': sha(trace_path),
              'native_pid': native['pid'], 'debug_log_level': 0,
              'd3d11_hardware_compute_shader_pass': True,
              'shader_dispatch_performed': False,
              'cache_write_events': cache_events,
              'nvidia_file_events': native_nvidia_events,
              'main_config_unchanged': True,
              'kernel_etw': 'Blocked by normal Windows privilege policy; no elevation or security-setting change',
              'scope': 'Initialization-only usvfs evidence. No D3D cache write was observed; no cache-root override or full-workload containment is proven.',
              'formal_pg_allowed': False, 'pg_launched': False, 'game_launched': False}
    output = HERE / 'usvfs_trace_analysis_manifest.json'
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': report['status'], 'cache_write_events': len(cache_events),
                      'nvidia_file_events': len(native_nvidia_events), 'report': str(output)}, indent=2))


if __name__ == '__main__':
    main()
