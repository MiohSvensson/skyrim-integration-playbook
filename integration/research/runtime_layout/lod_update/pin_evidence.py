"""Pin small primary-author pages/config evidence without starting a tool."""
import hashlib
import json
import shutil
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
PAGES = {'Updating': 'https://dyndolod.info/Updating',
         'Command-Line-Argument': 'https://dyndolod.info/Help/Command-Line-Argument',
         'Terrain-LOD-and-Water-LOD': 'https://dyndolod.info/Help/Terrain-LOD-and-Water-LOD',
         'Grass-LOD': 'https://dyndolod.info/Help/Grass-LOD',
         'TexGen': 'https://dyndolod.info/Help/TexGen',
         'Advanced-Mode': 'https://dyndolod.info/Help/Advanced-Mode',
         'Occlusion-Data': 'https://dyndolod.info/Help/Occlusion-Data'}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    directory = OUT / 'primary_sources'
    directory.mkdir(exist_ok=True)
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'pages': [], 'local': []}
    for key, url in PAGES.items():
        request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 Skyrim integration read-only evidence'})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                data = response.read()
                assert response.status == 200 and b'<title>' in data and key.split('-')[0].lower().encode() in data.lower()
            path = directory / (key + '.html')
            path.write_bytes(data)
            report['pages'].append({'url': url, 'path': str(path), 'bytes': len(data), 'sha256': sha(path), 'status': 'Author page contents retrieved; claims separately inspected'})
        except Exception as error:
            report['pages'].append({'url': url, 'status': 'RETRIEVAL_FAILED', 'error': str(error)})
    local = [ROOT / 'TuLED/Tool/DynDOLOD/Edit Scripts/DynDOLOD/DynDOLOD_SSE.ini',
             ROOT / 'TuLED/Tool/DynDOLOD/Edit Scripts/DynDOLOD/Presets/DynDOLOD_SSE_Default.ini',
             ROOT / 'TuLED/Tool/DynDOLOD/Edit Scripts/DynDOLOD/Configs/DynDOLOD_SSE_worldspace_ignore.txt']
    for source in local:
        target = directory / source.name
        shutil.copyfile(source, target)
        report['local'].append({'source': str(source), 'copy': str(target), 'sha256': sha(target)})
    for relative in ('TuLED/Tool/DynDOLOD/DynDOLODx64.exe', 'TuLED/Tool/DynDOLOD/TexGenx64.exe', 'TuLED/Tool/xLODGen/xLODGenx64.exe'):
        source = ROOT / relative
        report['local'].append({'source': str(source), 'bytes': source.stat().st_size, 'sha256': sha(source), 'copied': False})
    report['obsolete_export_path_evidence'] = {
        'source': str(ROOT / 'TuLED/Tool/DynDOLOD/Edit Scripts/Export/LODGen_SSE_Export_Tamriel.txt'),
        'sha256': sha(ROOT / 'TuLED/Tool/DynDOLOD/Edit Scripts/Export/LODGen_SSE_Export_Tamriel.txt'),
        'warning': 'Existing exports contain C:\\Modding 2 absolute TerrainData/GrassMap/PathGrass/TextureAtlasMap/PathData/PathOutput/Resource paths. Never execute those unchanged.'}
    (OUT / 'primary_source_manifest.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Pinned primary pages:', sum(row.get('bytes', 0) > 0 for row in report['pages']), '/', len(PAGES))


if __name__ == '__main__':
    main()
