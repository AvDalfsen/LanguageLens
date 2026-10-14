from types import SimpleNamespace
from language_lens.domain import WordTranslation
from language_lens.services import translation_assets as assets, translation_backends as backends

def test_only_benchmarked_pair_function_exceptions_are_routed():
    assert len(assets.catalog()['full_text'])==24 and len(assets.catalog()['words'])==6
    assert assets.selection('pt','en')==assets.selection('en','nl')=={'full':None,'word':None}
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
