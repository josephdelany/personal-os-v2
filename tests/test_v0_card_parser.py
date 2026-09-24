"""Pure source-preservation contracts; no personal export fixtures."""
import base64
import csv
import hashlib
import io
import pytest
from tools.importers.v0_card import prepare, CardFileError

ACCOUNT = '00000000-0000-4000-8000-000000000001'
HEADER = ['Transaction Date','Post Date','Description','Category','Type','Amount','Memo']


def csv_bytes(rows):
    out=io.StringIO(newline='')
    writer=csv.writer(out)
    writer.writerow(HEADER)
    writer.writerows(rows)
    return out.getvalue().encode()


def row(**changes):
    record=dict(zip(HEADER,['03/07/2026','03/08/2026','fixture store','fixture category','Sale','-12.50','']))
    record.update(changes)
    return [record[k] for k in HEADER]


def test_REQ_FIN_014_040_preserves_bytes_fields_and_duplicate_multiplicity():
    data=csv_bytes([row(),row()])
    result=prepare(data,ACCOUNT)
    assert base64.b64decode(result['source_base64'])==data
    assert result['source_sha256']==hashlib.sha256(data).hexdigest()
    assert len(result['rows'])==2
    a,b=result['rows']
    assert [a['source_row'],b['source_row']]==[1,2]
    assert a['row_digest']==b['row_digest']
    assert a['amount']=='-12.50' and a['currency']=='USD'
    assert a['occurred_on']=='2026-03-07' and a['posted_on']=='2026-03-08'
    assert a['source_type']=='Sale' and a['source_category']=='fixture category'
    assert a['source_record']==dict(zip(HEADER,row()))


def test_REQ_FIN_040_042_equal_supplied_dates_remain_distinct_fields():
    result=prepare(csv_bytes([row(**{'Post Date':'03/07/2026'})]),ACCOUNT)
    r=result['rows'][0]
    assert r['occurred_on']==r['posted_on']=='2026-03-07'
    assert prepare(csv_bytes([row(**{'Post Date':''})]),ACCOUNT)['rows'][0]['posted_on'] is None


def test_REQ_FIN_010_equivalent_file_digest_ignores_order_not_multiplicity():
    a=row();b=row(**{'Description':'second fixture'})
    first=prepare(csv_bytes([a,a,b]),ACCOUNT)
    reordered=prepare(csv_bytes([b,a,a]),ACCOUNT)
    less=prepare(csv_bytes([a,b]),ACCOUNT)
    assert first['source_sha256']!=reordered['source_sha256']
    assert first['content_digest']==reordered['content_digest']
    assert first['content_digest']!=less['content_digest']


@pytest.mark.parametrize('amount',['NaN','1e2','12.345','--3','USD12'])
def test_REQ_FIN_015_invalid_amount_refuses_without_contents(amount):
    with pytest.raises(CardFileError,match='invalid USD amount'):
        prepare(csv_bytes([row(**{'Amount':amount})]),ACCOUNT)


def test_REQ_FIN_014_unknown_header_and_invalid_dates_refuse():
    with pytest.raises(CardFileError,match='unsupported header'):
        prepare(b'Date,Amount\n2026-03-07,-1\n',ACCOUNT)
    with pytest.raises(CardFileError,match='invalid occurred_on'):
        prepare(csv_bytes([row(**{'Transaction Date':'02/30/2026'})]),ACCOUNT)


def test_REQ_FIN_010_positive_payment_and_unknown_type_are_preserved():
    rows=prepare(csv_bytes([row(**{'Amount':'12.50','Type':'Payment'}),
                           row(**{'Type':'Unrecognized'})]),ACCOUNT)['rows']
    assert rows[0]['amount']=='12.50' and rows[0]['source_type']=='Payment'
    assert rows[1]['source_type']=='Unrecognized'


@pytest.mark.parametrize('data', [b'"unclosed header', b'\xff', b'',
    csv_bytes([row(**{'Memo':'bad\x00cell'})]), csv_bytes([])])
def test_REQ_FIN_015_unusable_file_is_recoverable(data):
    with pytest.raises(CardFileError):
        prepare(data,ACCOUNT)


def test_REQ_FIN_014_account_is_explicit_and_generic_mappings_stay_separate():
    from tools.importers.bank import load_mappings
    assert not any(m.get('institution')=='chase_credit_us' for m in load_mappings())
    with pytest.raises(CardFileError,match='account UUID'):
        prepare(csv_bytes([row()]),'inferred-from-filename')


def test_REQ_FIN_014_040_quoted_fields_bom_and_reordered_columns_preserve_source():
    original=row(**{'Description':'fixture, "quoted" store','Memo':'line one\nline two'})
    data=csv_bytes([original])
    result=prepare(b'\xef\xbb\xbf'+data,ACCOUNT)
    assert result['rows'][0]['description']=='fixture, "quoted" store'
    assert result['rows'][0]['memo']=='line one\nline two'
    out=io.StringIO(newline='')
    writer=csv.writer(out)
    writer.writerow(list(reversed(HEADER)))
    writer.writerow(list(reversed(original)))
    reordered=prepare(out.getvalue().encode(),ACCOUNT)
    assert reordered['content_digest']==result['content_digest']
    assert reordered['rows']==result['rows']


@pytest.mark.parametrize('data,reason', [
    (b'x'*1_048_577,'1 MiB'),
    (csv_bytes([row(**{'Memo':'x'*4001})]),'4000 characters'),
    (csv_bytes([row()]*10001),'10000 rows')])
def test_REQ_FIN_015_bounded_file_input_refuses_cleanly(data,reason):
    with pytest.raises(CardFileError,match=reason):
        prepare(data,ACCOUNT)
