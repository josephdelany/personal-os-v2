"""Private CLI acknowledgement, transaction and validation boundaries."""
import json
from tools import import_v0_card as cli

ACCOUNT='0195dc0b-3470-7000-8000-000000000401'
DATA=b'Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n09/20/2026,,fixture,,Sale,-1.00,\n'


def test_REQ_FIN_010_validation_default_never_connects(tmp_path,monkeypatch,capsys):
    import lib.db
    monkeypatch.setattr(lib.db,'connect',lambda: (_ for _ in ()).throw(AssertionError('unexpected connection')))
    source=tmp_path/'card.csv'
    source.write_bytes(DATA)
    assert cli.main(['--file',str(source),'--account',ACCOUNT])==0
    assert json.loads(capsys.readouterr().out)==dict(status='validated_not_saved',mapping_version='chase-credit-v0-1',source_rows=1)


def test_REQ_FIN_010_lost_commit_ack_is_unconfirmed_and_sanitized(tmp_path,monkeypatch,capsys):
    import lib.db
    calls=[]
    class Connection:
        def cursor(self):
            return object()
        def commit(self):
            calls.append('commit')
            raise RuntimeError('sensitive database detail')
        def rollback(self):
            calls.append('rollback')
        def close(self):
            calls.append('close')
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL','REFERENCE_EGRESS_DB_URL'):
        monkeypatch.delenv(key,raising=False)
    monkeypatch.setattr(lib.db,'connect',Connection)
    monkeypatch.setattr(cli,'import_bytes',lambda *args: dict(status='saved'))
    source=tmp_path/'card.csv'
    source.write_bytes(DATA)
    assert cli.main(['--file',str(source),'--account',ACCOUNT,'--apply'])==1
    output=capsys.readouterr().out
    assert json.loads(output)['status']=='unconfirmed'
    assert 'sensitive' not in output and 'saved' not in output
    assert calls==['commit','rollback','close']
