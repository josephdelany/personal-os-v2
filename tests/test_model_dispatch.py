"""Transaction ordering/failure proofs; SQL constraints have separate rollback tests."""
import datetime as dt
import json
import uuid
import pytest
from lib import egress

RID = str(uuid.UUID(int=1))
MODEL = '@cf/meta/llama-3.1-8b-instruct'

class Connection:
    def __init__(self, *, fail_commit=None, identity=('model_egress','model_egress'), permit=None):
        self.events = []
        self.commits = 0
        self.fail_commit = fail_commit
        self.identity = identity
        self.permit = permit or {'allowed': True, 'duplicate': False, 'request_id': RID,
            'reserved_at': '2026-09-22T23:59:00+00:00', 'valid_before': '2026-09-23T00:00:00+00:00'}
    def cursor(self): return self
    def execute(self, query, params=()):
        self.query = query
        self.events.append(('sql', query, params))
    def fetchone(self):
        return self.identity if 'session_user' in self.query else (self.permit,)
    def commit(self):
        self.commits += 1
        self.events.append(('commit', self.commits))
        if self.fail_commit == self.commits:
            raise RuntimeError('fixture secret error')
    def rollback(self): self.events.append(('rollback',))

@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    for name in ('SUPABASE_DB_URL','SUPABASE_SERVICE_ROLE_KEY'):
        monkeypatch.delenv(name, raising=False)

def invoke(conn, transport=None, clock=lambda: 0):
    def send(model, body):
        assert conn.commits == 1
        conn.events.append(('send', model))
        return json.dumps({'result': {'response': 'fixture'}}).encode()
    return egress.dispatch(conn, request_id=RID, model_id=MODEL, call_kind='plan',
        payload={'prompt': 'fixture only'}, estimated_neurons=5,
        _transport=transport or send, _monotonic=clock)

def test_RULE_29_reservation_commits_before_send_and_settlement_before_result():
    conn = Connection()
    assert invoke(conn) == {'result': {'response': 'fixture'}}
    assert [event[0] for event in conn.events] == ['sql','sql','commit','send','sql','commit']
    assert conn.events[1][2][0] == RID
    assert len(conn.events[1][2][-1]) == 64

def test_RULE_29_uncertain_reservation_commit_never_sends():
    conn = Connection(fail_commit=1)
    with pytest.raises(egress.DispatchRefused, match='not confirmed'):
        invoke(conn)
    assert not any(event[0] == 'send' for event in conn.events)

@pytest.mark.parametrize('identity', [('postgres','model_egress'), ('service_role','service_role')])
def test_RULE_29_set_role_does_not_hide_private_session_capability(identity):
    conn = Connection(identity=identity)
    with pytest.raises(egress.DispatchRefused, match='dedicated model identity'):
        invoke(conn)
    assert conn.commits == 0

def test_REQ_CAP_037_expired_committed_permit_never_sends():
    conn = Connection()
    clocks = iter([0, 60])
    with pytest.raises(egress.DispatchRefused, match='expired'):
        invoke(conn, clock=lambda: next(clocks))
    assert conn.commits == 1
    assert not any(event[0] == 'send' for event in conn.events)

def test_REQ_CAP_035_duplicate_reservation_never_sends():
    conn = Connection(permit={'allowed': False, 'duplicate': True, 'reason': 'already_reserved'})
    with pytest.raises(egress.DispatchRefused, match='already reserved'):
        invoke(conn)
    assert conn.commits == 0

def test_RULE_29_provider_failure_settles_once_without_retry_or_private_error():
    conn = Connection()
    def fail(model, body):
        conn.events.append(('send', model))
        raise TimeoutError('fixture private provider body')
    with pytest.raises(egress.DispatchUncertain, match='reservation retained'):
        invoke(conn, transport=fail)
    assert conn.commits == 2
    assert len([x for x in conn.events if x[0] == 'send']) == 1
    assert conn.events[-2][2] == (RID, 'error', None)

def test_RULE_29_uncertain_settlement_returns_no_provider_result():
    conn = Connection(fail_commit=2)
    with pytest.raises(egress.DispatchUncertain, match='could not be recorded'):
        invoke(conn)
    assert len([x for x in conn.events if x[0] == 'send']) == 1

def test_RULE_29_private_credentials_refuse_before_any_SQL(monkeypatch):
    monkeypatch.setenv('SUPABASE_DB_URL', 'fixture-private-credential')
    conn = Connection()
    with pytest.raises(egress.DispatchRefused, match='private credentials'):
        invoke(conn)
    assert conn.events == []


def test_RULE_29_legacy_cursor_path_cannot_issue_real_request():
    conn = Connection()
    with pytest.raises(egress.DispatchRefused, match='isolated committed dispatcher'):
        egress.call(conn, model_id=MODEL, call_kind='plan', payload={'prompt': 'fixture'},
                    estimated_neurons=5)
    assert conn.events == []


def test_RULE_29_model_redirect_refuses_before_following_destination():
    handler = egress._RefuseModelRedirect()
    class ForbiddenRedirect:
        def open(self, *args, **kwargs):
            pytest.fail('redirect attempted another request')
    handler.add_parent(ForbiddenRedirect())
    request = egress.urllib.request.Request('https://api.cloudflare.com/fixture',
        data=b'{}', headers={'Authorization': 'Bearer fixture-token'})
    with pytest.raises(egress.PayloadRefused, match='redirect refused'):
        handler.http_error_302(request, None, 302, 'Found',
                               {'location': 'https://example.invalid/'})


def test_RULE_29_model_transport_installs_redirect_refusal(monkeypatch):
    monkeypatch.setenv('CF_ACCOUNT_ID', 'fixture-account')
    monkeypatch.setenv('CF_API_TOKEN', 'fixture-token')
    calls = []
    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{}'
    class Opener:
        def open(self, req, timeout):
            calls.append((req.full_url, req.data, timeout))
            return Reply()
    def build(handler):
        assert isinstance(handler, egress._RefuseModelRedirect)
        return Opener()
    monkeypatch.setattr(egress.urllib.request, 'build_opener', build)
    assert egress._post(MODEL, b'{}') == b'{}'
    assert calls == [('https://api.cloudflare.com/client/v4/accounts/fixture-account/ai/run/'+MODEL,
                      b'{}', egress.TIMEOUT_SECONDS)]


def test_RULE_29_dispatcher_CLI_uses_prepared_request_and_returns_correlated_result(monkeypatch, capsys):
    import io
    from tools import model_egress as cli
    conn = Connection()
    closed = []
    conn.close = lambda: closed.append(True)
    request = {'request_id': RID, 'model_id': MODEL, 'call_kind': 'plan',
               'payload': {'prompt': 'fixture only'}, 'estimated_neurons': 5}
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps(request)))
    monkeypatch.setattr(cli.db, 'connect_model_egress', lambda: conn)
    monkeypatch.setattr(egress, '_post', lambda model, body: b'{"result":{"response":"fixture"}}')
    assert cli.main() == 0
    output = capsys.readouterr()
    assert output.err == ''
    assert json.loads(output.out) == {'request_id': RID, 'result': {'result': {'response': 'fixture'}}}
    assert conn.commits == 2 and closed == [True]


def test_RULE_29_dispatcher_CLI_failure_emits_only_error_class(monkeypatch, capsys):
    import io
    from tools import model_egress as cli
    request = {'request_id': RID, 'model_id': MODEL, 'call_kind': 'plan',
               'payload': {'prompt': 'fixture only'}, 'estimated_neurons': 5}
    monkeypatch.setattr(cli.sys, 'stdin', io.StringIO(json.dumps(request)))
    def fail(): raise RuntimeError('fixture secret connection string')
    monkeypatch.setattr(cli.db, 'connect_model_egress', fail)
    assert cli.main() == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert json.loads(output.err) == {'status': 'error', 'error_type': 'RuntimeError'}


def test_RULE_29_model_connection_rejects_private_credentials_before_connect(monkeypatch):
    from lib import db
    monkeypatch.setenv('SUPABASE_DB_URL', 'fixture-private-credential')
    monkeypatch.setattr(db, '_connect_url', lambda url: pytest.fail('must refuse before connection'))
    with pytest.raises(RuntimeError, match='private database credentials'):
        db.connect_model_egress()
