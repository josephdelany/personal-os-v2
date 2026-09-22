"""Actual receipt RPC, disposable schema rows, entire transaction rolled back."""
import json
from pathlib import Path
import pytest
from tests._location_fixture import apply_chain
from tests._sql_fixture import connect, requires_disposable
from tools.run_migration import split_statements

pytestmark = requires_disposable
CID = '0195dc0b-3470-7000-8000-000000000001'
GOOD = dict(capture_id=CID, captured_at='2026-09-22T08:00:00-04:00',
            source='shortcut_text', payload={'text': 'fixture only'})

@pytest.fixture(scope='module')
def connection():
    conn = connect()
    try:
        conn.cursor().execute('CREATE ROLE authenticator NOLOGIN')
        apply_chain(conn.cursor())
        yield conn
    finally:
        conn.rollback()
        conn.close()

@pytest.fixture
def cur(connection):
    cursor = connection.cursor()
    cursor.execute('SAVEPOINT capture_case')
    try:
        yield cursor
    finally:
        cursor.execute('ROLLBACK TO SAVEPOINT capture_case')

def receive(cur, raw):
    cur.execute('SELECT public.receive_capture(%s)', (raw,))
    return cur.fetchone()[0]

def test_REQ_CAP_006_011_018_receipt_and_stored_client_identity(cur):
    cur.execute('SELECT clock_timestamp()')
    before = cur.fetchone()[0]
    assert receive(cur, json.dumps(GOOD)) == {'status': 'created', 'capture_id': CID}
    cur.execute('SELECT capture_id, captured_at, source, trust_level, payload, '
                'processing_status, recorded_at BETWEEN %s AND clock_timestamp() FROM core_pytest.raw_captures',
                (before,))
    cid, occurred, source, trust, payload, state, stamped = cur.fetchone()
    assert str(cid) == CID and occurred.hour == 12
    assert (source, trust, payload, state, stamped) == (
        'shortcut_text', 'trusted', GOOD['payload'], 'received', True)

def test_REQ_CAP_016_017_duplicate_comes_from_insert_and_preserves_original(cur):
    assert receive(cur, json.dumps(GOOD))['status'] == 'created'
    assert receive(cur, json.dumps({**GOOD, 'payload': {'text': 'different retry'}})) == {
        'status': 'duplicate', 'capture_id': CID}
    cur.execute('SELECT payload FROM core_pytest.raw_captures')
    rows = cur.fetchall()
    assert len(rows) == 1 and rows[0][0] == GOOD['payload']

@pytest.mark.parametrize('field', ['capture_id', 'captured_at'])
def test_REQ_CAP_007_missing_identity_retains_exact_body_without_capture(cur, field):
    raw = json.dumps({k: v for k, v in GOOD.items() if k != field}, indent=2)
    assert receive(cur, raw) == {'status': 'rejected', 'error': 'missing_identity_fields'}
    cur.execute('SELECT raw_body, reason FROM ops_pytest.ingest_rejections')
    assert tuple(cur.fetchone()) == (raw, 'missing_identity_fields')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures')
    assert cur.fetchone()[0] == 0

@pytest.mark.parametrize('patch,reason', [
    ({'capture_id': 'not-uuid'}, 'invalid_capture_id'),
    ({'capture_id': CID.replace('-7000-', '-4000-')}, 'invalid_capture_id'),
    ({'captured_at': '2026-09-22T12:00:00'}, 'invalid_captured_at'),
    ({'captured_at': '2026-02-31T12:00:00Z'}, 'invalid_captured_at'),
    ({'source': 'location'}, 'invalid_source'),
    ({'source': None}, 'invalid_source'),
    ({'payload': None}, 'missing_payload'),
])
def test_REQ_CAP_006_018_invalid_contract_is_retained_and_never_inserted(cur, patch, reason):
    raw = json.dumps({**GOOD, **patch})
    assert receive(cur, raw) == {'status': 'rejected', 'error': reason}
    cur.execute('SELECT raw_body FROM ops_pytest.ingest_rejections')
    assert cur.fetchone()[0] == raw
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures')
    assert cur.fetchone()[0] == 0

@pytest.mark.parametrize('raw,reason', [('{broken', 'invalid_json'),
                                      (r'{"payload":"\u0000"}', 'invalid_json'),
                                      (r'{"payload":"\ud800"}', 'invalid_json'),
                                      ('{"payload":1e1000000}', 'invalid_json'),
                                      ('null', 'invalid_envelope'), ('[]', 'invalid_envelope')])
def test_REQ_CAP_007_malformed_body_retained(cur, raw, reason):
    assert receive(cur, raw) == {'status': 'rejected', 'error': reason}
    cur.execute('SELECT raw_body FROM ops_pytest.ingest_rejections')
    assert cur.fetchone()[0] == raw

def test_REQ_CAP_008_009_rpc_only_service_role_and_rejections_not_public(cur):
    for role, allowed in [('anon', False), ('authenticated', False),
                          ('service_role', True), ('capture_ingest', True)]:
        cur.execute("SELECT has_function_privilege(%s, 'public.receive_capture(text)', 'EXECUTE')",
                    (role,))
        assert cur.fetchone()[0] is allowed
    cur.execute('SET LOCAL ROLE capture_ingest')
    assert receive(cur, json.dumps(GOOD))['status'] == 'created'
    cur.execute('RESET ROLE')
    for role in ['anon', 'authenticated', 'capture_ingest']:
        cur.execute("SELECT has_table_privilege(%s, 'ops_pytest.ingest_rejections', 'SELECT')", (role,))
        assert cur.fetchone()[0] is False

def test_REQ_CAP_009_ingress_role_has_no_private_read_or_other_public_rpc(cur):
    cur.execute("""SELECT n.nspname, c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname IN ('core_pytest','ops_pytest','restricted_pytest','analysis_pytest')
          AND c.relkind IN ('r','v','m','p')
          AND has_table_privilege('capture_ingest',c.oid,'SELECT')""")
    assert cur.fetchall() == ()
    cur.execute("""SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND has_function_privilege('capture_ingest',p.oid,'EXECUTE')
          AND p.proname <> 'receive_capture'
          AND NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid='pg_proc'::regclass
            AND d.objid=p.oid AND d.refclassid='pg_extension'::regclass AND d.deptype='e')""")
    exposed = cur.fetchall()
    assert not exposed, repr(exposed)

def test_REQ_CAP_009_ingress_role_scope_and_collision_fail_closed(cur):
    cur.execute("SELECT rolsuper, rolinherit, rolcreaterole, rolcreatedb, rolcanlogin, "
                "rolreplication, rolbypassrls FROM pg_roles WHERE rolname='capture_ingest'")
    assert not any(cur.fetchone())
    cur.execute("SELECT count(*) FROM pg_auth_members WHERE member='capture_ingest'::regrole")
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT pg_has_role('authenticator','capture_ingest','MEMBER')")
    assert cur.fetchone()[0] is True
    first = split_statements((Path(__file__).resolve().parents[1] /
                              'migrations/0075_capture_receipts.sql').read_text())[0]
    cur.execute('SAVEPOINT role_collision')
    with pytest.raises(Exception, match='already exists'):
        cur.execute(first)
    cur.execute('ROLLBACK TO SAVEPOINT role_collision')

def test_REQ_CAP_012_receipt_never_requires_mutable_raw_capture(cur):
    receive(cur, json.dumps(GOOD))
    cur.execute('SAVEPOINT immutable')
    with pytest.raises(Exception, match='append-only'):
        cur.execute("UPDATE core_pytest.raw_captures SET processing_status='enriched'")
    cur.execute('ROLLBACK TO SAVEPOINT immutable')
