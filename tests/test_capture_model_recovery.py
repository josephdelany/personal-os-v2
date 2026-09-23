"""Receipt-bound recovery in rollback-only SQL; no process durability claim."""
import hashlib
import json
import uuid
import pytest
from lib import egress
from lib.model_contract import request_bytes
from tests._sql_fixture import requires_disposable
from tests.test_capture_transcription import (cur, CID, RESPONSE, prepare, settle,
    extraction_request, extraction_response)
from tools.engines import capture_model_recovery as recovery, capture_transcription

pytestmark = requires_disposable


@pytest.mark.parametrize('stage', ['transcribe','extract'])
def test_REQ_CAP_026_034_050_lost_model_stdout_recovers_saved_stage_once(cur,monkeypatch,stage):
    request = prepare(cur) if stage=='transcribe' else extraction_request(cur)
    response = RESPONSE if stage=='transcribe' else extraction_response()
    events=[]
    class Probe:
        def cursor(self): return cur
        def commit(self): events.append('commit')  # rollback-only ordering proof
        def rollback(self): raise AssertionError('unexpected rollback')
    def transport(model,body):
        assert events==['commit']
        events.append('send')
        return request_bytes(response)
    monkeypatch.delenv('SUPABASE_DB_URL',raising=False)
    cur.execute('SET SESSION AUTHORIZATION model_egress')
    try:
        egress.dispatch(Probe(),**request,_transport=transport)  # discard result
    finally:
        cur.execute('RESET SESSION AUTHORIZATION')
    assert events==['commit','send','commit']
    cur.execute('SET LOCAL ROLE service_role')
    first=recovery.reconcile(cur,request_id=request['request_id'],stage=stage,schema='core_pytest')
    assert first['applied']
    assert first['processing_status']==('transcribed' if stage=='transcribe' else 'extracted')
    assert recovery.reconcile(cur,request_id=request['request_id'],stage=stage,schema='core_pytest')==first
    saved=capture_transcription.readback(cur,capture_id=CID,schema='core_pytest')
    assert saved['transcription']['text']==RESPONSE['result']['text']
    if stage=='extract': assert saved['extraction']['fields']


def reserve(cur,request):
    body=request_bytes(request['payload'])
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
        (request['request_id'],request['model_id'],request['call_kind'],request['estimated_neurons'],
         request['capture_id'],len(body),hashlib.sha256(body).hexdigest()))
    assert cur.fetchone()[0]['allowed']


def test_REQ_CAP_026_missing_or_live_reservation_never_becomes_retry_permission(cur):
    request=prepare(cur)
    assert recovery.reconcile(cur,request_id=request['request_id'],stage='transcribe',schema='core_pytest')['status']=='awaiting_dispatch'
    reserve(cur,request)
    assert recovery.reconcile(cur,request_id=request['request_id'],stage='transcribe',schema='core_pytest')['status']=='awaiting_result'
    cur.execute('SELECT count(*) FROM core_pytest.capture_transcription_outcomes')
    assert cur.fetchone()[0]==0
    with pytest.raises(ValueError,match='saved capture attempt'):
        recovery.reconcile(cur,request_id=uuid.uuid4(),stage='transcribe',schema='core_pytest')


def test_REQ_CAP_025_settled_provider_error_recovers_append_only_status(cur):
    request=prepare(cur); reserve(cur,request)
    cur.execute("SELECT public.settle_model_response(%s,'error',NULL,503)",(request['request_id'],))
    result=recovery.reconcile(cur,request_id=request['request_id'],stage='transcribe',schema='core_pytest')
    assert result['processing_status']=='pending_enrichment'
    assert capture_transcription.readback(cur,capture_id=CID,schema='core_pytest')['last_error']=='503'


def test_RULE_29_model_cannot_read_bodies_or_bypass_body_settlement(cur):
    request=prepare(cur);reserve(cur,request)
    cur.execute('SET LOCAL ROLE model_egress')
    for query,params in [
        ('SELECT * FROM ops_pytest.model_response_bodies',()),
        ('SELECT public.record_model_http_failure(%s,503)',(request['request_id'],)),
        ("SELECT public.settle_model_call(%s,'ok',1,%s)",(request['request_id'],'a'*64))]:
        cur.execute('SAVEPOINT denial')
        with pytest.raises(Exception,match='permission denied'):cur.execute(query,params)
        cur.execute('ROLLBACK TO SAVEPOINT denial')
    cur.execute("SELECT public.settle_model_response(%s,'ok',%s,NULL)",(request['request_id'],request_bytes(RESPONSE).decode()))
    cur.execute('RESET ROLE')
    cur.execute('SAVEPOINT immutable')
    with pytest.raises(Exception,match='RULE-02'):
        cur.execute("UPDATE ops_pytest.model_response_bodies SET response_body='{}'")
    cur.execute('ROLLBACK TO SAVEPOINT immutable')


def test_REQ_CAP_026_old_digest_only_success_is_explicitly_unrecoverable(cur):
    request=prepare(cur);settle(cur,request)
    assert recovery.reconcile(cur,request_id=request['request_id'],stage='transcribe',schema='core_pytest')['status']=='response_unavailable'


@pytest.mark.parametrize('body', ['not json', '"'+'x'*2097152+'"'])
def test_RULE_29_invalid_body_cannot_leave_success_receipt(cur,body):
    request=prepare(cur);reserve(cur,request)
    cur.execute('SAVEPOINT invalid_body')
    with pytest.raises(Exception):
        cur.execute("SELECT public.settle_model_response(%s,'ok',%s,NULL)",(request['request_id'],body))
    cur.execute('ROLLBACK TO SAVEPOINT invalid_body')
    cur.execute('SELECT count(*) FROM core_pytest.model_call_results')
    assert cur.fetchone()[0]==0
    cur.execute('SELECT outcome FROM core_pytest.neuron_ledger')
    assert cur.fetchone()[0]=='issued'


@pytest.mark.parametrize('commit_fails',[False,True])
def test_REQ_CAP_026_recovery_CLI_emits_success_only_after_commit(cur,monkeypatch,capsys,commit_fails):
    from tools import capture_transcription as cli
    request=prepare(cur);reserve(cur,request)
    cur.execute("SELECT public.settle_model_response(%s,'ok',%s,NULL)",(request['request_id'],request_bytes(RESPONSE).decode()))
    events=[]
    class Probe:
        def cursor(self): return cur
        def commit(self):
            events.append('commit')
            if commit_fails: raise RuntimeError('fixture private failure')
        def rollback(self): events.append('rollback')
        def close(self): events.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    actual=recovery.reconcile
    monkeypatch.setattr(recovery,'reconcile',lambda cursor,**kw:actual(cursor,schema='core_pytest',**kw))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['reconcile-model','transcribe',request['request_id']])==int(commit_fails)
        output=capsys.readouterr()
        if commit_fails:
            assert output.out=='' and json.loads(output.err)['error_type']=='RuntimeError'
            assert events==['commit','rollback','close']
        else:
            assert json.loads(output.out)['processing_status']=='transcribed'
            assert events==['commit','close']
    finally:cur.execute('RESET SESSION AUTHORIZATION')


@pytest.mark.parametrize('settled',[False,True])
def test_REQ_CAP_026_037_stopped_owned_model_preserves_success_or_retains_failed_charge(cur,settled):
    request=prepare(cur);reserve(cur,request)
    if settled:
        cur.execute("SELECT public.settle_model_response(%s,'ok',%s,NULL)",
                    (request['request_id'],request_bytes(RESPONSE).decode()))
    cur.execute('SELECT sum(estimated_neurons) FROM core_pytest.neuron_ledger')
    cost=cur.fetchone()[0]
    cur.execute('SET LOCAL ROLE service_role')
    cur.execute('SAVEPOINT private_denial')
    with pytest.raises(Exception,match='permission denied'):
        cur.execute('SELECT public.reconcile_stopped_model_call(%s)',(request['request_id'],))
    cur.execute('ROLLBACK TO SAVEPOINT private_denial')
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE model_egress')
    for _ in range(2):
        cur.execute('SELECT public.reconcile_stopped_model_call(%s)',(request['request_id'],))
        assert cur.fetchone()[0]==('ok' if settled else 'error')
    cur.execute('RESET ROLE')
    cur.execute('SELECT sum(estimated_neurons) FROM core_pytest.neuron_ledger')
    assert cur.fetchone()[0]==cost
    result=recovery.reconcile(cur,request_id=request['request_id'],stage='transcribe',schema='core_pytest')
    assert result['processing_status']==('transcribed' if settled else 'pending_enrichment')
