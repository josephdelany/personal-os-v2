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


def test_REQ_CAP_026_034_050_REQ_NUT_016_private_runtime_reaches_atoms_from_saved_receipts(cur,advance):
    action=advance()
    assert action['stage']=='transcribe' and action['worker']=='model'
    assert advance()==action  # initial polling cannot mint duplicate work
    assert count(cur,'capture_transcription_attempts')==1
    text='one '+NAME+' from Examplo'
    model_receipt(cur,action,{'success':True,'result':{'text':text,'segments':[]}})
    action=advance()
    assert action['stage']=='extract'
    assert action['request']['payload']['messages'][1]['content']==text
    assert advance()==action
    model_receipt(cur,action,extraction_response(name=NAME,evidence=NAME,evidence_start=4,
        quantity=1,quantity_evidence='one',quantity_evidence_start=0))
    action=advance()
    assert action['worker']=='reference' and action['request']['brand']=='Examplo'
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
