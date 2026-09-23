"""Immutable upload identity and ambiguous-completion recovery; rollback-only twin."""
import pytest
from tests._location_fixture import apply_chain
from tests._sql_fixture import connect,requires_disposable

pytestmark=requires_disposable
CID='0195dc0b-3470-7000-8000-000000000004'
DIGEST='a'*64

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


def begin(cur,digest=DIGEST):
    cur.execute("SELECT public.begin_capture_media_upload(%s,'voice',%s,12,'audio/mp4')",(CID,digest))
    return cur.fetchone()[0]


def test_REQ_CAP_006_012_media_identity_precedes_raw_capture_and_never_changes(cur):
    cur.execute('SET LOCAL ROLE capture_media_upload')
    first=begin(cur)
    assert first['status']=='awaiting_upload' and not first['duplicate']
    assert first['media_path']==CID+'/audio'
    assert begin(cur)=={**first,'duplicate':True}
    cur.execute('SAVEPOINT altered')
    with pytest.raises(Exception,match='different content'):
        begin(cur,'b'*64)
    cur.execute('ROLLBACK TO SAVEPOINT altered')
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures')
    assert cur.fetchone()[0]==0


def test_REQ_CAP_011_016_upload_completion_and_lost_response_reconcile_are_idempotent(cur):
    begin(cur)
    cur.execute('SET LOCAL ROLE service_role')
    cur.execute('SELECT public.reconcile_capture_media_upload(%s,%s)',(CID,DIGEST))
    receipt=cur.fetchone()[0]
    assert receipt['status']=='available'
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE capture_media_upload')
    assert begin(cur)['status']=='available'
    cur.execute('SELECT public.complete_capture_media_upload(%s,%s)',(CID,DIGEST))
    assert cur.fetchone()[0]==receipt
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*),min(verification_method) FROM core_pytest.capture_media_receipts')
    assert tuple(cur.fetchone())==(1,'private_hash_check')


def test_REQ_CAP_009_upload_role_cannot_read_private_evidence_or_reconcile(cur):
    begin(cur)
    for sql in ['SELECT * FROM core_pytest.capture_media_uploads',
                'SELECT * FROM core_pytest.raw_captures',
                "SELECT public.reconcile_capture_media_upload('%s','%s')" % (CID,DIGEST)]:
        cur.execute('SAVEPOINT permission')
        cur.execute('SET LOCAL ROLE capture_media_upload')
        with pytest.raises(Exception):cur.execute(sql)
        cur.execute('ROLLBACK TO SAVEPOINT permission')


def test_REQ_CAP_012_completed_media_is_readable_but_not_replaceable_by_storage_policy(cur):
    begin(cur)
    cur.execute('SET LOCAL ROLE capture_media_upload')
    cur.execute("SELECT public.capture_media_upload_allowed('captures',%s)",(CID+'/audio',))
    assert cur.fetchone()[0] is True
    cur.execute('SELECT public.complete_capture_media_upload(%s,%s)',(CID,DIGEST))
    cur.execute("SELECT public.capture_media_upload_allowed('captures',%s)",(CID+'/audio',))
    assert cur.fetchone()[0] is False
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE capture_media_reader')
    cur.execute("SELECT public.capture_media_read_allowed('captures',%s),public.capture_media_read_allowed('elsewhere',%s)",(CID+'/audio',CID+'/audio'))
    assert tuple(cur.fetchone())==(True,False)


def test_REQ_CAP_012_media_records_reject_mutation_and_digest_substitution(cur):
    begin(cur)
    cur.execute('SAVEPOINT wrong_digest')
    with pytest.raises(Exception,match='matching media'):
        cur.execute('SELECT public.complete_capture_media_upload(%s,%s)',(CID,'b'*64))
    cur.execute('ROLLBACK TO SAVEPOINT wrong_digest')
    for sql in ["UPDATE core_pytest.capture_media_uploads SET sha256='b'",
                'DELETE FROM core_pytest.capture_media_uploads',
                'TRUNCATE core_pytest.capture_media_uploads CASCADE']:
        cur.execute('SAVEPOINT immutable')
        with pytest.raises(Exception,match='append-only'):cur.execute(sql)
        cur.execute('ROLLBACK TO SAVEPOINT immutable')


def storage_policies(cur,dangerous=False):
    from pathlib import Path
    from tools import run_migration
    # This tests actual PostgreSQL RLS policy bodies against a disposable shape,
    # not the vendor Storage HTTP implementation or a live bucket.
    cur.execute('CREATE SCHEMA storage_pytest')
    cur.execute('CREATE TABLE storage_pytest.buckets (id text PRIMARY KEY,public boolean,file_size_limit bigint)')
    cur.execute("INSERT INTO storage_pytest.buckets VALUES ('captures',false,52428800)")
    cur.execute('CREATE TABLE storage_pytest.objects (bucket_id text,name text,UNIQUE(bucket_id,name))')
    cur.execute('ALTER TABLE storage_pytest.objects ENABLE ROW LEVEL SECURITY')
    # Deliberately hostile inherited privileges: the new restrictive guards must win.
    cur.execute('GRANT USAGE ON SCHEMA storage_pytest TO PUBLIC')
    cur.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON storage_pytest.objects TO PUBLIC')
    cur.execute('CREATE POLICY fixture_legacy_public ON storage_pytest.objects TO PUBLIC USING(true) WITH CHECK(true)')
    if dangerous:
        cur.execute('GRANT TRUNCATE ON storage_pytest.objects TO PUBLIC')
    sql=Path('supabase/capture_storage_policies.sql').read_text().replace('storage.','storage_pytest.').replace('SCHEMA storage ','SCHEMA storage_pytest ')
    for statement in run_migration.split_statements(sql):cur.execute(statement)


def test_REQ_CAP_009_012_storage_policy_contains_inherited_public_access(cur):
    begin(cur)
    storage_policies(cur)
    cur.execute('SET LOCAL ROLE capture_media_upload')
    cur.execute("INSERT INTO storage_pytest.objects VALUES ('captures',%s)",(CID+'/audio',))
    cur.execute('SELECT * FROM storage_pytest.objects')
    assert not cur.fetchall()
    cur.execute('RESET ROLE')
    for role in ('anon','authenticated','model_egress','capture_ingest'):
        cur.execute('SET LOCAL ROLE '+role)
        cur.execute('SELECT * FROM storage_pytest.objects')
        assert not cur.fetchall()
        cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE capture_media_reader')
    cur.execute('SELECT * FROM storage_pytest.objects')
    assert [tuple(row) for row in cur.fetchall()]==[('captures',CID+'/audio')]
    for sql in ["UPDATE storage_pytest.objects SET name='changed'",
                'DELETE FROM storage_pytest.objects']:
        cur.execute(sql)
        assert cur.rowcount==0
    cur.execute('RESET ROLE')
    cur.execute("INSERT INTO storage_pytest.objects VALUES ('unrelated','existing-policy')")
    cur.execute('SET LOCAL ROLE anon')
    cur.execute('SELECT * FROM storage_pytest.objects')
    assert [tuple(row) for row in cur.fetchall()]==[('unrelated','existing-policy')]


@pytest.mark.parametrize('role,bucket,name',[
    ('capture_media_upload','captures','unregistered/audio'),
    ('capture_media_upload','other',CID+'/audio'),
    ('capture_media_reader','captures',CID+'/audio'),
    ('anon','captures',CID+'/audio'),
])
def test_REQ_CAP_009_012_storage_rejects_unregistered_or_wrong_role_uploads(cur,role,bucket,name):
    begin(cur)
    storage_policies(cur)
    cur.execute('SET LOCAL ROLE '+role)
    with pytest.raises(Exception,match='row-level security'):
        cur.execute('INSERT INTO storage_pytest.objects VALUES (%s,%s)',(bucket,name))


def test_REQ_CAP_006_012_reconcile_verifies_bytes_and_recovers_missing_raw_hash(cur,monkeypatch):
    import hashlib,json,uuid
    from lib import db
    from tools.engines import capture_transcription as engine
    body=b'fixturebytes'
    digest=hashlib.sha256(body).hexdigest()
    begin(cur,digest)
    cur.execute("""INSERT INTO core_pytest.raw_captures
        (capture_id,captured_at,source,trust_level,payload)
        VALUES (%s,now(),'shortcut_voice','untrusted',%s)""",
        (CID,json.dumps({'media_path':CID+'/audio','duration_s':12})))
    cur.execute('SELECT to_jsonb(r) FROM core_pytest.raw_captures r WHERE capture_id=%s',(CID,))
    original=cur.fetchone()[0]
    cur.execute('SET LOCAL ROLE service_role')
    with pytest.raises(ValueError,match='verified media binding'):
        engine.prepare_media(cur,capture_id=CID,request_id=uuid.uuid4(),schema='core_pytest')
    def unavailable(*args):raise db.CaptureMediaUnavailable('fixture unreadable')
    monkeypatch.setattr(db,'read_capture_media',unavailable)
    with pytest.raises(db.CaptureMediaUnavailable):
        engine.reconcile_media(cur,capture_id=CID,schema='core_pytest')
    cur.execute('SELECT count(*) FROM core_pytest.capture_media_receipts')
    assert cur.fetchone()[0]==0
    calls=[]
    def download(cid,path,sha):
        calls.append((cid,path,sha))
        return body
    monkeypatch.setattr(db,'read_capture_media',download)
    assert engine.reconcile_media(cur,capture_id=CID,schema='core_pytest')['status']=='available'
    prepared=engine.prepare_media(cur,capture_id=CID,request_id=uuid.uuid4(),schema='core_pytest')
    assert prepared['capture_id']==CID
    assert calls==[(CID,CID+'/audio',digest)]*2
    cur.execute('SELECT to_jsonb(r) FROM core_pytest.raw_captures r WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==original


def test_REQ_CAP_012_storage_activation_refuses_public_truncate_bypass(cur):
    with pytest.raises(Exception,match='PUBLIC privileges bypass RLS'):
        storage_policies(cur,dangerous=True)


def test_REQ_CAP_006_011_016_030_034_uploaded_voice_reaches_saved_transcript(cur,monkeypatch):
    """Use real scoped RPCs and private engine across the upload/ingress boundary.

    Provider bytes/response are fixtures; the whole transaction rolls back. This
    proves stage compatibility, not commit visibility or live provider behavior.
    """
    import hashlib,json,uuid
    from lib import db
    from lib.model_contract import request_bytes
    from tools.engines import capture_transcription as engine
    body=b'fixturebytes'
    digest=hashlib.sha256(body).hexdigest()
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL'):
        monkeypatch.delenv(key,raising=False)
    cur.execute('SET LOCAL ROLE capture_media_upload')
    identity=begin(cur,digest)
    cur.execute('SELECT public.complete_capture_media_upload(%s,%s)',(CID,digest))
    media=cur.fetchone()[0]
    assert media['status']=='available'
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE capture_ingest')
    envelope={'capture_id':CID,'captured_at':'2026-09-22T08:00:00-04:00',
              'source':'shortcut_voice','payload':{'kind':'food','duration_s':12,
              'media_path':media['media_path'],'media_sha256':media['media_sha256']}}
    cur.execute('SELECT public.receive_capture(%s)',(json.dumps(envelope),))
    assert cur.fetchone()[0]=={'capture_id':CID,'status':'created'}
    cur.execute('SELECT public.receive_capture(%s)',(json.dumps(envelope),))
    assert cur.fetchone()[0]=={'capture_id':CID,'status':'duplicate'}
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE service_role')
    def download(cid,path,sha):
        assert (cid,path,sha)==(CID,identity['media_path'],digest)
        return body
    monkeypatch.setattr(db,'read_capture_media',download)
    prepared=engine.prepare_media(cur,capture_id=CID,request_id=uuid.uuid4(),schema='core_pytest')
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE model_egress')
    sent=request_bytes(prepared['payload'])
    cur.execute('SELECT public.reserve_model_call(%s,%s,%s,%s,%s,%s,%s)',
        (prepared['request_id'],prepared['model_id'],prepared['call_kind'],
         prepared['estimated_neurons'],CID,len(sent),hashlib.sha256(sent).hexdigest()))
    assert cur.fetchone()[0]['allowed']
    response={'success':True,'result':{'text':'fixture words',
              'segments':[{'start':0,'end':1.2,'text':'fixture words'}]}}
    received=request_bytes(response)
    cur.execute('SELECT public.settle_model_response(%s,%s,%s,%s)',
        (prepared['request_id'],'ok',received.decode(),None))
    cur.execute('RESET ROLE')
    cur.execute('SET LOCAL ROLE service_role')
    outcome=engine.consume(cur,request_id=prepared['request_id'],response=response,schema='core_pytest')
    assert outcome['applied'] and outcome['processing_status']=='transcribed'
    assert engine.consume(cur,request_id=prepared['request_id'],response=response,schema='core_pytest')==outcome
    cur.execute('SELECT transcript FROM core_pytest.capture_transcription_current WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]=='fixture words'
    cur.execute('SELECT payload FROM core_pytest.raw_captures WHERE capture_id=%s',(CID,))
    assert cur.fetchone()[0]==envelope['payload']
    cur.execute('RESET ROLE')
    cur.execute('SELECT count(*) FROM core_pytest.raw_captures')
    assert cur.fetchone()[0]==1
    cur.execute('SELECT count(*) FROM core_pytest.capture_transcription_outcomes')
    assert cur.fetchone()[0]==1
    cur.execute('SELECT count(*) FROM core_pytest.atoms')
    assert cur.fetchone()[0]==0, 'transcribed must not be mistaken for extracted/enriched'


def test_REQ_CAP_009_012_034_processing_receipt_read_is_private_and_read_only(cur):
    for role in ('anon','authenticated','capture_ingest','capture_media_upload','capture_media_reader','model_egress'):
        cur.execute("SELECT has_table_privilege(%s,'core_pytest.capture_processing_events','SELECT')",(role,))
        assert cur.fetchone()[0] is False
    for privilege in ('INSERT','UPDATE','DELETE','TRUNCATE'):
        cur.execute("SELECT has_table_privilege('service_role','core_pytest.capture_processing_events',%s)",(privilege,))
        assert cur.fetchone()[0] is False
