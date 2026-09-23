"""REQ-CAP-026 process deadline; no DB fixture, credentials or provider calls."""
import os
import sys
import time
import pytest
from tools import capture_private_service as service


@pytest.fixture
def options(monkeypatch,tmp_path):
    for key in service.PRIVATE_ENV+('CF_API_TOKEN','MODEL_EGRESS_DB_URL','REFERENCE_EGRESS_DB_URL',
                                   'USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY','PERSONAL_OS_TEST_SOCKET'):
        monkeypatch.delenv(key,raising=False)
    return {key:tmp_path/key for key in ('state_directory','model_outbox','model_results','reference_outbox')}


def test_REQ_CAP_026_private_service_kills_stall_and_keeps_uncertain_outcome(options,monkeypatch,tmp_path):
    pid=tmp_path/'pid'
    monkeypatch.setattr(service,'_command',lambda args:[sys.executable,'-c',
        f'import os,time,signal;open({str(pid)!r},"w").write(str(os.getpid()));'
        'signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(60)'])
    started=time.monotonic()
    assert service.run(**options,deadline=0.5)=={'status':'unconfirmed','timed_out':True}
    assert time.monotonic()-started<5
    with pytest.raises(ProcessLookupError):os.kill(int(pid.read_text()),0)


@pytest.mark.parametrize('code',[0,1])
def test_REQ_CAP_026_private_service_reports_invocation_not_capture_completion(options,monkeypatch,code):
    monkeypatch.setattr(service,'_command',lambda args:[sys.executable,'-c',
        f'import sys;print("private fixture output");sys.exit({code})'])
    assert service.run(**options)=={
        'status':'invocation_finished' if code==0 else 'unconfirmed','timed_out':False}


def test_REQ_CAP_026_private_service_drops_unrelated_environment(options,monkeypatch,tmp_path):
    output=tmp_path/'keys'
    monkeypatch.setenv('UNRELATED_SECRET','fixture')
    monkeypatch.setattr(service,'_command',lambda args:[sys.executable,'-c',
        f'import os,json;open({str(output)!r},"w").write(json.dumps(sorted(os.environ)))'])
    assert service.run(**options)['status']=='invocation_finished'
    assert 'UNRELATED_SECRET' not in output.read_text()


def test_REQ_CAP_026_actual_private_entrypoint_refuses_missing_credentials(options):
    assert service.run(**options)=={'status':'unconfirmed','timed_out':False}


@pytest.mark.parametrize('key',['PERSONAL_OS_TEST_SOCKET','CF_API_TOKEN','MODEL_EGRESS_DB_URL','REFERENCE_EGRESS_DB_URL'])
def test_REQ_CAP_026_private_service_refuses_foreign_or_disposable_context(options,monkeypatch,key):
    monkeypatch.setenv(key,'fixture')
    monkeypatch.setattr(service.subprocess,'Popen',lambda *a,**kw:pytest.fail('forbidden launch'))
    with pytest.raises((RuntimeError,ValueError)):service.run(**options)
