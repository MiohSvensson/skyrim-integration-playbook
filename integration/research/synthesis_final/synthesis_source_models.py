"""Compare candidate ARMA model fields with their exact source-master records."""
from pathlib import Path


class SourceModels:
    def __init__(self, data_root, reader, sources=None, input_fields=None):
        self.data_root = Path(data_root) if data_root is not None else None
        self.reader = reader
        self.sources = sources or {}
        self.input_fields = input_fields
        self.cache = {}
        self.plugin_cache = {}

    def fields_for(self, masters, record):
        name = masters[record['fid'] >> 24]
        if self.input_fields is not None:
            key = f'{name.casefold()}:{record["fid"] & 0xffffff:06X}'
            if key not in self.input_fields:
                raise ValueError('Missing verified input-model context for ' + key)
            return self.input_fields[key]
        if Path(name).name != name or name.casefold().endswith('synthesis - patch.esp'):
            raise ValueError('Invalid source master name: ' + name)
        object_id = record['fid'] & 0xffffff
        cache_key = (name, object_id)
        if cache_key not in self.cache:
            if name not in self.plugin_cache:
                if name in self.sources:
                    _, source_records = self.sources[name]
                else:
                    _, source_records = self.reader(self.data_root / name)
                self.plugin_cache[name] = source_records
            matches = [row for row in self.plugin_cache[name] if row['sig'] == 'ARMA' and row['fid'] & 0xffffff == object_id]
            if len(matches) != 1:
                raise ValueError(f'Expected one source ARMA for {name}:{object_id:06X}')
            source = matches[0]
            if source.get('edid') != record.get('edid'):
                raise ValueError(f'Source ARMA editor ID differs for {name}:{object_id:06X}')
            self.cache[cache_key] = dict(source['fields'])
        return self.cache[cache_key]


def origin(source_fields, tag, value):
    return 'inherited_unchanged' if source_fields.get(tag, b'').rstrip(b'\0') == value.rstrip(b'\0') else 'changed_by_synthesis'
