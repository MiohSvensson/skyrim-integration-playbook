"""Exact, fail-closed source resolution for mesh and material resources."""
from pathlib import Path
import shutil
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'rootcause'))
from bsarch_readonly import extract_files
import vfs_common as vfs


class SourceResolver:
    def __init__(self, source_dir, overrides=None, strict=True):
        self.base = source_dir.parents[3]
        self.collection = self.base.parent
        self.source_dir = Path(source_dir)
        self.source_root = self.collection / 'Anno/iniRePather-Skyrim/mods/PGPatcher_Output'
        self.overrides = overrides or {}
        self.strict = strict
        self.sources = {}
        self.alternatives = {}

    def archive_rows(self, path):
        if path not in self.alternatives:
            with sqlite3.connect((self.base / 'baseline/skyrim_research.sqlite').as_uri() + '?mode=ro', uri=True) as db:
                self.alternatives[path] = db.execute('''select distinct e.sha256,a.path,a.sha256 archive_sha256,s.source_kind,e.size_bytes from bsa_entries e
                    join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=a.id
                    where e.path_key=? order by a.id''', (path,)).fetchall()
        return self.alternatives[path]

    def extract(self, archive, path, digest, archive_sha, basis):
        archive = Path(archive).resolve(strict=True)
        if vfs.digest(archive) != archive_sha:
            raise ValueError('Archive hash changed: ' + str(archive))
        blob = extract_files(archive, {path: digest})[path]
        if shutil.disk_usage(self.base).free < 32 * 1024**3 + len(blob) + 4096:
            raise RuntimeError('Disk reserve would be crossed')
        extracted = self.source_dir / path
        extracted.parent.mkdir(parents=True, exist_ok=True)
        if not extracted.exists():
            with extracted.open('xb') as stream:
                stream.write(blob)
        elif vfs.digest(extracted) != digest:
            raise ValueError('Extracted source differs from archive hash: ' + path)
        return extracted, basis

    def source_for(self, path):
        if path in self.sources:
            return self.sources[path]
        if path in self.overrides:
            row = self.overrides[path]
            result = self.extract(row['archive'], path, row['entry_sha256'], row['archive_sha256'], row['basis'])
            self.sources[path] = result
            return result
        loose = self.source_root / path
        if path == 'meshes/dr aris tag/dr_aris_armor.nif' and (self.collection / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2/meshes/dr aris tag/dr_aris_armor_0.nif').is_file():
            result = (self.collection / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2/meshes/dr aris tag/dr_aris_armor_0.nif',
                      'Derived default base alias from the exact author weight-0 mesh; weight-1 is separately present')
        elif (path.startswith('meshes/dr aris tag/') or path.startswith('textures/dr aris tag/')) and (self.collection / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2' / path).is_file():
            result = (self.collection / 'TuLED/File Mod Skyrim SE/mods/ADVG 1st #05 The Adventurer\'s Guild by PI Update v2' / path, 'Exact Adventurer\'s Guild author asset')
        elif loose.is_file():
            result = (loose, 'Exact author PGPatcher_Output asset')
        elif path.startswith('textures/pbr/') and (self.collection / 'Anno/iniRePather-Skyrim/mods/原版装备材质替换-Faultier\'s PBR conversion of Xavbio\'s armors - vanilla res' / path).is_file():
            result = (self.collection / 'Anno/iniRePather-Skyrim/mods/原版装备材质替换-Faultier\'s PBR conversion of Xavbio\'s armors - vanilla res' / path, 'Exact Faultier PBR material source')
        else:
            rows = self.archive_rows(path)
            if not rows:
                raise ValueError('Missing runtime and source asset: ' + path)
            if self.strict and len({row[0] for row in rows}) != 1:
                raise ValueError('Ambiguous archive source hashes: ' + path)
            if path.startswith('textures/armor/darkcrusaderreforged/kingcrusaderarmor/'):
                rows = [row for row in rows if Path(row[1]).name == 'DCR_KingCrusaderMegaPack_SSE - Textures.bsa']
            baseline = [row for row in rows if 'TuLED' in Path(row[1]).parts]
            if baseline:
                rows = baseline
            if path == 'textures/cubemaps/blacksky_e.dds':
                rows = [row for row in rows if Path(row[1]).name == 'LegacyoftheDragonborn - Textures.bsa']
            stock = [row for row in rows if row[3] == 'stock Data'
                     and (self.base / 'repairs/consistent_stock/Data' / Path(row[1]).name).is_file()
                     and vfs.digest(self.base / 'repairs/consistent_stock/Data' / Path(row[1]).name) == row[2]]
            if stock:
                rows = stock
            if len({row[0] for row in rows}) != 1:
                raise ValueError('Ambiguous selected archive source: ' + path)
            digest, archive, archive_sha, _, _ = rows[0]
            result = self.extract(archive, path, digest, archive_sha, 'Exact archive-backed author asset: ' + archive)
        self.sources[path] = result
        return result
