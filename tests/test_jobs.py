"""Exercise task ownership through the real Qt dispatcher and process boundary."""
import gc
import sys
import time
import weakref
from threading import Event

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QObject, QRect
from PySide6.QtGui import QImage, QPixmap
from language_lens.config import Settings
from language_lens.domain import OcrLine
from language_lens.services import jobs, process_job
from language_lens.services.tasks import OcrTask, TranslationTask, MoreCandidatesTask, TaskSignals
from language_lens.ui.review import ReviewWindow

WORKER = r"""import json,os,sys,time
payload=json.loads(sys.stdin.buffer.read())
mode=os.environ.get('LANGUAGE_LENS_JOB_TEST_MODE','success')
if mode=='cancel': time.sleep(60)
if mode=='failure':
 print(json.dumps({'error':'Synthetic failure'}),flush=True)
 sys.exit(1)
command=sys.argv[1]
if command=='ocr': result=[{'text':'Hello','confidence':1,'polygon':[[0,0],[100,0],[100,30],[0,30]],'token_spans':[[0,5]]}]
elif command=='translate': result={'sentence':'Hallo','words':{word:{'candidates':['Hallo'],'note':''} for word in payload['words']}}
else: result={'candidates':['Hallo','Hoi'],'note':''}
print(json.dumps({'result':result}),flush=True)
print(json.dumps({'ok':True}),flush=True)
"""


def wait(qapp, predicate):
    deadline = time.monotonic()+10
    while not predicate() and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.005)
    assert predicate(), "Synthetic worker did not settle"
    qapp.processEvents()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    gc.collect()


@pytest.fixture
def synthetic_worker(monkeypatch,tmp_path):
    monkeypatch.setattr(jobs,"settings_path",lambda:tmp_path/"settings.json")
    monkeypatch.setattr(process_job,"worker_command",lambda _module:(sys.executable,['-c',WORKER]))


@pytest.mark.parametrize("kind",["ocr","translate","more"])
@pytest.mark.parametrize("mode",["success","failure","cancel","scratch"])
def test_disposable_tasks_release_signals_and_task_references(qapp,monkeypatch,tmp_path,synthetic_worker,kind,mode):
    monkeypatch.setenv("LANGUAGE_LENS_JOB_TEST_MODE",mode)
    if mode=='scratch':
        blocked=tmp_path/'blocked'
        blocked.write_bytes(b'not a directory')
        monkeypatch.setattr(jobs,'settings_path',lambda:blocked/'settings.json')
    settings=Settings(speech_enabled=False,show_ipa=False)
    if kind=='ocr':
        image=QImage(200,50,QImage.Format.Format_RGB32)
        image.fill(0)
        task=OcrTask(image,settings)
    elif kind=='translate':
        task=TranslationTask([OcrLine('Hello',1,((0,0),(100,0),(100,30),(0,30)))],['Hello'],settings)
    else:
        task=MoreCandidatesTask('Hello',settings,None,Event())
    owner=QObject()
    task.signals.setParent(owner)
    reference=weakref.ref(task)
    job=jobs.TaskPool.globalInstance().start(task)
    del task
    if mode=='cancel':
        wait(qapp,lambda:job._stager is None)
        job.cancel()
    wait(qapp,lambda:not job.active)
    assert not owner.findChildren(TaskSignals)
    assert not owner.findChildren(jobs.ServiceJob)
    assert reference() is None
    assert not list(tmp_path.glob('jobs/.job-*'))
    owner.deleteLater()


def test_repeated_review_retries_keep_only_active_tasks(qapp,monkeypatch,synthetic_worker):
    monkeypatch.setenv('LANGUAGE_LENS_JOB_TEST_MODE','success')
    window=ReviewWindow(QPixmap(1000,700),QRect(100,100,300,40),Settings(speech_enabled=False,show_ipa=False))
    try:
        wait(qapp,lambda:not window._jobs)
        for _ in range(10):
            window._start_translation()
            wait(qapp,lambda:not window._jobs)
        for _ in range(10):
            window._retry_ocr()
            wait(qapp,lambda:not window._jobs)
        assert not window.findChildren(TaskSignals)
        assert not window.findChildren(jobs.ServiceJob)
        assert window._translation_job is window._more_job is None
        window._request_more_candidates('Hello')
        wait(qapp,lambda:not window._jobs)
        assert window._more_job is None
        monkeypatch.setenv('LANGUAGE_LENS_JOB_TEST_MODE','cancel')
        for _ in range(5):
            window._retry_ocr()
            qapp.processEvents()
        window.close()
        wait(qapp,lambda:not window._jobs)
        assert not window.findChildren(TaskSignals)
    finally:
        window.close()


@pytest.mark.parametrize("mode", ["start", "scratch", "staging"])
def test_supervisor_errors_are_localizable_and_do_not_expose_paths(qapp, monkeypatch, tmp_path, caplog, mode):
    from language_lens.i18n import set_language, tr_message

    private = "PRIVATE-IMAGE-TEXT"
    root = tmp_path / private
    root.mkdir()
    monkeypatch.setattr(jobs, "settings_path", lambda: root / "settings.json")
    monkeypatch.setattr(process_job, "worker_command",
                        lambda _module: (str(root / "missing-python.exe"), []))
    images = None
    if mode == "scratch":
        blocked = root / "blocked"
        blocked.write_bytes(b"not a directory")
        monkeypatch.setattr(jobs, "settings_path", lambda: blocked / "settings.json")
    elif mode == "staging":
        image = QImage(20, 20, QImage.Format.Format_RGB32)
        image.fill(0)
        images = {"../invalid.png": image}
    job = jobs.ServiceJob()
    failures = []
    job.failed.connect(failures.append)
    try:
        job.start("ocr", {}, images)
        wait(qapp, lambda: bool(failures) and not job.active)
        assert len(failures) == 1
        assert private not in failures[0]
        assert private not in caplog.text
        set_language("fr")
        assert tr_message(failures[0]) != failures[0]
        assert not list(root.glob("jobs/.job-*"))
    finally:
        set_language("en")
        job.deleteLater()
