"""REQ-CAP-026 private pagination and once-daily retry sweep control."""
import datetime as dt
import os
from pathlib import Path
import signal
import subprocess
import sys
import uuid
import pytest
from tools import capture_private_worker as worker


@pytest.fixture
def setup(tmp_path,monkeypatch):
    paths={key:tmp_path/key for key in
           ('state_directory','model_outbox','model_results','reference_outbox')}
    for path in paths.values():path.mkdir(mode=0o700)
    class Connection:
        today=dt.date(2026,9,23)
        commits=0
        rollbacks=0
        def cursor(self):return self
        def execute(self,*args):pass
        def fetchone(self):return (self.today,)
        def commit(self):self.commits+=1
        def rollback(self):self.rollbacks+=1
    conn=Connection()
    monkeypatch.setattr(worker,'owner_context',lambda cur:None)
    monkeypatch.setattr(worker.capture_transcription,'_private',lambda schema:schema)
    return conn,paths


def test_REQ_CAP_026_nightly_cursor_continues_after_failure_and_holds_until_next_day(setup,monkeypatch):
    conn,paths=setup;seen=[];cursors=[]
    def queue(cur,*,cursor,**kwargs):
        cursors.append(cursor)
        return {'items':[{'capture_id':'first' if cursor is None else 'second'}],
                'next_cursor':{'page':2} if cursor is None else None}
    def advance(conn,capture_id,**kwargs):
        seen.append((capture_id,kwargs['retry']))
        if capture_id=='first':raise RuntimeError('one broken capture')
        return {'status':'queued'}
    monkeypatch.setattr(worker.capture_transcription,'work_queue',queue)
    monkeypatch.setattr(worker,'advance',advance)
    first=worker.poll(conn,**paths,retry=True)
    assert first['status']=='incomplete' and not first['sweep_complete']
    second=worker.poll(conn,**paths,retry=True)
    assert second['status']=='incomplete' and second['sweep_complete']
    assert worker.poll(conn,**paths,retry=True)['status']=='incomplete'
    assert seen==[('first',True),('second',True)] and conn.rollbacks==1
    conn.today+=dt.timedelta(days=1)
    worker.poll(conn,**paths,retry=True)
    assert cursors==[None,{'page':2},None]


def test_REQ_CAP_026_regular_poll_does_not_enable_retry_and_nightly_success_stays_idle(setup,monkeypatch):
    conn,paths=setup;seen=[]
    monkeypatch.setattr(worker.capture_transcription,'work_queue',lambda *a,**kw:
        {'items':[{'capture_id':'capture'}],'next_cursor':None})
    def advance(conn,capture_id,**kwargs):
        seen.append(kwargs['retry']);return {'status':'retry_pending'}
    monkeypatch.setattr(worker,'advance',advance)
    worker.poll(conn,**paths)
    worker.poll(conn,**paths)
    worker.poll(conn,**paths,retry=True)
    assert worker.poll(conn,**paths,retry=True)['status']=='already_scanned'
    assert seen==[False,False,True]


@pytest.mark.parametrize('retry',[False,True])
def test_REQ_CAP_026_interrupted_capture_advances_without_certifying_success(setup,monkeypatch,retry):
    conn,paths=setup;seen=[]
    def queue(cur,*,cursor,**kwargs):
        return {'items':[{'capture_id':'first' if cursor is None else 'second'}],
                'next_cursor':{'page':2} if cursor is None else None}
    def advance(conn,capture_id,**kwargs):
        seen.append(capture_id)
        if capture_id=='first':raise KeyboardInterrupt()
        return {'status':'queued'}
    monkeypatch.setattr(worker.capture_transcription,'work_queue',queue)
    monkeypatch.setattr(worker,'advance',advance)
    with pytest.raises(KeyboardInterrupt):worker.poll(conn,**paths,retry=retry)
    result=worker.poll(conn,**paths,retry=retry)
    assert seen==['first','second']
    assert result['status']=='incomplete' and result['sweep_complete']
    if retry:
        assert worker.poll(conn,**paths,retry=True)['status']=='incomplete'
    else:
        with pytest.raises(KeyboardInterrupt):worker.poll(conn,**paths)
        assert seen==['first','second','first']


def test_REQ_CAP_026_interrupted_final_nightly_page_keeps_daily_gate_incomplete(setup,monkeypatch):
    conn,paths=setup;calls=[]
    monkeypatch.setattr(worker.capture_transcription,'work_queue',lambda *a,**kw:
        {'items':[{'capture_id':'last'}],'next_cursor':None})
    def crash(*a,**kw):calls.append('attempt');raise KeyboardInterrupt()
    monkeypatch.setattr(worker,'advance',crash)
    with pytest.raises(KeyboardInterrupt):worker.poll(conn,**paths,retry=True)
    assert worker.poll(conn,**paths,retry=True)['status']=='incomplete'
    assert calls==['attempt']
    conn.today+=dt.timedelta(days=1)
    with pytest.raises(KeyboardInterrupt):worker.poll(conn,**paths,retry=True)
    assert calls==['attempt','attempt']


def test_REQ_CAP_026_real_process_kill_preserves_cursor_for_next_capture(setup,monkeypatch):
    conn,paths=setup
    script='''
import datetime as dt,os,signal
from tools import capture_private_worker as worker
class Connection:
    def cursor(self):return self
    def execute(self,*args):pass
    def fetchone(self):return (dt.date(2026,9,23),)
    def commit(self):pass
worker.owner_context=lambda cur:None
worker.capture_transcription.work_queue=lambda *a,**kw: {
    'items':[{'capture_id':'first'}],'next_cursor':{'page':2}}
def killed(*args,**kwargs):os.kill(os.getpid(),signal.SIGKILL)
worker.advance=killed
worker.poll(Connection(),**PATHS)
'''.replace('PATHS',repr({key:str(value) for key,value in paths.items()}))
    child=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).resolve().parents[1],
        env={'PYTHONPATH':str(Path(__file__).resolve().parents[1])},
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert child.returncode==-signal.SIGKILL
    seen=[]
    def queue(cur,*,cursor,**kwargs):
        assert cursor=={'page':2}
        return {'items':[{'capture_id':'second'}],'next_cursor':None}
    monkeypatch.setattr(worker.capture_transcription,'work_queue',queue)
    monkeypatch.setattr(worker,'advance',lambda conn,capture_id,**kw:
        seen.append(capture_id) or {'status':'queued'})
    assert worker.poll(conn,**paths)['status']=='incomplete'
    assert seen==['second']


def test_REQ_CAP_026_empty_active_queue_still_retires_consumed_requests_fairly(setup,monkeypatch):
    conn,paths=setup
    from lib import capture_mailbox as mailbox
    requests=[{'request_id':str(uuid.UUID(int=n)),'call_kind':'transcribe','payload':{}}
              for n in (1,2)]
    for request in requests:mailbox.publish(paths['model_outbox'],request)
    monkeypatch.setattr(worker.capture_transcription,'work_queue',lambda *a,**kw:
        {'items':[],'next_cursor':None})
    monkeypatch.setattr(worker,'consumed',lambda cur,request,**kw:request==requests[1])
    assert worker.poll(conn,**paths,retry=True)['cleanup']['status']=='awaiting_consumption'
    # Even after nightly completion, cleanup operates independently.
    assert worker.poll(conn,**paths,retry=True)['cleanup']['status']=='retired'
    assert mailbox.pending(paths['model_outbox'])==[requests[0]['request_id']]


def test_REQ_CAP_026_unconfirmed_cleanup_commit_retains_request(setup,monkeypatch):
    conn,paths=setup
    from lib import capture_mailbox as mailbox
    request={'request_id':str(uuid.uuid4()),'call_kind':'transcribe','payload':{}}
    mailbox.publish(paths['model_outbox'],request)
    monkeypatch.setattr(worker,'consumed',lambda *a,**kw:True)
    def unavailable():raise RuntimeError('commit unconfirmed')
    conn.commit=unavailable
    with mailbox._directory(paths['state_directory'],write=True) as state:
        with pytest.raises(RuntimeError):
            worker._retire_saved(conn,state,{},model_outbox=paths['model_outbox'],
                reference_outbox=paths['reference_outbox'],schema='core')
    assert mailbox.read(paths['model_outbox'],request['request_id'])==request
