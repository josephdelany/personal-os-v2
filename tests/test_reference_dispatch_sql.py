"""Real persisted source meters/receipts in full-chain disposable rollback fixtures."""
import hashlib
import json
import uuid
import pytest
from tests._location_fixture import apply_chain
from tests._sql_fixture import connect, requires_disposable

pytestmark=requires_disposable
BODY='{}'
DIGEST=hashlib.sha256(BODY.encode()).hexdigest()


@pytest.fixture
def cur():
    conn=connect()
    try:
        cursor=conn.cursor()
        apply_chain(cursor)
        yield cursor
    finally:
        conn.rollback()
        conn.close()


def reserve(cur,source='usda_branded',rid=None):
    rid=str(rid or uuid.uuid4())
    cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',(rid,source,DIGEST,100))
    return rid,cur.fetchone()[0]


def test_RULE_29_REQ_NUT_005_receipt_binding_and_repeat_identity(cur):
    cur.execute('SET LOCAL ROLE reference_egress')
    rid,permit=reserve(cur)
    assert permit['allowed']
    assert not reserve(cur,rid=rid)[1]['allowed']
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,None))
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,None))
    cur.execute('SELECT r.payload_sha256,s.response_sha256 FROM ops_pytest.reference_requests r JOIN ops_pytest.reference_results s USING(request_id)')
    assert tuple(cur.fetchone())==(DIGEST,DIGEST)
    cur.execute('SAVEPOINT changed')
    with pytest.raises(Exception):
        cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,'{"changed":true}',None))
    cur.execute('ROLLBACK TO SAVEPOINT changed')
    cur.execute('SAVEPOINT private_read')
    with pytest.raises(Exception): cur.execute('SELECT * FROM core_pytest.raw_captures')
    cur.execute('ROLLBACK TO SAVEPOINT private_read')


@pytest.mark.parametrize('meter,source,limit',[('usda','usda_branded',900),('off_search','off_search',10),('off_product','off_product',15)])
def test_REQ_NUT_009_011_database_meter_refuses_at_limit(cur,meter,source,limit):
    cur.execute('INSERT INTO ops_pytest.rate_limit_events(meter,issued_at) SELECT %s,clock_timestamp() FROM generate_series(1,%s)',(meter,limit-1))
    cur.execute('SET LOCAL ROLE reference_egress')
    rid,permit=reserve(cur,source)
    assert permit['allowed']
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,None))
    other='usda_foundation' if source=='usda_branded' else source
    assert reserve(cur,other)[1]=={'allowed':False,'reason':'source_quota'}


def test_REQ_NUT_012_provider_cooldown_survives_a_new_request_identity(cur):
    cur.execute('SET LOCAL ROLE reference_egress')
    rid,permit=reserve(cur)
    assert permit['allowed']
    cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,429))
    assert reserve(cur,'usda_foundation')[1]=={'allowed':False,'reason':'source_cooldown'}
    assert reserve(cur,'off_search')[1]['allowed']
    cur.execute('RESET ROLE')
    cur.execute("SELECT blocked_until>clock_timestamp()+interval '59 minutes',reason FROM ops_pytest.rate_limit_cooldowns WHERE meter='usda'")
    assert tuple(cur.fetchone())==(True,'provider_429')


def test_RULE_29_REQ_NUT_003_private_consumer_cannot_forge_source_receipt(cur):
    rid,_=reserve(cur)
    cur.execute('SET LOCAL ROLE service_role')
    cur.execute('SELECT payload_sha256 FROM ops_pytest.reference_requests WHERE request_id=%s',(rid,))
    assert cur.fetchone()[0]==DIGEST
    cur.execute('SAVEPOINT forbidden')
    with pytest.raises(Exception): cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,None))
    cur.execute('ROLLBACK TO SAVEPOINT forbidden')


@pytest.mark.parametrize('meter,source,limit,age',[
    ('off_search','off_search',10,'61 seconds'),
    ('off_product','off_product',15,'61 seconds'),
    ('usda','usda_foundation',900,'3601 seconds'),
])
def test_REQ_NUT_009_011_delayed_permits_still_count_in_provider_window(cur,meter,source,limit,age):
    # Permits can send up to60s after reservation. These rows are outside the
    # ordinary quota window but their latest legal sends remain inside it.
    cur.execute('INSERT INTO ops_pytest.rate_limit_events(meter,issued_at) SELECT %s,clock_timestamp()-%s::interval FROM generate_series(1,%s)',(meter,age,limit))
    cur.execute('SET LOCAL ROLE reference_egress')
    assert reserve(cur,source)[1]=={'allowed':False,'reason':'source_quota'}


def test_REQ_NUT_012_uncertain_predecessor_starts_a_full_cooldown_when_discovered(cur):
    rid,_=reserve(cur)
    # No result exists; in runtime the global session lock prevents another
    # dispatcher entering while the first still owns its network operation.
    cur.execute('SET LOCAL ROLE reference_egress')
    assert reserve(cur,'usda_foundation')[1]=={'allowed':False,'reason':'source_uncertain'}
    cur.execute('SELECT outcome,response_sha256,provider_status FROM ops_pytest.reference_results WHERE request_id=%s',(rid,))
    assert tuple(cur.fetchone())==('uncertain',None,None)
    cur.execute('SAVEPOINT late_result')
    with pytest.raises(Exception):
        cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',(rid,BODY,None))
    cur.execute('ROLLBACK TO SAVEPOINT late_result')
    cur.execute('RESET ROLE')
    cur.execute("SELECT blocked_until>clock_timestamp()+interval '59 minutes',reason FROM ops_pytest.rate_limit_cooldowns WHERE meter='usda'")
    assert tuple(cur.fetchone())==(True,'dispatch_uncertain')
    # Expiry allows a fresh identity; the old attempt never acquires a made-up
    # response or changes into a successful source receipt.
    cur.execute("UPDATE ops_pytest.rate_limit_cooldowns SET blocked_until=clock_timestamp()-interval '1 second' WHERE meter='usda'")
    cur.execute('SET LOCAL ROLE reference_egress')
    assert reserve(cur,'usda_foundation')[1]['allowed']
