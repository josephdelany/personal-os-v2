"""Private prepare/model receipt/consume path on disposable, rollback-only SQL."""
import datetime as dt
import hashlib
import json
import uuid
import pytest
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable
from tools.engines import ask_jobs as jobs
from lib.model_contract import request_bytes

pytestmark = requires_disposable

@pytest.fixture
def cur(monkeypatch):
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL'):
        monkeypatch.delenv(key, raising=False)
    conn = connect()
    try:
        cursor = conn.cursor()
        apply_chain(cursor)
        as_owner(cursor)
        cursor.execute("""INSERT INTO core_pytest.metric_registry
            (metric_key,display_name,family,unit,state_class) VALUES
            ('steps','Steps','test','count','total') ON CONFLICT DO NOTHING""")
        cursor.execute("""INSERT INTO config.panel_aggregation
            (metric,method,method_version,note) VALUES ('steps','sum','fixture','rollback fixture')
            ON CONFLICT DO NOTHING""")
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def prepare(cur, job_id=None):
    return jobs.prepare(cur, job_id=job_id or uuid.uuid4(), question='summarize steps please',
                        as_of=dt.date(2026,9,21), schema='core_pytest')


def settle(cur, request, response):
    raw = request_bytes(request['payload'])
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,NULL,%s,%s)',
        (request['request_id'],request['model_id'],request['call_kind'],request['estimated_neurons'],
         len(raw),hashlib.sha256(raw).hexdigest()))
    assert cur.fetchone()[0]['allowed']
    cur.execute('SELECT public.settle_model_call(%s,%s,%s,%s)',
                (request['request_id'],'ok',20,hashlib.sha256(request_bytes(response)).hexdigest()))


def test_REQ_ASK_004_006_prepared_model_result_executes_and_persists_once(cur):
    # Real raw -> atom -> panel -> computation path, all inside the rolled-back twin.
    for offset in range(28):
        day = dt.date(2026,9,21)-dt.timedelta(days=offset)
        cid = uuid.uuid4()
        occurred = dt.datetime.combine(day,dt.time(12),dt.timezone.utc)
        cur.execute("""INSERT INTO core_pytest.raw_captures
            (capture_id,source,captured_at,payload,trust_level)
            VALUES (%s,'file_import',%s,'{}','trusted')""", (cid,occurred))
        cur.execute("""INSERT INTO core_pytest.atoms
            (id,raw_capture_id,kind,metric_key,occurred_at,subject_day,subject_day_rule_version,
             presence,value_low,value_point,value_high,estimate_method,unit,state_class,
             value_type,trust_level,provenance,evidence_span,code_version)
            VALUES (%s,%s,'activity_sample','steps',%s,%s,'v1','observed',100,100,100,
             'measured','count','total','numeric','trusted','extracted',
             'apple_health:fixture;source=fixture Apple Watch','fixture')""",
            (uuid.uuid4(),cid,occurred,day))
    job_id = uuid.uuid4()
    prepared = prepare(cur, job_id)
    assert prepared['state'] == 'needs_model'
    assert set(prepared['request']) == {'request_id','model_id','call_kind','estimated_neurons','payload'}
    # JSON reordering across persistence/transport cannot change reservation identity.
    assert jobs.readback(cur,job_id=job_id,schema='core_pytest') == prepared
    late_capture = uuid.uuid4()
    cur.execute("""INSERT INTO core_pytest.raw_captures
        (capture_id,source,captured_at,payload,trust_level)
        VALUES (%s,'file_import',now(),'{}','trusted')""", (late_capture,))
    cur.execute("""INSERT INTO core_pytest.atoms
        (id,raw_capture_id,kind,metric_key,occurred_at,subject_day,subject_day_rule_version,
         recorded_at,presence,value_low,value_point,value_high,estimate_method,unit,state_class,
         value_type,trust_level,provenance,evidence_span,code_version)
        SELECT gen_random_uuid(),%s,kind,metric_key,occurred_at,subject_day,subject_day_rule_version,
         clock_timestamp(),'observed',9000,9000,9000,estimate_method,unit,state_class,
         value_type,trust_level,provenance,evidence_span,code_version
        FROM core_pytest.atoms ORDER BY subject_day DESC LIMIT 1""", (late_capture,))
    response = {'result': {'response': json.dumps({'op':'describe','metric':'steps'})}}
    settle(cur, prepared['request'], response)
    result = jobs.consume(cur, request_id=prepared['request']['request_id'],response=response,schema='core_pytest')
    assert result['state'] == 'complete' and result['provenance'] == 'planned'
    assert result['answer']['as_of'] == '2026-09-21'
    assert result['answer']['result']['max'] == 100, 'later import must not enter delayed response'
    # Current reads see the later insert, while the saved job keeps its earlier cutoff.
    cur.execute("SELECT value FROM analysis_pytest.f_daily_panel(DATE '2026-09-21') "
                "WHERE metric='steps' AND day=DATE '2026-09-21'")
    assert cur.fetchone()[0] == 9100
    cur.execute("SELECT public.ask('how is my Steps',DATE '2026-09-21')")
    assert cur.fetchone()[0]['result']['max'] == 9100
    cur.execute("""INSERT INTO config.domains
        (domain_key,pillar,display_name,hero_metric,capture_action,sort_order)
        VALUES ('fixture_steps','movement','Fixture Steps','steps','fixture',999)""")
    cur.execute("SELECT latest_value FROM analysis_pytest.f_domain_status(DATE '2026-09-21') "
                "WHERE domain_key='fixture_steps'")
    assert cur.fetchone()[0] == 9100
    cur.execute("""SELECT value FROM analysis_pytest.f_panel_provenance
        ('steps',DATE '2026-09-21',DATE '2026-09-21',DATE '2026-09-21')""")
    assert cur.fetchone()[0] == 9100
    cur.execute('SELECT clock_timestamp()')
    before_search = cur.fetchone()[0]
    cur.execute("SELECT public.search_record('fixture',50)")
    searched = cur.fetchone()[0]
    assert dt.datetime.fromisoformat(searched['known_at']) >= before_search

    cur.execute('SELECT count(*) FROM core_pytest.computations')
    computations = cur.fetchone()[0]
    assert computations > 0
    assert jobs.consume(cur,request_id=prepared['request']['request_id'],response=response,schema='core_pytest') == result
    cur.execute('SELECT count(*) FROM core_pytest.computations')
    assert cur.fetchone()[0] == computations
    assert jobs.readback(cur,job_id=job_id,schema='core_pytest') == result


def test_REQ_ASK_008_031_invalid_plans_stop_at_five_with_nearest_and_no_tier(cur):
    prepared = prepare(cur)
    for attempt in range(1,6):
        request = prepared['request']
        settle(cur, request, {'op':'invented_execute_sql'})
        prepared = jobs.consume(cur, request_id=request['request_id'],
            response={'op':'invented_execute_sql'},schema='core_pytest')
        assert prepared['state'] == ('needs_model' if attempt < 5 else 'complete')
    assert prepared['answer']['refusal'] == 'I cannot compute that.'
    assert prepared['answer']['nearest'] and 'tier' not in prepared['answer']
    cur.execute('SELECT count(*) FROM core_pytest.ask_planning_attempts')
    assert cur.fetchone()[0] == 5


def test_RULE_29_unsettled_request_cannot_be_consumed_as_model_success(cur):
    request = prepare(cur)['request']
    with pytest.raises(ValueError,match='matching settled'):
        jobs.consume(cur,request_id=request['request_id'],response={'op':'describe','metric':'steps'},schema='core_pytest')


def test_REQ_ASK_006_same_job_identity_is_bound_to_question_and_date(cur):
    job_id = uuid.uuid4()
    original = prepare(cur, job_id)
    assert prepare(cur, job_id) == original
    with pytest.raises(ValueError,match='different question or date'):
        jobs.prepare(cur,job_id=job_id,question='another question',as_of=dt.date(2026,9,21),schema='core_pytest')


def test_RULE_29_model_role_cannot_read_private_planning_state(cur):
    prepare(cur)
    cur.execute('SET LOCAL ROLE model_egress')
    with pytest.raises(Exception,match='permission denied'):
        cur.execute('SELECT * FROM core_pytest.ask_planning_jobs')


def test_RULE_29_response_digest_must_match_dispatcher_settlement(cur):
    request = prepare(cur)['request']
    settle(cur, request, {'op':'describe','metric':'steps'})
    with pytest.raises(ValueError,match='matching settled'):
        jobs.consume(cur,request_id=request['request_id'],response={'op':'last','metric':'steps'},schema='core_pytest')


def test_REQ_ASK_004_private_consumer_service_role_can_consume_receipt(cur):
    request = prepare(cur)['request']
    response = {'op':'describe','metric':'steps'}
    settle(cur,request,response)
    cur.execute('SET LOCAL ROLE service_role')
    result = jobs.consume(cur,request_id=request['request_id'],response=response,schema='core_pytest')
    assert result['state'] == 'complete'
    cur.execute('RESET ROLE')


def test_RULE_15_dispatch_failure_persists_original_fallback_without_retry(cur):
    job_id = uuid.uuid4()
    request = prepare(cur,job_id)['request']
    result = jobs.fail(cur,request_id=request['request_id'],error_type='BudgetExceeded',schema='core_pytest')
    assert result['state'] == 'complete'
    assert result['provenance'] == 'deterministic_after_planner_refused'
    assert jobs.readback(cur,job_id=job_id,schema='core_pytest') == result
    assert jobs.fail(cur,request_id=request['request_id'],error_type='BudgetExceeded',schema='core_pytest') == result
    cur.execute('SELECT count(*) FROM core_pytest.ask_planning_attempts')
    assert cur.fetchone()[0] == 1


def test_REQ_ASK_004_private_preparer_service_role_can_read_registry(cur):
    cur.execute('SET LOCAL ROLE service_role')
    assert prepare(cur)['state'] == 'needs_model'
    cur.execute('RESET ROLE')


def test_REQ_ASK_008_malformed_field_types_are_rejected_as_an_attempt(cur):
    request = prepare(cur)['request']
    response = {'op': ['describe'], 'metric': 'steps'}
    settle(cur,request,response)
    result = jobs.consume(cur,request_id=request['request_id'],response=response,schema='core_pytest')
    assert result['state'] == 'needs_model'
    assert 'malformed_plan_fields' in result['request']['payload']['messages'][-1]['content']


def test_RULE_29_private_CLI_prepares_via_actual_service_identity(cur,monkeypatch,capsys):
    from tools import ask_jobs as cli
    calls = []
    class Probe:
        def cursor(self): return cur
        def commit(self): calls.append('commit')  # No fixture commit.
        def rollback(self): calls.append('rollback')
        def close(self): calls.append('close')
    real = jobs.prepare
    def twin(cursor, **kwargs): return real(cursor,schema='core_pytest',**kwargs)
    monkeypatch.setattr(cli.engine,'prepare',twin)
    monkeypatch.setattr(cli.db,'connect',lambda:Probe())
    cur.execute('SET SESSION AUTHORIZATION service_role')
    try:
        assert cli.main(['prepare',str(uuid.uuid4()),'summarize steps please','--as-of','2026-09-21']) == 0
    finally:
        cur.execute('RESET SESSION AUTHORIZATION')
    output = capsys.readouterr()
    assert json.loads(output.out)['state'] == 'needs_model'
    assert calls == ['commit','close'] and output.err == ''


def test_RULE_29_private_CLI_rejects_model_identity_before_setting_owner_claim(cur):
    from tools import ask_jobs as cli
    cur.execute('SET SESSION AUTHORIZATION model_egress')
    try:
        with pytest.raises(PermissionError,match='private backend'):
            cli.owner_context(cur)
    finally:
        cur.execute('RESET SESSION AUTHORIZATION')


def test_REQ_ASK_006_pending_request_parameters_survive_configuration_change(cur,monkeypatch):
    job_id = uuid.uuid4()
    prepared = prepare(cur,job_id)
    monkeypatch.setattr(jobs.planner,'MODEL_ID','@cf/fixture/changed-model')
    monkeypatch.setattr(jobs.planner,'ESTIMATED_NEURONS_PER_PLAN',30)
    assert jobs.readback(cur,job_id=job_id,schema='core_pytest') == prepared
    response = {'op':'describe','metric':'steps'}
    settle(cur,prepared['request'],response)
    assert jobs.consume(cur,request_id=prepared['request']['request_id'],response=response,
                        schema='core_pytest')['state'] == 'complete'


def test_RULE_15_29_privacy_refusal_uses_saved_fallback(cur):
    from lib import egress
    request = prepare(cur)['request']
    with pytest.raises(egress.PayloadRefused):
        egress.screen_payload({'is_home':True})
    result = jobs.fail(cur,request_id=request['request_id'],error_type='PayloadRefused',schema='core_pytest')
    assert result['state'] == 'complete'
    assert result['answer']['planner'] == {'used':False,'reason':'PayloadRefused'}
    cur.execute('SELECT count(*) FROM core_pytest.neuron_ledger')
    assert cur.fetchone()[0] == 0
