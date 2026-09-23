"""Real bounded reference child processes; never a provider call."""
import os
import sys
import pytest
from tools import reference_worker as worker
from tests.test_reference_dispatch import REQUEST, RID, Connection
from tools.engines import reference_dispatch


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key in reference_dispatch.PRIVATE_CREDENTIALS+worker.REFERENCE_ENV+('PERSONAL_OS_TEST_SOCKET',):
        monkeypatch.delenv(key,raising=False)


@pytest.mark.parametrize('owned',[False,True])
def test_REQ_CAP_026_REQ_NUT_012_reference_timeout_requires_owned_dead_child(monkeypatch,tmp_path,owned):
    pidfile=tmp_path/'child.pid'
    source="import os,json,sys,time\nr=json.load(sys.stdin)\n"
    source+=f"open({str(pidfile)!r},'w').write(str(os.getpid()))\n"
    if owned:
        source+="os.write(int(os.environ['PERSONAL_OS_REFERENCE_RESERVATION_FD']),json.dumps({'request_id':r['request_id'],'reserved':True}).encode())\n"
    source+="time.sleep(60)"
    monkeypatch.setattr(worker,'_command',lambda:[sys.executable,'-c',source])
    calls=[]
    def reconcile(rid):
        with pytest.raises(ProcessLookupError):os.kill(int(pidfile.read_text()),0)
        calls.append(rid)
        return 'uncertain'
    monkeypatch.setattr(worker,'_reconcile',reconcile)
    result=worker.run(REQUEST,deadline=0.5)
    assert calls==([RID] if owned else [])
    assert result['status']==('settled' if owned else 'unconfirmed')
    if owned:assert result['outcome']=='uncertain' and result['timed_out']


@pytest.mark.parametrize('key',reference_dispatch.PRIVATE_CREDENTIALS+('PERSONAL_OS_TEST_SOCKET',))
def test_RULE_29_reference_worker_rejects_foreign_or_disposable_launch(monkeypatch,key):
    monkeypatch.setenv(key,'fixture forbidden')
    monkeypatch.setattr(worker.process.subprocess,'Popen',lambda *a,**kw:pytest.fail('must not launch'))
    with pytest.raises(ValueError):worker.run(REQUEST)


@pytest.mark.parametrize('mode',['success','duplicate','uncertain_commit'])
def test_RULE_29_reference_ack_is_new_committed_reservation_only(mode):
    conn=Connection(allowed=mode!='duplicate',fail_commit=1 if mode=='uncertain_commit' else None)
    events=[]
    def ack(rid):
        assert conn.commits==1 and rid==RID
        events.append('ack')
    def send(*args):
        assert events==['ack']
        events.append('send')
        return b'{"foods":[]}'
    if mode=='success':
        reference_dispatch.dispatch(conn,REQUEST,env={'USDA_FDC_API_KEY':'fixture'},
            _transport=send,_on_reserved=ack,_monotonic=lambda:0)
        assert events==['ack','send']
    else:
        from lib import egress
        with pytest.raises(egress.DispatchRefused):
            reference_dispatch.dispatch(conn,REQUEST,env={'USDA_FDC_API_KEY':'fixture'},
                _transport=send,_on_reserved=ack,_monotonic=lambda:0)
        assert events==[]
