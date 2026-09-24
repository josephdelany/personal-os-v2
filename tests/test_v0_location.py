"""V0 location transport and owner readback in disposable, rollback-only schemas."""
import json
import pytest
from tests import _location_fixture as lf

pytestmark = lf.requires_disposable


@pytest.fixture(scope='module')
def connection():
    conn=lf.connect()
    try:
        lf.apply_chain(conn.cursor())
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def cur(connection):
    c=connection.cursor()
    c.execute('SAVEPOINT v0_location_case')
    try:
        yield c
    finally:
        c.execute('ROLLBACK TO SAVEPOINT v0_location_case')
        c.execute('RELEASE SAVEPOINT v0_location_case')


def point(at='2026-09-20T12:00:00Z'):
    return dict(type='Feature',geometry=dict(type='Point',coordinates=[0.0,0.0]),
                properties=dict(timestamp=at,horizontal_accuracy=5,device_id='fixture-device'))


def batch(cur,points):
    cur.execute('SELECT public.ingest_location_batch(%s::jsonb)',(json.dumps(dict(locations=points)),))
    return cur.fetchone()[0]


def test_REQ_CAP_017_REQ_LOC_001_overland_retry_does_not_duplicate_fixes(cur):
    assert batch(cur,[point()])['result']=='ok'
    assert batch(cur,[point()])['result']=='ok'
    cur.execute(f'SELECT count(*) FROM {lf.LOC_SCHEMA}.location_fixes')
    assert cur.fetchone()[0]==1


@pytest.mark.parametrize('role',['anon','authenticated','service_role'])
def test_RULE_29_location_collection_requires_transport_capability(cur,role):
    cur.execute('SET LOCAL ROLE '+role)
    with pytest.raises(Exception):
        cur.execute("SELECT public.ingest_location(NULL,'2026-09-20T12:00:00Z',0.0,0.0)")


def test_REQ_CAP_017_partial_reordered_and_changed_batch_count(cur):
    a,b=point(),point('2026-09-20T12:05:00Z')
    a['properties']['locations_in_payload']=2
    first=batch(cur,[a,b,a])
    assert first['inserted']==2 and first['duplicates']==1
    assert first['capture_ids'][0]==first['capture_ids'][2]
    a['properties']['locations_in_payload']=1
    second=batch(cur,[b,a])
    assert second['inserted']==0 and second['duplicates']==2
    assert second['capture_ids']==[first['capture_ids'][1],first['capture_ids'][0]]
    cur.execute(f'SELECT source_record FROM {lf.LOC_SCHEMA}.location_receipts WHERE raw_capture_id=%s',
                (first['capture_ids'][0],))
    assert cur.fetchone()[0]['properties']['locations_in_payload']==2


def test_REQ_LOC_001_004_distinct_source_metadata_is_not_silently_collapsed(cur):
    a,b=point(),point()
    b['properties']['device_id']='another-fixture-device'
    result=batch(cur,[a,b])
    assert result['inserted']==2
    assert len(set(result['capture_ids']))==2


def test_REQ_LOC_001_invalid_final_record_rolls_back_all_receipts_and_fixes(cur):
    cur.execute('SAVEPOINT bad_batch')
    bad=point('bad timestamp')
    with pytest.raises(Exception):
        batch(cur,[point(),bad])
    cur.execute('ROLLBACK TO SAVEPOINT bad_batch')
    for table in ('location_receipts','location_fixes'):
        cur.execute(f'SELECT count(*) FROM {lf.LOC_SCHEMA}.{table}')
        assert cur.fetchone()[0]==0
    cur.execute(f'SELECT count(*) FROM {lf.CORE}.raw_captures')
    assert cur.fetchone()[0]==0


def test_RULE_29_private_service_batch_still_works_and_raw_evidence_is_redacted(cur):
    cur.execute('SET LOCAL ROLE service_role')
    result=batch(cur,[point()])
    assert result['inserted']==1
    cur.execute('RESET ROLE')
    cur.execute(f'SELECT payload FROM {lf.CORE}.raw_captures WHERE capture_id=%s',(result['capture_ids'][0],))
    assert cur.fetchone()[0]=={'kind':'location','redacted':True,'source':'overland'}


@pytest.mark.parametrize('role',['anon','authenticated','service_role'])
def test_RULE_29_location_receipt_cannot_be_read_directly(cur,role):
    batch(cur,[point()])
    cur.execute('SET LOCAL ROLE '+role)
    with pytest.raises(Exception):
        cur.execute(f'SELECT * FROM {lf.LOC_SCHEMA}.location_receipts')


@pytest.mark.parametrize('action',['UPDATE','DELETE','TRUNCATE'])
def test_RULE_02_location_retry_evidence_is_immutable(cur,action):
    batch(cur,[point()])
    query=(f'UPDATE {lf.LOC_SCHEMA}.location_receipts SET source_record=source_record'
           if action=='UPDATE' else (f'DELETE FROM {lf.LOC_SCHEMA}.location_receipts'
           if action=='DELETE' else f'TRUNCATE {lf.LOC_SCHEMA}.location_receipts'))
    with pytest.raises(Exception,match='RULE-02'):
        cur.execute(query)


def refresh(cur):
    cur.execute('SELECT public.refresh_v0_visits()')
    return cur.fetchone()[0]


def read(cur,day='2026-09-20'):
    cur.execute('SET LOCAL ROLE authenticated')
    lf.as_owner(cur)
    cur.execute('SELECT public.get_v0_visits(%s)',(day,))
    result=cur.fetchone()[0]
    cur.execute('RESET ROLE')
    return result


def test_REQ_LOC_015_018_saved_fixes_pending_then_traceable_visit(cur):
    assert read(cur)['processing_status']=='missing'
    receipt=batch(cur,[point(),point('2026-09-20T12:15:00Z')])
    assert read(cur)['processing_status']=='awaiting_derivation'
    assert refresh(cur)==1
    result=read(cur)
    assert result['processing_status']=='available'
    visit=result['entries'][0]
    assert visit['label']=='unknown place' and visit['place_resolution']=='unknown'
    assert visit['source_capture_ids']==receipt['capture_ids']
    assert visit['observed_span_min']==15 and visit['unit']=='min'
    assert visit['lane']=='observed' and visit['code_version']=='visits-v2'
    from datetime import datetime
    assert datetime.fromisoformat(visit['derived_at'])>=datetime.fromisoformat(visit['last_received_at'])
    assert result['coverage']['fix_count']==2 and result['coverage']['presence']=='unknown'
    cur.execute(f'SELECT result FROM {lf.LOC_SCHEMA}.v0_visit_reads WHERE read_id=%s',(result['read_id'],))
    assert cur.fetchone()[0]==result
    assert 'coordinates' not in json.dumps(result) and 'identity_sha256' not in json.dumps(result)


def test_REQ_LOC_015_fix_without_detected_stay_is_not_absence(cur):
    batch(cur,[point()])
    refresh(cur)
    result=read(cur)
    assert result['processing_status']=='no_detected_visits'
    assert result['entries']==[] and result['coverage']['presence']=='unknown'


def test_REQ_LOC_012_late_offline_batch_refreshes_actual_past_day(cur):
    batch(cur,[point('2026-08-01T12:00:00Z'),point('2026-08-01T12:15:00Z')])
    refresh(cur)
    assert read(cur,'2026-08-01')['processing_status']=='available'
    batch(cur,[point('2026-07-01T12:00:00Z'),point('2026-07-01T12:15:00Z')])
    refresh(cur)
    assert read(cur,'2026-07-01')['processing_status']=='available'
    assert len(read(cur,'2026-08-01')['entries'])==1


def test_REQ_LOC_006_RULE_10_human_place_survives_rebuild(cur):
    batch(cur,[point(),point('2026-09-20T12:15:00Z')])
    refresh(cur)
    visit=read(cur)['entries'][0]
    cur.execute('SET LOCAL ROLE authenticated')
    lf.as_owner(cur)
    cur.execute("SELECT public.assign_place(%s,'Fixture place','other')",(visit['visit_id'],))
    cur.execute('RESET ROLE')
    batch(cur,[point('2026-09-20T12:20:00Z')])
    refresh(cur)
    result=read(cur)['entries'][0]
    assert result['label']=='Fixture place' and result['place_resolution']=='human'
    assert result['n_fixes']==3


def test_REQ_LOC_012_refresh_cut_does_not_duplicate_cross_day_stay(cur):
    batch(cur,[point('2026-09-19T07:55:00Z'),point('2026-09-19T08:10:00Z')])
    refresh(cur)
    cur.execute(f"SELECT {lf.LOC_SCHEMA}.derive_visits('2026-09-19')")
    cur.execute(f'SELECT count(*) FROM {lf.LOC_SCHEMA}.visits')
    assert cur.fetchone()[0]==1
    visit=read(cur,'2026-09-19')['entries'][0]
    assert visit['source_subject_day']=='2026-09-18'
    assert visit['observed_span_min']==15


@pytest.mark.parametrize('day,hours',[('2026-03-07',23),('2026-10-31',25)])
def test_RULE_03_REQ_LOC_015_day_bounds_are_explicit_et_across_dst(cur,day,hours):
    from datetime import datetime
    cur.execute("SET LOCAL TIME ZONE 'Asia/Tokyo'")
    result=read(cur,day)
    start=datetime.fromisoformat(result['day_start'])
    end=datetime.fromisoformat(result['day_end'])
    assert (end-start).total_seconds()/3600==hours


@pytest.mark.parametrize('role,email',[('anon','joseph.delany21@gmail.com'),
    ('authenticated','not-owner@example.invalid'),('service_role','joseph.delany21@gmail.com')])
def test_RULE_29_visit_read_requires_owner_session(cur,role,email):
    cur.execute('SET LOCAL ROLE '+role)
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps({'email':email}),))
    with pytest.raises(Exception):
        cur.execute("SELECT public.get_v0_visits('2026-09-20')")


def test_REQ_LOC_018_RULE_12_daily_response_reuses_card_and_visit_owners(cur):
    from tools.importers.v0_card_store import import_bytes
    csv=b'Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n09/20/2026,,fixture,,Sale,-1.00,\n'
    account='0195dc0b-3470-7000-8000-000000000501'
    import_bytes(cur,csv,account,schema=lf.CORE)
    batch(cur,[point(),point('2026-09-20T12:15:00Z')])
    refresh(cur)
    cur.execute('SET LOCAL ROLE authenticated')
    lf.as_owner(cur)
    cur.execute("SELECT public.get_v0_day('2026-09-20')")
    result=cur.fetchone()[0]
    assert set(result)>={'checkins','meals','workouts','health','spending','visits'}
    card=result['spending']['accounts'][0]
    assert card['account_id']==account and card['source_subtotals'][0]['signed_amount']==-1
    assert result['visits']['entries'][0]['observed_span_min']==15
    cur.execute('RESET ROLE')
    cur.execute(f'SELECT result FROM {lf.CORE}.v0_card_reads WHERE read_id=%s',(card['read_id'],))
    assert cur.fetchone()[0]==card
    cur.execute(f'SELECT result FROM {lf.LOC_SCHEMA}.v0_visit_reads WHERE read_id=%s',
                (result['visits']['read_id'],))
    assert cur.fetchone()[0]==result['visits']


def test_RULE_10_late_bridge_never_discards_conflicting_human_labels(cur):
    batch(cur,[point(),point('2026-09-20T12:10:00Z'),
               point('2026-09-20T13:00:00Z'),point('2026-09-20T13:10:00Z')])
    refresh(cur)
    rows=read(cur)['entries']
    assert len(rows)==2
    cur.execute('SET LOCAL ROLE authenticated')
    lf.as_owner(cur)
    for row,label in zip(rows,['Fixture A','Fixture B']):
        cur.execute("SELECT public.assign_place(%s,%s,'other')",(row['visit_id'],label))
    cur.execute('RESET ROLE')
    batch(cur,[point('2026-09-20T12:35:00Z')])
    cur.execute('SAVEPOINT conflicting_refresh')
    with pytest.raises(Exception,match='conflicting human assignments'):
        refresh(cur)
    cur.execute('ROLLBACK TO SAVEPOINT conflicting_refresh')
    pending=read(cur)
    assert pending['processing_status']=='awaiting_derivation'
    assert {x['label'] for x in pending['entries']}=={'Fixture A','Fixture B'}
    # An explicit owner correction can resolve the conflict, then the same job recovers.
    cur.execute('SET LOCAL ROLE authenticated')
    lf.as_owner(cur)
    cur.execute("SELECT public.assign_place(%s,'Fixture A','other')",(rows[1]['visit_id'],))
    cur.execute('RESET ROLE')
    refresh(cur)
    resolved=read(cur)
    assert resolved['processing_status']=='available'
    assert len(resolved['entries'])==1 and resolved['entries'][0]['label']=='Fixture A'


def test_REQ_LOC_015_negative_accuracy_is_retained_but_not_a_usable_fix(cur):
    a,b=point(),point('2026-09-20T12:15:00Z')
    b['properties']['horizontal_accuracy']=-1
    batch(cur,[a,b])
    refresh(cur)
    result=read(cur)
    assert result['coverage']['fix_count']==2
    assert result['entries']==[] and result['processing_status']=='no_detected_visits'


@pytest.mark.parametrize('stamp',['2026-09-20T24:00:00Z','2026-09-20T12:60:00Z',
    '2026-09-20T12:00:60Z','2026-09-20T12:00:00+0160','2026-09-20T12:00:00.1234567Z',
    '2026-09-20 12:00:00','2026-02-30T12:00:00Z'])
def test_RULE_03_location_timestamp_never_silently_normalizes(cur,stamp):
    with pytest.raises(Exception):
        batch(cur,[point(stamp)])


def test_RULE_03_documented_overland_offset_and_fraction_are_preserved(cur):
    record=point('2026-09-20T05:00:00.123-0700')
    record['properties']['motion']=['stationary']
    receipt=batch(cur,[record])
    cur.execute(f'SELECT source_record FROM {lf.LOC_SCHEMA}.location_receipts WHERE raw_capture_id=%s',
                (receipt['capture_ids'][0],))
    assert cur.fetchone()[0]==record


def test_REQ_LOC_012_initial_refresh_bootstraps_pre_receipt_history(cur):
    for at in ('2026-01-01T12:00:00Z','2026-01-01T12:15:00Z'):
        cur.execute('SELECT public.ingest_location(NULL,%s,0.0,0.0)',(at,))
    cur.execute(f'SELECT count(*) FROM {lf.LOC_SCHEMA}.location_receipts')
    assert cur.fetchone()[0]==0
    refresh(cur)
    result=read(cur,'2026-01-01')
    assert result['processing_status']=='available'
    assert len(result['entries'][0]['source_capture_ids'])==2
