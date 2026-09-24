"""V0 owner day composition, native health units and two freshness clocks."""
import datetime as dt
import json
import uuid
import pytest
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable

pytestmark = requires_disposable


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
    c.execute('SAVEPOINT day_case')
    try:
        c.execute('SET LOCAL ROLE authenticated')
        as_owner(c)
        yield c
    finally:
        c.execute('ROLLBACK TO SAVEPOINT day_case')
        c.execute('RELEASE SAVEPOINT day_case')


def read(cur, day='2026-03-07'):
    cur.execute('SELECT public.get_v0_day(%s)', (day,))
    return cur.fetchone()[0]


def atom(cur, metric='steps', value=100, device='Apple Watch', day='2026-03-07',
         kind='activity_sample', state='total', unit='count', supersedes=None,
         interval=None, configured=True, importer='apple_health'):
    cur.execute('RESET ROLE')
    cur.execute('''INSERT INTO core_pytest.metric_registry
        (metric_key,display_name,family,unit,state_class)
        VALUES (%s,%s,'health',%s,%s) ON CONFLICT DO NOTHING''', (metric, metric, unit, state))
    if configured:
        cur.execute('''INSERT INTO config.panel_aggregation(metric,method,method_version,note)
            VALUES (%s,%s,'atom-panel-v1','fixture registered aggregation') ON CONFLICT DO NOTHING''',
                    (metric, 'sum' if state == 'total' else 'median'))
    cid, aid = uuid.uuid4(), uuid.uuid4()
    event = day + 'T12:00:00-05:00'
    cur.execute('''INSERT INTO core_pytest.raw_captures(capture_id,source,captured_at,payload,trust_level)
        VALUES (%s,'file_import',%s,%s,'trusted')''', (cid, event, json.dumps({'importer':importer})))
    cur.execute('''INSERT INTO core_pytest.atoms
        (id,raw_capture_id,kind,metric_key,occurred_at,valid_interval,subject_day,
         subject_day_rule_version,presence,value_low,value_point,value_high,estimate_method,
         unit,state_class,trust_level,provenance,evidence_span,code_version,supersedes)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'v1-2026-08-23','observed',%s,%s,%s,'measured',
                %s,%s,'trusted','extracted',%s,'fixture',%s)''',
                (aid,cid,kind,metric,event,interval,day,value,value,value,unit,state,
                 'apple_health:fixture;source='+device,supersedes))
    cur.execute('SET LOCAL ROLE authenticated')
    return str(aid), str(cid)


def test_RULE_06_missing_day_has_empty_entries_and_null_freshness(cur):
    row = read(cur)
    for key in ['checkins','meals','workouts']:
        assert row[key]['entries'] == []
    h = row['health']
    assert h['latest_measurements'] == h['daily_aggregates'] == h['recorded_workout_sessions'] == []
    assert h['freshness']['last_event_at'] is None
    assert h['freshness']['last_received_at'] is None


def test_REQ_ASK_021_RULE_12_device_selection_and_stored_trace(cur):
    watch, _ = atom(cur, value=100)
    phone, _ = atom(cur, value=250, device='iPhone')
    row = read(cur)['health']['daily_aggregates'][0]
    assert row['value'] == 100 and row['unit'] == 'count'
    assert row['device'] == 'Watch' and row['n_devices'] == 2 and row['n_atoms'] == 1
    assert row['method'] == 'sum' and row['method_version'] == 'atom-panel-v1'
    assert row['trace']['atom_ids'] == [watch] and phone not in row['trace']['atom_ids']


def test_RULE_03_06_latest_native_measurement_has_distinct_event_received_times(cur):
    aid, cid = atom(cur, metric='fixture_body_mass', value=70, state='measurement',
                    kind='body_measurement', unit='kg', day='2026-03-06')
    row = read(cur)['health']['latest_measurements'][0]
    assert row['metric'] == 'fixture_body_mass' and row['value'] == 70 and row['unit'] == 'kg'
    assert row['atom_id'] == aid and row['capture_id'] == cid
    assert dt.datetime.fromisoformat(row['received_at']) > dt.datetime.fromisoformat(row['occurred_at'])
    assert row['subject_day'] == '2026-03-06'
    assert read(cur)['health']['daily_aggregates'] == []


def test_RULE_10_current_health_correction_excludes_predecessor(cur):
    old, _ = atom(cur, value=100)
    new, _ = atom(cur, value=150, supersedes=old)
    row = read(cur)['health']['daily_aggregates'][0]
    assert row['value'] == 150 and row['trace']['atom_ids'] == [new]


def test_REQ_WKT_003_session_active_duration_is_not_interval_length(cur):
    aid, _ = atom(cur, metric='workout_session_min', kind='workout', state='measurement',
                  unit='min', value=45, interval='[2026-03-07T12:00:00-05:00,2026-03-07T14:00:00-05:00)')
    h = read(cur)['health']
    assert h['daily_aggregates'] == [] and h['latest_measurements'] == []
    row = h['recorded_workout_sessions'][0]
    assert row['atom_id'] == aid and row['active_duration'] == 45 and row['unit'] == 'min'
    assert row['valid_interval'] is not None


@pytest.mark.parametrize('day,hours', [('2026-03-07',23),('2026-10-31',25)])
def test_RULE_03_day_boundaries_are_local_and_dst_safe(cur,day,hours):
    bounds = []
    for zone in ['UTC','America/Los_Angeles']:
        cur.execute("SELECT set_config('TimeZone',%s,true)", (zone,))
        row = read(cur,day)
        start,end = (dt.datetime.fromisoformat(row[k]) for k in ['day_start','day_end'])
        assert (end-start).total_seconds() == hours*3600
        bounds.append((start,end))
    assert bounds[0] == bounds[1]


def test_RULE_06_unconfigured_aggregate_is_explicit_not_zero(cur):
    atom(cur,metric='fixture_unconfigured',configured=False)
    h = read(cur)['health']
    assert h['daily_aggregates'] == []
    assert h['aggregation_unavailable'] == [{'metric':'fixture_unconfigured',
                                            'reason':'no_registered_daily_aggregate'}]


@pytest.mark.parametrize('role,email', [('anon','joseph.delany21@gmail.com'),
                                       ('authenticated','other@example.invalid')])
def test_RULE_29_day_is_owner_only(cur,role,email):
    cur.execute('SET LOCAL ROLE '+role)
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps({'email':email}),))
    with pytest.raises(Exception):
        read(cur)


def test_REQ_CAP_014_WKT_020_current_v0_entry_ids_survive_day_composition(cur):
    from tests.test_v0_meals import request as meal_request,save as save_meal,CID,NEXT
    from tests.test_v0_workouts import request as workout_request,save as save_workout
    when='2026-03-07T12:00:00-05:00'
    save_meal(cur,meal_request(occurred_at=when))
    save_meal(cur,meal_request(entry_id=NEXT,supersedes=CID,occurred_at=when,text='corrected fixture'))
    w=save_workout(cur,workout_request(occurred_at=when))
    checkin={'entry_id':'0195dc0b-3470-7000-8000-000000000301','supersedes':None,
             'occurred_at':when,'period':'morning','ratings':{'sleep_quality':7,'energy':6},'note':''}
    cur.execute('SELECT public.save_v0_checkin(%s::jsonb)',(json.dumps(checkin),))
    cur.fetchone()
    row=read(cur)
    assert row['checkins']['entries'][0]['entry_id']==checkin['entry_id']
    assert row['meals']['entries'][0]['entry_id']==NEXT
    assert row['meals']['entries'][0]['supersedes']==CID
    assert row['workouts']['entries'][0]['entry_id']==w['entry_id']


@pytest.mark.parametrize('incompatible', ['source','unit'])
def test_RULE_05_12_day_refuses_mixed_selected_sources_or_units(cur,incompatible):
    atom(cur,value=100)
    atom(cur,value=900,importer='other_importer' if incompatible=='source' else 'apple_health',
         unit='min' if incompatible=='unit' else 'count')
    h=read(cur)['health']
    assert h['daily_aggregates']==[]
    assert h['aggregation_unavailable']==[{'metric':'steps',
        'reason':'selected_contributors_have_incompatible_source_or_unit'}]


def test_RULE_12_unselected_device_does_not_poison_selected_daily_total(cur):
    selected,_=atom(cur,value=100)
    atom(cur,value=900,device='iPhone',unit='min',importer='other_importer')
    h=read(cur)['health']
    assert h['aggregation_unavailable']==[]
    assert h['daily_aggregates'][0]['value']==100
    assert h['daily_aggregates'][0]['trace']['atom_ids']==[selected]


def test_RULE_03_saved_entry_crosses_04_boundary_independent_of_server_timezone(cur):
    from tests.test_v0_meals import request,save,CID,NEXT
    save(cur,request(occurred_at='2026-03-08T03:59:59-04:00'))
    save(cur,request(entry_id=NEXT,occurred_at='2026-03-08T04:00:00-04:00'))
    for zone in ['UTC','America/Los_Angeles']:
        cur.execute("SELECT set_config('TimeZone',%s,true)",(zone,))
        assert [r['entry_id'] for r in read(cur,'2026-03-07')['meals']['entries']]==[CID]
        assert [r['entry_id'] for r in read(cur,'2026-03-08')['meals']['entries']]==[NEXT]
