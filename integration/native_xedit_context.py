"""Independent validation of xEdit's native loaded-plugin sequence and log markers."""
import hashlib
import json
from pathlib import Path
import re

from materialize import sha


def read_log(path):
    path = Path(path)
    if not path.is_file():
        return ''
    raw = path.read_bytes()
    return raw.decode('utf-16') if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else raw.decode('utf-8-sig', errors='replace')


def evaluate(task, prepared, inputs, log):
    content = read_log(log)
    profile_names = [r['name'] for r in inputs['plugins']]
    expected = [profile_names[0], 'SkyrimSE.exe', *profile_names[1:]]
    loaded = re.findall(r'Background Loader: loading "([^"]+)"', content)
    expected_keys = {n.casefold() for n in expected}
    loaded_keys = {n.casefold() for n in loaded}
    done = f'Done: Applying script "{Path(task).name}"' in content
    return {'expected_profile_plugins': len(profile_names), 'expected_native_entries': len(expected),
            'loaded_native_entries': len(loaded), 'exact_order_match': loaded == expected,
            'expected_not_loaded': [n for n in expected if n.casefold() not in loaded_keys],
            'unexpected_loaded': [n for n in loaded if n.casefold() not in expected_keys],
            'order_sha256': hashlib.sha256(json.dumps(loaded, ensure_ascii=False).encode('utf-8')).hexdigest(),
            'pseudo_plugin_note': 'SkyrimSE.exe is an xEdit module-list entry, not evidence of a launched game process.',
            'marker_seen': prepared['pass_marker'] in content,
            'script_done_marker_seen': done, 'log_sha256': sha(log) if Path(log).is_file() else None}
