"""Real bounded child processes; no database fixture or provider call."""
import json
import os
import sys
import time
import uuid
import pytest
from tools import model_worker as worker

RID=str(uuid.UUID(int=7))
REQUEST={'request_id':RID,'model_id':'@cf/meta/fixture','call_kind':'extract',
         'payload':{'prompt':'fixture'},'estimated_neurons':1}


@pytest.fixture(autouse=True)
def no_capabilities(monkeypatch):
    for key in worker.FOREIGN_CREDENTIALS+worker.MODEL_ENV+('PERSONAL_OS_TEST_SOCKET',):
        monkeypatch.delenv(key,raising=False)


def program(monkeypatch,source):
    monkeypatch.setattr(worker,'_command',lambda:[sys.executable,'-c',source])


ACK='''import os,json,sys,signal,time
request=json.load(sys.stdin)
os.write(int(os.environ['PERSONAL_OS_MODEL_RESERVATION_FD']),json.dumps({'request_id':request['request_id'],'reserved':True}).encode())
'''


def test_REQ_CAP_026_timed_out_owned_child_is_dead_before_reconciliation(monkeypatch,tmp_path):
    pidfile=tmp_path/'worker.pid'
    program(monkeypatch,ACK+f"open({str(pidfile)!r},'w').write(str(os.getpid()))\n"+
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(60)")
    calls=[]
    def reconcile(request_id):
        pid=int(pidfile.read_text())
        with pytest.raises(ProcessLookupError):os.kill(pid,0)
        calls.append(request_id)
        return 'error'
    monkeypatch.setattr(worker,'_reconcile',reconcile)
    started=time.monotonic()
    assert worker.run(REQUEST,deadline=0.5)=={
        'request_id':RID,'status':'settled','outcome':'error','timed_out':True}
    assert time.monotonic()-started<5 and calls==[RID]


@pytest.mark.parametrize('tail', ['sys.exit(0)','sys.exit(1)'])
def test_REQ_CAP_026_owned_exit_recovers_receipt_instead_of_trusting_stdout(monkeypatch,tail):
    program(monkeypatch,ACK+"print('fixture private response')\n"+tail)
    calls=[]
    monkeypatch.setattr(worker,'_reconcile',lambda rid:(calls.append(rid) or 'ok'))
    assert worker.run(REQUEST)['outcome']=='ok'
    assert calls==[RID]


@pytest.mark.parametrize('source',[
    'import time;time.sleep(60)',
    "import sys;print('duplicate request',file=sys.stderr);sys.exit(1)",
    ACK.replace("request['request_id']","'wrong-request'")])
def test_REQ_CAP_026_unowned_child_cannot_authorize_replacement(monkeypatch,source):
    program(monkeypatch,source)
    monkeypatch.setattr(worker,'_reconcile',lambda rid:pytest.fail('unowned reconciliation'))
    assert worker.run(REQUEST,deadline=0.5)=={'request_id':RID,'status':'unconfirmed'}


def test_REQ_CAP_037_budget_refusal_has_no_owned_reservation(monkeypatch):
    program(monkeypatch,"import sys;print('{\"error_type\":\"BudgetExceeded\"}',file=sys.stderr);sys.exit(1)")
    monkeypatch.setattr(worker,'_reconcile',lambda rid:pytest.fail('no reservation'))
    assert worker.run(REQUEST)=={'request_id':RID,'status':'deferred_budget'}


def test_REQ_CAP_026_failed_reconciliation_does_not_claim_settlement(monkeypatch):
    program(monkeypatch,ACK)
    def unavailable(rid): raise RuntimeError('fixture private database detail')
    monkeypatch.setattr(worker,'_reconcile',unavailable)
    assert worker.run(REQUEST)=={'request_id':RID,'status':'settlement_unconfirmed'}


@pytest.mark.parametrize('key',worker.FOREIGN_CREDENTIALS+('PERSONAL_OS_TEST_SOCKET',))
def test_RULE_29_foreign_or_disposable_context_refuses_before_worker_launch(monkeypatch,key):
    monkeypatch.setenv(key,'fixture forbidden')
    monkeypatch.setattr(worker.subprocess,'Popen',lambda *a,**kw:pytest.fail('must not launch'))
    with pytest.raises(ValueError):worker.run(REQUEST)


def test_RULE_29_child_does_not_inherit_unrelated_environment(monkeypatch):
    monkeypatch.setenv('FIXTURE_UNRELATED_SECRET','fixture')
    program(monkeypatch,"import os;assert 'FIXTURE_UNRELATED_SECRET' not in os.environ\n"+ACK)
    monkeypatch.setattr(worker,'_reconcile',lambda rid:'ok')
    assert worker.run(REQUEST)['outcome']=='ok'


def test_RULE_29_reservation_ack_follows_confirmed_commit_and_precedes_send(monkeypatch):
    from lib import egress
    from tests.test_model_dispatch import Connection, MODEL
    events=[]
    conn=Connection()
    conn.permit['request_id']=RID
    def ack(rid):
        assert conn.commits==1
        events.append('ack')
    def send(model,body):
        assert events==['ack']
        events.append('send')
        return b'{}'
    egress.dispatch(conn,request_id=RID,model_id=MODEL,call_kind='plan',payload={'prompt':'fixture'},
        estimated_neurons=1,_on_reserved=ack,_transport=send)
    assert events==['ack','send']


@pytest.mark.parametrize('mode',['duplicate','uncertain_commit'])
def test_REQ_CAP_026_no_ownership_ack_for_duplicate_or_unconfirmed_commit(mode):
    from lib import egress
    from tests.test_model_dispatch import Connection, MODEL
    conn=Connection(fail_commit=1 if mode=='uncertain_commit' else None)
    conn.permit['request_id']=RID
    if mode=='duplicate':conn.permit={'allowed':False,'duplicate':True}
    with pytest.raises(egress.DispatchRefused):
        egress.dispatch(conn,request_id=RID,model_id=MODEL,call_kind='plan',payload={'prompt':'fixture'},
            estimated_neurons=1,_on_reserved=lambda rid:pytest.fail('unconfirmed ownership'),
            _transport=lambda *args:pytest.fail('unconfirmed send'))


def test_RULE_29_actual_model_CLI_writes_only_bound_reservation_to_private_pipe(monkeypatch,capsys):
    import io
    from tools import model_egress as cli
    from tests.test_model_dispatch import Connection
    conn=Connection();conn.permit['request_id']=RID;conn.close=lambda:None
    monkeypatch.setattr(cli.db,'connect_model_egress',lambda:conn)
    monkeypatch.setattr(cli.egress,'_post',lambda *args:b'{}')
    monkeypatch.setattr(cli.sys,'stdin',io.StringIO(json.dumps(REQUEST)))
    reader,writer=os.pipe()
    try:
        monkeypatch.setenv('PERSONAL_OS_MODEL_RESERVATION_FD',str(writer))
        assert cli.main()==0
        os.set_blocking(reader,False)
        assert json.loads(os.read(reader,4096))=={'request_id':RID,'reserved':True}
        assert conn.commits==2
        assert json.loads(capsys.readouterr().out)=={'request_id':RID,'result':{}}
    finally:
        os.close(reader);os.close(writer)
