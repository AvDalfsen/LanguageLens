"""Real process-boundary coverage of retention, priority and stale results."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import pytest
from PySide6.QtCore import QObject
from language_lens.config import Settings, validate_settings, save_settings, load_settings
from language_lens.services import translation_session as sessions

WORKER=r'''import json,os,sys,time
print(json.dumps({'ready':True,'protocol':'translation-v1','pid':os.getpid()}),flush=True)
for line in sys.stdin:
 r=json.loads(line)
 with open(os.environ['LENS_SESSION_TEST_LOG'],'a',encoding='utf-8') as f:f.write(json.dumps({'pid':os.getpid(),'text':r['text'],'command':r['command']})+'\n')
 time.sleep(.04)
 if r['command']=='sentence':v={'sentence':r['text'],'words':{}}
 elif r['command']=='word':v={'sentence':None,'words':{r['text']:{'candidates':['translated'],'note':''}}}
 else:v={'candidates':['expanded'],'note':''}
 print(json.dumps({'id':r['id'],'result':v,'done':True}),flush=True)
'''

def wait(qapp,predicate):
    until=time.monotonic()+10
    while not predicate() and time.monotonic()<until:qapp.processEvents();time.sleep(.003)
    assert predicate()
    qapp.processEvents()

@pytest.fixture
def fake(qapp,monkeypatch,tmp_path):
    sessions.invalidate();log=tmp_path/'requests.jsonl'
    monkeypatch.setenv('LENS_SESSION_TEST_LOG',str(log))
    monkeypatch.setattr(sessions,'worker_command',lambda _: (sys.executable,['-c',WORKER]))
    yield log
    sessions.invalidate();qapp.processEvents()

def payload(*,keep=False,words=('first','last'),source='pt',target='en'):
    return {'settings':asdict(Settings(keep_translation_models_loaded=keep,source_language=source,target_language=target)),
            'text':'selection','words':words,'word':'explicit'}

def records(path):return [json.loads(line) for line in path.read_text('utf-8').splitlines()]

def test_retention_defaults_off_and_round_trips(tmp_path):
    assert not Settings().keep_translation_models_loaded
    assert not validate_settings({'keep_translation_models_loaded':'true'}).keep_translation_models_loaded
    path=tmp_path/'settings.json';save_settings(Settings(keep_translation_models_loaded=True),path)
    assert load_settings(path).keep_translation_models_loaded

def test_capture_mode_releases_process_and_next_capture_has_new_pid(qapp,fake):
    first=QObject();request=payload();service=sessions.session_for(request['settings'],first)
    job=service.submit('translate',request);wait(qapp,lambda:not job.active)
    pid=service.process.processId();assert pid
    sessions.close_capture(first);assert service.process is None
    second=QObject();next_service=sessions.session_for(request['settings'],second)
    next_job=next_service.submit('translate',request);wait(qapp,lambda:not next_job.active)
    assert next_service.process.processId()!=pid
    sessions.close_capture(second)

def test_retained_mode_survives_review_close_and_disable_releases_it(qapp,fake):
    owner=QObject();request=payload(keep=True);service=sessions.session_for(request['settings'],owner)
    job=service.submit('translate',request);wait(qapp,lambda:not job.active)
    pid=service.process.processId();sessions.close_capture(owner)
    second=QObject();assert sessions.session_for(request['settings'],second) is service
    job=service.submit('translate',request);wait(qapp,lambda:not job.active)
    assert service.process.processId()==pid
    sessions.configure(Settings(keep_translation_models_loaded=False))
    assert service.process is None and service.closed

def test_language_change_and_maintenance_release_retained_models(qapp,fake):
    owner=QObject();request=payload(keep=True);service=sessions.session_for(request['settings'],owner)
    job=service.submit('translate',request);wait(qapp,lambda:not job.active)
    sessions.configure(Settings(keep_translation_models_loaded=True,source_language='en',target_language='nl'))
    assert service.closed and service.process is None
    service=sessions.session_for(request['settings'],owner)
    job=service.submit('translate',request);wait(qapp,lambda:not job.active)
    sessions.invalidate();assert service.closed and service.process is None

def test_hover_and_expanded_request_precede_speculative_words(qapp,fake):
    service=sessions.TranslationSession();request=payload(words=('first','middle','last'))
    job=service.submit('translate',request)
    wait(qapp,lambda:service.current is not None and service.current[2]=='sentence' and service.ready)
    job.promote('last')
    more=service.submit('more',request)
    wait(qapp,lambda:not job.active and not more.active)
    seen=records(fake)
    assert [r['text'] for r in seen[:3]]==['selection','last','explicit']
    assert [r['text'] for r in seen].count('last')==1
    service.shutdown()

def test_cancelled_calculation_does_not_publish_or_reload_worker(qapp,fake):
    service=sessions.TranslationSession();request=payload(words=())
    old=service.submit('translate',request);published=[];old.event.connect(published.append)
    wait(qapp,lambda:service.current is not None and service.ready)
    pid=service.process.processId();old.cancel()
    new=service.submit('translate',{**request,'text':'new selection'})
    wait(qapp,lambda:not old.active and not new.active)
    assert not published and service.process.processId()==pid
    assert records(fake)[-1]['text']=='new selection'
    service.shutdown()
