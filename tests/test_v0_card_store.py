"""Source storage contracts in rollback-only disposable twins; no real imports."""
import base64
import json
import uuid
import pytest
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable
from tools.importers.v0_card_store import import_bytes

pytestmark = requires_disposable
ACCOUNT = '0195dc0b-3470-7000-8000-000000000401'
OTHER = '0195dc0b-3470-7000-8000-000000000402'
HEADER = 'Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n'
A = '09/20/2026,09/21/2026,fixture merchant,Food,Sale,-10.00,\n'
B = '09/22/2026,,fixture second,Travel,Sale,-20.00,note\n'


@pytest.fixture(scope='module')
def connection():
    conn = connect()
    try:
        apply_chain(conn.cursor())
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def cur(connection):
    c = connection.cursor()
    c.execute('SAVEPOINT card_case')
    try:
        yield c
    finally:
        c.execute('ROLLBACK TO SAVEPOINT card_case')
        c.execute('RELEASE SAVEPOINT card_case')


def save(cur, rows=A+B, account=ACCOUNT):
    return import_bytes(cur, (HEADER+rows).encode(), account, schema='core_pytest')


def test_REQ_FIN_010_014_RULE_02_exact_receipt_source_fields_and_account_scope(cur):
    saved = save(cur)
    assert save(cur) == saved
    assert saved['source_rows'] == saved['distinct_rows'] == 2
    assert save(cur, account=OTHER)['file_id'] != saved['file_id']
    cur.execute('SELECT payload FROM core_pytest.raw_captures WHERE capture_id=%s', (saved['file_id'],))
    assert base64.b64decode(cur.fetchone()[0]['source_base64']) == (HEADER+A+B).encode()
    cur.execute('''SELECT amount::text,occurred_on::text,posted_on::text,source_record
        FROM core_pytest.v0_card_rows WHERE file_id=%s ORDER BY source_row''', (saved['file_id'],))
    rows = cur.fetchall()
    assert rows[0][:3] == ['-10.00','2026-09-20','2026-09-21']
    assert rows[1][2] is None and rows[1][3]['Memo'] == 'note'
    cur.execute('SELECT count(*) FROM core_pytest.v0_card_files')
    assert cur.fetchone()[0] == 2


def test_REQ_FIN_014_reordered_file_retains_bytes_without_new_activity(cur):
    first = save(cur, A+A+B)
    assert first['distinct_rows'] == 2 and first['review_rows'] == 1
    reordered = save(cur, B+A+A)
    assert reordered['equivalent_to'] == first['file_id']
    assert reordered['equivalent_rows'] == 3 and reordered['distinct_rows'] == 0
    cur.execute('''SELECT equivalent_row_id FROM core_pytest.v0_card_rows
        WHERE file_id=%s''', (reordered['file_id'],))
    assert len({str(row[0]) for row in cur.fetchall()}) == 3
    assert save(cur, B+A+A) == reordered


def test_REQ_FIN_014_partial_overlap_and_changed_memo_require_review(cur):
    first = save(cur)
    partial = save(cur, A.replace(',-10.00,', ',-10.00,changed'))
    assert partial['equivalent_to'] is None and partial['review_rows'] == 1
    cur.execute('''SELECT candidate_ids FROM core_pytest.v0_card_rows WHERE file_id=%s''', (partial['file_id'],))
    candidates = cur.fetchone()[0]
    cur.execute('''SELECT row_id FROM core_pytest.v0_card_rows WHERE file_id=%s AND source_row=1''', (first['file_id'],))
    assert [str(x) for x in candidates] == [str(cur.fetchone()[0])]


@pytest.mark.parametrize('table', ['v0_card_files','v0_card_rows'])
@pytest.mark.parametrize('operation', ['UPDATE','DELETE','TRUNCATE'])
def test_RULE_02_card_source_immutable_even_for_table_owner(cur,table,operation):
    save(cur)
    sql = f'UPDATE core_pytest.{table} SET account_id=account_id' if operation=='UPDATE' else (
        f'DELETE FROM core_pytest.{table}' if operation=='DELETE' else f'TRUNCATE core_pytest.{table} CASCADE')
    with pytest.raises(Exception):
        cur.execute(sql)


@pytest.mark.parametrize('role', ['anon','authenticated','service_role','capture_ingest'])
def test_RULE_29_card_private_tables_not_directly_readable(cur,role):
    save(cur)
    cur.execute('SET LOCAL ROLE '+role)
    with pytest.raises(Exception):
        cur.execute('SELECT * FROM core_pytest.v0_card_rows')


def test_REQ_FIN_010_atomic_failure_rolls_back_raw_and_receipt(cur):
    cur.execute('''CREATE FUNCTION core_pytest.fail_card() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'injected card failure'; END $$''')
    cur.execute('''CREATE TRIGGER fail_card BEFORE INSERT ON core_pytest.v0_card_rows
        FOR EACH ROW EXECUTE FUNCTION core_pytest.fail_card()''')
    cur.execute('SAVEPOINT failed_import')
    with pytest.raises(Exception, match='injected card failure'):
        save(cur)
    cur.execute('ROLLBACK TO SAVEPOINT failed_import')
    cur.execute('SELECT count(*) FROM core_pytest.v0_card_files')
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT count(*) FROM core_pytest.raw_captures WHERE payload->>'kind'='v0_card_source'")
    assert cur.fetchone()[0] == 0


@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_REQ_FIN_014_refuse_stale_snapshot_isolation(isolation):
    conn = connect()
    try:
        c = conn.cursor()
        c.execute('SET TRANSACTION ISOLATION LEVEL '+isolation)
        with pytest.raises(ValueError, match='READ COMMITTED'):
            save(c)
    finally:
        conn.rollback()
        conn.close()


def test_REQ_FIN_014_refuse_autocommit_before_any_write():
    conn = connect()
    try:
        conn.autocommit = True
        with pytest.raises(ValueError, match='caller-owned transaction'):
            save(conn.cursor())
    finally:
        conn.close()


def owner(cur):
    cur.execute('SET LOCAL ROLE authenticated')
    as_owner(cur)


def read(cur, account=ACCOUNT, start='2026-09-01', end='2026-09-30'):
    cur.execute('SELECT public.get_v0_card_activity(%s,%s,%s)', (account,start,end))
    return cur.fetchone()[0]


def decision(row, action='distinct', target=None, previous=None):
    return dict(decision_id=str(uuid.uuid4()),row_id=row,action=action,target_id=target,supersedes=previous)


def review(cur, request):
    cur.execute('SELECT public.review_v0_card_row(%s::jsonb)', (json.dumps(request),))
    return cur.fetchone()[0]


def test_REQ_FIN_014_RULE_10_owner_review_retry_correct_and_reimport(cur):
    original = save(cur,A+A)
    owner(cur)
    initial = read(cur)
    assert initial['coverage']=='incomplete'
    assert initial['source_subtotals'][0]['signed_amount']==-10
    first,second = initial['entries']
    req = decision(second['row_id'],'link',first['row_id'])
    receipt = review(cur,req)
    assert review(cur,req)==receipt
    linked = read(cur)
    assert linked['coverage']=='imported_observations_only'
    assert linked['entries'][1]['status']=='linked'
    assert linked['source_subtotals'][0]['signed_amount']==-10
    correction = decision(second['row_id'],previous=req['decision_id'])
    review(cur,correction)
    cur.execute('RESET ROLE')
    assert save(cur,A+A)==original
    owner(cur)
    corrected = read(cur)
    assert corrected['source_subtotals'][0]['signed_amount']==-20
    assert corrected['entries'][1]['decision_id']==correction['decision_id']
    # An old receipt retry is not a command to reinstate the old decision.
    assert review(cur,req)==receipt
    assert read(cur)['entries'][1]['status']=='distinct'
    cur.execute('RESET ROLE')
    cur.execute('SELECT result FROM core_pytest.v0_card_reads WHERE read_id=%s', (initial['read_id'],))
    assert cur.fetchone()[0]==initial
    for subtotal in corrected['source_subtotals']:
        assert subtotal['lane']=='observed'
        assert subtotal['provenance']=='imported_statement' and subtotal['method']=='sum'
        assert subtotal['code_version']==corrected['code_version']=='v0_card_activity_v1'
        cur.execute('''SELECT sum(amount),count(*) FROM core_pytest.v0_card_rows
            WHERE row_id=ANY(%s::uuid[])''', (subtotal['source_row_ids'],))
        amount,count=cur.fetchone()
        assert amount==subtotal['signed_amount'] and count==subtotal['included_rows']


def test_RULE_06_card_missing_is_not_zero_and_types_stay_separate(cur):
    save(cur,A+'09/20/2026,09/20/2026,fixture payment,,Payment,10.00,\n')
    owner(cur)
    result=read(cur)
    assert {s['source_type']:s['signed_amount'] for s in result['source_subtotals']}=={'Sale':-10,'Payment':10}
    missing=read(cur,start='2026-08-01',end='2026-08-02')
    assert missing['coverage']=='missing' and missing['source_subtotals']==[]
    assert missing['last_received_at'] is None


def test_RULE_10_card_stale_review_refused(cur):
    save(cur,A+A)
    owner(cur)
    row=read(cur)['entries'][1]['row_id']
    review(cur,decision(row))
    with pytest.raises(Exception,match='stale review'):
        review(cur,decision(row))


def test_RULE_10_card_changed_retry_refused(cur):
    save(cur,A+A)
    owner(cur)
    first,second=read(cur)['entries']
    req=decision(second['row_id'])
    review(cur,req)
    with pytest.raises(Exception,match='identity reused'):
        review(cur,dict(req,action='link',target_id=first['row_id']))


def test_RULE_29_card_link_cannot_cross_accounts(cur):
    save(cur)
    save(cur,account=OTHER)
    owner(cur)
    own=read(cur)['entries'][0]['row_id']
    other=read(cur,account=OTHER)['entries'][0]['row_id']
    with pytest.raises(Exception,match='same account'):
        review(cur,decision(own,'link',other))


def test_RULE_10_card_links_cannot_form_chain_or_cycle(cur):
    save(cur,A+A+B)
    owner(cur)
    a,b,c=read(cur)['entries']
    review(cur,decision(b['row_id'],'link',a['row_id']))
    with pytest.raises(Exception,match='incoming links'):
        review(cur,decision(a['row_id'],'link',c['row_id']))


@pytest.mark.parametrize('role,email', [('anon','joseph.delany21@gmail.com'),
    ('authenticated','not-owner@example.invalid'),('capture_ingest','joseph.delany21@gmail.com')])
@pytest.mark.parametrize('operation',['read','review'])
def test_RULE_29_card_rpc_owner_only(cur,role,email,operation):
    cur.execute('SET LOCAL ROLE '+role)
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps({'email':email}),))
    with pytest.raises(Exception):
        read(cur) if operation=='read' else review(cur,decision(ACCOUNT))
