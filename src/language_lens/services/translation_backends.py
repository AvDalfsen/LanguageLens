"""Local provider routing with one loaded instance of each active backend."""
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import unicodedata

from language_lens.domain import WordTranslation
from language_lens.services import translation_assets as assets
from language_lens.services.errors import KnownTaskError
from language_lens.services.translation import TranslationUnavailable


class WordModel:
    def __init__(self,kind):
        import ctranslate2
        import sentencepiece
        self.kind=kind;directory=assets.verified_model(kind)
        self.tokenizer=sentencepiece.SentencePieceProcessor(model_proto=(directory/'sentencepiece.bpe.model').read_bytes())
        self.vocab=set(json.loads((directory/'shared_vocabulary.json').read_text('utf-8')))
        self.backend=ctranslate2.Translator(str(directory),device='cpu',intra_threads=2,inter_threads=1,compute_type='auto')

    def candidates(self,text,source,target,expanded):
        from language_lens.services.sentence_models import split
        if 'pb' in (source,target):raise TranslationUnavailable('Unsupported Portuguese variety.')
        source_code='no' if source=='nb' else source;target_code='no' if target=='nb' else target
        if any('__'+c+'__' not in self.vocab for c in (source_code,target_code)):
            raise TranslationUnavailable('Unsupported local language.')
        units=split(text,source); n=12 if expanded else 5
        inputs=[]
        for unit in units:
            pieces=[p if p in self.vocab else '<unk>' for p in self.tokenizer.encode(unit,out_type=str)]
            inputs.append(['__'+(target_code if self.kind=='small' else source_code)+'__',*pieces,'</s>'])
        if not inputs or any(len(tokens)>1024 for tokens in inputs):raise TranslationUnavailable('Lookup is too long.')
        prefix=[['__'+target_code+'__'] for _ in inputs] if self.kind=='m2m' else None
        results=self.backend.translate_batch(inputs,target_prefix=prefix,beam_size=max(4,n),num_hypotheses=n,
            length_penalty=.2,return_scores=True,max_input_length=1024,max_decoding_length=256,max_batch_size=32,batch_type='tokens')
        if any(len(h)>=256 for r in results for h in r.hypotheses):raise TranslationUnavailable('Output limit reached.')
        guesses=[]
        for i in range(n):
            pieces=[p for r in results for p in r.hypotheses[i] if p not in {'<s>','</s>','<unk>','<pad>'} and not(p.startswith('__') and p.endswith('__'))]
            value=self.tokenizer.decode_pieces(pieces).replace('▁',' ').strip()
            value=' '.join(unicodedata.normalize('NFC',value).split());score=sum(r.scores[i] for r in results)
            if value and math.isfinite(score):guesses.append((value,score))
        seen=set();values=[]
        for value,_ in sorted(guesses,key=lambda v:v[1],reverse=True):
            key=value.strip(' \t.,;:!?…。！？"\'“”‘’«»')
            if key and key not in seen:seen.add(key);values.append(value)
        if not values:raise TranslationUnavailable('No usable word alternatives.')
        return WordTranslation(tuple(values if expanded else values[:4]))


class FirefoxModel:
    def __init__(self,model_id):
        directory=assets.verified_model(model_id);model=assets.catalog()['models'][model_id]
        self.source=model['source']
        root=assets.root();info=assets.catalog()
        for kind in ('node_runtime','bergamot_runtime'):
            if not all(assets.valid(root/kind/item['name'],item) for item in info[kind]['files']):raise KnownTaskError('missing_assets')
        script=Path(__file__).with_name('bergamot_host.cjs')
        args=[str(root/'node_runtime/node.exe'),'--preserve-symlinks-main','--preserve-symlinks',str(script),
            str(root/'bergamot_runtime'),str(directory),model['source'],model['target']]
        self.messages=queue.Queue();self.serial=0
        environment=os.environ.copy()
        for key in ('NODE_OPTIONS','NODE_PATH'):environment.pop(key,None)
        self.process=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=environment,
            text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        from language_lens.services.worker_children import own_child
        self._ownership=own_child(self.process)
        def read():
            try:
                for line in self.process.stdout:
                    if len(line)>8*1024*1024:break
                    try:self.messages.put(json.loads(line))
                    except ValueError:break
            finally:self.messages.put(None)
        threading.Thread(target=read,daemon=True).start()
        try:
            ready=self.messages.get(timeout=60)
            if not ready or not ready.get('ready'):raise KnownTaskError('runtime')
        except BaseException:
            self.close();raise

    def call(self,command,**data):
        self.serial+=1
        self.process.stdin.write(json.dumps({'id':self.serial,'command':command,**data},ensure_ascii=True)+'\n');self.process.stdin.flush()
        result=self.messages.get(timeout=30)
        if not result or result.get('id')!=self.serial or not result.get('ok'):raise TranslationUnavailable('Local translation failed.')
        return result['value']

    def translate(self,text):
        # Decode bounded sentences separately. The WASM decoder can omit parts of
        # multi-sentence Hindi/Korean inputs when passed an entire paragraph.
        from language_lens.services.sentence_models import split
        return '\n'.join(' '.join(self.call('translate',text=unit).strip() for unit in split(line,self.source))
                         for line in text.split('\n'))
    def close(self):
        if self.process.poll() is None:
            try:self.process.stdin.close();self.process.wait(timeout=1)
            except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait(timeout=2)
        for handle in (self.process.stdin,self.process.stdout):
            if handle and not handle.closed:handle.close()
        if getattr(self,'_ownership',None):self._ownership.close()


class RoutedTranslator:
    def __init__(self):
        from language_lens.services.translation import ArgosTranslator
        self.argos=ArgosTranslator();self._full={};self._words={}

    def _modules(self):return self.argos._modules()
    def argos_required(self,source,target):
        choice=assets.selection(source,target)
        return source!=target and (not choice['full'] or not choice['word'] or choice['full'].get('pivot'))

    def route(self,source,target):return self.argos.route(source,target) if self.argos_required(source,target) else []
    def is_pair_installed(self,source,target):
        return assets.ready(source,target) and (not self.argos_required(source,target) or self.argos.is_pair_installed(source,target))

    def install_pair(self,source,target,report=None,progress=None,*,staged=False,force=False):
        if self.argos_required(source,target):self.argos.install_pair(source,target,report,progress,staged=staged,force=force)
        assets.prepare(source,target,report or (lambda _:None),progress or (lambda _:None),force=force)

    @lru_cache(maxsize=4096)
    def translate(self,text,source,target):
        if not text or source==target:return text
        choice=assets.selection(source,target)['full']
        if choice is None:return self.argos.translate(text,source,target)
        model=self._full.get(choice['model'])
        if model is None:model=self._full.setdefault(choice['model'],FirefoxModel(choice['model']))
        result=model.translate(text)
        if choice.get('pivot'):result=self.argos.translate(result,'en',target)
        if not result.strip():raise TranslationUnavailable('No usable full translation.')
        return result.strip()

    @lru_cache(maxsize=4096)
    def word_candidates(self,text,source,target,*,expanded=False):
        if not text or source==target:return self.argos.word_candidates(text,source,target,**({'expanded':True} if expanded else {}))
        kind=assets.selection(source,target)['word']
        if kind is None:return self.argos.word_candidates(text,source,target,**({'expanded':True} if expanded else {}))
        model=self._words.get(kind)
        if model is None:model=self._words.setdefault(kind,WordModel(kind))
        return model.candidates(text,source,target,expanded)

    def close(self):
        for model in self._full.values():model.close()
        self._full.clear();self._words.clear()
        self.translate.cache_clear();self.word_candidates.cache_clear()

    def inspect(self):
        def backends(item):
            if hasattr(item,'underlying'):return backends(item.underlying)
            if hasattr(item,'t1'):return backends(item.t1)+backends(item.t2)
            return [item.translator] if getattr(item,'translator',None) is not None else []
        values=[]
        try:
            _package,module=self.argos._modules()
            for value in module.installed_translates:values.extend(backends(value))
        except ImportError:pass
        return {'pid':os.getpid(),'argos':[{'object_id':id(value),'loaded':value.model_is_loaded} for value in dict.fromkeys(values)],
            'words':{kind:{'object_id':id(model.backend),'loaded':model.backend.model_is_loaded} for kind,model in self._words.items()},
            'firefox':{kind:model.call('inspect') for kind,model in self._full.items()}}
