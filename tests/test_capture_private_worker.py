"""REQ-CAP-026 private pagination and once-daily retry sweep control."""
import datetime as dt
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
