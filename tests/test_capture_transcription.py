"""Actual immutable transcript persistence in a rolled-back full-chain twin."""
import hashlib
import json
import uuid
import pytest
from lib.model_contract import request_bytes
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable
from tools.engines import capture_transcription as transcription
from tools.engines.capture_processing import record_outcome

pytestmark = requires_disposable
CID = '0195dc0b-3470-7000-8000-000000000003'
PAYLOAD = {'audio':'Zml4dHVyZQ==','language':'en','vad_filter':True,'condition_on_previous_text':False}
RESPONSE = {'success':True,'result':{'text':'fixture words','segments':[{'start':0,'end':1.2,'text':'fixture words'}]}}

@pytest.fixture
def cur(monkeypatch, request):
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL'):
        monkeypatch.delenv(key,raising=False)
    conn = connect()
    try:
        cursor = conn.cursor()
        apply_chain(cursor)
        cursor.execute('SELECT public.receive_capture(%s)',(json.dumps({
            'capture_id':CID,'captured_at':'2026-09-22T08:00:00-04:00','source':'shortcut_voice',
            'payload':{'kind':'food','media_path':'fixture/audio','duration_s':getattr(request,'param',12)}}),))
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def prepare(cur, request_id=None):
    return transcription.prepare(cur,request_id=request_id or uuid.uuid4(),capture_id=CID,
                                 payload=PAYLOAD,schema='core_pytest')


def settle(cur,request,response=RESPONSE):
    body = request_bytes(request['payload'])
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
        (request['request_id'],request['model_id'],request['call_kind'],request['estimated_neurons'],
         request['capture_id'],len(body),hashlib.sha256(body).hexdigest()))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SELECT public.settle_model_call(%s,%s,%s,%s)',
        (request['request_id'],'ok',len(request_bytes(response)),hashlib.sha256(request_bytes(response)).hexdigest()))


def consume(cur,request,response=RESPONSE):
    return transcription.consume(cur,request_id=request['request_id'],response=response,schema='core_pytest')


def count(cur,table):
    cur.execute(f'SELECT count(*) FROM core_pytest.{table}')
    return cur.fetchone()[0]


def test_REQ_CAP_034_persisted_transcript_has_timings_and_immutable_raw(cur):
    cur.execute('SELECT to_jsonb(r) FROM core_pytest.raw_captures r WHERE capture_id=%s',(CID,))
    before = cur.fetchone()[0]
    request = prepare(cur)
    assert request['estimated_neurons'] == 9.326
    settle(cur,request)
    result = consume(cur,request)
    assert result['applied'] and result['processing_status']=='transcribed'
    assert consume(cur,request)==result
    assert count(cur,'capture_transcription_outcomes')==1
    cur.execute('SELECT transcript,segments FROM core_pytest.capture_transcription_current WHERE capture_id=%s',(CID,))
    row = cur.fetchone()
    assert row[0]=='fixture words' and row[1]==RESPONSE['result']['segments']
    cur.execute('SELECT to_jsonb(r) FROM core_pytest.raw_captures r WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==before
    # Later extraction failure does not erase usable transcript evidence.
    record_outcome(cur,capture_id=CID,attempt_id=uuid.uuid4(),expected_event_id=result['event_id'],
        status='pending_enrichment',error='extract_failed',processor_version='fixture')
    assert count(cur,'capture_transcription_current')==1
    with pytest.raises(ValueError,match='usable transcript'):
        prepare(cur)


def test_REQ_CAP_034_late_response_retained_without_current_promotion(cur):
    first, second = prepare(cur),prepare(cur)
    settle(cur,first)
    settle(cur,second)
    winner = consume(cur,second)
    late = consume(cur,first)
    assert winner['applied'] and not late['applied']
    assert count(cur,'capture_transcription_outcomes')==2
    cur.execute('SELECT request_id FROM core_pytest.capture_transcription_current')
    assert str(cur.fetchone()[0])==second['request_id']


def test_REQ_CAP_034_missing_receipt_and_response_substitution_refused(cur):
    request=prepare(cur)
    with pytest.raises(ValueError,match='receipt'):
        consume(cur,request)
    settle(cur,request)
    with pytest.raises(ValueError,match='receipt'):
        consume(cur,request,{'success':True,'result':{'text':'substituted','segments':[]}})
    assert count(cur,'capture_processing_events')==0
    consume(cur,request)
    with pytest.raises(ValueError,match='identity'):
        consume(cur,request,{'success':True,'result':{'text':'changed','segments':[]}})


@pytest.mark.parametrize('response,error',[
    ({'success':True,'result':{'text':'','segments':[]}},'empty_transcript'),
    ({'success':True,'result':{'text':'words','segments':[{'start':2,'end':1}]}},'invalid_transcription'),
    ({'success':False,'result':{}},'invalid_transcription'),
])
def test_REQ_CAP_043_045_invalid_or_empty_response_remains_pending(cur,response,error):
    request=prepare(cur)
    settle(cur,request,response)
    result=consume(cur,request,response)
    assert result['processing_status']=='pending_enrichment'
    assert count(cur,'capture_transcription_current')==0
    cur.execute('SELECT last_error FROM core_pytest.capture_processing_current WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==error
    assert consume(cur,request,response)==result
    if error == 'empty_transcript':
        as_owner(cur)
        cur.execute('SET LOCAL ROLE authenticated')
        cur.execute('SELECT public.get_capture_processing_reviews()')
        reviews = cur.fetchone()[0]
        assert len(reviews)==1 and reviews[0]['reason']=='empty_transcript'
        cur.execute('RESET ROLE')


def test_REQ_CAP_025_038_failure_and_budget_are_persisted_idempotently(cur):
    request=prepare(cur)
    failed=transcription.fail(cur,request_id=request['request_id'],error_type='BudgetExceeded',schema='core_pytest')
    assert failed['processing_status']=='deferred_budget'
    assert transcription.fail(cur,request_id=request['request_id'],error_type='BudgetExceeded',schema='core_pytest')==failed
    retry=prepare(cur)
    failed2=transcription.fail(cur,request_id=retry['request_id'],error_type='DispatcherUnavailable',schema='core_pytest')
    assert failed2['applied'] and failed2['processing_status']=='pending_enrichment'
    assert count(cur,'capture_transcription_outcomes')==2


def test_REQ_CAP_034_service_role_consumer_and_model_read_denial(cur):
    cur.execute('SET LOCAL ROLE service_role')
    request=prepare(cur)
    cur.execute('RESET ROLE')
    settle(cur,request)
    cur.execute('SET LOCAL ROLE service_role')
    assert consume(cur,request)['applied']
    cur.execute('RESET ROLE')
    cur.execute('SAVEPOINT permissions')
    cur.execute('SET LOCAL ROLE model_egress')
    with pytest.raises(Exception):
        cur.execute('SELECT * FROM core_pytest.capture_transcription_current')
    cur.execute('ROLLBACK TO SAVEPOINT permissions')


def test_REQ_CAP_034_transcript_outcomes_reject_mutation(cur):
    request=prepare(cur)
    settle(cur,request)
    consume(cur,request)
    for sql in ["UPDATE core_pytest.capture_transcription_outcomes SET transcript='changed'",
                'DELETE FROM core_pytest.capture_transcription_outcomes',
                'TRUNCATE core_pytest.capture_transcription_outcomes']:
        cur.execute('SAVEPOINT immutable')
        with pytest.raises(Exception):
            cur.execute(sql)
        cur.execute('ROLLBACK TO SAVEPOINT immutable')
    assert count(cur,'capture_transcription_outcomes')==1


def test_REQ_CAP_034_persistence_failure_cannot_leave_orphan_success(cur,monkeypatch):
    request=prepare(cur)
    settle(cur,request)
    class Fault:
        def execute(self,sql,args=None):
            if 'INSERT INTO core_pytest.capture_transcription_outcomes' in sql:
                raise RuntimeError('fixture insertion failure')
            return cur.execute(sql,args) if args is not None else cur.execute(sql)
        def fetchone(self): return cur.fetchone()
    with pytest.raises(RuntimeError,match='fixture'):
        consume(Fault(),request)
    assert count(cur,'capture_processing_events')==0
    assert count(cur,'capture_transcription_outcomes')==0
    assert consume(cur,request)['applied']


def test_REQ_CAP_025_provider_status_requires_bound_receipt(cur):
    request=prepare(cur)
    params=dict(request_id=request['request_id'],error_type='DispatchUncertain',provider_status=503,schema='core_pytest')
    with pytest.raises(ValueError,match='receipt'):
        transcription.fail(cur,**params)
    body=request_bytes(request['payload'])
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
        (request['request_id'],request['model_id'],request['call_kind'],request['estimated_neurons'],CID,
         len(body),hashlib.sha256(body).hexdigest()))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SET LOCAL ROLE model_egress')
    cur.execute("SELECT public.settle_model_call(%s,'error',NULL,NULL)",(request['request_id'],))
    cur.execute('SELECT public.record_model_http_failure(%s,503)',(request['request_id'],))
    cur.execute('RESET ROLE')
    result=transcription.fail(cur,**params)
    assert result['applied'] and result['processing_status']=='pending_enrichment'
    assert transcription.fail(cur,**params)==result
    cur.execute('SELECT last_error FROM core_pytest.capture_processing_current WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]=='503'
    with pytest.raises(ValueError,match='receipt'):
        transcription.fail(cur,**{**params,'provider_status':429})


@pytest.mark.parametrize('cur',[1],indirect=True)
def test_REQ_CAP_036_fractional_estimate_uses_one_owner_and_exact_receipt(cur):
    from lib import egress
    from tools.engines.capture_budget import estimated_neurons
    request=prepare(cur)
    assert request['estimated_neurons']==egress.audio_neurons(1)==estimated_neurons(1)
    cur.execute('SELECT estimated_neurons FROM core_pytest.capture_transcription_attempts')
    from decimal import Decimal
    assert cur.fetchone()[0]==Decimal(str(request['estimated_neurons']))
    settle(cur,request)
    assert consume(cur,request)['applied']


def test_REQ_CAP_026_initial_queue_and_extraction_resume_use_current_transcript(cur):
    queue=transcription.work_queue(cur,schema='core_pytest')['items']
    assert len(queue)==1 and queue[0]['next_stage']=='transcribe'
    assert transcription.readback(cur,capture_id=CID,schema='core_pytest')['transcription'] is None
    request=prepare(cur)
    settle(cur,request)
    consume(cur,request)
    queue=transcription.work_queue(cur,schema='core_pytest')['items']
    assert len(queue)==1 and queue[0]['next_stage']=='extract'
    read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
    assert read['processing_status']=='transcribed'
    assert read['transcription']['text']=='fixture words'
    assert read['transcription']['request_id']==request['request_id']


def test_REQ_CAP_034_private_cli_commits_before_output_and_reads_stored_result(cur,monkeypatch,capsys):
    import io
    from tools import capture_transcription as cli
    request=prepare(cur)
    settle(cur,request)
    events=[]
    class Probe:
        def cursor(self): return cur
        def commit(self): events.append('commit') # ordering probe; fixtures never commit
        def rollback(self): events.append('rollback')
        def close(self): events.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    consume_actual=transcription.consume
    read_actual=transcription.readback
    monkeypatch.setattr(cli.engine,'consume',lambda cursor,**kw:consume_actual(cursor,schema='core_pytest',**kw))
    monkeypatch.setattr(cli.engine,'readback',lambda cursor,**kw:read_actual(cursor,schema='core_pytest',**kw))
    monkeypatch.setattr(cli.sys,'stdin',io.StringIO(json.dumps({'request_id':request['request_id'],'result':RESPONSE})))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['consume'])==0
        assert events==['commit','close']
        result=json.loads(capsys.readouterr().out)
        assert result['applied'] and result['processing_status']=='transcribed'
        assert cli.main(['readback',CID])==0
        assert json.loads(capsys.readouterr().out)['transcription']['text']=='fixture words'
    finally:
        cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_CAP_034_private_cli_refuses_model_identity(cur,monkeypatch,capsys):
    from tools import capture_transcription as cli
    class Probe:
        def cursor(self): return cur
        def commit(self): raise AssertionError('must not commit')
        def rollback(self): pass # fixture rollback remains outer owner
        def close(self): pass
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    cur.execute('SET SESSION AUTHORIZATION model_egress')
    try:
        assert cli.main(['queue'])==1
        output=capsys.readouterr()
        assert not output.out
        assert json.loads(output.err)['error_type']=='PermissionError'
    finally:
        cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_CAP_026_queue_paginates_past_failed_heads_without_new_arrival_starvation(cur):
    # 102 old pending captures plus the received fixture. No fixture commits.
    cur.execute("""INSERT INTO core_pytest.raw_captures
        (capture_id,captured_at,source,trust_level,payload,processing_status)
        SELECT gen_random_uuid(),TIMESTAMPTZ '2026-09-20T12:00:00Z',
            'shortcut_voice','untrusted','{}','pending_enrichment'
        FROM generate_series(1,102)""")
    first=transcription.work_queue(cur,schema='core_pytest')
    assert len(first['items'])==100 and first['next_cursor'] is not None
    # A late backdated arrival must not change this run's cohort.
    late=uuid.uuid4()
    cur.execute("""INSERT INTO core_pytest.raw_captures
        (capture_id,captured_at,source,trust_level,payload,processing_status)
        VALUES (%s,TIMESTAMPTZ '2026-09-21T12:00:00Z','shortcut_voice','untrusted','{}','received')""",(late,))
    second=transcription.work_queue(cur,cursor=first['next_cursor'],schema='core_pytest')
    assert len(second['items'])==3 and second['next_cursor'] is None
    ids=[item['capture_id'] for page in (first,second) for item in page['items']]
    assert len(set(ids))==103 and CID in ids and str(late) not in ids
    again=transcription.work_queue(cur,cursor=first['next_cursor'],schema='core_pytest')
    assert again==second
