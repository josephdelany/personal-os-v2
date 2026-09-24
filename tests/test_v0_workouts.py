"""Owner workout save/read contracts against rollback-only disposable schemas."""
import json
import pytest
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable

pytestmark = requires_disposable
CID = '0195dc0b-3470-7000-8000-000000000201'
NEXT = '0195dc0b-3470-7000-8000-000000000202'


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
    c.execute('SAVEPOINT workout_case')
    try:
        c.execute('SET LOCAL ROLE authenticated')
        as_owner(c)
        yield c
    finally:
        c.execute('ROLLBACK TO SAVEPOINT workout_case')
        c.execute('RELEASE SAVEPOINT workout_case')


def request(**changes):
    return dict(dict(entry_id=CID, supersedes=None, occurred_at='2026-09-24T12:00:00-04:00',
                     exercise='fixture squat', movement_mode='external_load', load=100,
                     load_unit='lb', reps=5, rpe=7.5, note=''), **changes)


def save(cur, payload):
    cur.execute('SELECT public.save_v0_workout(%s::jsonb)', (json.dumps(payload),))
    return cur.fetchone()[0]


def read(cur, day='2026-09-24'):
    cur.execute('SELECT public.get_v0_workouts(%s)', (day,))
    return cur.fetchone()[0]['entries']


def test_REQ_WKT_001_018_workout_saved_retry_and_missing_day(cur):
    receipt = save(cur, request())
    assert receipt['status'] == 'saved' and save(cur, request()) == receipt
    entries = read(cur)
    assert len(entries) == 1 and entries[0]['entry_id'] == CID
    assert entries[0]['load']['external_load_lb'] == 100
    assert entries[0]['reps'] == 5
    assert entries[0]['rpe'] == {'value': 7.5, 'scale': [0, 10], 'step': 0.5, 'kind': 'self_report'}
    assert entries[0]['exercise_status'] == 'unresolved'
    assert read(cur, '2026-09-23') == []
    with pytest.raises(Exception, match='identity reused'):
        save(cur, request(reps=6))


@pytest.mark.parametrize('mode,amount,unit', [('external_load', 45.359237, 'kg'),
                                            ('assisted', 45.359237, 'kg'),
                                            ('bodyweight', None, None)])
def test_REQ_WKT_004_007_load_units_modes_and_missing_rpe(cur, mode, amount, unit):
    save(cur, request(movement_mode=mode, load=amount, load_unit=unit, rpe=None))
    row = read(cur)[0]
    assert row['movement_mode'] == mode and row['rpe'] is None
    load = row['load']
    assert load['stated_amount'] == amount and load['stated_unit'] == unit
    assert load['external_load_lb'] == (100 if mode == 'external_load' else None)
    assert load['assistance_lb'] == (100 if mode == 'assisted' else None)


@pytest.mark.parametrize('change', [dict(load=0), dict(load=-1), dict(load='100'),
    dict(load_unit='oz'), dict(reps=0), dict(reps=1.5), dict(reps=True), dict(rpe=10.5),
    dict(rpe=7.2), dict(rpe='8'), dict(exercise=' '), dict(movement_mode='unknown'),
    dict(movement_mode='bodyweight'), dict(occurred_at='2026-09-24T24:00:00Z')])
def test_REQ_WKT_003_004_007_invalid_set_refuses(cur, change):
    with pytest.raises(Exception):
        save(cur, request(**change))


def test_REQ_WKT_020_RULE_02_workout_correction_is_current_and_immutable(cur):
    save(cur, request())
    corrected = request(entry_id=NEXT, supersedes=CID, reps=8,
                        occurred_at='2026-09-23T12:00:00-04:00')
    save(cur, corrected)
    assert read(cur) == []
    assert read(cur, '2026-09-23')[0]['reps'] == 8
    cur.execute('RESET ROLE')
    cur.execute('SELECT payload FROM core_pytest.raw_captures WHERE capture_id=%s', (CID,))
    assert cur.fetchone()[0]['entry']['reps'] == 5
    cur.execute('SET LOCAL ROLE authenticated')
    with pytest.raises(Exception, match='stale'):
        save(cur, request(entry_id='0195dc0b-3470-7000-8000-000000000203', supersedes=CID))


@pytest.mark.parametrize('role,email', [('anon', 'joseph.delany21@gmail.com'),
                                       ('authenticated', 'not-owner@example.invalid')])
@pytest.mark.parametrize('operation', ['save', 'read'])
def test_RULE_29_workout_owner_only(cur, role, email, operation):
    cur.execute('SET LOCAL ROLE ' + role)
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)", (json.dumps({'email': email}),))
    with pytest.raises(Exception):
        save(cur, request()) if operation == 'save' else read(cur)


def test_REQ_WKT_020_atomic_failure_and_legacy_extractor_isolation(cur):
    cur.execute('RESET ROLE')
    cur.execute("""CREATE FUNCTION core_pytest.fail_workout() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'injected workout failure'; END $$""")
    cur.execute('''CREATE TRIGGER fail_workout BEFORE INSERT ON core_pytest.v0_workout_entries
        FOR EACH ROW EXECUTE FUNCTION core_pytest.fail_workout()''')
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SAVEPOINT failed_workout')
    with pytest.raises(Exception, match='injected workout failure'):
        save(cur, request())
    cur.execute('ROLLBACK TO SAVEPOINT failed_workout')
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures WHERE capture_id=%s', (CID,))
    assert cur.fetchone()[0] == 0
    cur.execute('DROP TRIGGER fail_workout ON core_pytest.v0_workout_entries')
    cur.execute('SET LOCAL ROLE authenticated')
    save(cur, request())
    cur.execute('RESET ROLE')
    from tools.extract_workouts import extract
    written, counters, seen = extract(cur, 'core_pytest', 'ops_pytest')
    assert written == 0 and seen == 0
    assert read(cur)[0]['entry_id'] == CID


def test_REQ_CAP_017_retry_survives_registry_change_but_new_entry_validates(cur):
    receipt = save(cur, request())
    cur.execute('RESET ROLE')
    cur.execute("UPDATE core_pytest.metric_registry SET plausible_high=50 WHERE metric_key='strength_load_lb'")
    cur.execute('SET LOCAL ROLE authenticated')
    assert save(cur, request()) == receipt
    with pytest.raises(Exception, match='registered bounds'):
        save(cur, request(entry_id=NEXT))


def test_REQ_WKT_020_mode_correction_does_not_inherit_external_load(cur):
    save(cur, request())
    save(cur, request(entry_id=NEXT, supersedes=CID, movement_mode='bodyweight',
                      load=None, load_unit=None, rpe=None))
    row = read(cur)[0]
    assert row['entry_id'] == NEXT and row['supersedes'] == CID
    assert row['load'] == dict(stated_amount=None, stated_unit=None,
                               external_load_lb=None, assistance_lb=None)
    assert row['rpe'] is None


@pytest.mark.parametrize('action', ['SELECT * FROM', 'DELETE FROM',
                                  'UPDATE'])
def test_RULE_02_29_workout_ledger_not_directly_accessible(cur, action):
    save(cur, request())
    sql = action + ' core_pytest.v0_workout_entries'
    if action == 'UPDATE':
        sql += " SET canonical_load_lb=0"
    with pytest.raises(Exception):
        cur.execute(sql)


def test_RULE_02_workout_ledger_immutable_even_as_owner(cur):
    save(cur, request())
    cur.execute('RESET ROLE')
    with pytest.raises(Exception):
        cur.execute('DELETE FROM core_pytest.v0_workout_entries')
