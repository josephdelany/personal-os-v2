"""Owner correction request boundary; persistence acceptance remains separate."""
import uuid
import io
import json

import pytest

from tools.engines.capture_corrections import validate_request


def request(**changes):
    payload = dict(request_id=str(uuid.uuid4()), capture_id=str(uuid.uuid4()),
                   expected_item_id=str(uuid.uuid4()), actor='joe', operation='replace',
                   food_id=str(uuid.uuid4()), quantity={'grams': 150})
    return {**payload, **changes}


@pytest.mark.parametrize('quantity', [{'grams': 150}, {'servings': 2.5}, {'item_count': 2.5}])
def test_REQ_CAP_014_REQ_NUT_050_correction_preserves_explicit_dimension_and_source(quantity):
    payload = request(quantity=quantity)
    saved = validate_request(payload)
    assert saved == payload
    payload['quantity'].clear()
    assert saved['quantity']
    assert saved['food_id'] == payload['food_id']


@pytest.mark.parametrize('quantity', [None, {}, {'grams': 0}, {'grams': -1},
    {'grams': True}, {'grams': '150'}, {'grams': float('nan')}, {'grams': float('inf')},
    {'grams': 10**1000}, {'grams': 150, 'servings': 1}, {'ml': 150}, {'calories': 150}])
def test_REQ_CAP_014_RULE_06_RULE_09_correction_refuses_ambiguous_or_invalid_quantity(quantity):
    with pytest.raises(ValueError):
        validate_request(request(quantity=quantity))


def test_REQ_CAP_014_RULE_06_removal_is_explicit_without_fabricated_quantity():
    payload = request(operation='remove')
    del payload['quantity'], payload['food_id']
    assert validate_request(payload) == payload
    with pytest.raises(ValueError):
        validate_request({**payload, 'quantity': {'grams': 0}})


def retime_request(**changes):
    payload=request(operation='retime',occurred_at='2026-09-22T02:00:00-04:00',time_precision='minute')
    del payload['food_id'],payload['quantity']
    return {**payload,**changes}


def test_REQ_CAP_014_RULE_03_time_correction_canonicalizes_instant_not_precision():
    payload=retime_request()
    saved=validate_request(payload)
    assert saved['occurred_at']=='2026-09-22T06:00:00+00:00'
    assert saved['time_precision']=='minute'
    assert validate_request({**payload,'occurred_at':'2026-09-22T06:00:00Z'})==saved


@pytest.mark.parametrize('changes',[
    {'occurred_at':'yesterday'}, {'occurred_at':'2026-09-22'},
    {'occurred_at':'2026-09-22T02:00:00'}, {'occurred_at':'2026-02-30T02:00:00Z'},
    {'occurred_at':'2026-09-22T02:00:00+24:00'},
    {'occurred_at':'2026-01-01T12:00:00+01:99'},
    {'occurred_at':'2026-01-01T12:00:00-00:60'}, {'occurred_at':None},
    {'time_precision':None}, {'time_precision':'guessed'}, {'subject_day':'2026-09-21'},
    {'quantity':{'grams':150}}, {'food_id':str(uuid.uuid4())},
])
def test_REQ_CAP_014_RULE_06_time_correction_requires_explicit_time_without_other_edits(changes):
    with pytest.raises(ValueError):
        validate_request(retime_request(**changes))


@pytest.mark.parametrize('changes', [{'actor': 'model'}, {'food_id': None},
    {'expected_item_id': 'latest'}, {'request_id': 'retry'}, {'capture_id': ''},
    {'operation': 'update'}, {'nutrients': {'energy_kcal': 10}}, {'approved': True}])
def test_REQ_CAP_014_RULE_10_request_requires_exact_identity_and_no_extra_claims(changes):
    with pytest.raises(ValueError):
        validate_request(request(**changes))


@pytest.mark.parametrize('fail_at',[None,'apply','commit'])
def test_REQ_CAP_014_RULE_02_correction_command_prints_success_only_after_commit(monkeypatch,capsys,fail_at):
    from tools import capture_correct
    events=[]
    class Connection:
        def cursor(self):
            return self
        def commit(self):
            events.append('commit')
            assert capsys.readouterr().out==''
            if fail_at=='commit':
                raise RuntimeError('private credential in driver message')
        def rollback(self):
            events.append('rollback')
        def close(self):
            events.append('close')
    def apply(cur,payload):
        events.append('apply')
        if fail_at=='apply':
            raise PermissionError('private credential in driver message')
        return {'status':'resolved','request_id':payload['request_id']}
    monkeypatch.setattr(capture_correct.db,'connect',Connection)
    monkeypatch.setattr(capture_correct.capture_corrections,'apply',apply)
    monkeypatch.setattr('sys.stdin',io.StringIO(json.dumps(request())))
    for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL','REFERENCE_EGRESS_DB_URL',
                'USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY'):
        monkeypatch.delenv(key,raising=False)
    status=capture_correct.main([])
    output=capsys.readouterr()
    if fail_at:
        assert status==1 and not output.out
        assert json.loads(output.err)['status']=='error'
        assert 'private credential' not in output.err
        assert events[-2:]==['rollback','close']
    else:
        assert status==0 and not output.err
        assert json.loads(output.out)['status']=='resolved'
        assert events==['apply','commit','close']
