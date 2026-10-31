"""Compare a root-downloaded author package without extracting whole asset sets."""
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import zipfile

sys.dont_write_bytecode = True
OWN = Path(__file__).resolve().parent
BASE = OWN.parents[2]
sys.path.insert(0, str(BASE / 'rootcause'))
import bsarch_readonly as bsa
sys.path.insert(0, str(BASE / 'integration/research/vfs_validation'))
from quest_resource_seeds import records, plugin_header, text

ARCHIVE = BASE / 'integration/research/forgotten_city_restoration/downloads/The Forgotten City-1179-1-8.zip'
ZIP_SHA = 'cf9d3f5b0609b498b23f35976260ebec0e1a39fb69286d0acf4aec91e415a31a'
TARGETS = ['sound/fx/forgottencity/fcarbitermotifsound.wav',
           'sound/fx/forgottencity/fcarbitermotifsound.xwm']
TARGET_RECORDS = {'forgottencity.esp|0e2673', 'forgottencity.esp|0c38b4'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def pin(path):
    return {'path': str(path), 'sha256': digest(path), 'bytes': Path(path).stat().st_size}


def normalized(name):
    return name.replace('\\', '/').casefold()


def list_bsa_and_extract_exact(path):
    handle = bsa.create()
    names = []
    record_refs = {}
    extracted = []
    try:
        loaded = bsa.load(handle, str(path))
        assert loaded.code >= 0, loaded.text
        @bsa.callback
        def visit(archive, name, record, folder, context):
            names.append(name)
            if normalized(name) in TARGETS:
                record_refs[normalized(name)] = record
            return False
        result = bsa.iterate(handle, visit, None)
        assert result.code >= 0, result.text
        for key, record in record_refs.items():
            result = bsa.extract(handle, record)
            try:
                assert result.message.code >= 0, result.message.text
                payload = bsa.ctypes.string_at(result.buffer.data, result.buffer.size)
                destination = OWN / 'author_exact_resources' / key
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    assert destination.read_bytes() == payload
                else:
                    destination.write_bytes(payload)
                extracted.append({'path_key': key, **pin(destination), 'source_archive': str(path)})
            finally:
                if result.buffer.data:
                    assert bsa.freebuf(handle, result.buffer).code >= 0
        return names, extracted
    finally:
        bsa.close(handle)
        bsa.free(handle)


def main():
    OWN.mkdir(parents=True, exist_ok=True)
    assert ARCHIVE.stat().st_size == 113963051
    assert digest(ARCHIVE) == ZIP_SHA
    database = sqlite3.connect((BASE / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True)
    database.row_factory = sqlite3.Row
    source_mod = Path(database.execute('select path from mods where id=137').fetchone()[0])
    original_plugin = source_mod / 'ForgottenCity.esp'
    zip_rows = []
    bsa_comparisons = []
    all_target_resources = []
    all_runtime_names = set()
    with zipfile.ZipFile(ARCHIVE) as package:
        assert len(package.infolist()) == 3
        for entry in package.infolist():
            key = normalized(entry.filename)
            assert '/' not in key and key in {'forgottencity.esp', 'forgottencity.bsa', 'forgottencity - textures.bsa'}
            h = hashlib.sha256()
            with package.open(entry) as stream:
                for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                    h.update(chunk)
            sha = h.hexdigest()
            zip_rows.append({'member': entry.filename, 'bytes': entry.file_size,
                'compressed_bytes': entry.compress_size, 'crc32': f'{entry.CRC:08x}',
                'date_time': entry.date_time, 'compression_type': entry.compress_type,
                'sha256': sha, 'zip_stream_crc_verified': True})
            local = source_mod / entry.filename
            assert local.is_file() and local.stat().st_size == entry.file_size
            assert digest(local) == sha
            if key.endswith('.esp'):
                author_plugin = OWN / entry.filename
                if author_plugin.exists():
                    assert digest(author_plugin) == sha
                else:
                    author_plugin.write_bytes(package.read(entry))
                continue
            indexed = database.execute('select id from bsa_archives where path=? and sha256=?', (str(local), sha)).fetchone()
            assert indexed, local
            archive_id = indexed[0]
            names, extracted = list_bsa_and_extract_exact(local)
            normalized_names = [normalized(n) for n in names]
            assert len(normalized_names) == len(set(normalized_names))
            with local.open('rb') as stream:
                header = stream.read(36)
            assert header[:4] == b'BSA\0'
            version = struct.unpack_from('<I', header, 4)[0]
            count = struct.unpack_from('<I', header, 20)[0]
            assert count == len(names)
            indexed_members = {r['path_key']: r['sha256'] for r in database.execute(
                "select path_key,sha256 from bsa_entries where archive_id=? and status='ok'", (archive_id,))}
            assert set(normalized_names) == set(indexed_members)
            all_runtime_names.update(normalized_names)
            all_target_resources += extracted
            inventory_path = OWN / (key.replace('.bsa', '') + '_member_inventory.json')
            inventory_path.write_text(json.dumps({'archive': str(local), 'archive_sha256': sha,
                'zip_member': entry.filename, 'members': sorted(names)}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            fx_prefix = 'sound/fx/forgottencity/'
            fx_members = sorted(n for n in normalized_names if n.startswith(fx_prefix))
            direct_related = sorted(n for n in normalized_names if not n.startswith('sound/voice/')
                                    and ('motif' in n or 'arbiter' in n))
            voice_response = sorted(n for n in normalized_names if n.startswith('sound/voice/forgottencity.esp/')
                                    and '000c38b4_' in n)
            bsa_comparisons.append({'zip_member': entry.filename, 'canonical_sha256': sha,
                'byte_identical_existing_local_archive': pin(local), 'metadata_archive_id': archive_id,
                'bsa_version': version, 'header_file_count': count, 'directly_enumerated_members': len(names),
                'entire_name_set_equals_previously_full_hash_verified_inventory': True,
                'inventory_evidence': pin(inventory_path),
                'exact_missing_target_presence': {k: k in normalized_names for k in TARGETS},
                'nonvoice_arbiter_or_motif_related_paths': direct_related,
                'sound_fx_forgottencity_paths': fx_members,
                'provided_consumer_voice_response_paths': [{'path_key': k, 'sha256': indexed_members[k]} for k in voice_response]})
    author_header = plugin_header(author_plugin)
    local_header = plugin_header(original_plugin)
    assert author_header == local_header
    authored = {r['identity']: r for r in records(author_plugin, TARGET_RECORDS, author_header['masters'], 'ForgottenCity.esp')}
    selected = {r['identity']: r for r in records(original_plugin, TARGET_RECORDS, local_header['masters'], 'ForgottenCity.esp')}
    assert set(authored) == set(selected) == TARGET_RECORDS
    record_rows = []
    for identity in sorted(TARGET_RECORDS):
        author, local = authored[identity], selected[identity]
        assert author['payload_sha256'] == local['payload_sha256']
        assert author['fields'] == local['fields'] and author['flags'] == local['flags']
        row = {'identity': identity, 'signature': author['sig'], 'raw_form_id': f'{author["fid"]:08X}',
            'flags': author['flags'], 'author_payload_sha256': author['payload_sha256'],
            'selected_payload_sha256': local['payload_sha256'], 'byte_identical_decompressed_payload': True,
            'fields': [{'tag': t, 'bytes_hex': v.hex(), 'text': text(v)} for t, v in author['fields']]}
        if author['sig'] == 'INFO':
            responses = []
            for tag, value in author['fields']:
                if tag == 'TRDT':
                    sound = struct.unpack_from('<I', value, 16)[0]
                    responses.append({'number': value[12], 'sound_raw_id': f'{sound:08X}',
                                      'TRDT_sha256': hashlib.sha256(value).hexdigest()})
            row['typed_response_sound_fields'] = responses
            assert next(r for r in responses if r['number'] == 5)['sound_raw_id'] == '010E2673'
        record_rows.append(row)
    absent = not all_target_resources and all(k not in all_runtime_names for k in TARGETS)
    report = {'schema': 'skyrim.forgotten_city_author_compare.v1',
        'status': 'AUTHOR_SSE18_EXACT_PACKAGE_CONFIRMS_UPSTREAM_MISSING_MOTIF_AUDIO' if absent else 'EXACT_AUTHOR_AUDIO_RESOURCE_RECOVERED',
        'package': pin(ARCHIVE), 'author_release': 'The Forgotten City SSE1.8',
        'public_author_file_page': 'https://www.nexusmods.com/skyrimspecialedition/mods/1179?file_id=32847&tab=files',
        'download_provenance': 'Root downloaded the ordinary author-issued manual link from its logged-in browser; this comparison uses only the supplied archive, public file page, and verified local content. No cookie, API key or temporary signed-CDN URL is read or stored.',
        'zip_member_count': len(zip_rows), 'zip_members': zip_rows,
        'source_plugin': pin(original_plugin), 'author_plugin': pin(author_plugin),
        'whole_author_and_selected_plugin_sha_equal': author_header['sha256'] == local_header['sha256'],
        'record_comparisons': record_rows, 'bsa_comparisons': bsa_comparisons,
        'exact_audio_resources_to_import': all_target_resources,
        'disposition': 'Preserve the authored SNDR and INFO unchanged. The exact motif WAV/XWM is absent from the complete original author SSE1.8 package; no file can be restored from this package, and no other audio or FUZ is substituted. Retain an explicit upstream audio limitation, never mark this effect repaired.' if absent else 'Import only the exact authored recovered audio after its SHA is verified.',
        'scope': 'The author ZIP, its complete BSA filename inventories and two exact record payloads were checked. No runtime/profile/source package was modified; no game or GUI was started. BSA bytes were not duplicated: each ZIP member hash equals the existing already-inventoried local archive, which was directly re-enumerated with the read-only libbsarch adapter.'}
    output = OWN / 'author_compare.json'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': report['status'], 'output': str(output), 'sha256': digest(output),
        'zip_members': len(zip_rows), 'record_payloads_equal': len(record_rows),
        'bsa_member_counts': [x['directly_enumerated_members'] for x in bsa_comparisons],
        'recovered_exact_audio': len(all_target_resources)}))


if __name__ == '__main__':
    main()
