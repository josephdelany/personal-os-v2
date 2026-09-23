"""REQ-CAP-025/026 durable transport boundaries; SQL remains authoritative."""
import os
import uuid

import pytest

from lib import capture_mailbox as mailbox


@pytest.fixture
def boxes(tmp_path):
    paths=[tmp_path/'requests',tmp_path/'results']
    for path in paths:path.mkdir(mode=0o750)
    return paths


@pytest.fixture
def request_body():
    return {'request_id':str(uuid.uuid4()),'payload':{'text':'fixture'}}


def test_REQ_CAP_025_restart_republish_and_retire(boxes,request_body):
    requests,results=boxes
    mailbox.publish(requests,request_body)
    mailbox.publish(requests,request_body)
    identity=request_body['request_id']
    assert mailbox.pending(requests)==[identity]
    assert mailbox.read(requests,identity)==request_body
    with pytest.raises(ValueError,match='identity reused'):
        mailbox.publish(requests,{**request_body,'payload':{}})
    receipt={'request_id':identity,'status':'settled'}
    mailbox.store_result(results,request_body,receipt)
    assert mailbox.result(results,request_body)==receipt
    with pytest.raises(ValueError,match='unbound'):
        mailbox.result(results,{**request_body,'payload':{}})
    with pytest.raises(ValueError,match='retirement identity'):
        mailbox.retire(requests,{**request_body,'payload':{}})
    assert mailbox.read(requests,identity)==request_body
    mailbox.retire(requests,request_body)
    assert mailbox.pending(requests)==[]


@pytest.mark.parametrize('mode',[0o770,0o755])
def test_REQ_CAP_026_unsafe_directory_refused(boxes,request_body,mode):
    requests,_=boxes
    requests.chmod(mode)
    with pytest.raises(ValueError,match='one owner'):
        mailbox.publish(requests,request_body)
    assert list(requests.iterdir())==[]


@pytest.mark.parametrize('kind',['symlink','fifo','public','noncanonical'])
def test_REQ_CAP_026_unsafe_entry_refused(boxes,request_body,kind):
    requests,_=boxes
    identity=request_body['request_id']
    path=requests/(identity+'.json')
    if kind=='symlink':path.symlink_to(requests/'missing')
    elif kind=='fifo':os.mkfifo(path,0o600)
    else:
        mailbox.publish(requests,request_body)
        if kind=='public':path.chmod(0o644)
        else:path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises((ValueError,OSError)):
        mailbox.read(requests,identity)


def test_REQ_CAP_025_failed_publication_leaves_no_partial_request(boxes,request_body,monkeypatch):
    requests,_=boxes
    def fail(*args,**kwargs):raise OSError('publication interrupted')
    monkeypatch.setattr(mailbox.os,'link',fail)
    with pytest.raises(OSError,match='interrupted'):mailbox.publish(requests,request_body)
    assert mailbox.pending(requests)==[]
    assert list(requests.iterdir())==[]


def test_REQ_CAP_025_publication_assigns_channel_reader_group_and_refuses_failure(boxes,request_body,monkeypatch):
    requests,_=boxes
    calls=[]
    actual=os.fchown
    def change(fd,uid,gid):
        calls.append((uid,gid));actual(fd,uid,gid)
    monkeypatch.setattr(mailbox.os,'fchown',change)
    mailbox.publish(requests,request_body)
    assert calls==[(-1,requests.stat().st_gid)]
    assert (requests/(request_body['request_id']+'.json')).stat().st_gid==requests.stat().st_gid
    mailbox.retire(requests,request_body)
    def denied(*args):raise PermissionError('reader group not provisioned')
    monkeypatch.setattr(mailbox.os,'fchown',denied)
    with pytest.raises(PermissionError):mailbox.publish(requests,request_body)
    assert list(requests.iterdir())==[]


@pytest.mark.parametrize('role',['model','reference'])
def test_REQ_CAP_025_role_dispatch_persists_bound_control_without_retiring(boxes,request_body,monkeypatch,role):
    from tools import capture_dispatch_mailbox,model_worker,reference_worker
    requests,results=boxes
    mailbox.publish(requests,request_body)
    receipt={'request_id':request_body['request_id'],'status':'settled'}
    selected=model_worker if role=='model' else reference_worker
    other=reference_worker if role=='model' else model_worker
    def run(request):
        assert request==request_body
        return receipt
    def forbidden(request):raise AssertionError('other role invoked')
    monkeypatch.setattr(selected,'run',run)
    monkeypatch.setattr(other,'run',forbidden)
    assert capture_dispatch_mailbox.dispatch(role,requests,results,request_body['request_id'])==receipt
    assert mailbox.result(results,request_body)==receipt
    assert mailbox.read(requests,request_body['request_id'])==request_body


@pytest.mark.parametrize('status',['settled','deferred_budget'])
def test_REQ_CAP_026_completed_control_prevents_redispatch(boxes,request_body,monkeypatch,status):
    from tools import capture_dispatch_mailbox,model_worker
    requests,results=boxes
    mailbox.publish(requests,request_body)
    receipt={'request_id':request_body['request_id'],'status':status}
    mailbox.store_result(results,request_body,receipt)
    def forbidden(request):raise AssertionError('terminal request dispatched twice')
    monkeypatch.setattr(model_worker,'run',forbidden)
    assert capture_dispatch_mailbox.dispatch('model',requests,results,request_body['request_id'])==receipt


@pytest.mark.parametrize('commit_fails',[False,True])
def test_REQ_CAP_025_private_cli_commits_before_publication(boxes,request_body,monkeypatch,capsys,commit_fails):
    from tools import capture_transcription as cli
    from tools.engines import capture_runtime
    events=[]
    class Connection:
        def cursor(self):return object()
        def commit(self):
            events.append('commit')
            assert mailbox.pending(boxes[0])==[]
            if commit_fails:raise RuntimeError('commit unconfirmed')
        def rollback(self):events.append('rollback')
        def close(self):events.append('close')
    monkeypatch.setattr(cli.engine,'_private',lambda schema:schema)
    monkeypatch.setattr(cli.db,'connect',Connection)
    monkeypatch.setattr(cli,'owner_context',lambda cur:None)
    monkeypatch.setattr(capture_runtime,'advance',lambda *args,**kwargs:
        {'status':'dispatch','worker':'model','stage':'transcribe','request':request_body})
    code=cli.main(['advance',str(uuid.uuid4()),'--model-outbox',str(boxes[0]),
                   '--reference-outbox',str(boxes[1])])
    output=capsys.readouterr()
    if commit_fails:
        assert code==1 and mailbox.pending(boxes[0])==[] and output.out==''
        assert events==['commit','rollback','close']
    else:
        assert code==0 and mailbox.read(boxes[0],request_body['request_id'])==request_body
        assert 'payload' not in output.out and 'queued' in output.out
        assert events==['commit','close']


@pytest.mark.parametrize('ready,commit_fails',[(False,False),(True,False),(True,True)])
def test_REQ_CAP_026_retirement_requires_consumption_and_confirmed_commit(boxes,request_body,monkeypatch,capsys,ready,commit_fails):
    from tools import capture_transcription as cli
    from tools.engines import capture_mailbox as private
    mailbox.publish(boxes[0],request_body)
    class Connection:
        def cursor(self):return object()
        def commit(self):
            assert mailbox.read(boxes[0],request_body['request_id'])==request_body
            if commit_fails:raise RuntimeError('commit unconfirmed')
        def rollback(self):pass
        def close(self):pass
    monkeypatch.setattr(cli.engine,'_private',lambda schema:schema)
    monkeypatch.setattr(cli.db,'connect',Connection)
    monkeypatch.setattr(cli,'owner_context',lambda cur:None)
    monkeypatch.setattr(private,'consumed',lambda *args,**kwargs:ready)
    code=cli.main(['retire-request','transcribe',str(boxes[0]),request_body['request_id']])
    capsys.readouterr()
    assert code==int(commit_fails)
    assert bool(mailbox.pending(boxes[0]))==(not ready or commit_fails)


def test_REQ_CAP_026_poll_persists_fair_position_across_failure_and_restart(boxes,tmp_path,monkeypatch):
    from tools import capture_dispatch_mailbox as worker
    state=tmp_path/'state';state.mkdir(mode=0o700)
    ids=[str(uuid.UUID(int=n)) for n in (1,2,3)]
    for identity in ids:mailbox.publish(boxes[0],{'request_id':identity})
    seen=[]
    def dispatch(role,requests,results,identity):
        seen.append(identity)
        if identity==ids[0]:raise RuntimeError('unavailable provider')
        return {'request_id':identity,'status':'settled'}
    monkeypatch.setattr(worker,'dispatch',dispatch)
    for _ in range(4):
        result=worker.poll('model',*boxes,state)
        assert len(result['items'])==1
    assert seen==ids+[ids[0]]
    with pytest.raises(ValueError,match='configuration mismatch'):
        worker.poll('reference',*boxes,state)


def test_REQ_CAP_026_poll_crash_advances_cursor_without_losing_request(boxes,tmp_path,monkeypatch):
    from tools import capture_dispatch_mailbox as worker
    state=tmp_path/'state';state.mkdir(mode=0o700)
    ids=[str(uuid.UUID(int=n)) for n in (1,2)]
    for identity in ids:mailbox.publish(boxes[0],{'request_id':identity})
    def crash(*args):raise KeyboardInterrupt()
    monkeypatch.setattr(worker,'dispatch',crash)
    with pytest.raises(KeyboardInterrupt):worker.poll('model',*boxes,state)
    seen=[]
    def dispatch(*args):
        seen.append(args[-1]);return {'request_id':args[-1],'status':'settled'}
    monkeypatch.setattr(worker,'dispatch',dispatch)
    worker.poll('model',*boxes,state)
    worker.poll('model',*boxes,state)
    assert seen==[ids[1],ids[0]]
    assert mailbox.pending(boxes[0])==ids
    with pytest.raises(ValueError,match='separate'):
        worker.poll('model',*boxes,boxes[1])
