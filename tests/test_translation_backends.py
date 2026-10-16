from types import SimpleNamespace
import pytest
from language_lens.domain import WordTranslation
from language_lens.services import translation_assets as assets, translation_backends as backends

def test_only_benchmarked_pair_function_exceptions_are_routed():
    assert len(assets.catalog()['full_text'])==25 and len(assets.catalog()['words'])==6
    assert assets.selection('pt','en')=={'full':None,'word':None}
    assert assets.selection('en','nl')=={'full':{'model':'t5-en-nl-24l','pivot':None},'word':None}
    assert assets.selection('nl','en')=={'full':None,'word':None}
    assert assets.selection('pb','en')=={'full':None,'word':None}
    assert assets.selection('ko','nl')['full'] is None
    assert assets.selection('ko','nl')['word']=='small'
    assert assets.selection('tr','nl')['full']=={'model':'tr-en-tiny-3.0','pivot':'nl'}
    assert assets.selection('en','en')=={'full':None,'word':None}

def test_full_text_and_words_use_separate_providers_and_reuse_models(monkeypatch):
    calls=[];constructed=[]
    class Firefox:
        def __init__(self,model):constructed.append(model)
        def translate(self,text):calls.append(('firefox',text));return 'intermediate'
        def close(self):pass
    class Word:
        def __init__(self,kind):constructed.append(kind)
        def candidates(self,text,source,target,expanded):
            calls.append(('word',text,source,target,expanded));return WordTranslation(('meaning',))
    monkeypatch.setattr(backends,'FirefoxModel',Firefox);monkeypatch.setattr(backends,'WordModel',Word)
    translator=backends.RoutedTranslator()
    translator.argos=SimpleNamespace(translate=lambda text,s,t:calls.append(('argos',text,s,t)) or 'final',
        word_candidates=lambda text,s,t,**kw:WordTranslation(('Argos',)))
    assert translator.translate('full text','tr','nl')=='final'
    assert calls[-2:]==[('firefox','full text'),('argos','intermediate','en','nl')]
    assert translator.word_candidates('isolated','tr','nl').candidates==('Argos',)
    translator.word_candidates('isolated','en','ja',expanded=False)
    translator.word_candidates('another','en','ja',expanded=True)
    assert constructed.count('m2m')==1
    assert calls[-1]==('word','another','en','ja',True)
    translator.close()

def test_selected_models_have_complete_fixed_download_integrity_metadata():
    for model in assets.catalog()['models'].values():
        for file in model['files']:
            assert file['bytes']>0 and len(file['sha256'])==64
            assert not file.get('bundled')
            assert file['url'].startswith('https://') and len(file['compressed_sha256'])==64
            assert file['compressed_bytes']>0 and file['compression']=='zstd'
    assert all(m['license']=='MPL-2.0' for m in assets.catalog()['models'].values() if m['kind']=='firefox')

def test_full_text_decodes_all_sentences_and_preserves_paragraphs(monkeypatch):
    from language_lens.services import sentence_models
    monkeypatch.setattr(sentence_models,'split',lambda text,language:[s for s in text.split('|') if s])
    model=backends.FirefoxModel.__new__(backends.FirefoxModel);model.source='hi'
    model.call=lambda command,**kw:kw['text'].upper()
    assert model.translate('first|second\n\nthird|last')=='FIRST SECOND\n\nTHIRD LAST'


def test_dutch_full_text_uses_t5_but_word_lookup_and_reverse_keep_argos(monkeypatch):
    constructed=[]
    class T5:
        def __init__(self,model):constructed.append(model)
        def translate(self,text):return 'Dutch '+text
        def close(self):constructed.append('closed')
    monkeypatch.setattr(backends,'T5Model',T5)
    translator=backends.RoutedTranslator()
    translator.argos=SimpleNamespace(translate=lambda text,s,t:'Argos '+text,
        word_candidates=lambda text,s,t,**kw:WordTranslation(('Argos word',)))
    assert translator.translate('first','en','nl')=='Dutch first'
    assert translator.translate('second','en','nl')=='Dutch second'
    assert translator.word_candidates('Where','en','nl').candidates==('Argos word',)
    assert translator.translate('reverse','nl','en')=='Argos reverse'
    assert translator.argos_required('en','nl')  # Still needed for independent words.
    assert constructed==['t5-en-nl-24l']
    translator.close()
    assert constructed[-1]=='closed'


def test_t5_matches_benchmark_prefix_unknown_tokens_and_line_decoding(monkeypatch):
    from language_lens.services import sentence_models
    monkeypatch.setattr(sentence_models,'split',lambda text,language:text.split('|'))
    seen=[];decoded=[]
    class Tokenizer:
        def encode(self,text):seen.append(text);return SimpleNamespace(tokens=['known','unmapped-glyph','</s>'])
        def decode(self,ids,**kw):
            decoded.append((ids,kw));return ' '.join(map(str,ids))
    class Backend:
        def translate_batch(self,batch,**kw):
            assert batch==[['known','<unk>','</s>']]
            assert kw==dict(beam_size=4,length_penalty=1,max_input_length=0,max_decoding_length=1024)
            return [SimpleNamespace(hypotheses=[['known']])]
    model=backends.T5Model.__new__(backends.T5Model)
    model.source='en';model.prefix='translate English to Dutch: '
    model.tokenizer=Tokenizer();model.vocab={'known':7,'<unk>':2,'</s>':1};model.backend=Backend()
    assert model.translate('first|second\n\nthird')=='7 7\n\n7'
    assert seen==[model.prefix+s for s in ('first','second','third')]
    assert decoded==[([7,7],{'skip_special_tokens':True}),([],{'skip_special_tokens':True}),([7],{'skip_special_tokens':True})]


@pytest.mark.parametrize('limit',['input','output'])
def test_t5_rejects_bounded_output_instead_of_publishing_truncated_translation(monkeypatch,limit):
    from language_lens.services import sentence_models
    monkeypatch.setattr(sentence_models,'split',lambda text,language:[text])
    model=backends.T5Model.__new__(backends.T5Model)
    model.source='en';model.prefix='prefix ';model.vocab={'<unk>':2,'token':3}
    model.tokenizer=SimpleNamespace(encode=lambda _:SimpleNamespace(tokens=['token']*(1025 if limit=='input' else 1)))
    def infer(*args,**kwargs):
        assert limit=='output', 'Oversized input must not reach inference.'
        return [SimpleNamespace(hypotheses=[['token']*1024])]
    model.backend=SimpleNamespace(translate_batch=infer)
    with pytest.raises(backends.TranslationUnavailable):model.translate('long selection')
