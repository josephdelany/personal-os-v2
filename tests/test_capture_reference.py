"""Saved capture -> isolated source receipt -> private cache -> atoms, rollback-only."""
import copy
import hashlib
import io
import json
import uuid
import pytest

from lib.model_contract import request_bytes
from tests._sql_fixture import requires_disposable
from tests.test_capture_transcription import cur, CID, saved_food_extraction, count
from tests.test_nutrition_usda import branded_food
from tools.engines import capture_reference as reference, reference_dispatch, capture_resolution
from tools.engines import capture_transcription as transcription, nutrition, nutrition_usda as usda
from tools.engines.capture_processing import record_outcome

pytestmark = requires_disposable
NAME = 'Synthetic Crunch Bar'


@pytest.fixture(autouse=True)
def private_env(monkeypatch):
    for key in reference_dispatch.PRIVATE_CREDENTIALS+('REFERENCE_EGRESS_DB_URL','USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY'):
        monkeypatch.delenv(key,raising=False)


def prepared(cur, *, source='usda_branded'):
    extraction = saved_food_extraction(cur,food_name=NAME)
    request = reference.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,
        extraction_request_id=extraction['request_id'],item_index=0,source=source,schema='core_pytest')
    return extraction,request


def source_result():
    row=usda.cache_row(branded_food(householdServingFullText='1 bar'),'usda_branded')
    row['fetched_at']=row['fetched_at'].isoformat()
    return {'status':'resolved','row':row}


def settled(cur,request,response, *, payload_hash=None,provider_status=None):
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
        (request['request_id'],request['source'],payload_hash or hashlib.sha256(request_bytes(request)).hexdigest(),len(request_bytes(request))))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SELECT public.settle_reference_call(%s,%s,%s,%s)',
        (request['request_id'],hashlib.sha256(request_bytes(response)).hexdigest(),len(request_bytes(response)),provider_status))


def consume(cur,request,response):
    return reference.consume(cur,request_id=request['request_id'],response=response,schema='core_pytest',ops='ops_pytest')


def test_REQ_NUT_002_003_004_saved_item_preparation_reuses_identity_and_exports_no_transcript(cur):
    extraction,request=prepared(cur)
    again=reference.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,
        extraction_request_id=extraction['request_id'],item_index=0,source='usda_branded',schema='core_pytest')
    assert request==again
    assert set(request)=={'request_id','source','query','brand','barcode'}
    assert request['query']==NAME
    assert count(cur,'capture_reference_attempts')==1
    with pytest.raises(ValueError,match='identity reused'):
        reference.prepare(cur,request_id=request['request_id'],capture_id=CID,
            extraction_request_id=extraction['request_id'],item_index=0,source='off_search',schema='core_pytest')
    with pytest.raises(ValueError,match='verified saved food'):
        reference.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,
            extraction_request_id=extraction['request_id'],item_index=99,source='off_search',schema='core_pytest')


def test_REQ_NUT_003_004_005_receipt_bound_cache_alias_and_existing_atom_resolution(cur):
    extraction,request=prepared(cur)
    response=source_result()
    settled(cur,request,response)
    cur.execute('SET LOCAL ROLE service_role')
    out=consume(cur,request,response)
    assert out['status']=='resolved' and out['applied']
    assert consume(cur,request,response)==out
    assert count(cur,'foods_cache')==count(cur,'food_aliases')==1
    cur.execute('SELECT verbatim FROM core_pytest.food_aliases')
    assert cur.fetchone()[0]==NAME
    cur.execute('SELECT c.fetched_at=s.recorded_at FROM core_pytest.foods_cache c JOIN core_pytest.capture_reference_outcomes o USING(food_id) JOIN ops_pytest.reference_results s USING(request_id)')
    assert cur.fetchone()[0]
    done=capture_resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=CID,
        extraction_request_id=extraction['request_id'],schema='core_pytest',ops='ops_pytest')
    assert done['processing_status']=='enriched'
    read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
    assert read['reference_attempts'][0]['food_id']==out['food_id']
    atoms=read['extraction']['resolved_items'][0]['atoms']
    kcal=next(a for a in atoms if a['metric_key']=='kcal')
    assert (float(kcal['value_low']),float(kcal['value_point']),float(kcal['value_high']))==(162,180,198)


@pytest.mark.parametrize('mutation',['response','request_hash','computed_nutrient','wrong_food','http_failure'])
def test_RULE_09_29_REQ_NUT_025_substitution_cannot_publish_cache(cur,mutation):
    _,request=prepared(cur)
    response=source_result()
    if mutation=='computed_nutrient': response['row']['nutrients_per_100g']['kcal']=999
    if mutation=='wrong_food':
        row=usda.cache_row(branded_food(description='another item'),'usda_branded')
        row['fetched_at']=row['fetched_at'].isoformat()
        response={'status':'resolved','row':row}
    settled(cur,request,response,payload_hash='0'*64 if mutation=='request_hash' else None,
            provider_status=503 if mutation=='http_failure' else None)
    if mutation=='response': response['row']['nutrients_per_100g']['kcal']=999
    with pytest.raises((ValueError,usda.UsdaUnusable)):
        consume(cur,request,response)
    assert count(cur,'foods_cache')==count(cur,'capture_reference_outcomes')==0


def test_REQ_CAP_012_REQ_NUT_003_004_cache_alias_and_outcome_write_roll_back_together(cur,monkeypatch):
    _,request=prepared(cur)
    response=source_result()
    settled(cur,request,response)
    def broken(*args,**kwargs):raise RuntimeError('fixture alias failure')
    monkeypatch.setattr(nutrition,'remember_alias',broken)
    with pytest.raises(RuntimeError): consume(cur,request,response)
    assert count(cur,'foods_cache')==count(cur,'food_aliases')==count(cur,'capture_reference_outcomes')==0
    assert count(cur,'capture_reference_attempts')==1


def test_REQ_CAP_053_060_stale_processing_state_does_not_publish_a_source_row(cur):
    _,request=prepared(cur)
    response=source_result()
    settled(cur,request,response)
    cur.execute('SELECT event_id FROM core_pytest.capture_processing_current WHERE capture_id=%s',(CID,))
    record_outcome(cur,capture_id=CID,attempt_id=uuid.uuid4(),expected_event_id=cur.fetchone()[0],
                   status='failed',error='fixture_terminal',processor_version='fixture')
    out=consume(cur,request,response)
    assert out['status']=='stale' and not out['applied']
    assert count(cur,'foods_cache')==0


@pytest.mark.parametrize('status,reason',[('unresolved','no_exact_name_match'),('deferred','request_failed')])
def test_REQ_NUT_024_027_source_refusal_stays_distinct_without_fake_cache(cur,status,reason):
    _,request=prepared(cur)
    response={'status':status,'reason':reason}
    settled(cur,request,response)
    out=consume(cur,request,response)
    assert out['status']==status and out['reason']==reason and out['food_id'] is None
    assert count(cur,'foods_cache')==0
    assert transcription.readback(cur,capture_id=CID,schema='core_pytest')['processing_status']=='extracted'


def test_REQ_NUT_012_interrupted_source_receipt_can_be_reconciled_then_reprepared(cur):
    extraction,request=prepared(cur)
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
        (request['request_id'],request['source'],hashlib.sha256(request_bytes(request)).hexdigest(),len(request_bytes(request))))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SET LOCAL ROLE service_role')
    out=consume(cur,request,None)
    assert out['status']=='deferred' and out['reason']=='reference_dispatch_uncertain'
    assert consume(cur,request,None)==out
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM ops_pytest.reference_requests')
    assert cur.fetchone()[0]==1
    cur.execute("SELECT reason,blocked_until>clock_timestamp() FROM ops_pytest.rate_limit_cooldowns WHERE meter='usda'")
    assert tuple(cur.fetchone())==('dispatch_uncertain',True)
    next_request=reference.prepare(cur,request_id=uuid.uuid4(),capture_id=CID,
        extraction_request_id=extraction['request_id'],item_index=0,source='usda_branded',schema='core_pytest')
    assert next_request['request_id']!=request['request_id']
    assert count(cur,'capture_reference_attempts')==2
    assert count(cur,'foods_cache')==0


def test_REQ_NUT_012_reconciliation_preserves_settled_receipt_and_refuses_unknown(cur):
    _,request=prepared(cur)
    response=source_result()
    settled(cur,request,response)
    cur.execute('SET LOCAL ROLE service_role')
    cur.execute('SELECT public.reconcile_reference_call(%s)',(request['request_id'],))
    cur.execute('SELECT outcome,response_sha256 FROM ops_pytest.reference_results WHERE request_id=%s',
                (request['request_id'],))
    assert tuple(cur.fetchone())==('settled',hashlib.sha256(request_bytes(response)).hexdigest())
    cur.execute('SAVEPOINT unknown_reference')
    with pytest.raises(Exception,match='reference reservation required'):
        cur.execute('SELECT public.reconcile_reference_call(%s)',(str(uuid.uuid4()),))
    cur.execute('ROLLBACK TO SAVEPOINT unknown_reference')
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM ops_pytest.reference_results')
    assert cur.fetchone()[0]==1


def test_REQ_NUT_003_changed_existing_cache_is_not_misreported_as_the_new_source_result(cur):
    _,request=prepared(cur)
    response=source_result()
    settled(cur,request,response)
    row=copy.deepcopy(response['row'])
    row['nutrients_per_100g']['kcal']=300
    from tools.engines.nutrition_off import insert_cache_row
    insert_cache_row(cur,row,schema='core_pytest')
    with pytest.raises(ValueError,match='cache version conflict'):
        consume(cur,request,response)
    assert count(cur,'foods_cache')==1
    assert count(cur,'food_aliases')==count(cur,'capture_reference_outcomes')==0


@pytest.mark.parametrize('commit_fails',[False,True])
def test_RULE_29_REQ_NUT_003_private_prepare_cli_waits_for_commit(cur,monkeypatch,capsys,commit_fails):
    from tools import capture_transcription as cli
    extraction=saved_food_extraction(cur,food_name=NAME)
    calls=[]
    class Probe:
        def cursor(self):return cur
        def commit(self):
            assert not capsys.readouterr().out
            calls.append('commit')
            if commit_fails:raise RuntimeError('fixture secret')
        def rollback(self):calls.append('rollback')
        def close(self):calls.append('close')
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    actual=reference.prepare
    monkeypatch.setattr(reference,'prepare',lambda cursor,**kw:actual(cursor,schema='core_pytest',**kw))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['prepare-reference',str(uuid.uuid4()),CID,extraction['request_id'],'0','usda_branded'])==(1 if commit_fails else 0)
        output=capsys.readouterr()
        if commit_fails:
            assert not output.out and calls==['commit','rollback','close']
            assert 'fixture secret' not in output.err
        else:
            assert json.loads(output.out)['query']==NAME
            assert calls==['commit','close']
    finally:cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_NUT_012_RULE_29_lost_settled_output_recovers_without_redispatch(cur):
    _,request=prepared(cur)
    response=source_result()
    cur.execute('SET LOCAL ROLE reference_egress')
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
        (request['request_id'],request['source'],hashlib.sha256(request_bytes(request)).hexdigest(),len(request_bytes(request))))
    assert cur.fetchone()[0]['allowed']
    body=request_bytes(response).decode('utf-8')
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(request['request_id'],body,None))
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(request['request_id'],body,None))
    cur.execute('SAVEPOINT forbidden_hash_only')
    with pytest.raises(Exception,match='permission denied'):
        cur.execute('SELECT public.settle_reference_call(%s,%s,%s,%s)',
                    (request['request_id'],hashlib.sha256(request_bytes(response)).hexdigest(),len(body),None))
    cur.execute('ROLLBACK TO SAVEPOINT forbidden_hash_only')
    cur.execute('SAVEPOINT unreadable_body')
    with pytest.raises(Exception,match='permission denied'):
        cur.execute('SELECT response_body FROM ops_pytest.reference_response_bodies')
    cur.execute('ROLLBACK TO SAVEPOINT unreadable_body')
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE service_role')
    # Simulate dropped stdout: private recovery receives only the request UUID.
    result=consume(cur,request,None)
    assert result['status']=='resolved' and result['applied']
    assert consume(cur,request,None)==result
    assert consume(cur,request,response)==result
    assert count(cur,'foods_cache')==count(cur,'capture_reference_outcomes')==1
    cur.execute('SELECT count(*) FROM ops_pytest.reference_requests')
    assert cur.fetchone()[0]==1
    cur.execute('SAVEPOINT immutable_body')
    with pytest.raises(Exception):
        cur.execute("UPDATE ops_pytest.reference_response_bodies SET response_body='{}'")
    cur.execute('ROLLBACK TO SAVEPOINT immutable_body')
    cur.execute('RESET ROLE')


def test_REQ_NUT_012_invalid_body_cannot_leave_a_settlement_receipt(cur):
    _,request=prepared(cur)
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
        (request['request_id'],request['source'],hashlib.sha256(request_bytes(request)).hexdigest(),len(request_bytes(request))))
    assert cur.fetchone()[0]['allowed']
    for body in ('[]','null','invalid',' '*4194305):
        cur.execute('SAVEPOINT invalid_body')
        with pytest.raises(Exception):
            cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(request['request_id'],body,None))
        cur.execute('ROLLBACK TO SAVEPOINT invalid_body')
        cur.execute('SELECT count(*) FROM ops_pytest.reference_results')
        assert cur.fetchone()[0]==0
        cur.execute('SELECT count(*) FROM ops_pytest.reference_response_bodies')
        assert cur.fetchone()[0]==0


def test_REQ_CAP_060_REQ_NUT_003_actual_cli_handoff_resolves_saved_food(cur,monkeypatch,capsys):
    from tools import capture_transcription as private_cli, reference_egress as source_cli
    extraction=saved_food_extraction(cur,food_name=NAME)
    commits=[]
    class Probe:
        # Deliberately rollback-only fixture: ordering evidence, not real commit
        # survival or independent-process proof.
        def cursor(self):return cur
        def commit(self):
            assert not capsys.readouterr().out
            commits.append('commit')
        def rollback(self):raise AssertionError('unexpected rollback')
        def close(self):pass
    monkeypatch.setattr(private_cli.db,'connect',lambda:Probe())
    monkeypatch.setattr(source_cli.db,'connect_reference_egress',lambda:Probe())
    prepare_actual,consume_actual,resolve_actual=reference.prepare,reference.consume,capture_resolution.resolve
    dispatch_actual=reference_dispatch.dispatch
    monkeypatch.setattr(reference,'prepare',lambda cursor,**kw:prepare_actual(cursor,schema='core_pytest',**kw))
    monkeypatch.setattr(reference,'consume',lambda cursor,**kw:consume_actual(cursor,schema='core_pytest',ops='ops_pytest',**kw))
    monkeypatch.setattr(capture_resolution,'resolve',lambda cursor,**kw:resolve_actual(cursor,schema='core_pytest',ops='ops_pytest',**kw))
    sends=[]
    def transport(*args):
        assert len(commits)==2  # prepare and source reservation precede network
        sends.append(1)
        return json.dumps({'foods':[branded_food(householdServingFullText='1 bar')]}).encode()
    monkeypatch.setattr(reference_dispatch,'dispatch',lambda conn,request:dispatch_actual(
        conn,request,env={'USDA_FDC_API_KEY':'fixture'},ops='ops_pytest',config='config',_transport=transport))
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert private_cli.main(['prepare-reference',str(uuid.uuid4()),CID,extraction['request_id'],'0','usda_branded'])==0
        prepared_output=capsys.readouterr().out
        request=json.loads(prepared_output)
    finally:cur.execute('RESET SESSION AUTHORIZATION')
    cur.execute('SET SESSION AUTHORIZATION reference_egress')
    try:
        monkeypatch.setattr(source_cli.sys,'stdin',io.StringIO(prepared_output))
        assert source_cli.main()==0
        dispatched=json.loads(capsys.readouterr().out)
        assert dispatched['request_id']==request['request_id']
    finally:cur.execute('RESET SESSION AUTHORIZATION')
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        # Drop the response deliberately; invoke the actual private recovery CLI.
        assert private_cli.main(['reconcile-reference',request['request_id']])==0
        recovered=json.loads(capsys.readouterr().out)
        assert recovered['status']=='resolved'
        assert private_cli.main(['resolve',str(uuid.uuid4()),CID,extraction['request_id']])==0
        assert json.loads(capsys.readouterr().out)['processing_status']=='enriched'
        read=transcription.readback(cur,capture_id=CID,schema='core_pytest')
        atoms=read['extraction']['resolved_items'][0]['atoms']
        kcal=next(a for a in atoms if a['metric_key']=='kcal')
        assert (float(kcal['value_low']),float(kcal['value_point']),float(kcal['value_high']))==(162,180,198)
        assert len(sends)==1 and len(commits)==5
    finally:cur.execute('RESET SESSION AUTHORIZATION')
