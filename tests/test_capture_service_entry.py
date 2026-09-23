"""REQ-CAP-026 / RULE-29 service configuration isolation without real secrets."""
import json
import os
import sys
import pytest
from tools import capture_service_entry as entry


@pytest.fixture
def secret(tmp_path):
    path=tmp_path/'role.json'
    path.write_text(json.dumps({'MODEL_EGRESS_DB_URL':'fixture','CF_API_TOKEN':'fixture','CF_ACCOUNT_ID':'fixture'}))
    path.chmod(0o600)
    return path


@pytest.mark.parametrize('mode',[0o640,0o644,0o666])
def test_RULE_29_shared_secret_file_refuses(secret,mode):
    secret.chmod(mode)
    with pytest.raises(ValueError):entry.credentials(secret,'model')


def test_RULE_29_secret_symlink_and_cross_role_configuration_refuse(secret,tmp_path):
    link=tmp_path/'link';link.symlink_to(secret)
    with pytest.raises(OSError):entry.credentials(link,'model')
    with pytest.raises(ValueError):entry.credentials(secret,'private')
    assert set(entry.credentials(secret,'model'))==set(entry.MODEL_ENV)


def test_RULE_29_service_exec_receives_only_selected_role_configuration(secret,tmp_path,monkeypatch):
    for key in entry.ALL_CREDENTIALS|{'PERSONAL_OS_TEST_SOCKET'}:monkeypatch.delenv(key,raising=False)
    monkeypatch.setenv('UNRELATED_SECRET','fixture')
    monkeypatch.setattr(sys,'argv',['service','model','--secrets',str(secret),'--runtime-root',str(tmp_path)])
    monkeypatch.setattr(entry.os,'chdir',lambda path:None)
    observed=[]
    def execute(binary,args,env):
        observed.append((binary,args,env));raise SystemExit(0)
    monkeypatch.setattr(entry.os,'execve',execute)
    with pytest.raises(SystemExit):entry.main()
    binary,args,env=observed[0]
    assert binary==sys.executable and args==entry.command('model',tmp_path)
    assert set(env)==set(entry.MODEL_ENV)|{'PYTHONPATH'}
    assert 'fixture' not in ' '.join(args)


def test_RULE_29_preloaded_credentials_fail_before_secret_read(secret,tmp_path,monkeypatch,capsys):
    monkeypatch.setenv('SUPABASE_DB_URL','fixture')
    monkeypatch.setattr(sys,'argv',['service','model','--secrets',str(secret),'--runtime-root',str(tmp_path)])
    monkeypatch.setattr(entry,'credentials',lambda *a:pytest.fail('combined credential parent'))
    assert entry.main()==1
    assert 'fixture' not in capsys.readouterr().err


def test_REQ_CAP_026_fixed_private_nightly_and_outbound_commands(tmp_path):
    private=entry.command('private',tmp_path)
    nightly=entry.command('nightly',tmp_path)
    assert private[2]=='tools.capture_private_service' and nightly==private+['--retry']
    assert entry.command('reference',tmp_path)[2:4]==['tools.capture_dispatch_mailbox','reference']


@pytest.mark.parametrize('hour',[5,6])
def test_REQ_CAP_026_nightly_entry_waits_for_utc_window(secret,tmp_path,monkeypatch,capsys,hour):
    for key in entry.ALL_CREDENTIALS|{'PERSONAL_OS_TEST_SOCKET'}:monkeypatch.delenv(key,raising=False)
    real=entry.dt.datetime
    class Clock(real):
        @classmethod
        def now(cls,tz=None):return real(2026,9,23,hour,tzinfo=entry.dt.timezone.utc)
    monkeypatch.setattr(entry.dt,'datetime',Clock)
    monkeypatch.setattr(sys,'argv',['service','nightly','--secrets',str(secret),'--runtime-root',str(tmp_path)])
    loaded=[]
    def load(*args):loaded.append(args);return {'SUPABASE_DB_URL':'fixture'}
    monkeypatch.setattr(entry,'credentials',load)
    monkeypatch.setattr(entry.os,'chdir',lambda path:None)
    def execute(binary,args,env):
        assert args[-1]=='--retry';raise SystemExit(0)
    monkeypatch.setattr(entry.os,'execve',execute)
    if hour==5:
        assert entry.main()==0 and loaded==[]
        assert json.loads(capsys.readouterr().out)['status']=='not_due'
    else:
        with pytest.raises(SystemExit):entry.main()
        assert len(loaded)==1
