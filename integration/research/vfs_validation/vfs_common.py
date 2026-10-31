"""Read-only inspection helpers for an explicit physical or MO2 VFS data view."""
import collections
import configparser
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import sqlite3
import struct
import sys
import unicodedata

sys.dont_write_bytecode=True
OWN=Path(__file__).resolve().parent
BASE=OWN.parents[2]
DEFAULT_TARGET=BASE/'UnifiedSkyrim'
STOCK_NAMES=['Skyrim.esm','Update.esm','Dawnguard.esm','HearthFires.esm','Dragonborn.esm']
EXCLUDED_ROOTS={'root','calientetools','nemesis_engine','pandora_engine','fnis behavior se','tools','.git','.svn','__pycache__'}
EXCLUDED_FILES={'meta.ini','.ds_store','thumbs.db','desktop.ini'}


def key(s):return unicodedata.normalize('NFC',str(s).replace('\\','/')).casefold()
def lp(path):
    s=os.path.abspath(path);return s if s.startswith('\\\\?\\') else '\\\\?\\'+s
def safe_output(path):
    p=Path(path).resolve()
    if not p.is_relative_to(OWN.resolve()) or p==OWN:raise ValueError('Output must be inside '+str(OWN))
    p.parent.mkdir(parents=True,exist_ok=True);return p
def digest(path):
    with open(lp(path),'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write_json(path,value):safe_output(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def documented_hkx_slots():
    evidence=OWN/'graph_issue_evidence.json'
    if not evidence.is_file():return {'evidence_path':str(evidence),'sha256':None,'files':[]}
    report=json.loads(evidence.read_text(encoding='utf-8'))
    return {'evidence_path':str(evidence),'sha256':digest(evidence),'files':report['sos']['graph_files']}
def runtime_candidate(relative):
    parts=key(relative).split('/')
    return bool(parts) and parts[0] not in EXCLUDED_ROOTS and not any(p.endswith('.mohidden') or p in ('__pycache__','.git','.svn') for p in parts) and parts[-1] not in EXCLUDED_FILES


def walk(root):
    root=Path(root);stack=[(root,'')]
    if not os.path.isdir(lp(root)):return
    while stack:
        folder,rel=stack.pop()
        with os.scandir(lp(folder)) as entries:
            for entry in entries:
                r=(rel+'/'+entry.name).lstrip('/')
                if not runtime_candidate(r):continue
                if entry.is_dir(follow_symlinks=False):stack.append((folder/entry.name,r))
                elif entry.is_file(follow_symlinks=False):yield r,folder/entry.name,entry.stat(follow_symlinks=False)
                else:raise ValueError('Non-regular runtime entry: '+str(folder/entry.name))


kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.GetModuleHandleW.argtypes=[wintypes.LPCWSTR];kernel.GetModuleHandleW.restype=wintypes.HMODULE
kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
kernel.CreateFileW.restype=wintypes.HANDLE
kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
class FileIDInfo(ctypes.Structure):_fields_=[('volume',ctypes.c_ulonglong),('identifier',ctypes.c_ubyte*16)]
kernel.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
kernel.GetFileInformationByHandleEx.restype=wintypes.BOOL
def injected():return bool(kernel.GetModuleHandleW('usvfs_x64.dll'))
def file_identity(path):
    handle=kernel.CreateFileW(lp(path),0,7,None,3,0,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:
        out=FileIDInfo()
        if not kernel.GetFileInformationByHandleEx(handle,18,ctypes.byref(out),ctypes.sizeof(out)):raise ctypes.WinError(ctypes.get_last_error())
        return f'{out.volume:016X}:'+bytes(out.identifier).hex()
    finally:kernel.CloseHandle(handle)


def plugin_header(path):
    with open(lp(path),'rb') as f:
        h=f.read(24)
        if h[:4]!=b'TES4':raise ValueError('Not TES4: '+str(path))
        size,flags=struct.unpack_from('<II',h,4);payload=f.read(size);f.seek(0);sha=hashlib.file_digest(f,'sha256').hexdigest()
    pos=0;masters=[];extended=None;version=None
    while pos<len(payload):
        tag=payload[pos:pos+4];n=struct.unpack_from('<H',payload,pos+4)[0];pos+=6
        if tag==b'XXXX':extended=struct.unpack_from('<I',payload,pos)[0];pos+=n;continue
        if extended is not None:n=extended;extended=None
        v=payload[pos:pos+n];pos+=n
        if tag==b'MAST':masters.append(v.rstrip(b'\0').decode('utf-8'))
        if tag==b'HEDR':version=struct.unpack_from('<f',v)[0]
    assert pos==len(payload)
    return {'sha256':sha,'masters':masters,'flags':flags,'version':version,'is_light':bool(flags&0x200) or Path(path).suffix.casefold()=='.esl'}
def dll_info(path):
    with open(lp(path),'rb') as f:
        h=f.read(64);offset=struct.unpack_from('<I',h,0x3c)[0];f.seek(offset);pe=f.read(6);f.seek(0);sha=hashlib.file_digest(f,'sha256').hexdigest()
    assert h[:2]==b'MZ' and pe[:4]==b'PE\0\0'
    return {'sha256':sha,'machine':struct.unpack_from('<H',pe,4)[0]}


def owned_id_range(path,master_count,is_light):
    """Inspect actual record headers; source-level zero diagnostics do not prove valid ESL range."""
    with open(lp(path),'rb') as f:data=f.read()
    pos=0;count=0;lowest=None;highest=None;bad=[];scope=[]
    while pos<len(data):
        if pos+24>len(data):raise ValueError('Truncated record/group header')
        signature=data[pos:pos+4];size=struct.unpack_from('<I',data,pos+4)[0]
        if signature==b'GRUP':
            if size<24 or pos+size>len(data):raise ValueError('Invalid GRUP bounds')
            pos+=24;continue
        if pos+24+size>len(data):raise ValueError('Invalid record bounds')
        fid=struct.unpack_from('<I',data,pos+12)[0]
        if signature!=b'TES4' and fid>>24>=master_count:
            object_id=fid&0xffffff;count+=1;lowest=object_id if lowest is None else min(lowest,object_id);highest=object_id if highest is None else max(highest,object_id)
            if fid>>24>master_count and len(scope)<8:scope.append({'signature':signature.decode('ascii','replace'),'fid':f'{fid:08X}'})
            if is_light and object_id>0xfff and len(bad)<16:bad.append({'signature':signature.decode('ascii','replace'),'fid':f'{fid:08X}','object_id':f'{object_id:06X}'})
        pos+=24+size
    return {'owned_record_count':count,'minimum_owned_object_id':lowest,'maximum_owned_object_id':highest,
      'light_owned_id_range_valid':not bad,'out_of_light_range_examples':bad,'scope_alias_examples':scope,
      'requires_extended_esl_low_id_support':bool(is_light and lowest is not None and lowest<0x800)}


def read_text(path):
    b=Path(path).read_bytes()
    return b.decode('utf-16') if b.startswith((b'\xff\xfe',b'\xfe\xff')) else b.decode('utf-8-sig',errors='replace')
def controls(target,profile):
    paths=[profile/n for n in ['modlist.txt','plugins.txt','loadorder.txt','Skyrim.ini','SkyrimCustom.ini','initweaks.ini','archives.txt','settings.ini']]
    paths.append(target/'Game/Skyrim.ccc')
    return {str(p):digest(p) for p in paths if p.is_file()}
def names(target,profile,present):
    out=list(STOCK_NAMES);ccc=target/'Game/Skyrim.ccc';absent=[]
    if ccc.is_file():
        for line in read_text(ccc).splitlines():
            n=line.strip()
            if n and not n.startswith('#'):
                if key(n) in present:out.append(n)
                else:absent.append(n)
    out += [line[1:].strip() for line in read_text(profile/'plugins.txt').splitlines() if line.startswith('*')]
    return list(dict((key(n),n) for n in out).values()),absent
def active_archive_names(profile,enabled,present):
    ini=configparser.ConfigParser(strict=False,interpolation=None)
    for n in ['Skyrim.ini','SkyrimCustom.ini','initweaks.ini']:
        p=profile/n
        if p.is_file():ini.read_string(read_text(p))
    out=[]
    if ini.has_section('Archive'):
        for setting in ['sResourceArchiveList','sResourceArchiveList2']:
            out += [n.strip() for n in ini.get('Archive',setting,fallback='').split(',') if n.strip()]
    for plugin in enabled:
        stem=Path(plugin).stem
        out += [stem+'.bsa',stem+' - Textures.bsa']
    return list(dict((key(n),n) for n in out if key(n) in present).values()),dict(ini['Archive']) if ini.has_section('Archive') else {}


def asset_key(value,kind=None,parent=None):
    s=value.strip('\0 \r\n\t').replace('\\','/')
    if not s or ':' in s:return None
    if key(s).startswith('data/'):s=s[5:]
    suffix=Path(s).suffix.casefold()
    if suffix not in {'.dds','.nif','.tri','.xml','.hkx','.wav','.xwm','.fuz'}:return None
    if kind=='texture' and not key(s).startswith('textures/'):s='textures/'+s
    elif suffix in ('.nif','.tri','.hkx') and not key(s).startswith('meshes/'):s='meshes/'+s
    elif suffix=='.dds' and not key(s).startswith('textures/'):s='textures/'+s
    elif suffix=='.xml' and not key(s).startswith(('meshes/','skse/')) and parent:s=posixpath.dirname(parent)+'/'+s
    s=posixpath.normpath(s).strip('/')
    return key(s) if not s.startswith('../') else None


class ResourceCatalog:
    """Actual logical archive names choose the archive; indexed sources only supply known member hashes."""
    def __init__(self,physical,archives):
        self.physical=physical;self.archives=archives;self.cache={};self.archive_hashes={};self.archive_checks=[]
        self.db=sqlite3.connect((BASE/'baseline/skyrim_research.sqlite').as_uri()+'?mode=ro',uri=True);self.db.row_factory=sqlite3.Row
    def resolve(self,k):
        k=key(k)
        if k in self.cache:return self.cache[k]
        if k in self.physical:
            r=self.physical[k];out={'kind':'loose','relative_path':r['relative_path'],'physical_path':r['physical_path'],'provider':r['provider'],'bytes':r['size_bytes']}
        else:
            matches=[]
            for row in self.db.execute('''select distinct a.id,a.path,a.sha256 archive_sha256,e.sha256,e.size_bytes from bsa_entries e
              join bsa_archives a on a.id=e.archive_id join bsa_sources s on s.archive_id=a.id
              where e.path_key=? and s.source_kind in ('mod','stock Data') and e.status='ok' ''',(k,)):
                basename=key(Path(row['path']).name)
                if basename not in self.archives:continue
                archive=self.archives[basename];pp=archive['physical_path']
                if basename not in self.archive_hashes:self.archive_hashes[basename]=digest(pp)
                if self.archive_hashes[basename]!=row['archive_sha256']:continue
                matches.append((archive['order'],dict(row),archive))
            if matches:
                _,r,a=max(matches,key=lambda x:x[0]);out={'kind':'bsa','archive':a['relative_path'],'archive_physical':a['physical_path'],
                  'archive_sha256':r['archive_sha256'],'metadata_archive_id':r['id'],'entry':k,'sha256':r['sha256'],'bytes':r['size_bytes'],
                  'provider':a['provider'],'order':a['order']}
            else:out={'kind':'missing','entry':k}
        self.cache[k]=out;return out


def resource_seeds():
    seeds=collections.defaultdict(set);optional=set();provenance=[]
    ledger=BASE/'integration/imported_equipment.json'
    if ledger.is_file():
        equipment=json.loads(ledger.read_text(encoding='utf-8'));provenance.append(str(ledger))
        for r in equipment['inputs']:
            p=Path(r['path']);assert digest(p)==r['sha256'];j=json.loads(p.read_text(encoding='utf-8'))
            for k,a in j['asset_sources'].items():seeds[key(k)].add('gear:'+','.join(a['requested_by']))
            for plugin in j['plugins']:optional.update(key(p) for p in plugin['missing_optional_morph_tri'])
    rihad=json.loads((BASE/'repairs/upstream_asset_expectations_TuLED.json').read_text(encoding='utf-8'))
    canonical={}
    for row in rihad:seeds[key(row['relative'])].add('rihad45');canonical[key(row['relative'])]=row['expected_sha256']
    supplement=BASE/'integration/research/plugin_integration/gear_behavior_graph_supplement.json'
    if supplement.is_file():
        for row in json.loads(supplement.read_text(encoding='utf-8'))['assets']:seeds[row['path_key']].add('gear_auxiliary_graph')
    return seeds,optional,canonical,provenance
