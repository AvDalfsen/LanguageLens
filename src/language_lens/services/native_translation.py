"""Pinned CPU translation frontends shared by sentence and scalar word calls."""
import http.client
import json
import os
import secrets
import socket
import subprocess
import time

from language_lens.services import translation_assets as assets
from language_lens.services.errors import KnownTaskError
from language_lens.services.translation import TranslationUnavailable


def repair_latin_boundaries(text, units):
    """The tested Turkish repair: join only a split inside a Latin word."""
    import unicodedata
    def latin(c):
        return c.isalpha() and 'LATIN' in unicodedata.name(c, '')
    result, cursor = [], 0
    for unit in units:
        start = text.find(unit, cursor)
        if not unit or start < cursor:
            raise TranslationUnavailable('Invalid sentence boundary.')
        if result and start == cursor and latin(result[-1][-1]) and latin(unit[0]):
            result[-1] += unit
        else:
            result.append(unit)
        cursor = start + len(unit)
    if ''.join(''.join(result).split()) != ''.join(text.split()):
        raise TranslationUnavailable('Sentence boundary lost source text.')
    return result


class NativeCT2Model:
    def __init__(self, model_id):
        import ctranslate2
        import sentencepiece
        self.info = assets.catalog()['models'][model_id]
        self.directory = assets.verified_model(model_id)
        self.kind = self.info['kind']
        self.vocab = set(json.loads((self.directory / self.info['vocabulary']).read_text('utf-8')))
        self.source_sp = sentencepiece.SentencePieceProcessor(
            model_file=str(self.directory / self.info['source_tokenizer']))
        self.target_sp = sentencepiece.SentencePieceProcessor(
            model_file=str(self.directory / self.info['target_tokenizer']))
        self.encoder = set(json.loads((self.directory / self.info['encoder']).read_text('utf-8'))) if self.kind == 'm2m_full' else self.vocab
        self.special = {'<s>', '</s>', '<unk>', '<pad>'}
        if self.kind == 'm2m_full':
            self.special |= {p for p in self.vocab if p.startswith('__') and p.endswith('__')}
        self.normalizer = None
        if self.kind == 'marian':
            from sacremoses import MosesPunctNormalizer
            self.normalizer = MosesPunctNormalizer(self.info['normalizer_language']).normalize
        self.backend = ctranslate2.Translator(str(self.directory), device='cpu',
            compute_type='int8_float32', intra_threads=2, inter_threads=1)
        self.last_units = []

    def translate(self, text, source, target, options):
        from language_lens.services.sentence_models import split
        lines = []; self.last_units = []
        for line in text.split('\n'):
            units = split(line, source) if line.strip() else []
            if options.get('repair_latin_boundaries'):
                units = repair_latin_boundaries(line, units)
            joined = []
            for unit in units:
                body = self.normalizer(unit) if self.normalizer is not None and options.get('normalize') and unit else unit
                pieces = self.source_sp.encode(body, out_type=str)
                if self.kind == 'm2m_full':
                    source_tag = '__' + {'nb':'no','pb':'pt'}.get(source, source) + '__'
                    target_tag = '__' + {'nb':'no','pb':'pt'}.get(target, target) + '__'
                    if source_tag not in self.vocab or target_tag not in self.vocab:
                        raise TranslationUnavailable('Unsupported native direction.')
                    tokens = [source_tag] + [p if p in self.encoder else '<unk>' for p in pieces] + ['</s>']
                    target_prefix = [[target_tag]]
                else:
                    prefix = options.get('prefix', '').strip()
                    if prefix and prefix not in self.vocab:
                        raise TranslationUnavailable('Unsupported native target tag.')
                    tokens = [p if p in self.vocab else '<unk>' for p in ([prefix] if prefix else []) + pieces + ['</s>']]
                    target_prefix = None
                if len(tokens) > options['input_bound']:
                    raise TranslationUnavailable('Translation input limit reached.')
                kwargs = dict(beam_size=4, length_penalty=1, max_input_length=0,
                              max_decoding_length=options['output_bound'])
                if target_prefix: kwargs['target_prefix'] = target_prefix
                if options.get('require_eos'): kwargs['return_end_token'] = True
                if options.get('disable_unk'): kwargs['disable_unk'] = True
                out = self.backend.translate_batch([tokens], **kwargs)[0].hypotheses[0]
                self.last_units.append({'source':unit, 'input_tokens':tokens, 'output_tokens':out})
                if (len(out) >= options['output_bound'] or
                    (options.get('require_eos') and (not out or out[-1] != '</s>')) or
                    (target_prefix and (not out or out[0] != target_prefix[0][0]))):
                    raise TranslationUnavailable('Translation output limit reached or incomplete output.')
                joined.extend(out)
            lines.append(self.target_sp.decode([p for p in joined if p not in self.special]).replace('▁',' ').strip())
        return '\n'.join(lines)

    def close(self):
        self.backend.unload_model()


class HyModel:
    """Owned loopback llama.cpp server; external capture networking stays blocked."""
    def __init__(self, model_id):
        from language_lens.services.worker_children import own_child
        self.info = assets.catalog()['models'][model_id]
        directory = assets.verified_model(model_id)
        self.process = self.ownership = None
        self.key = secrets.token_hex(24)
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            self.port = reserve.getsockname()[1]
        exe = directory / self.info['runtime_executable']
        args = [str(exe), '-m', str(directory / self.info['weights']), '--host', '127.0.0.1',
                '--port', str(self.port), '--api-key', self.key, '-ngl','0','-t','2','-tb','2',
                '-c','8192','-np','1','--no-warmup','--no-webui','--no-context-shift']
        try:
            self.process = subprocess.Popen(args, cwd=exe.parent, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.ownership = own_child(self.process)
            deadline = time.monotonic() + 120
            while True:
                if self.process.poll() is not None: raise KnownTaskError('runtime')
                try:
                    if self.request('/health', timeout=.5).get('status') == 'ok': break
                except (OSError, TimeoutError, http.client.HTTPException): pass
                if time.monotonic() > deadline: raise TimeoutError('Local model startup timeout.')
                time.sleep(.05)
        except BaseException:
            self.close()
            raise

    def request(self, path, value=None, *, timeout=180):
        from language_lens.services.offline import connect_owned_loopback
        if path not in ('/health','/tokenize','/completion') or self.process.poll() is not None:
            raise KnownTaskError('runtime')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        connection._create_connection = lambda address, timeout, source_address=None: connect_owned_loopback(
            self.process, self.port, address, timeout, source_address)
        try:
            body = json.dumps(value, ensure_ascii=False).encode('utf-8') if value is not None else None
            connection.request('POST' if body is not None else 'GET', path, body,
                {'Content-Type':'application/json', 'Authorization':'Bearer '+self.key})
            response = connection.getresponse()
            data = response.read(16 * 1024 * 1024 + 1)
            if path == '/health' and response.status == 503:
                return {'status':'loading'}
            if response.status != 200 or len(data) > 16 * 1024 * 1024: raise KnownTaskError('runtime')
            return json.loads(data)
        finally:
            connection.close()

    @staticmethod
    def prompt(text, target_name):
        return ('<｜hy_begin▁of▁sentence｜><｜hy_User｜>Translate the following text into ' + target_name +
                '. Note that you should only output the translated result without any additional explanation:\n' +
                text + '<｜hy_Assistant｜>')

    def translate(self, text, source, target, options):
        prompt = self.prompt(text, options['target_name'])
        ids = self.request('/tokenize', {'content':prompt,'add_special':False})['tokens']
        if len(ids) + 4096 > 8192: raise TranslationUnavailable('Translation input limit reached.')
        params = {'prompt':ids,'n_predict':4096,'cache_prompt':False,'return_tokens':True,'stream':False,
                  'seed':123,'min_p':0,'typical_p':1,'presence_penalty':0,'frequency_penalty':0,'ignore_eos':False,
                  **options['decoding']}
        raw = self.request('/completion', params)
        if (raw.get('stop_type') != 'eos' or raw.get('truncated',False) or
            raw['timings']['cache_n'] != 0 or raw['timings']['prompt_n'] != len(ids)):
            raise TranslationUnavailable('Incomplete native translation.')
        return raw['content'].strip()

    def close(self):
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill(); self.process.wait(timeout=3)
        finally:
            if self.ownership: self.ownership.close(); self.ownership = None
