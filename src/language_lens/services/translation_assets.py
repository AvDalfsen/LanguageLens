"""Checksummed local provider assets; downloads only during explicit preparation."""
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
from pathlib import Path
import stat
import tarfile
import time
from urllib.request import Request
from uuid import uuid4
import zipfile

from language_lens.config import settings_path
from language_lens.services.errors import KnownTaskError
from language_lens.services.model_download import DownloadProgress, urlopen


@lru_cache(maxsize=1)
def catalog():
    return json.loads(files('language_lens').joinpath('data/translation-providers.json').read_text('utf-8'))


def selection(source, target):
    if source == target:return {'full':None, 'word':None}
    pair=source+'-'+target
    return {'full':catalog()['full_text'].get(pair), 'word':catalog()['words'].get(pair)}


def identity(source, target):
    choice=selection(source,target)
    return {'version':catalog()['version'], **choice} if choice['full'] or choice['word'] else {'version':'argos-v1'}


def root():return settings_path().parent/'offline/translators'
def model_path(model_id):
    if model_id not in catalog()['models']:raise KnownTaskError('missing_assets')
    return root()/model_id


def model_ids(source,target):
    choice=selection(source,target)
    return list(dict.fromkeys([*( [choice['full']['model']] if choice['full'] else []),
                              *( [choice['word']] if choice['word'] else [])]))


def needs_firefox(source, target):
    return any(catalog()['models'][model_id].get('kind') == 'firefox' for model_id in model_ids(source, target))


def _owned_path(path,base):
    """Reject links/junctions and verify the absolute application-owned target."""
    if not path.resolve().is_relative_to(base.resolve()):raise KnownTaskError('integrity')
    for part in (base,*path.relative_to(base).parents,path):
        candidate=part if part.is_absolute() else base/part
        try:info=candidate.lstat()
        except FileNotFoundError:continue
        if candidate.is_symlink() or getattr(info,'st_file_attributes',0)&stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise KnownTaskError('integrity')
    return path


@lru_cache(maxsize=256)
def _checksum(name,size,modified,digest):
    hasher=hashlib.sha256()
    with Path(name).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):hasher.update(chunk)
    return hasher.hexdigest()==digest


def valid(path,item):
    try:
        stat=path.stat()
        return stat.st_size==item['bytes'] and _checksum(str(path),stat.st_size,stat.st_mtime_ns,item['sha256'])
    except OSError:return False


def required_files(source,target):
    result=[]
    for model_id in model_ids(source,target):
        result.extend((model_path(model_id)/item['name'],item) for item in catalog()['models'][model_id]['files'])
    if needs_firefox(source,target):
        for kind in ('bergamot_runtime','node_runtime'):
            result.extend((root()/kind/item['name'],item) for item in catalog()[kind]['files'])
    return result


def ready(source,target):return all(valid(path,item) for path,item in required_files(source,target))


def verified_model(model_id):
    path=model_path(model_id)
    if not all(valid(path/item['name'],item) for item in catalog()['models'][model_id]['files']):
        raise KnownTaskError('missing_assets')
    return path


def _download(item,temporary,progress):
    count=0; hasher=hashlib.sha256(); last=0.
    progress(DownloadProgress(0,item.get('bytes')))
    with urlopen(Request(item['url'],headers={'User-Agent':'LanguageLens','Accept-Encoding':'identity'}),timeout=30) as response, temporary.open('xb') as output:
        while chunk:=response.read(256*1024):
            count+=len(chunk)
            if item.get('bytes') and count>item['bytes']:raise KnownTaskError('integrity')
            if count>256*1024**2 and not item.get('bytes'):raise KnownTaskError('integrity')
            hasher.update(chunk);output.write(chunk)
            if time.monotonic()-last>.15:
                progress(DownloadProgress(count,item.get('bytes')));last=time.monotonic()
    if (item.get('bytes') and count!=item['bytes']) or hasher.hexdigest()!=item['sha256']:
        raise KnownTaskError('integrity')
    progress(DownloadProgress(count,item.get('bytes')))


def _decompress(packed,destination,item):
    """Stream large weights without retaining compressed/decompressed copies in RAM."""
    import zstandard
    count=0
    try:
        with packed.open('rb') as source, destination.open('xb') as output:
            with zstandard.ZstdDecompressor().stream_reader(source) as reader:
                while chunk:=reader.read(1024*1024):
                    count+=len(chunk)
                    if count>item['bytes']:raise KnownTaskError('integrity')
                    output.write(chunk)
    except zstandard.ZstdError as exc:
        raise KnownTaskError('integrity') from exc


def prepare(source,target,report,progress,*,force=False):
    from filelock import FileLock
    _owned_path(root(),settings_path().parent)
    root().mkdir(parents=True,exist_ok=True)
    paths=[]
    with FileLock(str(root()/'assets.lock'),timeout=10):
        for model_id in model_ids(source,target):
            model=catalog()['models'][model_id];directory=_owned_path(model_path(model_id),settings_path().parent);directory.mkdir(exist_ok=True)
            for item in model['files']:
                path=_owned_path(directory/item['name'],settings_path().parent);paths.append(path)
                if not force and valid(path,item):continue
                report('Preparing local files')
                temporary=path.with_name('.'+path.name+'.'+uuid4().hex+'.part')
                packed=temporary.with_suffix('.download')
                try:
                    _download({'url':item['url'],'bytes':item['compressed_bytes'],'sha256':item['compressed_sha256']},packed,progress)
                    _decompress(packed,temporary,item)
                    if not valid(temporary,item):raise KnownTaskError('integrity')
                    temporary.replace(path)
                finally:
                    temporary.unlink(missing_ok=True);packed.unlink(missing_ok=True)
        if needs_firefox(source,target):
            for kind in ('bergamot_runtime','node_runtime'):
                info=catalog()[kind];directory=_owned_path(root()/kind,settings_path().parent);directory.mkdir(exist_ok=True)
                expected={item['name']:item for item in info['files']}
                for name in expected:_owned_path(directory/name,settings_path().parent)
                paths.extend(directory/name for name in expected)
                if all(valid(directory/name,item) for name,item in expected.items()):continue
                report('Preparing local files')
                archive=directory/('.runtime-'+uuid4().hex+'.part')
                try:
                    _download(info,archive,progress)
                    if kind=='node_runtime':
                        with zipfile.ZipFile(archive) as handle:
                            content={name:handle.read('node-'+info['version']+'-win-x64/'+name) for name in expected}
                    else:
                        with tarfile.open(archive,'r:gz') as handle:
                            content={name:handle.extractfile('package/worker/'+name).read() for name in expected}
                    for name,data in content.items():
                        item=expected[name]
                        if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise KnownTaskError('integrity')
                    for name,data in content.items():
                        temporary=directory/('.'+name+'.part');temporary.write_bytes(data);temporary.replace(directory/name)
                finally:archive.unlink(missing_ok=True)
    return paths


def remove(source,target):
    # Model files can serve several directions, as Argos pivot packages already do.
    # Retire whole owned directories; all affected pairs need preparation again.
    base=settings_path().parent
    destination=_owned_path(base/'removed-translation-models',base);destination.mkdir(parents=True,exist_ok=True)
    for model_id in model_ids(source,target):
        path=_owned_path(model_path(model_id),base)
        if path.is_dir():path.replace(_owned_path(destination/(model_id+'-'+uuid4().hex),base))
