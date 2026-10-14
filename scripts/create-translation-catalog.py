"""Freeze the accepted benchmark choices as a portable production catalogue."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / 'artifacts/translation-cross-language-2026-10-13'
OLD = ROOT / 'artifacts/translation-accuracy-2026-10-12/execution-v1'
OUT = ROOT / 'src/language_lens/data/translation-providers.json'

def read(path):return json.loads(path.read_text('utf-8'))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    previous=read(OUT)
    selected=read(BENCH/'best-effort-selection/best-effort-model-selections.json')
    models={}; full={}; words={}
    for item in selected['full_text_exceptions']:
        source,target=item['source'],item['target']; hybrid=item['architecture'].endswith('Argos pivot')
        model_id='tr-en-tiny-3.0' if hybrid else item['model_id']
        full[source+'-'+target]={'model':model_id, 'pivot':target if hybrid else None}
        if model_id in models:continue
        receipt=read(BENCH/'best-effort-selection/model-receipts'/(model_id+'.json'))
        m=receipt['model']; files=[]
        for r in m['records']:
            a=r['attachment']
            files.append({'name':r['name'],'bytes':r['decompressedSize'],'sha256':r['decompressedHash'],
                'url':'https://firefox-settings-attachments.cdn.mozilla.net/'+a['location'],
                'compressed_bytes':a['size'],'compressed_sha256':a['hash'],'compression':'zstd','role':r['fileType']})
        models[model_id]={'kind':'firefox','source':m['source'],'target':m['target'],
            'architecture':m['architecture'],'files':files,'license':'MPL-2.0',
            'publisher':'https://mozilla.github.io/translations/firefox-models/'}
    for item in selected['word_exceptions']:
        kind=item['provider'];words[item['source']+'-'+item['target']]=kind
        if kind in models:continue
        if kind=='small':
            receipt=read(BENCH/'receipts/alirezamsh--small100-conversion.json')
            revision=receipt['source']['revision']; repo=receipt['source']['model']
            files=[{'name':Path(f['path']).name,'bytes':f['bytes'],'sha256':f['sha256']} for f in receipt['files']]
            tokenizer=BENCH/'downloads/alirezamsh--small100/sentencepiece.bpe.model'
            sources=[{'name':Path(f['path']).name,'bytes':f['bytes'],'sha256':f['sha256']} for f in receipt['source']['files']]
        else:
            receipt=read(OLD/'models/m2m100_418M-conversion.json');revision=receipt['revision'];repo=receipt['model']
            files=[{'name':name,'bytes':(OLD/'models/m2m100_418M-ct2-int8'/name).stat().st_size,'sha256':value} for name,value in receipt['converted_files'].items()]
            tokenizer=OLD/'downloads/m2m100_418M/sentencepiece.bpe.model'
            sources=[{'name':f['name'],'bytes':f['bytes'],'sha256':f['sha256']} for f in receipt['source_files']]
        files.append({'name':'sentencepiece.bpe.model','bytes':tokenizer.stat().st_size,'sha256':digest(tokenizer)})
        downloads={f['name']:f for f in previous['models'][kind]['files']}
        for file in files:
            pinned=downloads[file['name']]
            if any(file[key]!=pinned[key] for key in ('bytes','sha256')):
                raise RuntimeError('Changed word weights require a new packaged, pinned model release.')
            file.update({key:pinned[key] for key in ('url','compression','compressed_bytes','compressed_sha256')})
        models[kind]={'kind':kind,'files':files,'license':'MIT','repo':repo,'revision':revision,
            'source_files':sources,'publisher':'https://huggingface.co/'+repo}
    backend=ROOT/'artifacts/translation-production-integration-2026-10-13/backend'
    runtime=[{'name':name,'bytes':(backend/name).stat().st_size,'sha256':digest(backend/name)} for name in
        ['translator-worker.js','bergamot-translator-worker.js','bergamot-translator-worker.wasm']]
    package=read(backend/'package-receipt.json')
    catalog={'version':'2026-10-13-v1','default':'argos','full_text':full,'words':words,'models':models,
        'bergamot_runtime':{'url':package['publisher']['dist']['tarball'],'sha256':package['tar_sha256'],'files':runtime,
            'license':'MPL-2.0','publisher':'https://github.com/browsermt/bergamot-translator'},
        'node_runtime':read(backend/'node-receipt.json'),
        'word_model_release':previous['word_model_release']}
    OUT.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n','utf-8')
    print({'full_text_routes':len(full),'word_routes':len(words),'model_assets':len(models)})

if __name__=='__main__':main()
