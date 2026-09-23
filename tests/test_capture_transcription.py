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
            'payload':{'kind':'food','media_path':CID+'/audio.m4a','media_sha256':hashlib.sha256(b'fixture').hexdigest(),
                       'duration_s':getattr(request,'param',12)}}),))
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
    cur.execute("SELECT public.settle_model_response(%s,'error',NULL,503)",(request['request_id'],))
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


def test_REQ_CAP_006_034_prepare_media_uses_immutable_reference_then_bound_request(cur,monkeypatch):
    from lib import db
    calls=[]
    def download(cid,path,digest):
        calls.append((cid,path,digest))
        return b'fixture'
    monkeypatch.setattr(db,'read_capture_media',download)
    cur.execute('SET LOCAL ROLE service_role')
    request=transcription.prepare_media(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
    assert calls==[(CID,CID+'/audio.m4a',hashlib.sha256(b'fixture').hexdigest())]
    assert request['payload']==PAYLOAD
    cur.execute('RESET ROLE')
    settle(cur,request)
    assert consume(cur,request)['applied']


def test_REQ_CAP_050_051_saved_transcript_prepares_immutable_schema_bound_extraction(cur):
    from tools.engines import capture_extraction as extraction
    req=prepare(cur)
    settle(cur,req)
    transcript=consume(cur,req)
    cur.execute('SET LOCAL ROLE service_role')
    request_id=uuid.uuid4()
    prepared=extraction.prepare(cur,request_id=request_id,capture_id=CID,schema='core_pytest')
    assert prepared['payload']['messages'][1]['content']==RESPONSE['result']['text']
    assert prepared['call_kind']=='extract'
    assert prepared['payload']['response_format']['type']=='json_schema'
    assert extraction.prepare(cur,request_id=request_id,capture_id=CID,schema='core_pytest')==prepared
    assert extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')==prepared
    cur.execute('SELECT transcription_request_id,expected_event_id,payload_sha256,estimated_neurons FROM core_pytest.capture_extraction_attempts')
    saved=cur.fetchone()
    assert str(saved[0])==req['request_id'] and saved[1]==transcript['event_id']
    assert saved[2]==hashlib.sha256(request_bytes(prepared['payload'])).hexdigest()
    assert float(saved[3])==prepared['estimated_neurons']
    # Preparing a model call neither spends budget nor fabricates extraction success.
    cur.execute('RESET ROLE')
    assert count(cur,'neuron_ledger')==1
    assert count(cur,'atoms')==0
    assert transcription.readback(cur,capture_id=CID,schema='core_pytest')['processing_status']=='transcribed'
    cur.execute('SAVEPOINT attempt_immutable')
    with pytest.raises(Exception,match='append-only'):
        cur.execute("UPDATE core_pytest.capture_extraction_attempts SET profile='food'")
    cur.execute('ROLLBACK TO SAVEPOINT attempt_immutable')
    for role in ('anon','authenticated','model_egress','capture_ingest','capture_media_upload'):
        cur.execute("SELECT has_table_privilege(%s,'core_pytest.capture_extraction_attempts','SELECT')",(role,))
        assert cur.fetchone()[0] is False


def test_REQ_CAP_050_extraction_refuses_missing_transcript_and_other_capture_identity(cur):
    from tools.engines import capture_extraction as extraction
    with pytest.raises(ValueError,match='saved transcript'):
        extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
    req=prepare(cur);settle(cur,req);consume(cur,req)
    request_id=uuid.uuid4()
    extraction.prepare(cur,request_id=request_id,capture_id=CID,schema='core_pytest')
    with pytest.raises(ValueError,match='identity reused'):
        extraction.prepare(cur,request_id=request_id,capture_id=uuid.uuid4(),schema='core_pytest')


@pytest.mark.parametrize('commit_fails',[False,True])
def test_REQ_CAP_050_private_extraction_cli_exports_only_after_confirmed_commit(cur,monkeypatch,capsys,commit_fails):
    from tools import capture_transcription as cli
    from tools.engines import capture_extraction as extraction
    req=prepare(cur);settle(cur,req);consume(cur,req)
    calls=[]
    class Probe:
        def cursor(self):return cur
        def commit(self):
            assert not capsys.readouterr().out
            calls.append('commit')
            if commit_fails:raise RuntimeError('fixture uncertain commit')
        def rollback(self):calls.append('rollback')
        def close(self):calls.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    actual=extraction.prepare
    monkeypatch.setattr(extraction,'prepare',lambda cursor,**kw:actual(cursor,schema='core_pytest',**kw))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['prepare-extraction',str(uuid.uuid4()),CID])==(1 if commit_fails else 0)
        output=capsys.readouterr()
        if commit_fails:
            assert not output.out and calls==['commit','rollback','close']
            assert 'fixture uncertain commit' not in output.err
        else:
            assert json.loads(output.out)['payload']['messages'][1]['content']==RESPONSE['result']['text']
            assert calls==['commit','close']
    finally:cur.execute('RESET SESSION AUTHORIZATION')


def extraction_request(cur):
    from tools.engines import capture_extraction as extraction
    req = prepare(cur)
    settle(cur, req)
    consume(cur, req)
    return extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')


def extraction_response(**patch):
    item = {'name':'fixture words','evidence':'fixture words','evidence_start':0,
            'quantity':None,'quantity_unit':None,'quantity_evidence':None,'quantity_evidence_start':None}
    return {'success':True,'result':{'response':{'items':[{**item,**patch}],
                                               'temporal_evidence':None,'temporal_evidence_start':None}}}


def test_REQ_CAP_053_054_057_extraction_receipt_and_fields_persist_once(cur):
    from tools.engines import capture_extraction as extraction
    req = extraction_request(cur)
    response = extraction_response()
    with pytest.raises(ValueError,match='receipt'):
        extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
    settle(cur,req,response)
    cur.execute('SET LOCAL ROLE service_role')
    result=extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
    assert result['applied'] and result['processing_status']=='extracted'
    assert extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')==result
    assert count(cur,'capture_extraction_outcomes')==1
    cur.execute("SELECT value,provenance,evidence FROM core_pytest.capture_extraction_fields WHERE name='name'")
    assert tuple(cur.fetchone())==('fixture words','extracted','fixture words')
    assert count(cur,'atoms')==0  # deterministic nutrition is the next stage
    with pytest.raises(ValueError,match='identity'):
        extraction.consume(cur,request_id=req['request_id'],response=extraction_response(name='changed'),schema='core_pytest')


def test_REQ_CAP_054_extraction_mismatch_is_null_and_stale_result_has_no_fields(cur):
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    response=extraction_response(name='invented',evidence='invented')
    settle(cur,req,response)
    result=extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
    cur.execute("SELECT value,provenance,reason FROM core_pytest.capture_extraction_fields WHERE name='name'")
    assert tuple(cur.fetchone())==(None,'inferred','span_mismatch')
    # Explicit new processing episode can prepare a request; a later head wins.
    pending=record_outcome(cur,capture_id=CID,attempt_id=uuid.uuid4(),expected_event_id=result['event_id'],
                           status='pending_enrichment',error='fixture',processor_version='fixture')
    req2=extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
    record_outcome(cur,capture_id=CID,attempt_id=uuid.uuid4(),expected_event_id=pending['event_id'],
                   status='pending_enrichment',error='superseded',processor_version='fixture')
    settle(cur,req2,response)
    late=extraction.consume(cur,request_id=req2['request_id'],response=response,schema='core_pytest')
    assert not late['applied']
    cur.execute('SELECT count(*) FROM core_pytest.capture_extraction_fields WHERE request_id=%s',(req2['request_id'],))
    assert cur.fetchone()[0]==0


@pytest.mark.parametrize('patch',[{'unexpected':1},{'quantity':500,'quantity_unit':'kcal'},
                                 {'name':'protein','quantity':11,'quantity_unit':'g',
                                  'evidence':None,'evidence_start':None}])
def test_REQ_CAP_055_056_three_invalid_extractions_quarantine_without_values(cur,patch):
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    response=extraction_response(**patch)
    for attempt in range(3):
        if attempt:
            req=extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
        settle(cur,req,response)
        cur.execute('SET LOCAL ROLE service_role')
        result=extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
        assert result['applied']
        assert result['processing_status']==('pending_enrichment' if attempt<2 else 'extraction_quarantined')
        cur.execute('RESET ROLE')
    assert count(cur,'capture_extraction_fields')==0
    assert count(cur,'atoms')==0
    cur.execute("SELECT reason FROM core_pytest.capture_processing_reviews WHERE raw_capture_id=%s",(CID,))
    assert cur.fetchone()[0]=='extraction_quarantined'
    as_owner(cur)
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SELECT public.get_capture_processing_reviews()')
    reviews=cur.fetchone()[0]
    assert len(reviews)==1 and reviews[0]['reason']=='extraction_quarantined'
    cur.execute('SELECT public.dismiss_capture_processing_review(%s)',(CID,))
    cur.execute('SELECT public.get_capture_processing_reviews()')
    assert cur.fetchone()[0]==[]
    cur.execute('RESET ROLE')
    with pytest.raises(ValueError,match='awaiting extraction'):
        extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')


@pytest.mark.parametrize('commit_fails',[False,True])
def test_REQ_CAP_053_057_extraction_consumer_cli_commits_before_readback(cur,monkeypatch,capsys,commit_fails):
    import io
    from tools import capture_transcription as cli
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    response=extraction_response()
    settle(cur,req,response)
    calls=[]
    class Probe:
        def cursor(self):return cur
        def commit(self):
            assert not capsys.readouterr().out
            calls.append('commit')
            if commit_fails:raise RuntimeError('fixture uncertain commit')
        def rollback(self):calls.append('rollback')
        def close(self):calls.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    monkeypatch.setattr(cli.sys,'stdin',io.StringIO(json.dumps({'request_id':req['request_id'],'result':response})))
    actual=extraction.consume
    monkeypatch.setattr(extraction,'consume',lambda cursor,**kw:actual(cursor,schema='core_pytest',**kw))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['consume-extraction'])==(1 if commit_fails else 0)
        output=capsys.readouterr()
        if commit_fails:
            assert not output.out and calls==['commit','rollback','close']
            assert 'fixture uncertain commit' not in output.err
        else:
            assert json.loads(output.out)['processing_status']=='extracted'
            assert calls==['commit','close']
            read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
            assert read['extraction']['request_id']==req['request_id']
            assert next(f for f in read['extraction']['fields'] if f['name']=='name')['value']=='fixture words'
            assert transcription.work_queue(cur,schema='core_pytest')['items'][0]['next_stage']=='resolve'
    finally:cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_CAP_054_057_extraction_field_failure_rolls_back_processing_and_outcome(cur):
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    response=extraction_response()
    settle(cur,req,response)
    class BrokenFieldWrite:
        def execute(self,sql,params=None):
            if 'INSERT INTO core_pytest.capture_extraction_fields' in sql:
                raise RuntimeError('fixture field write failed')
            return cur.execute(sql) if params is None else cur.execute(sql,params)
        def fetchone(self):return cur.fetchone()
    before=count(cur,'capture_processing_events')
    with pytest.raises(RuntimeError,match='field write failed'):
        extraction.consume(BrokenFieldWrite(),request_id=req['request_id'],response=response,schema='core_pytest')
    assert count(cur,'capture_processing_events')==before
    assert count(cur,'capture_extraction_outcomes')==0
    assert count(cur,'capture_extraction_fields')==0
    assert extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')['applied']
    for table in ('capture_extraction_outcomes','capture_extraction_fields'):
        cur.execute('SAVEPOINT extraction_immutable')
        with pytest.raises(Exception,match='append-only'):
            cur.execute(f'DELETE FROM core_pytest.{table}')
        cur.execute('ROLLBACK TO SAVEPOINT extraction_immutable')
        for role in ('anon','authenticated','model_egress','capture_ingest','capture_media_upload'):
            cur.execute('SELECT has_table_privilege(%s,%s,\'SELECT\')',(role,'core_pytest.'+table))
            assert cur.fetchone()[0] is False


def test_REQ_CAP_025_038_extraction_dispatch_failures_preserve_validation_retry_budget(cur):
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    for error in ('BudgetExceeded','DispatcherUnavailable','DispatchUncertain'):
        cur.execute('SET LOCAL ROLE service_role')
        result=extraction.fail(cur,request_id=req['request_id'],error_type=error,schema='core_pytest')
        assert result['applied']
        assert result['processing_status']==('deferred_budget' if error=='BudgetExceeded' else 'pending_enrichment')
        assert extraction.fail(cur,request_id=req['request_id'],error_type=error,schema='core_pytest')==result
        req=extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
        cur.execute('RESET ROLE')
    assert count(cur,'capture_transcription_outcomes')==1
    bad=extraction_response(unexpected=1)
    settle(cur,req,bad)
    result=extraction.consume(cur,request_id=req['request_id'],response=bad,schema='core_pytest')
    assert result['processing_status']=='pending_enrichment'
    with pytest.raises(ValueError,match='receipt'):
        extraction.fail(cur,request_id=req['request_id'],error_type='DispatchUncertain',provider_status=429,schema='core_pytest')


def test_REQ_CAP_034_053_current_extraction_must_match_current_transcript(cur):
    from tools.engines import capture_extraction as extraction
    req=extraction_request(cur)
    response=extraction_response()
    settle(cur,req,response)
    result=extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
    assert count(cur,'capture_extraction_current')==1
    # Construct a later immutable transcription attempt in the disposable schema.
    # Normal prepare currently refuses retranscription; this probes selection under
    # a legal append-only revised transcript, not an implemented correction UI.
    tid=str(uuid.uuid4())
    cur.execute('''INSERT INTO core_pytest.capture_transcription_attempts
        (request_id,capture_id,expected_event_id,model_id,call_kind,payload_sha256,
         duration_seconds,estimated_neurons,processor_version)
        SELECT %s,capture_id,%s,model_id,call_kind,payload_sha256,duration_seconds,
               estimated_neurons,processor_version FROM core_pytest.capture_transcription_attempts
        WHERE capture_id=%s LIMIT 1 RETURNING model_id,call_kind,estimated_neurons''',
        (tid,result['event_id'],CID))
    model,kind,cost=cur.fetchone()
    revised={'request_id':tid,'capture_id':CID,'model_id':model,'call_kind':kind,
             'estimated_neurons':float(cost),'payload':PAYLOAD}
    text={'success':True,'result':{'text':'changed fixture transcript','segments':[]}}
    settle(cur,revised,text)
    assert consume(cur,revised,text)['applied']
    assert count(cur,'capture_extraction_current')==0
    assert count(cur,'capture_extraction_fields')==4  # history retained
    assert transcription.readback(cur,capture_id=CID,schema='core_pytest')['extraction'] is None
    assert transcription.work_queue(cur,schema='core_pytest')['items'][0]['next_stage']=='extract'


def saved_food_extraction(cur, *, repeated=False, quantity=1, quantity_text='one',food_name='fixture food',temporal=None,suffix='',prefix='',quantity_unit=None):
    from tools.engines import capture_extraction as extraction
    text=quantity_text+' '+prefix+food_name+suffix + (' and '+quantity_text+' '+prefix+food_name+suffix if repeated else '')
    starts=[0,text.rindex(quantity_text)] if repeated else [0]
    if temporal:text+=' '+temporal
    transcript={'success':True,'result':{'text':text,'segments':[]}}
    req=prepare(cur)
    settle(cur,req,transcript)
    consume(cur,req,transcript)
    req=extraction.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,schema='core_pytest')
    items=[]
    for start in starts:
        items.append({'name':food_name,'evidence':prefix+food_name,'evidence_start':start+len(quantity_text)+1,
                      'quantity':quantity,'quantity_unit':quantity_unit,'quantity_evidence':quantity_text,'quantity_evidence_start':start})
    response={'success':True,'result':{'response':{'items':items,'temporal_evidence':temporal,
                                                 'temporal_evidence_start':text.index(temporal) if temporal else None}}}
    settle(cur,req,response)
    extraction.consume(cur,request_id=req['request_id'],response=response,schema='core_pytest')
    return req


def cache_resolution_food(cur, *, name='fixture food',serving_g=250,household='one fixture item'):
    cur.execute('''INSERT INTO core_pytest.foods_cache
        (canonical_name,source,source_id,brand,nutrients_per_100g,serving_g,raw)
        VALUES (%s,'usda_branded','fixture-fdc-id','Fixture Brand',%s,%s,%s)''',
        (name,json.dumps({'kcal':200,'protein_g':10}),serving_g,json.dumps({'usda_food':{
            'householdServingFullText':household,'brandOwner':'Fixture Brand'}})))


@pytest.mark.parametrize('repeated',[False,True])
def test_REQ_CAP_065_REQ_NUT_050_capture_resolves_reference_atoms_once_per_item(cur,repeated):
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur,repeated=repeated)
    cache_resolution_food(cur)
    cur.execute('SET LOCAL ROLE service_role')
    rid=str(uuid.uuid4())
    result=resolution.resolve(cur,request_id=rid,capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')
    assert result['processing_status']=='enriched'
    assert all(item['status']=='resolved' for item in result['items'])
    assert resolution.resolve(cur,request_id=rid,capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')==result
    assert resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')==result
    cur.execute('''SELECT value_low,value_point,value_high,time_precision,provenance,estimate_method
        FROM core_pytest.atoms WHERE metric_key='kcal' ORDER BY id''')
    rows=cur.fetchall()
    assert len(rows)==(2 if repeated else 1)
    for row in rows:
        assert tuple(row)==(450,500,550,'unknown','inferred','labelled')
    read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
    saved=read['extraction']['resolved_items']
    assert len(saved)==len(rows)
    assert saved[0]['time_provenance']=='defaulted'
    assert saved[0]['resolution']['source_id']=='fixture-fdc-id'
    assert saved[0]['resolution']['serving_definition']['household_measure']=='one fixture item'
    assert len(saved[0]['atoms'])==2
    assert transcription.work_queue(cur,schema='core_pytest')['items']==[]


def test_REQ_CAP_025_resolution_outage_retains_saved_extraction_and_retries(cur):
    from tools.engines import capture_resolution as resolution, nutrition
    req=saved_food_extraction(cur)
    result=resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')
    assert result['processing_status']=='pending_enrichment'
    assert result['items'][0]['reason']=='no_source_available'
    assert count(cur,'atoms')==0
    queue=transcription.work_queue(cur,schema='core_pytest')['items'][0]
    assert queue['next_stage']=='resolve' and queue['extraction_request_id']==req['request_id']
    cache_resolution_food(cur)
    assert resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')['processing_status']=='enriched'
    assert count(cur,'capture_transcription_outcomes')==1
    assert count(cur,'capture_extraction_outcomes')==1
    assert count(cur,'atoms')==2
    cur.execute("SELECT resolved_by FROM core_pytest.unresolved_items WHERE raw_capture_id=%s",(CID,))
    assert cur.fetchone()[0]=='later_source'


@pytest.mark.parametrize('commit_fails',[False,True])
def test_REQ_CAP_065_REQ_NUT_050_actual_resolution_cli_commits_before_output(cur,monkeypatch,capsys,commit_fails):
    from tools import capture_transcription as cli
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur)
    cache_resolution_food(cur)
    calls=[]
    class Probe:
        def cursor(self):return cur
        def commit(self):
            assert not capsys.readouterr().out
            calls.append('commit')
            if commit_fails:raise RuntimeError('fixture uncertain commit')
        def rollback(self):calls.append('rollback')
        def close(self):calls.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    actual=resolution.resolve
    monkeypatch.setattr(resolution,'resolve',lambda cursor,**kw:actual(cursor,schema='core_pytest',ops='ops_pytest',**kw))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['resolve',str(uuid.uuid4()),CID,req['request_id']])==(1 if commit_fails else 0)
        output=capsys.readouterr()
        if commit_fails:
            assert not output.out and calls==['commit','rollback','close']
            assert 'fixture uncertain commit' not in output.err
        else:
            assert json.loads(output.out)['processing_status']=='enriched'
            assert calls==['commit','close']
            read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
            assert read['extraction']['resolved_items'][0]['atoms'][0]['value_point']==500
    finally:cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_CAP_012_REQ_NUT_034_resolution_atom_failure_is_atomic_and_stale_identity_refuses(cur,monkeypatch):
    from tools.engines import capture_resolution as resolution, nutrition
    req=saved_food_extraction(cur)
    cache_resolution_food(cur)
    rid=str(uuid.uuid4())
    before=count(cur,'capture_processing_events')
    actual=nutrition.persist_resolution
    def fail_after_atoms(*args,**kwargs):
        actual(*args,**kwargs)
        raise RuntimeError('fixture after atom write')
    monkeypatch.setattr(nutrition,'persist_resolution',fail_after_atoms)
    with pytest.raises(RuntimeError,match='after atom'):
        resolution.resolve(cur,request_id=rid,capture_id=CID,extraction_request_id=req['request_id'],
                           schema='core_pytest',ops='ops_pytest')
    assert count(cur,'capture_processing_events')==before
    for table in ('capture_resolved_items','capture_resolution_outcomes','atoms'):
        assert count(cur,table)==0
    with pytest.raises(ValueError,match='current saved extraction'):
        resolution.resolve(cur,request_id=rid,capture_id=CID,extraction_request_id=uuid.uuid4(),
                           schema='core_pytest',ops='ops_pytest')
    monkeypatch.setattr(nutrition,'persist_resolution',actual)
    assert resolution.resolve(cur,request_id=rid,capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')['processing_status']=='enriched'


def test_REQ_NUT_001_014_050_empty_cache_source_lookup_reaches_capture_atoms(cur):
    from tools.engines import capture_resolution as resolution, nutrition_usda, nutrition_off
    from tests.test_nutrition_usda import branded_food, search_transport
    req=saved_food_extraction(cur)
    calls=[]
    food=branded_food(description='fixture food',servingSize=250,
                      householdServingFullText='one fixture item')
    assert count(cur,'foods_cache')==0
    cur.execute('SET LOCAL ROLE service_role')
    pending=resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                               schema='core_pytest',ops='ops_pytest')
    assert pending['processing_status']=='pending_enrichment' and calls==[]
    cur.execute('RESET ROLE')
    # The separate source adapter can log/fetch but cannot read private rows.
    # This role probe substitutes transport; it is not process-launch evidence.
    cur.execute('SET LOCAL ROLE reference_egress')
    row=nutrition_usda.lookup_by_name(cur,'fixture food',nutrition_usda.BRANDED,
        quota=nutrition_usda.Quota(),env={'USDA_FDC_API_KEY':'SYNTHETICKEYNOTREAL'},
        schema='core_pytest',ops='ops_pytest',_transport=search_transport([food],calls))
    cur.execute('SAVEPOINT reference_private_denial')
    with pytest.raises(Exception,match='permission denied'):
        cur.execute('SELECT count(*) FROM core_pytest.raw_captures')
    cur.execute('ROLLBACK TO SAVEPOINT reference_private_denial')
    cur.execute('RESET ROLE')
    cur.execute("SELECT has_table_privilege('reference_egress','core_pytest.raw_captures','SELECT')")
    assert cur.fetchone()[0] is False
    cur.execute('SET LOCAL ROLE service_role')
    nutrition_off.insert_cache_row(cur,row,schema='core_pytest')
    result=resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                              schema='core_pytest',ops='ops_pytest')
    assert result['processing_status']=='enriched'
    assert len(calls)==1
    read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
    saved=read['extraction']['resolved_items'][0]
    assert saved['resolution']['source_id']==str(food['fdcId'])
    assert saved['resolution']['serving_definition']['household_measure']=='one fixture item'
    assert saved['resolution']['serving_definition']['brand_owner']==food['brandOwner']
    assert saved['resolution']['source']=='usda_branded'
    assert all(a['estimate_method']=='labelled' and a['provenance']=='inferred' for a in saved['atoms'])
    assert count(cur,'foods_cache')==1
    cur.execute('RESET ROLE')
    cur.execute("SELECT count(*) FROM ops_pytest.egress_log WHERE destination='api.nal.usda.gov'")
    assert cur.fetchone()[0]==1


def test_REQ_NUT_052_fractional_count_persists_separate_method_components(cur):
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur,quantity=2.5,quantity_text='2.5')
    cache_resolution_food(cur)
    resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                       schema='core_pytest',ops='ops_pytest')
    cur.execute('''SELECT capture_component,value_low,value_point,value_high,estimate_method
        FROM core_pytest.atoms WHERE metric_key='kcal' ORDER BY capture_component''')
    assert [tuple(r) for r in cur.fetchall()]==[
        ('fraction',200,250,300,'portion_table'),('whole',900,1000,1100,'labelled')]
    cur.execute('SELECT resolution FROM core_pytest.capture_resolved_items')
    stored=cur.fetchone()[0]
    assert stored['quantity_provenance']=='defaulted'
    assert stored['serving_definition']['household_measure']=='one fixture item'


def test_REQ_CAP_062_065_defaulted_event_time_is_excluded_at_statistics_boundary(cur):
    from tools.engines import capture_resolution as resolution
    from tools import nutrition_day
    req=saved_food_extraction(cur)
    cache_resolution_food(cur)
    resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                       schema='core_pytest',ops='ops_pytest')
    cur.execute("SELECT count(*) FROM analysis_pytest.f_atom_rows('2026-09-23',clock_timestamp())")
    assert cur.fetchone()[0]==0
    cur.execute('SELECT count(*) FROM core_pytest.atoms')
    assert cur.fetchone()[0]==2  # evidence survives and remains in private readback
    items,missing=nutrition_day.read_day(cur,'2026-09-22',schema='core_pytest')
    assert items==[] and missing[0]['reason']=='defaulted_event_time_excluded'
    report=nutrition_day.build_report(items,missing,target=2000)
    assert not report['total']['numeric']
    assert not report['deficit']['resolvable']


def test_REQ_NUT_050_item_count_uses_multi_piece_household_definition(cur):
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur,quantity=2,quantity_text='two',food_name='cookies')
    cache_resolution_food(cur,name='cookies',serving_g=30,household='3 cookies')
    out=resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                           schema='core_pytest',ops='ops_pytest')
    assert out['processing_status']=='enriched'
    cur.execute("SELECT value_low,value_point,value_high,estimate_method FROM core_pytest.atoms WHERE metric_key='kcal'")
    assert tuple(cur.fetchone())==(36,40,44,'labelled')
    cur.execute('SELECT resolution FROM core_pytest.capture_resolved_items')
    assert cur.fetchone()[0]['grams']==20


def test_REQ_NUT_051_missing_item_serving_mapping_remains_retryable(cur):
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur)
    cache_resolution_food(cur,household='1 cup')
    out=resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                           schema='core_pytest',ops='ops_pytest')
    assert out['processing_status']=='pending_enrichment'
    assert out['items'][0]['reason']=='no_branded_serving'
    assert count(cur,'atoms')==0
    assert transcription.work_queue(cur,schema='core_pytest')['items'][0]['next_stage']=='resolve'


def test_REQ_CAP_064_066_verified_time_keeps_local_day_and_statistics_eligibility(cur):
    import datetime as dt
    from tools.engines import capture_resolution as resolution
    req=saved_food_extraction(cur,temporal='today at 2am')
    cache_resolution_food(cur)
    resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                       schema='core_pytest',ops='ops_pytest')
    cur.execute('SELECT subject_day,time_precision,event_time_provenance FROM core_pytest.atoms')
    assert all(tuple(r)==(dt.date(2026,9,21),'hour','extracted') for r in cur.fetchall())
    cur.execute("SELECT count(*) FROM analysis_pytest.f_atom_rows('2026-09-23',clock_timestamp())")
    assert cur.fetchone()[0]==2


def test_REQ_CAP_062_REQ_NUT_052_defaulted_fraction_is_disclosed_and_excluded_from_statistics(cur):
    from tools.engines import capture_resolution as resolution
    from tools import nutrition_day
    req=saved_food_extraction(cur,quantity=2.5,quantity_text='2.5',temporal='today at 2am')
    cache_resolution_food(cur)
    resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,extraction_request_id=req['request_id'],
                       schema='core_pytest',ops='ops_pytest')
    cur.execute("SELECT capture_component,quantity_provenance FROM core_pytest.atoms WHERE metric_key='kcal' ORDER BY capture_component")
    assert [tuple(r) for r in cur.fetchall()]==[('fraction','defaulted'),('whole','extracted')]
    cur.execute("SELECT value FROM analysis_pytest.f_atom_rows('2026-09-23',clock_timestamp()) WHERE metric='kcal'")
    assert [r[0] for r in cur.fetchall()]==[1000]
    items,missing=nutrition_day.read_day(cur,'2026-09-21',schema='core_pytest')
    assert len(items)==1 and len(missing)==1
    assert missing[0]['reason']=='defaulted_quantity_excluded'
    report=nutrition_day.build_report(items,missing)
    assert 'defaulted quantity' in nutrition_day.render(report,'2026-09-21')
