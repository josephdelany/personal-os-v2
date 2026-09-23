"""Private CLI progression with actual SQL roles and rollback-only receipts."""
import hashlib
import json
import pytest
from lib import db
from lib.model_contract import request_bytes
from tests._sql_fixture import requires_disposable
from tests.test_capture_transcription import cur,CID,count,extraction_response
from tests.test_capture_reference import NAME,source_result
from tools import capture_transcription as cli
from tools.engines import capture_runtime, capture_transcription

pytestmark=requires_disposable


@pytest.fixture
def advance(cur,monkeypatch,capsys):
    monkeypatch.setattr(db,'read_capture_media',lambda *args:b'fixture')
    events=[]
    class Probe:
        def cursor(self):return cur
        def commit(self):events.append('commit')
        def rollback(self):events.append('rollback')
        def close(self):events.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    actual=capture_runtime.advance
    monkeypatch.setattr(capture_runtime,'advance',lambda cursor,**kw:
        actual(cursor,schema='core_pytest',ops='ops_pytest',config='config',**kw))
    def run(retry=False):
        events.clear()
        cur.execute('SET SESSION AUTHORIZATION service_role')
        try:
            assert cli.main(['advance',CID]+(['--retry'] if retry else []))==0
            assert events==['commit','close']
            output=capsys.readouterr()
            assert output.err==''
            return json.loads(output.out)
        finally:cur.execute('RESET SESSION AUTHORIZATION')
    return run


def model_receipt(cur,action,response=None,error=None):
    request=action['request'];body=request_bytes(request['payload'])
    cur.execute('SET LOCAL ROLE model_egress')
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
        (request['request_id'],request['model_id'],request['call_kind'],request['estimated_neurons'],
         request['capture_id'],len(body),hashlib.sha256(body).hexdigest()))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SELECT public.settle_model_response(%s,%s,%s,%s)',
        (request['request_id'],'error' if error else 'ok',
         None if error else request_bytes(response).decode(),error))
    cur.execute('RESET ROLE')


def test_REQ_CAP_026_038_private_worker_consumes_budget_and_retires_after_commit(cur,monkeypatch,tmp_path):
    from lib import capture_mailbox as mailbox
    from tools import capture_private_worker as worker
    monkeypatch.setattr(db,'read_capture_media',lambda *args:b'fixture')
    paths={name:tmp_path/name for name in ('model_outbox','model_results','reference_outbox')}
    for path in paths.values():path.mkdir(mode=0o750)
    commits=[]
    class Connection:
        def cursor(self):return cur
        def commit(self):commits.append(mailbox.pending(paths['model_outbox']))
    conn=Connection()
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        result=worker.advance(conn,CID,**paths,schema='core_pytest',ops='ops_pytest')
        assert result['status']=='queued' and commits==[[]]
        request=mailbox.read(paths['model_outbox'],result['request_id'])
        mailbox.store_result(paths['model_results'],request,
            {'request_id':result['request_id'],'status':'deferred_budget'})
        result=worker.advance(conn,CID,**paths,schema='core_pytest',ops='ops_pytest')
        assert result['status']=='deferred_budget'
        assert commits[-1]==[request['request_id']]
        assert mailbox.pending(paths['model_outbox'])==[]
    finally:cur.execute('RESET SESSION AUTHORIZATION')
    assert count(cur,'raw_captures')==1 and count(cur,'capture_transcription_outcomes')==1


def test_REQ_CAP_026_private_poll_uses_sql_queue_and_persists_daily_gate(cur,monkeypatch,tmp_path):
    from lib import capture_mailbox as mailbox
    from tools import capture_private_worker as worker
    monkeypatch.setattr(db,'read_capture_media',lambda *args:b'fixture')
    paths={name:tmp_path/name for name in
           ('state_directory','model_outbox','model_results','reference_outbox')}
    for path in paths.values():path.mkdir(mode=0o750)
    class Connection:
        def cursor(self):return cur
        def commit(self):pass
        def rollback(self):raise AssertionError('unexpected rollback')
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        first=worker.poll(Connection(),**paths,retry=True,schema='core_pytest',ops='ops_pytest')
        assert first['sweep_complete'] and first['result']['status']=='queued'
        second=worker.poll(Connection(),**paths,retry=True,schema='core_pytest',ops='ops_pytest')
        assert second['status']=='already_scanned'
        assert mailbox.pending(paths['model_outbox'])==[first['result']['request_id']]
    finally:cur.execute('RESET SESSION AUTHORIZATION')
    assert count(cur,'capture_transcription_attempts')==1


@pytest.mark.parametrize('reserved',[False,True])
@pytest.mark.parametrize('stage',['transcribe','extract'])
def test_REQ_CAP_026_038_budget_control_defers_only_without_sql_receipt(cur,advance,reserved,stage):
    from tools.engines.capture_mailbox import consume_control,consumed
    action=advance()
    if stage=='extract':
        model_receipt(cur,action,{'success':True,'result':{'text':'one '+NAME,'segments':[]}})
        action=advance()
    request=action['request']
    if reserved:
        response=({'success':True,'result':{'text':'one apple','segments':[]}} if stage=='transcribe'
                  else extraction_response(name=NAME,evidence=NAME,evidence_start=4,
                      quantity=1,quantity_evidence='one',quantity_evidence_start=0))
        model_receipt(cur,action,response)
    control={'request_id':request['request_id'],'status':'deferred_budget'}
    with pytest.raises(ValueError,match='saved attempt'):
        consume_control(cur,{**request,'payload':{}},control,stage=stage,schema='core_pytest')
    result=consume_control(cur,request,control,stage=stage,schema='core_pytest')
    assert result['processing_status']==(('transcribed' if stage=='transcribe' else 'extracted') if reserved else 'deferred_budget')
    assert consumed(cur,request,stage=stage,schema='core_pytest')
    if not reserved:
        assert advance()['status']=='deferred_budget'
        assert consume_control(cur,request,control,stage=stage,schema='core_pytest')==result


def test_REQ_CAP_026_034_050_REQ_NUT_016_private_runtime_reaches_atoms_from_saved_receipts(cur,advance):
    from tools.engines.capture_mailbox import consumed
    action=advance()
    transcript_request=action['request']
    assert not consumed(cur,transcript_request,stage='transcribe',schema='core_pytest')
    assert action['stage']=='transcribe' and action['worker']=='model'
    assert advance()==action  # initial polling cannot mint duplicate work
    assert count(cur,'capture_transcription_attempts')==1
    text='one '+NAME+' from Examplo'
    model_receipt(cur,action,{'success':True,'result':{'text':text,'segments':[]}})
    action=advance()
    assert action['stage']=='extract'
    assert consumed(cur,transcript_request,stage='transcribe',schema='core_pytest')
    with pytest.raises(ValueError,match='queued payload'):
        consumed(cur,{**transcript_request,'payload':{}},stage='transcribe',schema='core_pytest')
    extraction_request=action['request']
    assert action['request']['payload']['messages'][1]['content']==text
    assert advance()==action
    model_receipt(cur,action,extraction_response(name=NAME,evidence=NAME,evidence_start=4,
        quantity=1,quantity_evidence='one',quantity_evidence_start=0))
    action=advance()
    assert action['worker']=='reference' and action['request']['brand']=='Examplo'
    assert consumed(cur,extraction_request,stage='extract',schema='core_pytest')
    request=action['request'];body=request_bytes(request)
    assert advance()==action
    cur.execute('SET LOCAL ROLE reference_egress')
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
        (request['request_id'],request['source'],hashlib.sha256(body).hexdigest(),len(body)))
    assert cur.fetchone()[0]['allowed']
    cur.execute('RESET ROLE')
    assert advance()['status']=='awaiting_result'
    cur.execute('SET LOCAL ROLE reference_egress')
    cur.execute('SELECT public.settle_reference_response(%s,%s,NULL)',
        (request['request_id'],request_bytes(source_result()).decode()))
    cur.execute('RESET ROLE')
    assert advance()['status']=='progress'
    assert consumed(cur,request,stage='reference',schema='core_pytest')
    done=advance()
    assert done['status']=='complete' and done['result']['processing_status']=='enriched'
    before=count(cur,'atoms')
    assert before>0 and advance()['status']=='complete' and count(cur,'atoms')==before
    read=capture_transcription.readback(cur,capture_id=CID,schema='core_pytest')
    kcal=next(a for a in read['extraction']['resolved_items'][0]['atoms'] if a['metric_key']=='kcal')
    assert float(kcal['value_point'])==180 and count(cur,'raw_captures')==1


def test_REQ_CAP_025_026_runtime_provider_error_waits_for_explicit_scheduled_retry(cur,advance):
    action=advance();model_receipt(cur,action,error=503)
    assert advance()['status']=='retry_pending'
    assert advance()['status']=='retry_pending'
    assert count(cur,'capture_transcription_attempts')==1
    retried=advance(retry=True)
    assert retried['status']=='dispatch' and retried['request']['request_id']!=action['request']['request_id']
    assert count(cur,'atoms')==0


def test_REQ_CAP_038_runtime_budget_deferral_cannot_spin_same_day(cur,advance):
    action=advance()
    capture_transcription.fail(cur,request_id=action['request']['request_id'],error_type='BudgetExceeded',schema='core_pytest')
    assert advance(retry=True)['status']=='deferred_budget'
    assert count(cur,'capture_transcription_attempts')==1


def test_REQ_CAP_055_056_runtime_quarantine_is_terminal_even_with_retry(cur,advance):
    action=advance()
    model_receipt(cur,action,{'success':True,'result':{'text':'fixture words','segments':[]}})
    for index in range(3):
        action=advance(retry=True)
        assert action['stage']=='extract'
        model_receipt(cur,action,{'success':True,'result':{'response':'invalid fixture json'}})
        state=advance()
        assert state['status']==('review_required' if index==2 else 'retry_pending')
    assert advance()['status']=='review_required'
    assert advance(retry=True)['status']=='review_required'
    assert count(cur,'capture_extraction_attempts')==3 and count(cur,'atoms')==0
