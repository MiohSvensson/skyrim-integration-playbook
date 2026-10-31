"""Pin official offline grass generator 1.6 and its exact source, do not run it."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

OUT=Path(__file__).resolve().parent/'FasterNGIO_1.6'
COMMIT='5a1bff6ad3e44b5b9c4b5acdd0663ae20860ca40'
EXPECTED='e00f93c8ed978ae183630f8618082db06b8e59c9d15f2e719a2e58943643b5a2'


def download(url,path):
    if not path.exists():
        request=urllib.request.Request(url,headers={'User-Agent':'Codex Skyrim offline generator source audit'})
        with urllib.request.urlopen(request,timeout=30) as response:
            path.write_bytes(response.read())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(path,target):
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            destination=(target/member.filename).resolve()
            assert destination.is_relative_to(target.resolve()),'Unsafe archive member'
            if member.is_dir():
                destination.mkdir(parents=True,exist_ok=True)
            else:
                destination.parent.mkdir(parents=True,exist_ok=True)
                if not destination.exists():destination.write_bytes(archive.read(member))


def main():
    OUT.mkdir(exist_ok=True)
    release='https://api.github.com/repos/panthuncia/FasterNGIO/releases/tags/1.6'
    release_path=OUT/'release.json'
    download(release,release_path)
    data=json.loads(release_path.read_text(encoding='utf-8'))
    asset=next(asset for asset in data['assets'] if asset['name']=='FasterNGIO-Windows.zip')
    assert asset['digest']=='sha256:'+EXPECTED
    binary_zip=OUT/'FasterNGIO-Windows.zip'
    assert download(asset['browser_download_url'],binary_zip)==EXPECTED,'Release digest mismatch'
    assert binary_zip.stat().st_size==asset['size']
    extract(binary_zip,OUT/'binary')
    source_zip=OUT/('source-'+COMMIT+'.zip')
    source_url='https://codeload.github.com/panthuncia/FasterNGIO/zip/'+COMMIT
    source_sha=download(source_url,source_zip)
    extract(source_zip,OUT/'source')
    manifest={'status':'DOWNLOADED_AND_HASH_VERIFIED_NOT_EXECUTED','version':'1.6','source_commit':COMMIT,
      'published_at':data['published_at'],'release':release,'release_asset_url':asset['browser_download_url'],
      'expected_and_observed_binary_archive_sha256':EXPECTED,'binary_archive_bytes':binary_zip.stat().st_size,
      'source_url':source_url,'source_archive_sha256':source_sha,
      'binary_files':[{'relative':str(path.relative_to(OUT/'binary')),'size':path.stat().st_size,
                       'sha256':hashlib.sha256(path.read_bytes()).hexdigest()} for path in (OUT/'binary').rglob('*') if path.is_file()]}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('FasterNGIO 1.6 pinned and extracted; no executable started; release SHA256 verified')


if __name__=='__main__':main()
