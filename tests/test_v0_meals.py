"""Meal evidence saves independently from enrichment, rollback-only SQL."""
import json
import pytest
from tests._location_fixture import apply_chain, as_owner
from tests._sql_fixture import connect, requires_disposable

pytestmark=requires_disposable
CID='0195dc0b-3470-7000-8000-000000000101'
NEXT='0195dc0b-3470-7000-8000-000000000102'
PHOTO='0195dc0b-3470-7000-8000-000000000103'


@pytest.fixture(scope='module')
def connection():
    conn=connect()
    try:
        apply_chain(conn.cursor())
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def cur(connection):
    c=connection.cursor()
    c.execute('SAVEPOINT meal_case')
    try:
        c.execute('SET LOCAL ROLE authenticated')
        as_owner(c)
        yield c
    finally:
        c.execute('ROLLBACK TO SAVEPOINT meal_case')
        c.execute('RELEASE SAVEPOINT meal_case')


def request(**changes):
    return {**dict(entry_id=CID,supersedes=None,occurred_at='2026-09-24T12:00:00-04:00',
                   text='fixture lunch',photo_capture_id=None),**changes}


def save(cur,payload):
    cur.execute('SELECT public.save_v0_meal(%s::jsonb)',(json.dumps(payload),))
    return cur.fetchone()[0]


def read(cur,day='2026-09-24'):
    cur.execute('SELECT public.get_v0_meals(%s)',(day,))
    return cur.fetchone()[0]['entries']


def photo(cur,completed=True,payload_sha=None,source='shortcut_photo'):
    cur.execute('RESET ROLE')
    sha='a'*64
    cur.execute("SELECT public.begin_capture_media_upload(%s,'photo',%s,10,'image/jpeg')",(PHOTO,sha))
    media=cur.fetchone()[0]
    if completed:
        cur.execute('SELECT public.complete_capture_media_upload(%s,%s)',(PHOTO,sha))
    cur.execute('SELECT public.receive_capture(%s)',(json.dumps(dict(capture_id=PHOTO,
        captured_at='2026-09-24T12:00:00-04:00',source=source,
        payload={'kind':'food','media_path':media['media_path'],'media_sha256':payload_sha or sha})),))
    assert cur.fetchone()[0]['status']=='created'
    cur.execute('SET LOCAL ROLE authenticated')


def test_REQ_CAP_005_016_017_RULE_06_meal_saved_before_nutrition(cur):
    receipt=save(cur,request())
    assert receipt['status']=='saved' and receipt==save(cur,request())
    items=read(cur)
    assert len(items)==1 and items[0]['text']=='fixture lunch'
    assert items[0]['nutrition']=={'status':'pending','items':[]}
    assert items[0]['save_status']=='saved'
    assert read(cur,'2026-09-23')==[]
    with pytest.raises(Exception,match='identity reused'):
        save(cur,request(text='different content'))


@pytest.mark.parametrize('text',['','fixture photo with note'])
def test_REQ_CAP_003_006_meal_reuses_completed_shortcut_photo(cur,text):
    photo(cur)
    save(cur,request(text=text,photo_capture_id=PHOTO))
    assert read(cur)[0]['photo_capture_id']==PHOTO


def test_REQ_CAP_006_meal_refuses_unconfirmed_upload(cur):
    photo(cur,completed=False)
    with pytest.raises(Exception,match='completed Shortcut photo'):
        save(cur,request(text='',photo_capture_id=PHOTO))


@pytest.mark.parametrize('changes',[
    {'text':''},{'text':None},{'text':'x'*10001},{'text':'   '},
    {'photo_capture_id':PHOTO},{'occurred_at':'2026-09-24T24:00:00-04:00'},
    {'calories':400},{'entry_id':'invalid'},
])
def test_REQ_CAP_007_RULE_06_meal_refuses_invalid_input(cur,changes):
    with pytest.raises(Exception):
        save(cur,request(**changes))


def test_REQ_CAP_014_RULE_02_meal_correction_preserves_original(cur):
    save(cur,request())
    save(cur,request(entry_id=NEXT,supersedes=CID,text='corrected fixture lunch'))
    current=read(cur)
    assert len(current)==1 and current[0]['entry_id']==NEXT
    assert current[0]['supersedes']==CID
    cur.execute('RESET ROLE')
    cur.execute('SELECT payload FROM core_pytest.raw_captures WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]['text']=='fixture lunch'


@pytest.mark.parametrize('role,claims',[('anon',{'email':'joseph.delany21@gmail.com'}),
                                      ('authenticated',{}),('authenticated',{'email':'other@example.test'})])
@pytest.mark.parametrize('op',['save','read'])
def test_RULE_29_meal_requires_owner(cur,role,claims,op):
    cur.execute(f'SET LOCAL ROLE {role}')
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps(claims),))
    with pytest.raises(Exception) as error:
        save(cur,request()) if op=='save' else read(cur)
    assert error.value.args[0]['C']=='42501'


def test_REQ_CAP_003_RULE_29_owner_photo_download_scope(cur):
    from pathlib import Path
    from tests.test_capture_media_receipts import storage_policies
    from tools.run_migration import split_statements
    photo(cur)
    save(cur,request(photo_capture_id=PHOTO))
    image=read(cur)[0]['photo']
    assert image=={'bucket':'captures','path':PHOTO+'/photo','content_type':'image/jpeg','size_bytes':10}
    cur.execute('RESET ROLE')
    storage_policies(cur)
    sql=Path('supabase/v0_meal_photo_policies.sql').read_text().replace('storage.','storage_pytest.').replace('SCHEMA storage ','SCHEMA storage_pytest ')
    for statement in split_statements(sql):
        cur.execute(statement)
    cur.execute("INSERT INTO storage_pytest.objects VALUES ('captures',%s),('captures','unlinked/photo'),('unrelated','existing')",(PHOTO+'/photo',))
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute("SELECT name FROM storage_pytest.objects WHERE bucket_id='captures'")
    assert [tuple(r) for r in cur.fetchall()]==[(PHOTO+'/photo',)]
    for sql in ('DELETE FROM storage_pytest.objects WHERE bucket_id=\'captures\'',
                "UPDATE storage_pytest.objects SET name='changed' WHERE bucket_id='captures'"):
        cur.execute(sql)
        assert cur.rowcount==0
    cur.execute('SAVEPOINT photo_write')
    with pytest.raises(Exception):
        cur.execute("INSERT INTO storage_pytest.objects VALUES ('captures','forbidden')")
    cur.execute('ROLLBACK TO SAVEPOINT photo_write')
    for role,claims in [('anon',{'email':'joseph.delany21@gmail.com'}),('authenticated',{})]:
        cur.execute('SET LOCAL ROLE '+role)
        cur.execute("SELECT set_config('request.jwt.claims',%s,true)",(json.dumps(claims),))
        cur.execute('SELECT bucket_id,name FROM storage_pytest.objects')
        assert [tuple(r) for r in cur.fetchall()]==[('unrelated','existing')]


def test_REQ_CAP_014_RULE_02_meal_rollback_after_raw_insert(cur):
    cur.execute('RESET ROLE')
    cur.execute("""CREATE FUNCTION core_pytest.fail_meal() RETURNS trigger LANGUAGE plpgsql
        AS $$ BEGIN RAISE EXCEPTION 'injected meal failure'; END $$""")
    cur.execute('''CREATE TRIGGER fail_meal BEFORE INSERT ON core_pytest.v0_meal_entries
        FOR EACH ROW EXECUTE FUNCTION core_pytest.fail_meal()''')
    cur.execute('SET LOCAL ROLE authenticated')
    cur.execute('SAVEPOINT failed_meal')
    with pytest.raises(Exception,match='injected meal failure'):
        save(cur,request())
    cur.execute('ROLLBACK TO SAVEPOINT failed_meal')
    assert read(cur)==[]
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==0
    cur.execute('DROP TRIGGER fail_meal ON core_pytest.v0_meal_entries')
    cur.execute('SET LOCAL ROLE authenticated')
    assert save(cur,request())['status']=='saved'


@pytest.mark.parametrize('change',[{'payload_sha':'b'*64},{'source':'shortcut_text'}])
def test_REQ_CAP_003_006_meal_refuses_photo_binding_mismatch(cur,change):
    photo(cur,**change)
    with pytest.raises(Exception,match='completed Shortcut photo'):
        save(cur,request(photo_capture_id=PHOTO))


def test_REQ_CAP_014_RULE_03_meal_correction_moves_day_and_refuses_stale(cur):
    save(cur,request())
    save(cur,request(entry_id=NEXT,supersedes=CID,occurred_at='2026-09-24T03:59:59-04:00'))
    assert read(cur)==[]
    assert read(cur,'2026-09-23')[0]['entry_id']==NEXT
    with pytest.raises(Exception,match='stale'):
        save(cur,request(entry_id='0195dc0b-3470-7000-8000-000000000104',supersedes=CID))


def test_RULE_02_29_meal_ledger_private_and_immutable(cur):
    save(cur,request())
    cur.execute('SAVEPOINT forbidden_read')
    with pytest.raises(Exception):
        cur.execute('SELECT * FROM core_pytest.v0_meal_entries')
    cur.execute('ROLLBACK TO SAVEPOINT forbidden_read')
    cur.execute('RESET ROLE')
    with pytest.raises(Exception,match='RULE-02'):
        cur.execute('DELETE FROM core_pytest.v0_meal_entries')


@pytest.mark.parametrize('removed',[False,True])
def test_REQ_CAP_014_RULE_06_meal_results_bound_to_exact_version(cur,removed):
    """Seed stored-result fixtures, not a claim that V0 text enrichment runs."""
    import uuid
    save(cur,request())
    cur.execute('RESET ROLE')
    trans,extract,item=[str(uuid.uuid4()) for _ in range(3)]
    sha='a'*64
    cur.execute('''INSERT INTO core_pytest.capture_transcription_attempts
        (request_id,capture_id,model_id,call_kind,payload_sha256,duration_seconds,
         estimated_neurons,processor_version)
        VALUES(%s,%s,'@cf/openai/whisper-large-v3-turbo','transcribe',%s,1,1,'fixture')''',
        (trans,CID,sha))
    cur.execute("SELECT public.record_capture_processing(%s,%s,NULL,'transcribed',NULL,'fixture')",(CID,trans))
    head=cur.fetchone()[0]['event_id']
    cur.execute('''INSERT INTO core_pytest.capture_extraction_attempts
        (request_id,capture_id,transcription_request_id,expected_event_id,model_id,
         profile,payload,payload_sha256,estimated_neurons,processor_version)
        VALUES(%s,%s,%s,%s,'@cf/meta/llama-3.1-8b-instruct','food','{}',%s,1,'fixture')''',
        (extract,CID,trans,head,sha))
    cur.execute("SELECT public.record_capture_processing(%s,%s,%s,'extracted',NULL,'fixture')",(CID,extract,head))
    event=cur.fetchone()[0]['event_id']
    cur.execute('''INSERT INTO core_pytest.capture_extraction_outcomes
        (request_id,capture_id,event_id,response_sha256) VALUES(%s,%s,%s,%s)''',
        (extract,CID,event,sha))
    result={'status':'removed'} if removed else {'status':'resolved','nutrients':{'kcal':[90,100,110]},'canonical_name':'fixture food'}
    cur.execute('''INSERT INTO core_pytest.capture_resolved_items
        (item_id,capture_id,extraction_request_id,item_index,occurred_at,subject_day,
         time_precision,time_provenance,time_reason,resolution)
        VALUES(%s,%s,%s,0,'2026-09-24T12:00:00-04:00','2026-09-24',
               'exact','extracted','fixture',%s::jsonb)''',(item,CID,extract,json.dumps(result)))
    cur.execute('SET LOCAL ROLE authenticated')
    nutrition=read(cur)[0]['nutrition']
    assert nutrition['status']==('removed' if removed else 'results_available')
    assert nutrition['items'][0]['resolution']==result
    save(cur,request(entry_id=NEXT,supersedes=CID,text='changed fixture meal'))
    current=read(cur)
    assert len(current)==1 and current[0]['entry_id']==NEXT
    assert current[0]['nutrition']=={'status':'pending','items':[]}
