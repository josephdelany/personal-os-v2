"""Private media transport tests: no network, audio files, or database writes."""
import hashlib
import uuid
import pytest
from lib import db,egress

CID='0195dc0b-3470-7000-8000-000000000003'
BODY=b'opaque fixture bytes'
DIGEST=hashlib.sha256(BODY).hexdigest()
PATH=CID+'/audio.m4a'

@pytest.fixture
def storage(monkeypatch):
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('SUPABASE_URL','https://fixture.supabase.co')
    monkeypatch.setenv('SUPABASE_STORAGE_READ_JWT','fixture-read-only-token')
    monkeypatch.setenv('SUPABASE_ANON_KEY','fixture-public-key')
    calls=[]
    class Response:
        status=200
        headers={'Content-Length':str(len(BODY))}
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def read(self,limit):
            calls.append(('read_limit',limit))
            return BODY
    class Opener:
        def open(self,request,timeout):
            calls.append(('request',request,timeout))
            return Response()
    def build(handler):
        calls.append(('handler',handler))
        return Opener()
    monkeypatch.setattr(egress.urllib.request,'build_opener',build)
    return calls,Response


def test_REQ_CAP_006_011_private_media_is_bound_and_bounded(storage):
    calls,_=storage
    assert db.read_capture_media(CID,PATH,DIGEST)==BODY
    request=calls[1][1]
    assert request.full_url=='https://fixture.supabase.co/storage/v1/object/authenticated/captures/'+PATH
    assert request.get_header('Authorization')=='Bearer fixture-read-only-token'
    assert calls[1][2]==30 and calls[2]==('read_limit',50*1024*1024+1)


@pytest.mark.parametrize('path',[None,'https://elsewhere.invalid/audio',CID+'/../audio',
    CID+'/%2e%2e',CID+'/audio?x=1',str(uuid.UUID(int=2))+'/audio',CID+'/a/b'])
def test_REQ_CAP_006_media_reference_cannot_choose_destination_or_other_capture(storage,path):
    with pytest.raises(ValueError):
        db.read_capture_media(CID,path,DIGEST)
    assert storage[0]==[]


def test_REQ_CAP_012_changed_media_object_cannot_silently_change_evidence(storage):
    with pytest.raises(db.CaptureMediaUnavailable,match='digest mismatch'):
        db.read_capture_media(CID,PATH,'0'*64)


def test_RULE_29_private_media_never_follows_redirect_with_credentials(storage):
    db.read_capture_media(CID,PATH,DIGEST)
    handler=storage[0][0][1]
    request=storage[0][1][1]
    with pytest.raises(db.CaptureMediaUnavailable,match='redirect'):
        handler.http_error_302(request,None,302,'moved',{'location':'https://elsewhere.invalid'})
    assert len([x for x in storage[0] if x[0]=='request'])==1


@pytest.mark.parametrize('origin',['http://fixture.supabase.co','https://fixture.supabase.co.evil.invalid',
    'https://user@fixture.supabase.co','https://fixture.supabase.co/path'])
def test_RULE_29_private_storage_origin_is_fixed_before_request(storage,monkeypatch,origin):
    monkeypatch.setenv('SUPABASE_URL',origin)
    with pytest.raises(db.CaptureMediaUnavailable):db.read_capture_media(CID,PATH,DIGEST)
    assert storage[0]==[]


def test_REQ_CAP_043_missing_credential_or_oversize_media_refuses(storage,monkeypatch):
    monkeypatch.delenv('SUPABASE_STORAGE_READ_JWT')
    with pytest.raises(db.CaptureMediaUnavailable):db.read_capture_media(CID,PATH,DIGEST)
    assert storage[0]==[]
    monkeypatch.setenv('SUPABASE_STORAGE_READ_JWT','fixture')
    storage[1].headers={'Content-Length':str(50*1024*1024+1)}
    with pytest.raises(db.CaptureMediaUnavailable,match='size'):db.read_capture_media(CID,PATH,DIGEST)
    assert not any(x[0]=='read_limit' for x in storage[0])


def test_RULE_29_model_process_refuses_storage_read_capability(monkeypatch):
    monkeypatch.setenv('SUPABASE_STORAGE_READ_JWT','fixture')
    with pytest.raises(RuntimeError,match='private database credentials'):
        db.connect_model_egress()


def test_REQ_CAP_043_slow_media_read_has_overall_deadline_and_restores_timer(storage,monkeypatch):
    import signal
    import time
    previous=signal.getsignal(signal.SIGALRM)
    monkeypatch.setattr(db,'CAPTURE_MEDIA_DEADLINE_SECONDS',0.03)
    def slow(self,limit):
        time.sleep(5)
        return BODY
    monkeypatch.setattr(storage[1],'read',slow)
    started=time.monotonic()
    with pytest.raises(db.CaptureMediaUnavailable,match='deadline exceeded'):
        db.read_capture_media(CID,PATH,DIGEST)
    assert time.monotonic()-started < 1
    assert signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0)
    assert signal.getsignal(signal.SIGALRM)==previous


def test_REQ_CAP_043_existing_deadline_is_not_disarmed_by_media_read(storage):
    import signal
    previous=signal.getsignal(signal.SIGALRM)
    signal.setitimer(signal.ITIMER_REAL,60)
    try:
        with pytest.raises(db.CaptureMediaUnavailable,match='already in use'):
            db.read_capture_media(CID,PATH,DIGEST)
        remaining,interval=signal.getitimer(signal.ITIMER_REAL)
        assert 0 < remaining <= 60 and interval==0
        assert signal.getsignal(signal.SIGALRM)==previous
        assert storage[0]==[]
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
