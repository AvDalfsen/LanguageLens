import json
from types import SimpleNamespace

import pytest

from language_lens.domain import WordTranslation
from language_lens.services import translation_assets as assets, translation_backends as backends, offline
from language_lens.services.native_translation import NativeCT2Model, HyModel, repair_latin_boundaries
from language_lens.services.translation import TranslationUnavailable


def test_sentence_word_and_more_share_one_native_model(monkeypatch):
    from language_lens.services import native_translation
    made=[];calls=[];closed=[]
    class Native:
        def __init__(self,model):made.append(model)
        def translate(self,text,source,target,options):
            calls.append((text,source,target,options['prefix']))
            return f'{target}:{text}'
        def close(self):closed.append(True)
    monkeypatch.setattr(native_translation,'NativeCT2Model',Native)
    translator=backends.RoutedTranslator()
    translator.argos=SimpleNamespace(word_candidates=lambda *a,**kw:pytest.fail('Independent Argos word model used'))
    assert not translator.argos_required('da','nb')
    assert translator.translate('sentence','da','nb')=='nb:sentence'
    assert translator.word_candidates('word','da','nb')==WordTranslation(('nb:word',))
    assert translator.word_candidates('word','da','nb',expanded=True)==WordTranslation(('nb:word',))
    assert len(calls)==2  # More reuses the same scalar result, not another model/search.
    assert translator.translate('sentence','da','sv')=='sv:sentence'
    assert calls[-1][-1]=='>>swe<<' and calls[0][-1]=='>>nob<<'
    assert len(made)==1
    translator.close();assert closed==[True]


def native(monkeypatch, *, kind='marian', output=None):
    from language_lens.services import sentence_models
    monkeypatch.setattr(sentence_models,'split',lambda text,source:text.split('|'))
    model=NativeCT2Model.__new__(NativeCT2Model)
    model.kind=kind;model.vocab={'>>nob<<','word','WORD','</s>','__zh__','__ja__'}
    model.encoder={'word'};model.special={'<unk>','</s>','__ja__','__zh__'}
    model.source_sp=SimpleNamespace(encode=lambda text,**kw:text.split())
    model.target_sp=SimpleNamespace(decode=lambda tokens:' '.join(tokens))
    model.normalizer=str.upper if kind=='marian' else None
    seen=[]
    def translate(batch,**kwargs):
        seen.append((batch,kwargs))
        return [SimpleNamespace(hypotheses=[output if output is not None else ['word','</s>']])]
    model.backend=SimpleNamespace(translate_batch=translate)
    return model,seen


def test_marian_normalization_tags_unknowns_and_paragraphs(monkeypatch):
    model,seen=native(monkeypatch)
    options=dict(prefix='>>nob<<',normalize=True,input_bound=8,output_bound=8,require_eos=True)
    assert model.translate('word missing|word\n\nword','da','nb',options)=='word word\n\nword'
    assert seen[0][0]==[['>>nob<<','WORD','<unk>','</s>']]
    assert seen[0][1]['max_input_length']==0
    assert seen[0][1]['beam_size']==4 and seen[0][1]['length_penalty']==1
    assert seen[0][1]['return_end_token'] is True


@pytest.mark.parametrize('output',[['word'] , ['word']*8])
def test_incomplete_or_bounded_output_is_not_published(monkeypatch,output):
    model,_=native(monkeypatch,output=output)
    with pytest.raises(TranslationUnavailable):
        model.translate('word','da','nb',dict(input_bound=8,output_bound=8,require_eos=True))


def test_input_limit_rejects_before_inference(monkeypatch):
    model,seen=native(monkeypatch)
    with pytest.raises(TranslationUnavailable):
        model.translate('word word word','da','nb',dict(input_bound=3,output_bound=8))
    assert not seen


def test_native_m2m_uses_source_and_target_tags_not_word_decoder(monkeypatch):
    model,seen=native(monkeypatch,kind='m2m_full',output=['__ja__','word','</s>'])
    assert model.translate('word','zh','ja',dict(input_bound=8,output_bound=8,require_eos=True))=='word'
    assert seen[0][0]==[['__zh__','word','</s>']]
    assert seen[0][1]['target_prefix']==[['__ja__']]
    assert seen[0][1]['beam_size']==4 and seen[0][1]['length_penalty']==1


def test_owned_transport_does_not_enable_capture_networking():
    process=SimpleNamespace(poll=lambda:None)
    with offline.no_network():
        import socket
        with pytest.raises(RuntimeError):socket.create_connection(('example.invalid',80))
        for address in [('example.invalid',80),('127.0.0.2',12345),('127.0.0.1',12346)]:
            with pytest.raises(RuntimeError):offline.connect_owned_loopback(process,12345,address,.1)
        with pytest.raises(RuntimeError):offline.connect_owned_loopback(SimpleNamespace(poll=lambda:0),12345,('127.0.0.1',12345),.1)


def test_turkish_boundary_repair_is_limited_to_contiguous_latin_letters():
    assert repair_latin_boundaries('merhaba dünya',['mer','haba','dünya'])==['merhaba','dünya']
    assert repair_latin_boundaries('a. b',['a.','b'])==['a.','b']
    with pytest.raises(TranslationUnavailable):repair_latin_boundaries('hello world',['hello'])


def test_hy_prompt_decoder_and_eos_are_pinned():
    model=HyModel.__new__(HyModel);seen=[]
    def request(path,value):
        seen.append((path,value))
        if path=='/tokenize':return {'tokens':[1,2]}
        return {'content':'result','stop_type':'eos','timings':{'cache_n':0,'prompt_n':2}}
    model.request=request
    decoding=dict(temperature=.7,top_p=.6,top_k=20,repeat_penalty=1.05)
    assert model.translate('source','fr','ja',dict(target_name='Japanese',decoding=decoding))=='result'
    assert seen[0][1]['content']==HyModel.prompt('source','Japanese')
    assert seen[1][1]['seed']==123 and seen[1][1]['cache_prompt'] is False
    assert seen[1][1]['prompt']==[1,2] and seen[1][1]['n_predict']==4096


def test_local_pack_prepares_shared_full_word_files_without_network(monkeypatch,tmp_path):
    import hashlib
    data=b'local converted weights';item={'name':'model.bin','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    pack=tmp_path/'pack';(pack/'test').mkdir(parents=True);(pack/'test/model.bin').write_bytes(data)
    cat={'version':'test','full_text':{'da-nb':{'model':'test'}},'words':{'da-nb':'full'},
         'models':{'test':{'kind':'marian','files':[item]}}}
    monkeypatch.setattr(assets,'catalog',lambda:cat)
    monkeypatch.setattr(assets,'settings_path',lambda:tmp_path/'profile/settings.json')
    monkeypatch.setattr(assets,'bundle_roots',lambda:[pack])
    monkeypatch.setattr(assets,'urlopen',lambda *a,**kw:pytest.fail('Local pack attempted a download'))
    assert assets.model_ids('da','nb')==['test']
    assert not assets.supports_expansion('da','nb')
    paths=assets.prepare('da','nb',lambda *_:None,lambda *_:None)
    assert len(paths)==1 and paths[0].read_bytes()==data and assets.ready('da','nb')
    previous=assets.identity('da','nb')
    cat['models']['test']['kind']='m2m_full'
    assert assets.identity('da','nb')!=previous
