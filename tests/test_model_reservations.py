"""Shared reservation SQL, on rollback-only disposable schemas (ADR-0146)."""
import uuid
import pytest
from tests._location_fixture import apply_chain
from tests._sql_fixture import connect, requires_disposable

pytestmark = requires_disposable
MODEL = '@cf/meta/llama-3.1-8b-instruct'

@pytest.fixture
def cur():
    conn = connect()
    try:
        cursor = conn.cursor()
        apply_chain(cursor)
        yield cursor
    finally:
        conn.rollback()
        conn.close()

def reserve(cur, cost=10, request_id=None, digest='a'*64):
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
                (request_id or uuid.uuid4(), MODEL, 'plan', cost, None, 20, digest))
    return cur.fetchone()[0]

def test_REQ_CAP_035_037_shared_reservation_counts_issued_and_failed_spend(cur):
    first = reserve(cur, 8900)
    assert first['allowed']
    cur.execute('SELECT public.settle_model_call(%s,%s,%s)', (first['request_id'], 'error', None))
    assert reserve(cur, 100)['allowed']
    refused = reserve(cur, 1)
    assert refused['allowed'] is False and refused['spent'] == 9000
    assert refused['reason'] == 'soft_ceiling_reached'
    cur.execute('SELECT count(*) FROM ops_pytest.egress_log')
    assert cur.fetchone()[0] == 2

def test_REQ_CAP_035_request_replay_never_authorizes_second_send(cur):
    request_id = uuid.uuid4()
    assert reserve(cur, request_id=request_id)['allowed']
    assert reserve(cur, request_id=request_id) == {
        'allowed': False, 'duplicate': True, 'reason': 'already_reserved'}
    cur.execute('SAVEPOINT changed_content')
    with pytest.raises(Exception, match='different content'):
        reserve(cur, request_id=request_id, digest='b'*64)
    cur.execute('ROLLBACK TO SAVEPOINT changed_content')
    cur.execute('SELECT count(*) FROM core_pytest.neuron_ledger')
    assert cur.fetchone()[0] == 1

@pytest.mark.parametrize('cost', [0, -1, 10001, 'NaN', 'Infinity', '-Infinity', None])
def test_REQ_CAP_037_invalid_estimate_cannot_open_budget_gate(cur, cost):
    with pytest.raises(Exception, match='invalid model reservation'):
        reserve(cur, cost)

def test_RULE_29_model_role_has_logging_capability_without_private_reads(cur):
    cur.execute('SET LOCAL ROLE model_egress')
    result = reserve(cur)
    assert result['allowed']
    cur.execute('SELECT public.settle_model_call(%s,%s,%s)', (result['request_id'], 'ok', 5))
    for query in ('SELECT * FROM core_pytest.raw_captures',
                  'SELECT * FROM core_pytest.atoms',
                  'SELECT * FROM core_pytest.neuron_ledger',
                  'SELECT * FROM ops_pytest.egress_log',
                  'SELECT public.get_capture_processing_reviews()'):
        cur.execute('SAVEPOINT forbidden_read')
        with pytest.raises(Exception, match='permission denied'):
            cur.execute(query)
        cur.execute('ROLLBACK TO SAVEPOINT forbidden_read')
    cur.execute('RESET ROLE')

@pytest.mark.parametrize('role', ['anon', 'authenticated', 'capture_ingest', 'service_role'])
def test_RULE_29_other_app_roles_cannot_reserve_model_calls(cur, role):
    cur.execute(f'SET LOCAL ROLE {role}')
    with pytest.raises(Exception, match='permission denied'):
        reserve(cur)

def test_REQ_CAP_035_settlement_cannot_rewrite_observed_outcome(cur):
    receipt = reserve(cur)
    cur.execute('SELECT public.settle_model_call(%s,%s,%s)', (receipt['request_id'], 'error', None))
    with pytest.raises(Exception, match='conflicting model settlement'):
        cur.execute('SELECT public.settle_model_call(%s,%s,%s)', (receipt['request_id'], 'ok', 1))


def test_REQ_CAP_039_same_day_deferral_cannot_use_reserved_margin(cur):
    import json
    cid = '0195dc0b-3470-7000-8000-000000000003'
    cur.execute('SELECT public.receive_capture(%s)', (json.dumps({
        'capture_id': cid, 'captured_at': '2026-09-22T12:00:00Z',
        'source': 'shortcut_text', 'payload': {'text': 'fixture only'}}),))
    cur.execute('SELECT public.record_capture_processing(%s,%s,NULL,%s,%s,%s)',
                (cid, uuid.uuid4(), 'deferred_budget', 'budget_exhausted', 'fixture'))
    assert reserve(cur, 9000)['allowed']
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
                (uuid.uuid4(), MODEL, 'extract', 1, cid, 20, 'a'*64))
    receipt = cur.fetchone()[0]
    assert receipt['allowed'] is False and receipt['ceiling'] == 9000


def test_REQ_CAP_035_unrecognized_capture_creates_no_log_or_spend(cur):
    cur.execute('SAVEPOINT unknown_capture')
    with pytest.raises(Exception, match='capture unavailable'):
        cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
                    (uuid.uuid4(), MODEL, 'extract', 1, uuid.uuid4(), 20, 'a'*64))
    cur.execute('ROLLBACK TO SAVEPOINT unknown_capture')
    cur.execute('SELECT count(*) FROM ops_pytest.egress_log')
    assert cur.fetchone()[0] == 0
    cur.execute('SELECT count(*) FROM core_pytest.neuron_ledger')
    assert cur.fetchone()[0] == 0


def test_REQ_CAP_039_old_unresolved_deferral_margin_excludes_plan_and_finished_episode(cur):
    import json
    cid = '0195dc0b-3470-7000-8000-000000000004'
    cur.execute('SELECT public.receive_capture(%s)', (json.dumps({
        'capture_id': cid, 'captured_at': '2026-09-22T12:00:00Z',
        'source': 'shortcut_text', 'payload': {'text': 'fixture only'}}),))
    cur.execute('SELECT public.record_capture_processing(%s,%s,NULL,%s,%s,%s)',
                (cid, uuid.uuid4(), 'deferred_budget', 'budget_exhausted', 'fixture'))
    event = cur.fetchone()[0]['event_id']
    # Eligibility is evaluated at a future clock without changing stored history.
    cur.execute("SELECT core_pytest.model_retry_budget_eligible(%s,'extract',clock_timestamp()+interval '2 days'),"
                "core_pytest.model_retry_budget_eligible(%s,'plan',clock_timestamp()+interval '2 days')", (cid,cid))
    assert tuple(cur.fetchone()) == (True, False)
    cur.execute('SELECT public.record_capture_processing(%s,%s,%s,%s,NULL,%s)',
                (cid, uuid.uuid4(), event, 'enriched', 'fixture'))
    event = cur.fetchone()[0]['event_id']
    cur.execute('SELECT public.record_capture_processing(%s,%s,%s,%s,%s,%s)',
                (cid, uuid.uuid4(), event, 'deferred_budget', 'budget_exhausted', 'fixture'))
    # Current-day new episode cannot borrow the finished episode's deferral.
    cur.execute("SELECT core_pytest.model_retry_budget_eligible(%s,'extract',clock_timestamp())", (cid,))
    assert cur.fetchone()[0] is False


def test_REQ_CAP_037_reservation_expiry_is_next_UTC_midnight(cur):
    import datetime as dt
    receipt = reserve(cur)
    start = dt.datetime.fromisoformat(receipt['reserved_at'])
    end = dt.datetime.fromisoformat(receipt['valid_before'])
    assert end.date() == start.astimezone(dt.timezone.utc).date()+dt.timedelta(days=1)
    assert end.astimezone(dt.timezone.utc).time() == dt.time(0)
