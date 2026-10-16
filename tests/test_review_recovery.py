from language_lens.domain import OcrLine, WordTranslation
from language_lens.services.errors import failure_from_code
from language_lens.services import translation_session


def recognized(window):
    window._ocr_finished([OcrLine('Read this',.99,((0,0),(100,0),(100,25),(0,25)))])


def test_retry_buttons_are_absent_from_normal_results_and_menu(review_factory):
    w,_=review_factory();recognized(w)
    w._translation_finished(('Lees dit',{'Read':WordTranslation(('Lees',)),'this':WordTranslation(('dit',))}))
    assert w.retry_ocr.isHidden() and w.retry_translation.isHidden() and w._error_panel.isHidden()
    assert [button for _,button in w._recovery_actions]==[w.reselect,w.collapse_translation]
    assert w.edit_source.isEnabled()


def test_ocr_error_has_only_ocr_retry_and_clears_on_retry_or_empty_scan(review_factory):
    w,tasks=review_factory();capture=w.canvas.capture
    w._ocr_failed(failure_from_code('runtime','ocr').message)
    assert not w._error_panel.isHidden() and not w.retry_ocr.isHidden()
    assert w.retry_ocr.isEnabled() and w.retry_translation.isHidden()
    assert 'component' in w.error_message.text()
    count=len(tasks);w.retry_ocr.click()
    assert len(tasks)==count+1 and w.canvas.capture is capture
    assert w.retry_ocr.isHidden() and w._error_panel.isHidden()
    w._ocr_finished([])
    assert w.retry_ocr.isHidden() and w.retry_translation.isHidden()
    assert 'No text found' in w.status.text()


def test_translation_retry_preserves_edited_text_and_restarts_worker(review_factory,monkeypatch):
    w,tasks=review_factory();recognized(w)
    w._apply_corrected_source('Corrected source')
    w._translation_failed(failure_from_code('timeout','translate').message)
    assert w.retry_ocr.isHidden() and not w.retry_translation.isHidden()
    assert w.retry_translation.isEnabled() and 'timed out' in w.error_message.text()
    calls=[];monkeypatch.setattr(translation_session,'retry_capture',lambda settings,owner:calls.append(owner))
    w.retry_translation.click()
    assert calls==[w] and tasks[-1].lines[0].text=='Corrected source'
    assert w._corrected_source and w._error_panel.isHidden()
    assert w.retry_translation.isHidden() and not w.copy_translation.isEnabled()


def test_partial_failures_keep_error_visible_as_successful_results_arrive(review_factory):
    w,_=review_factory();recognized(w)
    w._translation_problem(failure_from_code('missing_assets','translate').message)
    w._translation_finished(('',{}))
    w._translation_finished((None,{'Read':WordTranslation(('Lees',))}))
    assert not w._error_panel.isHidden() and not w.retry_translation.isHidden()
    assert w.retry_ocr.isHidden() and 'missing' in w.error_message.text()
    assert w._translations['Read'].candidates==('Lees',)
    assert not w.copy_translation.isEnabled()


def test_word_failure_can_retry_without_losing_successful_sentence(review_factory):
    w,_=review_factory();recognized(w)
    w._translation_finished(('Lees dit',{'Read':WordTranslation((),'Unavailable')}))
    assert not w.retry_translation.isHidden() and w.retry_ocr.isHidden()
    assert w.translation.text()=='Lees dit' and w.copy_translation.isEnabled()


def test_error_retranslates_without_retrying_or_losing_recovery_control(review_factory):
    from language_lens.i18n import set_language,tr
    w,tasks=review_factory()
    w._ocr_failed(failure_from_code('runtime','ocr').message)
    original=w.error_message.text();before=list(tasks)
    try:
        set_language('nl');w.refresh_language('en')
        assert w.error_message.text()!=original and not w._error_panel.isHidden()
        assert w.retry_ocr.text()==tr('Retry OCR') and not w.retry_ocr.isHidden()
        assert w.retry_translation.isHidden() and tasks==before
    finally:
        set_language('en')
