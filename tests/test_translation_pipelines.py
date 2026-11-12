"""Explicit repair chains prepare, identify and retain every selected component."""
import copy
import json
from types import SimpleNamespace

import pytest

from language_lens.config import Settings
from language_lens.services import translation_assets as assets, translation_backends as backends
from language_lens.services.errors import KnownTaskError


@pytest.mark.parametrize('pair,models', [
    ('fi-es', ['marian-gap-fi-en', 'marian-wave-opus-en-es']),
    ('hi-uk', ['hi-en-tiny-3.0', 'en-uk-base-memory-3.0']),
    ('nl-uk', ['t5-en-nl-24l', 'en-uk-base-memory-3.0']),
    ('ja-hu', ['m2m-full-m2m12b-native-int8-v1']),
])
def test_named_repairs_prepare_all_leaves_and_share_the_full_route_for_words(pair, models):
    source, target = pair.split('-')
    assert assets.model_ids(source, target) == models
    assert assets.selection(source, target)['word'] == 'full'
    assert not backends.RoutedTranslator().argos_required(source, target)
    assert not assets.supports_expansion(source, target)
    assert assets.sentence_languages(source, target) == ([source] if pair == 'ja-hu' else [source, 'en'])


def test_pipeline_runs_in_order_reuses_components_for_words_and_closes_them(monkeypatch):
    calls, created, closed = [], [], []
    class Native:
        def __init__(self, model):
            self.model = model; created.append(model)
        def translate(self, text, source, target, options):
            calls.append((self.model, text, source, target, options))
            return text + '/' + target
        def close(self):
            closed.append(self.model)
    from language_lens.services import native_translation
    monkeypatch.setattr(native_translation, 'NativeCT2Model', Native)
    translator = backends.RoutedTranslator()
    translator.argos = SimpleNamespace(translate=lambda *_: pytest.fail('Native repair must not use Argos'))
    assert translator.translate('sentence', 'fi', 'es') == 'sentence/en/es'
    assert [(x[1], x[2], x[3]) for x in calls] == [('sentence', 'fi', 'en'), ('sentence/en', 'en', 'es')]
    assert calls[0][4] == assets.full_steps('fi', 'es')[0]['options']
    assert translator.word_candidates('word', 'fi', 'es').candidates == ('word/en/es',)
    count = len(calls)
    assert translator.word_candidates('word', 'fi', 'es', expanded=True).candidates == ('word/en/es',)
    assert len(calls) == count  # More reuses the same scalar route/output.
    assert created == assets.model_ids('fi', 'es')
    translator.close()
    assert closed == created and not translator._full


def test_empty_intermediate_is_not_sent_to_second_decoder(monkeypatch):
    from language_lens.services import native_translation
    created = []
    class Native:
        def __init__(self, model): created.append(model)
        def translate(self, *_): return ' \n '
        def close(self): pass
    monkeypatch.setattr(native_translation, 'NativeCT2Model', Native)
    translator = backends.RoutedTranslator()
    with pytest.raises(backends.TranslationUnavailable):
        translator.translate('text', 'fi', 'es')
    assert created == ['marian-gap-fi-en']
    translator.close()


@pytest.mark.parametrize('damage', ['start', 'join', 'end', 'model', 'pivot'])
def test_pipeline_rejects_broken_explicit_configuration_before_loading(monkeypatch, damage):
    catalog = copy.deepcopy(assets.catalog())
    pipeline = catalog['full_text']['fi-es']['pipeline']
    if damage == 'start': pipeline[0]['source'] = 'de'
    elif damage == 'join': pipeline[1]['source'] = 'fr'
    elif damage == 'end': pipeline[1]['target'] = 'it'
    elif damage == 'model': pipeline[1]['model'] = 'unknown'
    else: pipeline[0]['pivot'] = 'fr'
    monkeypatch.setattr(assets, 'catalog', lambda: catalog)
    with pytest.raises(KnownTaskError, match='runtime'):
        assets.model_ids('fi', 'es')


def test_identity_covers_second_model_and_intermediate_options(monkeypatch):
    catalog = copy.deepcopy(assets.catalog())
    monkeypatch.setattr(assets, 'catalog', lambda: catalog)
    original = copy.deepcopy(assets.identity('fi', 'es'))
    catalog['models']['marian-wave-opus-en-es']['files'][0]['sha256'] = '0' * 64
    assert assets.identity('fi', 'es')['models_sha256'] != original['models_sha256']
    catalog['full_text']['fi-es']['pipeline'][1]['options']['prefix'] = 'new-prefix'
    assert assets.identity('fi', 'es')['full'] != original['full']


def test_prepare_and_preview_require_second_model_and_intermediate_splitter(monkeypatch, tmp_path):
    from language_lens.services import local_files, offline, sentence_models
    monkeypatch.setattr(assets, 'settings_path', lambda: tmp_path/'settings.json')
    monkeypatch.setattr(sentence_models, 'model_root', lambda: tmp_path/'sentences')
    monkeypatch.setattr(offline, 'ocr_models', lambda _: [])
    monkeypatch.setattr(assets, 'local_file', lambda *_: None)
    assert not assets.ready('fi', 'es')
    paths = assets.required_files('fi', 'es')
    assert {p.parent.name for p, _ in paths} == set(assets.model_ids('fi', 'es'))
    # First decoder present still cannot make a two-decoder route ready.
    monkeypatch.setattr(assets, 'valid', lambda p, _: 'marian-gap-fi-en' in p.parts)
    assert not assets.ready('fi', 'es')
    summary = local_files.pair_file_summary(Settings(source_language='fi', target_language='es'),
        SimpleNamespace(argos_required=lambda *_: False), [])
    assert {r['name'] for r in summary['files']} == {
        'marian-gap-fi-en', 'marian-wave-opus-en-es', 'fi · MiniSBD', 'en · MiniSBD'}


def test_prepared_pipeline_marker_cannot_omit_intermediate_splitter(monkeypatch, tmp_path, offline_record):
    from language_lens.services import offline, sentence_models
    monkeypatch.setattr(offline, 'assets_root', lambda: tmp_path)
    asset = tmp_path/'weights'; asset.write_bytes(b'verified')
    record = offline_record('fi', 'es', asset)
    record['sentence_models'] = sentence_models.identities(['fi', 'en'])
    marker = offline.marker_path('fi', 'es')
    marker.write_text(json.dumps(record), encoding='utf-8')
    assert offline.offline_ready('fi', 'es')
    record['sentence_models'] = sentence_models.identities(['fi'])
    marker.write_text(json.dumps(record), encoding='utf-8')
    assert not offline.offline_ready('fi', 'es')


def test_status_shows_native_intermediate_without_loading_argos(monkeypatch, tmp_path):
    from dataclasses import asdict
    from language_lens.services import language_packs, local_files, offline, task_worker
    monkeypatch.setattr(assets, 'ready', lambda *_: True)
    monkeypatch.setattr(offline, 'offline_ready', lambda *_a, **_kw: True)
    monkeypatch.setattr(language_packs, 'inventory', lambda: [])
    monkeypatch.setattr(local_files, 'pair_file_summary', lambda *_: {})
    def forbidden(*_): pytest.fail('Native status must not load Argos')
    monkeypatch.setattr(backends.RoutedTranslator, '_modules', forbidden)
    events = []
    task_worker.execute('status', {'settings': asdict(Settings(source_language='hi', target_language='uk'))},
        tmp_path, events.append)
    assert events[-1]['result']['route'] == ['hi', 'en', 'uk']
    assert events[-1]['result']['ready'] and events[-1]['result']['prepared']
