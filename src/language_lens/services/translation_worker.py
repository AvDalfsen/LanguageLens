"""Resident, offline translation protocol. Each request is one schedulable unit."""
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import json
import os
import sys

from language_lens.config import validate_settings
from language_lens.services.offline import no_network


def main():
    # Keep CPU inference threads asleep between requests, including retained
    # models while a game or another application is using the computer.
    os.environ['OMP_WAIT_POLICY']='PASSIVE'
    os.environ['KMP_BLOCKTIME']='0'
    output=sys.stdout
    def emit(message):print(json.dumps(message,ensure_ascii=True),file=output,flush=True)
    translator=None; pair=None
    if sys.platform=='win32':
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    with open(os.devnull,'w',encoding='utf-8') as discard, no_network(), redirect_stdout(discard), redirect_stderr(discard):
        from language_lens.services.diagnostics import initialize, record_failure
        from language_lens.services.errors import describe_failure
        from language_lens.services.translation_backends import RoutedTranslator
        initialize('worker-translation')
        emit({'ready':True,'protocol':'translation-v1','pid':os.getpid()})
        try:
            while True:
                line=sys.stdin.buffer.readline(4*1024*1024+1)
                if not line:break
                request={}
                try:
                    if len(line)>4*1024*1024 or not line.endswith(b'\n'):raise ValueError('Request limit.')
                    request=json.loads(line)
                    if request.get('command')=='quit':break
                    settings=validate_settings(request['settings']);current=(settings.source_language,settings.target_language)
                    if pair is not None and pair!=current:raise ValueError('Restart worker when changing the language pair.')
                    if translator is None:translator=RoutedTranslator();pair=current
                    command=request['command'];text=request.get('text','')
                    if not isinstance(text,str):raise ValueError('Invalid text.')
                    if command=='sentence':result={'sentence':translator.translate(text,*pair),'words':{}}
                    elif command in ('word','more'):
                        value=translator.word_candidates(text,*pair,expanded=command=='more')
                        result=asdict(value) if command=='more' else {'sentence':None,'words':{text:asdict(value)}}
                    elif command=='inspect':result=translator.inspect()
                    else:raise ValueError('Unknown translation command.')
                    emit({'id':request['id'],'result':result,'done':True})
                except Exception as exc:
                    record_failure('resident-translation',exc)
                    command=request.get('command','translate')
                    emit({'id':request.get('id'),**describe_failure(exc,'more' if command=='more' else 'translate').event(),'done':True})
        finally:
            if translator is not None:translator.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
