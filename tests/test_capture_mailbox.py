"""REQ-CAP-025/026 durable transport boundaries; SQL remains authoritative."""
import os
import subprocess
import sys
import time
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


def test_REQ_CAP_026_contending_process_refuses_promptly_without_changing_queue(boxes,request_body):
    requests,_=boxes
    mailbox.publish(requests,request_body)

    script='''import os,fcntl,sys
fd=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY)
fcntl.flock(fd,fcntl.LOCK_EX)
print('ready',flush=True)
sys.stdin.read(1)
'''
    child=subprocess.Popen([sys.executable,'-c',script,str(requests)],env={},
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        # communicate cannot be used until the lock-holder is released.
        import select
        ready,_,_=select.select([child.stdout],[],[],5)
        assert ready and child.stdout.readline().strip()=='ready'
        start=time.monotonic()
        with pytest.raises(BlockingIOError):mailbox.publish(requests,request_body)
        assert time.monotonic()-start<1
        assert mailbox.read(requests,request_body['request_id'])==request_body
    finally:
        try:child.communicate('x',timeout=5)
        except subprocess.TimeoutExpired:child.kill();child.communicate()
    assert child.returncode==0
    mailbox.publish(requests,request_body)


def test_REQ_CAP_026_control_retention_follows_request_retirement(boxes,request_body):
    requests,results=boxes;identity=request_body['request_id']
    receipt={'request_id':identity,'status':'settled'}
    mailbox.publish(requests,request_body)
    mailbox.store_result(results,request_body,receipt)
    assert not mailbox.retire_control(requests,results,identity)
    assert mailbox.result(results,request_body)==receipt
    mailbox.retire(requests,request_body)
    assert mailbox.retire_control(requests,results,identity)
    assert mailbox.pending(results)==[]
    assert not mailbox.retire_control(requests,results,identity)


def test_REQ_CAP_026_missing_channel_or_present_symlink_cannot_authorize_control_removal(boxes,request_body,tmp_path):
    requests,results=boxes;identity=request_body['request_id']
    mailbox.store_result(results,request_body,{'request_id':identity,'status':'settled'})
    with pytest.raises(FileNotFoundError):mailbox.retire_control(tmp_path/'missing',results,identity)
    (requests/(identity+'.json')).symlink_to(requests/'missing')
    assert not mailbox.retire_control(requests,results,identity)
    assert mailbox.pending(results)==[identity]


def test_REQ_CAP_026_outbound_poll_cleans_orphan_control_without_provider(boxes,request_body,tmp_path,monkeypatch):
    from tools import capture_dispatch_mailbox as worker
    requests,results=boxes;state=tmp_path/'state';state.mkdir(mode=0o700)
    mailbox.store_result(results,request_body,{'request_id':request_body['request_id'],'status':'settled'})
    monkeypatch.setattr(worker,'dispatch',lambda *a:pytest.fail('no queued provider request'))
    result=worker.poll('model',requests,results,state)
    assert result['status']=='polled' and result['cleanup']['status']=='retired'
    assert result['items']==[] and mailbox.pending(results)==[]


@pytest.mark.parametrize('bound',['files','bytes','free'])
def test_REQ_CAP_026_capacity_refuses_new_work_without_removing_existing_request(boxes,request_body,monkeypatch,bound):
    requests,_=boxes
    mailbox.publish(requests,request_body)
    if bound=='files':monkeypatch.setattr(mailbox,'MAX_DIRECTORY_FILES',1)
    elif bound=='bytes':monkeypatch.setattr(mailbox,'MAX_DIRECTORY_BYTES',1)
    else:
        from types import SimpleNamespace
        monkeypatch.setattr(mailbox.os,'fstatvfs',lambda fd:SimpleNamespace(f_bavail=0,f_frsize=4096))
    mailbox.publish(requests,request_body)  # confirmed identical publication needs no disk allocation
    with pytest.raises(ValueError,match='capacity'):
        mailbox.publish(requests,{**request_body,'request_id':str(uuid.uuid4())})
    assert mailbox.read(requests,request_body['request_id'])==request_body
    assert list(requests.iterdir())==[requests/(request_body['request_id']+'.json')]


def test_REQ_CAP_026_killed_publication_temporary_recovers_under_writer_lock(boxes,request_body):
    import signal
    from pathlib import Path
    requests,_=boxes
    script='''import os,signal
from lib import capture_mailbox as mailbox
def crash(*args,**kwargs):os.kill(os.getpid(),signal.SIGKILL)
mailbox.os.link=crash
mailbox.publish(DIRECTORY,REQUEST)
'''.replace('DIRECTORY',repr(str(requests))).replace('REQUEST',repr(request_body))
    root=Path(__file__).resolve().parents[1]
    child=subprocess.run([sys.executable,'-c',script],cwd=root,env={'PYTHONPATH':str(root)},
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert child.returncode==-signal.SIGKILL
    assert len(list(requests.glob('.tmp-*')))==1 and mailbox.pending(requests)==[]
    mailbox.publish(requests,request_body)
    assert list(requests.glob('.tmp-*'))==[]
    assert mailbox.read(requests,request_body['request_id'])==request_body


def test_REQ_CAP_026_pruning_temporary_hardlink_preserves_published_request(boxes,request_body):
    requests,_=boxes
    mailbox.publish(requests,request_body)
    os.link(requests/(request_body['request_id']+'.json'),requests/('.tmp-'+str(uuid.uuid4())))
    mailbox.publish(requests,request_body)
    assert list(requests.glob('.tmp-*'))==[]
    assert mailbox.read(requests,request_body['request_id'])==request_body
