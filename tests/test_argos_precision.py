import hashlib
import sys
from types import SimpleNamespace

import pytest

from language_lens.services import argos_precision as precision
from language_lens.services import translation_assets as assets
from language_lens.services.translation import ArgosTranslator


@pytest.fixture
def package(tmp_path, monkeypatch):
    model = tmp_path / 'model/model.bin'
    model.parent.mkdir()
    model.write_bytes(b'pinned model')
    monkeypatch.setattr(precision, 'MODEL_SHA256', hashlib.sha256(model.read_bytes()).hexdigest())
    made = []
    def construct(path, **options):
        made.append((path, options))
        return SimpleNamespace(compute_type=options['compute_type'])
    monkeypatch.setitem(sys.modules, 'ctranslate2', SimpleNamespace(Translator=construct))
    value = SimpleNamespace(pkg=SimpleNamespace(from_code='es', to_code='en', package_version='1.9',
                                               package_path=tmp_path), translator=None)
    return value, made


def test_only_pinned_first_leg_is_repaired_and_cached_junk_is_discarded(package):
    first, made = package
    downstream = SimpleNamespace(pkg=SimpleNamespace(from_code='en', to_code='nl'), translator=None)
    cached = SimpleNamespace(underlying=first, cache={'source': 'old nonsense'})
    route = SimpleNamespace(t1=cached, t2=downstream)
    assert precision.prepare_translation(route)
    assert cached.cache == {} and downstream.translator is None
    assert made[0][1] == dict(device='cpu', inter_threads=1, intra_threads=2, compute_type='float32')
    cached.cache['source'] = 'new translation'
    assert not precision.prepare_translation(route)
    assert len(made) == 1 and cached.cache['source'] == 'new translation'


@pytest.mark.parametrize('field,value', [('from_code','fr'),('to_code','nl'),('package_version','2.0')])
def test_other_routes_and_versions_are_not_overridden(package, field, value):
    translation, made = package
    setattr(translation.pkg, field, value)
    assert not precision.prepare_translation(translation)
    assert not made


def test_same_version_with_different_weights_is_not_overridden(package):
    translation, made = package
    (translation.pkg.package_path / 'model/model.bin').write_bytes(b'different weights')
    assert not precision.prepare_translation(translation)
    assert not made


def test_previously_loaded_unhealthy_backend_is_replaced(package):
    translation, made = package
    unloaded = []
    translation.translator = SimpleNamespace(unload_model=lambda: unloaded.append(True))
    assert precision.prepare_translation(translation)
    assert unloaded == [True] and translation.translator.compute_type == 'float32'


def test_sentence_and_word_calls_both_prepare_the_repair(package, monkeypatch):
    translation, made = package
    translation.hypotheses = lambda *a, **k: [SimpleNamespace(value='word', score=0)]
    class Language:
        code = 'es'
        def get_translation(self, target): return translation
    backend = SimpleNamespace(get_installed_languages=lambda: [Language(), SimpleNamespace(code='en')],
                              get_translation_from_codes=lambda *a: translation,
                              translate=lambda *a: 'sentence' if translation.translator else pytest.fail('Unprepared model'))
    monkeypatch.setattr(ArgosTranslator, '_modules', staticmethod(lambda: (None, backend)))
    engine = ArgosTranslator()
    assert engine.word_candidates('word', 'es', 'en').candidates == ('word',)
    assert engine.translate('text', 'es', 'en') == 'sentence'
    assert len(made) == 1


def test_repair_policy_invalidates_only_relevant_argos_readiness_records():
    assert assets.identity('es', 'nl')['argos_precision'] == precision.POLICY_ID
    assert assets.identity('es', 'ja')['argos_precision'] == precision.POLICY_ID
    for pair in [('es','fr'),('es','en'),('fr','es'),('nl','en'),('es','es')]:
        assert 'argos_precision' not in assets.identity(*pair)
