"""Build pinned model resources for the separate translation-model releases.

Conversion runs only here, never in a capture process. Firefox weights and the
isolated runtime and word models download on demand by explicit file preparation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CATALOG=json.loads((ROOT/'src/language_lens/data/translation-providers.json').read_text('utf-8'))

def matches(path,item):
    if not path.is_file() or path.stat().st_size!=item['bytes']:return False
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()==item['sha256']

def download(url,path,item):
    if matches(path,item):return
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.part')
    try:
        count=0
        with urlopen(Request(url,headers={'User-Agent':'LanguageLens-model-builder'}),timeout=60) as source, temporary.open('wb') as target:
            while chunk:=source.read(1024*1024):
                count+=len(chunk)
                if count>item['bytes']:raise RuntimeError('Publisher file exceeds expected size.')
                target.write(chunk)
        if not matches(temporary,item):raise RuntimeError('Publisher checksum mismatch.')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reuse-benchmark',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'build/translation-word-models')
    parser.add_argument('--models',nargs='+',default=['small','m2m'],choices=['small','m2m','t5-en-nl-24l'])
    args=parser.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    for kind in args.models:
        model=CATALOG['models'][kind];destination=out/kind
        if all(matches(destination/item['name'],item) for item in model['files']):
            print(kind+': verified existing resources',flush=True);continue
        with tempfile.TemporaryDirectory(prefix='translation-model-',dir=out) as scratch:
            stage=Path(scratch)
            if args.reuse_benchmark:
                bench=ROOT/'artifacts/translation-cross-language-2026-10-13'
                old=ROOT/'artifacts/translation-accuracy-2026-10-12/execution-v1'
                source=bench/'models/alirezamsh--small100' if kind=='small' else old/'models/m2m100_418M-ct2-int8'
                tokenizer=bench/'downloads/alirezamsh--small100' if kind=='small' else old/'downloads/m2m100_418M'
                if kind=='t5-en-nl-24l':
                    pilot=ROOT/'artifacts/en-nl-specialist-research-2026-10-15'
                    source=pilot/'models/t5';tokenizer=pilot/'downloads/t5'
                for item in model['files']:
                    path=(tokenizer if item['name'] in ('sentencepiece.bpe.model','tokenizer.json') else source)/item['name']
                    if not matches(path,item):raise RuntimeError('Benchmark artifact is not the selected checkpoint.')
                    shutil.copyfile(path,stage/item['name'])
            else:
                source=ROOT/'build/translation-source-models'/kind
                for item in model['source_files']:
                    url='https://huggingface.co/'+model['repo']+'/resolve/'+model['revision']+'/'+item['name']
                    download(url,source/item['name'],item)
                from ctranslate2.converters import TransformersConverter
                TransformersConverter(str(source),low_cpu_mem_usage=True).convert(str(stage),quantization='int8',force=True)
                tokenizer_name='tokenizer.json' if model['kind']=='t5' else 'sentencepiece.bpe.model'
                shutil.copyfile(source/tokenizer_name,stage/tokenizer_name)
            if not all(matches(stage/item['name'],item) for item in model['files']):
                raise RuntimeError('Conversion does not match the benchmark. Use the pinned translation build requirements.')
            destination.mkdir(exist_ok=True)
            for item in model['files']:(stage/item['name']).replace(destination/item['name'])
        print(kind+': staged verified int8 resources',flush=True)

if __name__=='__main__':main()
