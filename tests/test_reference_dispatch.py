"""Source dispatch ordering; rollback SQL tests separately exercise database meters."""
import datetime as dt
import io
import json
import uuid

import pytest
from lib import db, egress
from lib.model_contract import request_bytes
from tools.engines import reference_dispatch as engine
from tests.test_nutrition_usda import branded_food, Http429

RID = str(uuid.UUID(int=42))
REQUEST = {'request_id':RID,'source':'usda_branded','query':'Synthetic Crunch Bar',
           'brand':None,'barcode':None}


class Connection:
    def __init__(self, fail_commit=None, identity=('reference_egress','reference_egress'), allowed=True):
        self.commits = 0
        self.events = []
        self.identity = identity
        self.fail_commit = fail_commit
        self.allowed = allowed

    def cursor(self): return self
    def execute(self, sql, params=()):
        self.sql = sql
        self.events.append(('sql',sql,params))
    def fetchone(self):
        if 'session_user' in self.sql: return self.identity
        if 'reserve_reference' in self.sql:
            return ({'allowed':self.allowed,'request_id':RID,'reserved_at':'2026-09-23T00:00:00+00:00',
                     'valid_before':'2026-09-23T00:01:00+00:00','reason':'source_quota'},)
        return (RID,)
    def commit(self):
        self.commits += 1
        self.events.append(('commit',self.commits))
        if self.fail_commit==self.commits: raise RuntimeError('fixture secret')
    def rollback(self): self.events.append(('rollback',))
    def close(self): self.events.append(('close',))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    for key in engine.PRIVATE_CREDENTIALS:
        monkeypatch.delenv(key,raising=False)


def invoke(conn, transport=None, clock=lambda:0):
    def send(*args):
        assert conn.commits == 1
        conn.events.append(('send',))
        return json.dumps({'foods':[branded_food()]}).encode()
    return engine.dispatch(conn,REQUEST,env={'USDA_FDC_API_KEY':'fixture'},
                           _transport=transport or send,_monotonic=clock)


def test_RULE_29_REQ_NUT_003_005_commit_before_send_and_receipt_before_result():
    conn=Connection()
    result=invoke(conn)
    assert result['status']=='resolved'
    assert result['row']['source_id']=='999001'
    assert conn.commits==2
    settlement=next(e for e in conn.events if e[0]=='sql' and 'settle_reference_response' in e[1])
    assert settlement[2][1].encode('utf-8')==request_bytes(result)
    assert settlement[2][-1] is None
    assert conn.events[-2]==('commit',2)
    assert 'pg_advisory_unlock' in conn.events[-1][1]


@pytest.mark.parametrize('number,error',[(1,egress.DispatchRefused),(2,egress.DispatchUncertain)])
def test_RULE_29_REQ_NUT_003_uncertain_commits_do_not_export_a_result(number,error):
    conn=Connection(fail_commit=number)
    with pytest.raises(error): invoke(conn)
    assert any(e[0]=='send' for e in conn.events)==(number==2)


@pytest.mark.parametrize('identity',[('postgres','reference_egress'),('service_role','service_role')])
def test_RULE_29_direct_login_required_not_set_role(identity):
    conn=Connection(identity=identity)
    with pytest.raises(egress.DispatchRefused): invoke(conn)
    assert conn.commits==0 and not any(e[0]=='send' for e in conn.events)


@pytest.mark.parametrize('key',engine.PRIVATE_CREDENTIALS)
def test_RULE_29_private_or_model_credentials_refuse_before_reservation(monkeypatch,key):
    monkeypatch.setenv(key,'fixture secret')
    conn=Connection()
    with pytest.raises(egress.DispatchRefused): invoke(conn)
    assert conn.events==[]
    with pytest.raises(RuntimeError): db.connect_reference_egress()


def test_REQ_NUT_009_011_quota_refusal_does_not_dispatch():
    conn=Connection(allowed=False)
    with pytest.raises(egress.DispatchRefused): invoke(conn)
    assert conn.commits==1 and not any(e[0]=='send' for e in conn.events)


def test_RULE_29_expired_reference_permit_does_not_send():
    conn=Connection()
    clock=iter([0,60])
    with pytest.raises(egress.DispatchRefused): invoke(conn,clock=lambda:next(clock))
    assert conn.commits==1 and not any(e[0]=='send' for e in conn.events)


def test_REQ_NUT_012_provider_429_is_settled_with_cooldown_signal():
    def send(*args): raise Http429()
    conn=Connection()
    result=invoke(conn,send)
    assert result=={'status':'deferred','reason':'rate_limited_provider'}
    settlement=next(e for e in conn.events if e[0]=='sql' and 'settle_reference_response' in e[1])
    assert settlement[2][-1]==429
    assert conn.commits==2


def test_REQ_NUT_024_exact_no_match_is_not_transport_failure():
    assert invoke(Connection(),lambda *args:b'{"foods":[]}')['status']=='unresolved'


def test_RULE_29_REQ_NUT_003_actual_dispatch_cli_exports_after_settlement(monkeypatch,capsys):
    from tools import reference_egress
    conn=Connection()
    monkeypatch.setattr(db,'connect_reference_egress',lambda:conn)
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(REQUEST)))
    monkeypatch.setenv('USDA_FDC_API_KEY','fixture')
    monkeypatch.setattr(egress,'_get',lambda *args:json.dumps({'foods':[branded_food()]}).encode())
    assert reference_egress.main()==0
    result=json.loads(capsys.readouterr().out)
    assert result['request_id']==RID and result['result']['row']['source_id']=='999001'
    assert conn.events[-3]==('commit',2)
    assert 'pg_advisory_unlock' in conn.events[-2][1]
    assert conn.events[-1]==('close',)


def test_REQ_NUT_012_dispatch_lock_spans_reservation_send_and_settlement():
    conn=Connection()
    invoke(conn)
    labels=[('lock' if 'pg_advisory_lock(' in e[1] else
             'unlock' if 'pg_advisory_unlock(' in e[1] else 'sql') if e[0]=='sql' else e[0]
            for e in conn.events]
    assert labels.index('lock') < labels.index('commit') < labels.index('send') < labels.index('unlock')
    assert labels[-2:]==['commit','unlock']


@pytest.mark.parametrize('key',['REFERENCE_EGRESS_DB_URL','USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY'])
def test_RULE_29_private_capture_stage_rejects_source_capabilities(monkeypatch,key):
    from tools.engines.capture_transcription import _private
    monkeypatch.setenv(key,'fixture')
    with pytest.raises(RuntimeError,match='provider capability'):
        _private('core')


def test_RULE_01_disposable_reference_dispatch_requires_explicit_injected_transport(monkeypatch):
    monkeypatch.setenv('PERSONAL_OS_TEST_SOCKET','/tmp/fixture-only')
    conn=Connection()
    with pytest.raises(egress.DispatchRefused,match='injected source transport'):
        engine.dispatch(conn,REQUEST,env={'USDA_FDC_API_KEY':'fixture'})
    assert conn.events==[]
