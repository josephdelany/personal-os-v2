"""V0 check-in RPCs against rollback-only disposable schemas."""
import json

import pytest

from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable

pytestmark = requires_disposable
CID = '0195dc0b-3470-7000-8000-000000000091'
NEXT = '0195dc0b-3470-7000-8000-000000000092'


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
    cursor = connection.cursor()
    cursor.execute('SAVEPOINT v0_case')
    try:
        cursor.execute('SET LOCAL ROLE authenticated')
        as_owner(cursor)
        yield cursor
    finally:
        cursor.execute('ROLLBACK TO SAVEPOINT v0_case')
        cursor.execute('RELEASE SAVEPOINT v0_case')


def request(**changes):
    return dict(entry_id=CID, supersedes=None, occurred_at='2026-09-24T08:00:00-04:00',
                period='morning', ratings={'sleep_quality':7, 'energy':6}, note='', **changes)


def save(cur, payload):
    cur.execute('SELECT public.save_v0_checkin(%s::jsonb)', (json.dumps(payload),))
    return cur.fetchone()[0]


def read(cur, day):
    cur.execute('SELECT public.get_v0_checkins(%s)', (day,))
    return cur.fetchone()[0]


def test_REQ_CAP_016_017_RULE_06_v0_save_retry_and_empty_day(cur):
    payload=request()
    receipt=save(cur,payload)
    assert receipt['status']=='saved' and receipt['entry_id']==CID
    assert receipt==save(cur,payload)
    assert read(cur,'2026-09-23')['entries']==[]
    entries=read(cur,'2026-09-24')['entries']
    assert len(entries)==1 and entries[0]['ratings']==payload['ratings']
    assert entries[0]['response_scale']==[1,10]
    assert entries[0]['definition']=='v0_checkin_v1'
    assert entries[0]['recorded_at'] and entries[0]['occurred_at']
    with pytest.raises(Exception,match='identity reused'):
        save(cur,{**payload,'note':'changed'})


def test_REQ_CAP_014_RULE_02_03_v0_correction_moves_day_preserves_original(cur):
    original=request()
    save(cur,original)
    corrected={**original,'entry_id':NEXT,'supersedes':CID,
               'occurred_at':'2026-09-24T03:59:59-04:00','ratings':{'sleep_quality':8,'energy':9}}
    save(cur,corrected)
    assert read(cur,'2026-09-24')['entries']==[]
    current=read(cur,'2026-09-23')['entries']
    assert len(current)==1 and current[0]['supersedes']==CID
    assert current[0]['ratings']==corrected['ratings']
    cur.execute('RESET ROLE')
    cur.execute('SELECT payload FROM core_pytest.raw_captures WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]['entry']==original
    cur.execute('SELECT count(*) FROM core_pytest.v0_checkin_entries')
    assert cur.fetchone()[0]==2
    cur.execute('SET LOCAL ROLE authenticated')
    with pytest.raises(Exception,match='stale'):
        save(cur,{**corrected,'entry_id':'0195dc0b-3470-7000-8000-000000000093'})


@pytest.mark.parametrize('claims',[{}, {'email':'not-owner@example.test'}])
@pytest.mark.parametrize('operation',['read','save'])
def test_RULE_29_v0_requires_owner_jwt(cur,claims,operation):
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps(claims),))
    with pytest.raises(Exception,match='owner only'):
        read(cur,'2026-09-24') if operation=='read' else save(cur,request())


@pytest.mark.parametrize('changes',[
    {'ratings':{'sleep_quality':0,'energy':6}},
    {'ratings':{'sleep_quality':11,'energy':6}},
    {'ratings':{'sleep_quality':1.5,'energy':6}},
    {'ratings':{'sleep_quality':True,'energy':6}},
    {'ratings':{'sleep_quality':'7','energy':6}},
    {'ratings':{'energy':6}}, {'ratings':None},
    {'period':'night'}, {'note':None}, {'note':'x'*4001},
    {'occurred_at':'2026-09-24T08:00:00'},
    {'occurred_at':'2026-09-24T08:00:00+01:99'},
    {'occurred_at':'2026-09-24T24:00:00-04:00'},
    {'occurred_at':'2026-09-24T23:59:60-04:00'},
    {'entry_id':'not-a-uuid'}, {'extra':'ignored?'},
])
def test_REQ_CAP_007_RULE_06_v0_refuses_invalid_input(cur,changes):
    with pytest.raises(Exception):
        save(cur,{**request(),**changes})


def test_RULE_02_29_v0_private_ledger_and_immutability(cur):
    save(cur,request())
    cur.execute('SAVEPOINT denied')
    with pytest.raises(Exception):
        cur.execute('SELECT * FROM core_pytest.v0_checkin_entries')
    cur.execute('ROLLBACK TO SAVEPOINT denied')
    cur.execute('RESET ROLE')
    with pytest.raises(Exception,match='RULE-02'):
        cur.execute('DELETE FROM core_pytest.v0_checkin_entries')


@pytest.mark.parametrize('time,day',[
    ('2026-09-24T03:59:59-04:00','2026-09-23'),
    ('2026-09-24T04:00:00-04:00','2026-09-24'),
    ('2026-11-01T01:30:00-05:00','2026-10-31'),
])
def test_REQ_CAP_066_RULE_03_v0_evening_boundary(cur,time,day):
    payload={**request(),'period':'evening','ratings':{'mood':1,'energy':10},
             'occurred_at':time,'note':'fixture reflection'}
    assert save(cur,payload)['subject_day']==day
    entries=read(cur,day)['entries']
    assert len(entries)==1 and entries[0]['ratings']=={'mood':1,'energy':10}
    assert entries[0]['note']=='fixture reflection'


@pytest.mark.parametrize('operation',['read','save'])
def test_RULE_29_v0_anon_cannot_execute_even_with_owner_claim(cur,operation):
    cur.execute('SET LOCAL ROLE anon')
    with pytest.raises(Exception) as error:
        read(cur,'2026-09-24') if operation=='read' else save(cur,request())
    assert error.value.args[0]['C']=='42501'


def test_REQ_CAP_014_RULE_02_v0_failed_ledger_insert_rolls_back_capture(cur):
    cur.execute('RESET ROLE')
    cur.execute("""CREATE FUNCTION core_pytest.fail_v0_entry() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected ledger failure'; END $$""")
    cur.execute('''CREATE TRIGGER fail_entry BEFORE INSERT ON core_pytest.v0_checkin_entries
        FOR EACH ROW EXECUTE FUNCTION core_pytest.fail_v0_entry()''')
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SAVEPOINT failed_save')
    with pytest.raises(Exception,match='injected ledger failure'):
        save(cur,request())
    cur.execute('ROLLBACK TO SAVEPOINT failed_save')
    cur.execute('RELEASE SAVEPOINT failed_save')
    assert read(cur,'2026-09-24')['entries']==[]
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==0
    cur.execute('DROP TRIGGER fail_entry ON core_pytest.v0_checkin_entries')
    cur.execute('SET LOCAL ROLE authenticated')
    assert save(cur,request())['status']=='saved'


def test_REQ_CAP_016_017_v0_refuses_identity_from_another_capture(cur):
    cur.execute('RESET ROLE')
    cur.execute('SELECT public.receive_capture(%s)',(json.dumps(dict(capture_id=CID,
        captured_at='2026-09-24T08:00:00-04:00',source='pwa_text',payload={'text':'fixture meal'})),))
    assert cur.fetchone()[0]['status']=='created'
    cur.execute('SET LOCAL ROLE authenticated')
    with pytest.raises(Exception,match='capture identity already used'):
        save(cur,request())
