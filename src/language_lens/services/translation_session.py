"""GUI-side scheduling and lifecycle of the isolated translation worker."""
from collections import deque
import json

from PySide6.QtCore import QObject, QCoreApplication, QProcess, QTimer, Signal
from language_lens.runtime import worker_command
from language_lens.services.errors import failure_from_code

_sessions=set()
_shared=None


class TranslationJob(QObject):
    event=Signal(object)
    failed=Signal(str)
    cancelled=Signal()
    finished=Signal()
    settled=Signal()

    def __init__(self,session,command,payload,parent=None):
        super().__init__(parent)
        self.session=session;self.command=command;self.payload=payload;self.active=True
        self.sentence_pending=command=='translate'
        self.words=deque(dict.fromkeys(payload.get('words',()))) if command=='translate' else deque()
        self.preferred=deque();self.dispatched=set()
        self.single_pending=command in ('more','word','inspect')
        self.stop_requested=False
        self._stager=None  # Translation requests have no image-staging thread.

    def promote(self,word):
        if self.active and word not in self.dispatched and word in self.words and word not in self.preferred:
            self.preferred.append(word);self.session.pump()

    def priority(self):
        return 0 if self.sentence_pending else 1 if self.single_pending or self.preferred else 2

    def unit(self):
        if self.sentence_pending:
            self.sentence_pending=False;return 'sentence',self.payload['text']
        if self.single_pending:
            self.single_pending=False;return self.command,self.payload.get('word','')
        while self.preferred or self.words:
            word=self.preferred.popleft() if self.preferred else self.words.popleft()
            if word not in self.dispatched:
                self.dispatched.add(word);return 'word',word
        return None

    def complete(self,*,error=None,cancelled=False):
        if not self.active:return
        self.active=False
        if cancelled:self.cancelled.emit()
        elif error:self.failed.emit(error)
        else:self.finished.emit()
        self.settled.emit()

    def cancel(self):
        self.stop_requested=True
        # Suppress in-flight output but let its calculation finish in the worker.
        QTimer.singleShot(0,lambda:self.complete(cancelled=True))
    shutdown=cancel


class TranslationSession(QObject):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.jobs=[];self.process=None;self.pair=None;self.closed=False
        self.buffer=b'';self.ready=False;self.current=None;self.serial=0
        self.close_when_idle=False
        self.restart_pending=False
        self.ownership=None
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.timeout)
        self.pump_timer=QTimer(self);self.pump_timer.setSingleShot(True);self.pump_timer.timeout.connect(self._pump)
        _sessions.add(self)

    def submit(self,command,payload,parent=None):
        job=TranslationJob(self,command,payload,parent)
        settings=payload['settings'];pair=(settings['source_language'],settings['target_language'])
        if self.pair is not None and self.pair!=pair:
            for previous in self.jobs:previous.complete(cancelled=True)
            self.jobs.clear();self._stop_process()
        self.pair=pair
        self.jobs=[j for j in self.jobs if j.active]
        if len(self.jobs)>=32:
            QTimer.singleShot(0,lambda:job.complete(error=failure_from_code('execution','translate').message))
            return job
        self.jobs.append(job);self.pump();return job

    def pump(self):
        if not self.closed:self.pump_timer.start(0)

    def _pump(self):
        if self.closed or self.current is not None:return
        if self.restart_pending:
            self._stop_process();self.restart_pending=False
        self.jobs=[job for job in self.jobs if job.active]
        while self.jobs:
            job=min(self.jobs,key=lambda j:j.priority())
            if job.stop_requested:
                job.complete(cancelled=True);self.jobs.remove(job);continue
            unit=job.unit()
            if unit is None:
                job.complete();self.jobs.remove(job);continue
            self.serial+=1;self.current=(self.serial,job,*unit)
            self.timer.start(60000 if not self.ready else 30000)
            if self.process is None:self._start()
            elif self.ready:self._send()
            return
        if self.close_when_idle:self.shutdown()

    def _start(self):
        process=self.process=QProcess(self);self.ready=False;self.buffer=b''
        program,args=worker_command('language_lens.services.translation_worker')
        process.setProgram(program);process.setArguments(args)
        process.readyReadStandardOutput.connect(lambda:self._read(process))
        process.readyReadStandardError.connect(lambda:process.readAllStandardError())
        process.errorOccurred.connect(lambda error:self._ended(process) if error==QProcess.ProcessError.FailedToStart else None)
        process.finished.connect(lambda *_args:self._ended(process))
        process.start()

    def _send(self):
        if self.current is None:return
        request_id,job,command,text=self.current
        request={'id':request_id,'command':command,'text':text,'settings':job.payload['settings']}
        self.process.write(json.dumps(request,ensure_ascii=True).encode('utf-8')+b'\n')

    def _read(self,process):
        if process is not self.process:return
        self.buffer+=bytes(process.readAllStandardOutput())
        if len(self.buffer)>16*1024*1024:self.timeout();return
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:message=json.loads(line)
            except (ValueError,UnicodeError):self.timeout();return
            if not isinstance(message,dict):self.timeout();return
            if message.get('ready'):
                if message.get('protocol')!='translation-v1':self.timeout();return
                if self.ready:self.timeout();return
                if isinstance(message.get('pid'),int):
                    from language_lens.services.worker_children import own_pid
                    try:self.ownership=own_pid(message['pid'])
                    except OSError:self.timeout();return
                self.ready=True;self._send();continue
            if self.current is None or message.get('id')!=self.current[0]:continue
            _id,job,command,text=self.current
            if job.active and not job.stop_requested:
                if message.get('error'):
                    code=message.get('failure',{}).get('code','execution')
                    from language_lens.services.errors import MESSAGES
                    failure=failure_from_code(code if code in MESSAGES else 'execution','more' if command=='more' else 'translate').message
                    if command in ('sentence','word'):
                        job.event.emit({'translation_error':failure})
                    if command=='sentence':
                        job.event.emit({'progress':'Whole-selection translation unavailable. Word lookups are independent.'})
                        job.event.emit({'result':{'sentence':'','words':{}}})
                    elif command=='word':
                        job.event.emit({'result':{'sentence':None,'words':{text:{'candidates':[],'note':failure}}}})
                    else:job.complete(error=failure)
                else:job.event.emit(message)
            if message.get('done'):
                self.current=None;self.timer.stop();self.pump()

    def _ended(self,process):
        if process is not self.process:return
        self._read(process)
        if process is not self.process:return
        self.process=None;self.ready=False;self.current=None;self.timer.stop()
        if self.ownership:self.ownership.close();self.ownership=None
        for job in self.jobs:
            if job.active:job.complete(error=failure_from_code('runtime','translate').message)
        self.jobs.clear();process.deleteLater()

    def timeout(self):
        for job in self.jobs:
            if job.active:job.complete(error=failure_from_code('timeout','translate').message)
        self.jobs.clear();self._stop_process()

    def _stop_process(self):
        process,self.process=self.process,None
        self.current=None;self.ready=False;self.timer.stop();self.buffer=b''
        if self.ownership:self.ownership.close();self.ownership=None
        if process is not None:
            process.kill();process.waitForFinished(1500);process.deleteLater()

    def shutdown(self):
        if self.closed:return
        self.closed=True;self.pump_timer.stop()
        for job in self.jobs:job.complete(cancelled=True)
        self.jobs.clear();self._stop_process();_sessions.discard(self);self.deleteLater()


def session_for(settings,owner):
    global _shared
    app=QCoreApplication.instance()
    if settings.get('keep_translation_models_loaded',False):
        if _shared is None or _shared.closed:
            _shared=TranslationSession(app)
            if app:app.aboutToQuit.connect(_shared.shutdown)
        return _shared
    session=getattr(owner,'_lens_translation_session',None) if owner else None
    if session is None or session.closed:
        session=TranslationSession(app)
        if owner:
            owner._lens_translation_session=session;owner.destroyed.connect(session.shutdown)
        else:session.close_when_idle=True
        if app:app.aboutToQuit.connect(session.shutdown)
    return session


def close_capture(owner):
    session=getattr(owner,'_lens_translation_session',None)
    if session is not None:session.shutdown()


def retry_capture(settings, owner):
    """Restart this capture's worker after a technical error, clearing native state."""
    session = session_for(settings, owner)
    # Other captures can share a retained worker. Wait for its in-flight unit
    # to finish, then restart before this retry, without cancelling their jobs.
    session.restart_pending = True


def configure(settings):
    global _shared
    if _shared and (not settings.keep_translation_models_loaded or _shared.pair not in
                    (None,(settings.source_language,settings.target_language))):
        _shared.shutdown();_shared=None


def invalidate():
    global _shared
    for session in tuple(_sessions):session.shutdown()
    _shared=None
