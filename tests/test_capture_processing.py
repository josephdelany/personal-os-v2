"""Persisted lifecycle through its real Python consumer; rollback-only fixtures."""
import datetime as dt
import json
import uuid
import pytest

from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable
from tools.engines.capture_processing import pending_work, record_outcome, maintain_reviews
from tools import capture_processing as cli

pytestmark = requires_disposable
CID = '0195dc0b-3470-7000-8000-000000000002'

@pytest.fixture
def connection():
    conn = connect()
    try:
        apply_chain(conn.cursor())
        yield conn
    finally:
        conn.rollback()
        conn.close()


def test_REQ_CAP_026_027_deferred_only_work_has_no_invented_failure_age(cur):
    record(cur, status='deferred_budget', error='budget_exhausted')
    assert state(cur)[3] is None
    due = pending_work(cur, now=dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=8),
                       schema='core_pytest')
    assert len(due) == 1 and due[0]['stalled'] is False
    assert due[0]['processing_status'] == 'deferred_budget'


def test_REQ_CAP_025_existing_terminal_ingestion_state_is_preserved(cur):
    other = uuid.uuid4()
    cur.execute("""INSERT INTO core_pytest.raw_captures
        (capture_id,captured_at,source,trust_level,payload,processing_status)
        VALUES (%s,now(),'file_import','untrusted','{}','enriched')""", (other,))
    cur.execute('SELECT processing_status,event_id FROM core_pytest.capture_processing_current '
                'WHERE capture_id=%s', (other,))
    assert tuple(cur.fetchone()) == ('enriched', None)
    assert pending_work(cur, now=dt.datetime.now(dt.timezone.utc), schema='core_pytest') == []


def maintain(cur, now):
    return maintain_reviews(cur, now=now)


def test_REQ_CAP_027_review_is_persisted_once_and_returned_by_owner_API(cur):
    first = record(cur)
    since = state(cur)[3]
    assert maintain(cur, since+dt.timedelta(hours=72))['reviews_added'] == 0
    report = maintain(cur, since+dt.timedelta(hours=73))
    assert report['reviews_added'] == 1 and report['enrichment_attempts'] == 0
    assert maintain(cur, since+dt.timedelta(hours=74))['reviews_added'] == 0
    as_owner(cur)
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SELECT public.get_capture_processing_reviews()')
    reviews = cur.fetchone()[0]
    assert len(reviews) == 1
    assert reviews[0]['capture_id'] == CID
    assert reviews[0]['reason'] == 'enrichment_stalled'
    assert reviews[0]['processing_event_id'] == first['event_id']
    cur.execute('RESET ROLE')
    cur.execute('SELECT detail FROM ops_pytest.runs ORDER BY started_at')
    details = [row[0] for row in cur.fetchall()]
    assert len(details) == 3
    assert CID not in json.dumps(details)
    assert all(row['scope'] == 'review_maintenance_only' for row in details)


def test_REQ_CAP_027_RULE_27_recovery_hides_review_and_dismissal_survives_new_episode(cur):
    first = record(cur)
    since = state(cur)[3]
    maintain(cur, since+dt.timedelta(hours=73))
    success = record(cur, status='enriched', error=None, expected=first['event_id'])
    as_owner(cur)
    cur.execute('SELECT public.get_capture_processing_reviews()')
    assert cur.fetchone()[0] == []
    # Dismiss an existing historical review: it must never be raised again.
    cur.execute('SELECT public.dismiss_capture_processing_review(%s)', (CID,))
    assert cur.fetchone()[0] is True
    cur.execute('SELECT public.dismiss_capture_processing_review(%s)', (CID,))
    assert cur.fetchone()[0] is True
    record(cur, expected=success['event_id'])
    new_since = state(cur)[3]
    assert maintain(cur, new_since+dt.timedelta(hours=73))['reviews_added'] == 0
    cur.execute('SELECT public.get_capture_processing_reviews()')
    assert cur.fetchone()[0] == []
    cur.execute('SELECT count(*) FROM core_pytest.capture_processing_review_dismissals')
    assert cur.fetchone()[0] == 1


def test_REQ_CAP_027_new_undismissed_episode_is_not_shown_before_its_own_review(cur):
    first = record(cur)
    maintain(cur, state(cur)[3]+dt.timedelta(hours=73))
    success = record(cur, status='enriched', error=None, expected=first['event_id'])
    cur.execute('SELECT pg_sleep(0.01)')
    record(cur, expected=success['event_id'])
    as_owner(cur)
    cur.execute('SELECT public.get_capture_processing_reviews()')
    assert cur.fetchone()[0] == []
    assert maintain(cur, state(cur)[3]+dt.timedelta(hours=73))['reviews_added'] == 1
    cur.execute('SELECT public.get_capture_processing_reviews()')
    assert len(cur.fetchone()[0]) == 1


@pytest.mark.parametrize('statement,params', [
    ('SELECT public.get_capture_processing_reviews()', ()),
    ('SELECT public.dismiss_capture_processing_review(%s)', (CID,)),
])
def test_REQ_CAP_027_review_API_rejects_nonowner(cur, statement, params):
    cur.execute("SELECT set_config('request.jwt.claims','{}',true)")
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SAVEPOINT nonowner')
    with pytest.raises(Exception, match='owner only'):
        cur.execute(statement, params)
    cur.execute('ROLLBACK TO SAVEPOINT nonowner')
    cur.execute('RESET ROLE')


@pytest.mark.parametrize('commit', [False, True])
def test_REQ_CAP_027_CLI_executes_SQL_and_obeys_transaction_mode(cur, monkeypatch, capsys, commit):
    record(cur)
    now = state(cur)[3]+dt.timedelta(hours=73)
    calls = []
    cur.execute('SAVEPOINT cli_boundary')

    class TransactionProbe:
        # Tests never commit fixtures. This tests CLI transaction intent; SQL
        # behavior is real and the outer fixture still rolls everything back.
        def cursor(self): return cur
        def commit(self): calls.append('commit')
        def rollback(self):
            calls.append('rollback')
            cur.execute('ROLLBACK TO SAVEPOINT cli_boundary')
        def close(self): calls.append('close')

    monkeypatch.setattr(cli.db, 'connect', lambda: TransactionProbe())
    monkeypatch.setattr(cli, 'utc_now', lambda: now)
    args = ['--commit'] if commit else []
    assert cli.main(args) == 0
    out = capsys.readouterr()
    report = json.loads(out.out)
    assert report['committed'] is commit
    assert report['reviews_added'] == (1 if commit else 0)
    assert calls == (['commit','close'] if commit else ['rollback','close'])
    assert CID not in out.out and 'fixture only' not in out.out
    cur.execute('SELECT count(*) FROM core_pytest.capture_processing_reviews')
    assert cur.fetchone()[0] == (1 if commit else 0)

@pytest.fixture
def cur(connection):
    cursor = connection.cursor()
    cursor.execute('SAVEPOINT processing_case')
    raw = json.dumps(dict(capture_id=CID, captured_at='2026-09-22T08:00:00-04:00',
                          source='shortcut_text', payload={'text': 'fixture only'}))
    cursor.execute('SELECT public.receive_capture(%s)', (raw,))
    try:
        yield cursor
    finally:
        cursor.execute('ROLLBACK TO SAVEPOINT processing_case')

def record(cur, status='pending_enrichment', expected=None, attempt=None, error='503'):
    return record_outcome(cur, capture_id=CID, attempt_id=attempt or uuid.uuid4(),
                          expected_event_id=expected, status=status, error=error,
                          processor_version='fixture-v1')

def state(cur):
    cur.execute('SELECT processing_status,last_error,event_id,pending_since '
                'FROM core_pytest.capture_processing_current WHERE capture_id=%s', (CID,))
    return tuple(cur.fetchone())

def test_REQ_CAP_025_failure_is_history_and_raw_remains_unchanged(cur):
    cur.execute('SELECT row_to_json(r) FROM core_pytest.raw_captures r WHERE capture_id=%s', (CID,))
    original = cur.fetchone()[0]
    assert state(cur) == ('received', None, None, None)
    event = record(cur)
    assert event['applied'] and not event['duplicate']
    status, error, event_id, since = state(cur)
    assert (status, error, event_id) == ('pending_enrichment', '503', event['event_id'])
    assert since is not None
    cur.execute('SELECT row_to_json(r) FROM core_pytest.raw_captures r WHERE capture_id=%s', (CID,))
    assert cur.fetchone()[0] == original

def test_REQ_CAP_026_027_repeated_failure_keeps_pending_age_and_exact_72_hour_boundary(cur):
    first = record(cur)
    since = state(cur)[3]
    cur.execute('SELECT pg_sleep(0.02)')
    latest = record(cur, expected=first['event_id'], error='429')
    assert state(cur)[3] == since
    cur.execute('SELECT recorded_at FROM core_pytest.capture_processing_events WHERE event_id=%s',
                (latest['event_id'],))
    assert cur.fetchone()[0] > since
    at_boundary = pending_work(cur, now=since+dt.timedelta(hours=72), schema='core_pytest')
    assert len(at_boundary) == 1 and at_boundary[0]['stalled'] is False
    overdue = pending_work(cur, now=since+dt.timedelta(hours=72,seconds=1), schema='core_pytest')
    assert overdue[0]['stalled'] is True
    assert overdue[0]['event_id'] == latest['event_id']
    assert overdue[0]['last_error'] == '429'

def test_REQ_CAP_025_026_success_clears_pending_and_late_failure_cannot_replace_it(cur):
    first = record(cur)
    success = record(cur, status='enriched', error=None, expected=first['event_id'])
    late = record(cur, error='502', expected=first['event_id'])
    assert late['applied'] is False
    assert state(cur) == ('enriched', None, success['event_id'], None)
    assert pending_work(cur, now=dt.datetime.now(dt.timezone.utc), schema='core_pytest') == []
    cur.execute('SELECT count(*) FROM core_pytest.capture_processing_events WHERE raw_capture_id=%s',
                (CID,))
    assert cur.fetchone()[0] == 3, 'late failure is retained, not discarded'

def test_REQ_CAP_025_attempt_retry_is_idempotent_but_changed_outcome_is_rejected(cur):
    attempt = uuid.uuid4()
    first = record(cur, attempt=attempt)
    duplicate = record(cur, attempt=attempt)
    assert duplicate == {**first, 'duplicate': True}
    cur.execute('SAVEPOINT changed_attempt')
    with pytest.raises(Exception, match='different outcome'):
        record(cur, attempt=attempt, error='502')
    cur.execute('ROLLBACK TO SAVEPOINT changed_attempt')
    cur.execute('SELECT count(*) FROM core_pytest.capture_processing_events WHERE raw_capture_id=%s', (CID,))
    assert cur.fetchone()[0] == 1

def test_REQ_CAP_025_history_is_immutable_and_ingress_cannot_forge_processing(cur):
    record(cur)
    for verb in ('UPDATE core_pytest.capture_processing_events SET last_error=NULL',
                 'DELETE FROM core_pytest.capture_processing_events',
                 'TRUNCATE core_pytest.capture_processing_events, core_pytest.capture_processing_reviews'):
        cur.execute('SAVEPOINT mutation')
        with pytest.raises(Exception, match='append-only'):
            cur.execute(verb)
        cur.execute('ROLLBACK TO SAVEPOINT mutation')
    for role in ('anon','authenticated','capture_ingest'):
        cur.execute("SELECT has_function_privilege(%s, "
                    "'public.record_capture_processing(uuid,uuid,bigint,text,text,text)', 'EXECUTE')", (role,))
        assert cur.fetchone()[0] is False

def test_REQ_CAP_026_027_budget_deferral_preserves_unresolved_failure_age(cur):
    first = record(cur)
    since = state(cur)[3]
    cur.execute('SELECT pg_sleep(0.02)')
    deferred = record(cur, status='deferred_budget', error='budget_exhausted',
                      expected=first['event_id'])
    assert state(cur)[3] == since
    due = pending_work(cur, now=since+dt.timedelta(hours=73), schema='core_pytest')
    assert len(due) == 1 and due[0]['stalled'] is True
    record(cur, expected=deferred['event_id'])
    assert state(cur)[3] == since

@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_REQ_CAP_025_026_unsupported_snapshot_isolation_is_rejected(isolation):
    conn = connect()
    try:
        conn.rollback()
        cursor = conn.cursor()
        cursor.execute(f'SET TRANSACTION ISOLATION LEVEL {isolation}')
        apply_chain(cursor)
        cursor.execute('SELECT public.receive_capture(%s)', (json.dumps(dict(
            capture_id=CID, captured_at='2026-09-22T12:00:00Z', source='shortcut_text',
            payload={'text': 'fixture only'})),))
        with pytest.raises(Exception, match='READ COMMITTED'):
            record(cursor)
    finally:
        conn.rollback()
        conn.close()


@pytest.mark.parametrize('role', ['anon', 'authenticated', 'capture_ingest'])
def test_REQ_CAP_027_untrusted_roles_cannot_run_maintenance(cur, role):
    cur.execute(f'SET LOCAL ROLE {role}')
    for query, params in (
        ('SELECT public.maintain_capture_processing(%s)', (dt.datetime.now(dt.timezone.utc),)),
        ('SELECT public.fail_capture_processing_maintenance(%s)', ('RuntimeError',)),
    ):
        cur.execute('SAVEPOINT denied_maintenance')
        with pytest.raises(Exception, match='permission denied'):
            cur.execute(query, params)
        cur.execute('ROLLBACK TO SAVEPOINT denied_maintenance')
    cur.execute('RESET ROLE')


@pytest.mark.parametrize('commit', [False, True])
def test_REQ_CAP_027_CLI_failure_rolls_back_reviews_and_sanitizes_heartbeat(
        cur, monkeypatch, capsys, commit):
    record(cur)
    now = state(cur)[3] + dt.timedelta(hours=73)
    cur.execute('SAVEPOINT failing_cli')
    calls = []

    class TransactionProbe:
        def cursor(self): return cur
        def rollback(self):
            calls.append('rollback')
            cur.execute('ROLLBACK TO SAVEPOINT failing_cli')
        def commit(self): calls.append('commit')  # Outer fixture never commits.
        def close(self): calls.append('close')

    real_maintenance = cli.processing.maintain_reviews

    def fail_after_write(cursor, *, now):
        real_maintenance(cursor, now=now)
        raise RuntimeError('fixture private body and credential must not escape')

    monkeypatch.setattr(cli.db, 'connect', lambda: TransactionProbe())
    monkeypatch.setattr(cli, 'utc_now', lambda: now)
    monkeypatch.setattr(cli.processing, 'maintain_reviews', fail_after_write)
    assert cli.main(['--commit'] if commit else []) == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert json.loads(output.err) == {'status': 'error', 'error_type': 'RuntimeError'}
    assert calls == (['rollback', 'commit', 'close'] if commit else ['rollback', 'close'])
    cur.execute('SELECT count(*) FROM core_pytest.capture_processing_reviews')
    assert cur.fetchone()[0] == 0
    cur.execute('SELECT status, rows_written, detail FROM ops_pytest.runs')
    rows = cur.fetchall()
    if commit:
        assert len(rows) == 1
        assert tuple(rows[0][:2]) == ('error', 0)
        assert rows[0][2] == {'code_version': 'capture-processing-v1', 'error_type': 'RuntimeError'}
    else:
        assert len(rows) == 0
