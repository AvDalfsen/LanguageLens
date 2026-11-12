"""Reproduce checksummed production model packs; never run during capture.

Install requirements from constraints/translation-model-build.txt into an isolated
build environment. Only catalogue-pinned files are downloaded. Converted output
must reproduce the selected checkpoint byte for byte before entering the pack.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def valid(path, item):
    if not path.is_file() or path.stat().st_size != item['bytes']:
        return False
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest() == item['sha256']


def download(item, destination):
    if valid(destination, item):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + '.part')
    # Resume interruptions, but never trust partial or redirected data until the
    # complete pinned size and digest have been checked.
    subprocess.run(['curl.exe', '--fail', '--location', '--silent', '--show-error',
                    '--proto', '=https', '--proto-redir', '=https', '--retry', '3',
                    '--connect-timeout', '20', '--max-time', '1800',
                    '--max-filesize', str(item['bytes']), '--continue-at', '-',
                    '--output', str(partial), item['url']], check=True)
    if not valid(partial, item):
        raise RuntimeError(f'Publisher checksum mismatch: {destination.name}')
    partial.replace(destination)


def build(catalog, model_id, source_root, output, keep_source):
    info = catalog['models'][model_id]
    destination = output / model_id
    if all(valid(destination / i['name'], i) for i in info['files']):
        print(model_id + ': verified existing pack', flush=True)
        return
    destination.mkdir(parents=True, exist_ok=True)
    spec = info.get('build')
    if spec:
        if spec['type'] != 'transformers':
            raise RuntimeError('Unsupported pinned build type.')
        source = source_root / model_id
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda i: download(i, source / i['name']), spec['source_files']))
        print(model_id + ': publisher files verified; converting', flush=True)
        import torch
        torch.set_num_threads(4)
        from ctranslate2.converters import TransformersConverter
        with tempfile.TemporaryDirectory(prefix='convert-', dir=output) as scratch:
            stage = Path(scratch) / 'model'
            TransformersConverter(str(source), low_cpu_mem_usage=True).convert(
                str(stage), quantization=spec['quantization'], force=True)
            for item in info['files']:
                name = item['name']
                path = stage / name
                if not path.exists() and valid(source / name, item):
                    shutil.copyfile(source / name, path)
                if not valid(path, item):
                    raise RuntimeError(f'Conversion differs from selected checkpoint: {model_id}/{name}')
            for item in info['files']:
                (stage / item['name']).replace(destination / item['name'])
        if not keep_source:
            for item in spec['source_files']:
                if item['name'] in ('model.safetensors', 'pytorch_model.bin'):
                    path = source / item['name']
                    if not path.resolve().is_relative_to(source_root.resolve()):
                        raise RuntimeError('Invalid source cleanup target.')
                    path.unlink()
    else:
        from language_lens.services import translation_assets as assets
        for item in info['files']:
            path = destination / item['name']
            if valid(path, item):
                continue
            # Reuse already staged resources, including the original T5 pack.
            candidates = [assets.local_file(model_id, item),
                          ROOT / 'build/translation-en-nl-reproduced' / model_id / item['name'],
                          ROOT / 'build/translation-en-nl-models' / model_id / item['name']]
            existing = next((p for p in candidates if p and valid(p, item)), None)
            if existing:
                if existing.resolve() != path.resolve():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(existing, path)
                continue
            if not item.get('url'):
                raise RuntimeError(f'An existing verified pack is required: {model_id}/{item["name"]}')
            packed = path.with_name(path.name + '.download')
            download({'url': item['url'], 'bytes': item['compressed_bytes'],
                      'sha256': item['compressed_sha256']}, packed)
            if item['compression'] == 'none':
                packed.replace(path)
            else:
                temporary = path.with_name(path.name + '.decoded')
                assets._decompress(packed, temporary, item)
                if not valid(temporary, item):
                    raise RuntimeError('Decoded model checksum mismatch.')
                temporary.replace(path)
                packed.unlink()
    assert all(valid(destination / i['name'], i) for i in info['files'])
    print(model_id + ': selected production resources verified', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--models', nargs='+', required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'src/language_lens/_translation_assets/providers')
    parser.add_argument('--source', type=Path, default=ROOT / 'build/native-translation-sources')
    parser.add_argument('--keep-source', action='store_true')
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'src/language_lens/data/translation-providers.json').read_text('utf-8'))
    if any(m not in catalog['models'] for m in args.models):
        parser.error('Unknown model identifier.')
    args.output.mkdir(parents=True, exist_ok=True)
    for model in dict.fromkeys(args.models):
        build(catalog, model, args.source, args.output, args.keep_source)
    shutil.copyfile(ROOT / 'THIRD_PARTY_TRANSLATION.md', args.output / 'THIRD_PARTY_TRANSLATION.md')


if __name__ == '__main__':
    main()
