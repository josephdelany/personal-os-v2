"""Reference runtime prerequisites: exercise the real GET boundary without sockets."""
import io
import json
from email.message import Message
import urllib.request

import pytest

from lib import egress


class Cursor:
    def __init__(self):
        self.calls = []

    def execute(self, sql, args):
        self.calls.append((sql, args))

    def fetchone(self):
        return (1,)


@pytest.mark.parametrize('url', [
    'http://api.nal.usda.gov/fdc/v1/foods/search',
    'https://secret@api.nal.usda.gov/fdc/v1/foods/search',
    'https://api.nal.usda.gov:444/fdc/v1/foods/search',
    'https://api.nal.usda.gov/fdc/v1/foods/search?api_key=secret',
    'https://api.nal.usda.gov/fdc/v1/foods/search#fragment',
])
def test_RULE_29_REQ_NUT_005_destination_refused_before_log_or_transport(url):
    cur = Cursor()
    sent = []
    with pytest.raises(egress.PayloadRefused):
        egress.get_json(cur, url, 'nutrition:usda_foundation_search',
                        _transport=lambda *args: sent.append(args))
    assert cur.calls == sent == []


def test_RULE_29_REQ_NUT_005_real_opener_refuses_redirect_before_second_destination(monkeypatch):
    destinations = []

    class RedirectingSource(urllib.request.BaseHandler):
        handler_order = 100

        def https_open(self, request):
            destinations.append(request.full_url)
            headers = Message()
            headers['Location'] = 'https://unapproved.example/collect'
            return self.parent.error('http', request, io.BytesIO(b''), 302,
                                     'Found', headers)

    original = urllib.request.build_opener
    monkeypatch.setattr(urllib.request, 'build_opener',
                        lambda *handlers: original(RedirectingSource(), *handlers))
    cur = Cursor()
    with pytest.raises(egress.PayloadRefused, match='redirect refused'):
        egress.get_json(cur, 'https://api.nal.usda.gov/fdc/v1/foods/search',
                        'nutrition:usda_foundation_search', params={'api_key': 'secret', 'query': 'food'})
    assert destinations == ['https://api.nal.usda.gov/fdc/v1/foods/search?api_key=secret&query=food']
    assert 'secret' not in repr(cur.calls)
    assert json.loads(cur.calls[-1][1][0]) == {'error': 'PayloadRefused'}


@pytest.mark.parametrize('declared,body,refused', [
    ('999999999', b'{}', True),
    ('-1', b'{}', True),
    (None, b'{}', False),
    ('2', b'{}', False),
    (None, b'x' * (egress.SOURCE_RESPONSE_MAX_BYTES + 1), True),
    ('2', b'x' * (egress.SOURCE_RESPONSE_MAX_BYTES + 1), True),
])
def test_RULE_29_REQ_NUT_006_real_transport_bounds_declared_and_actual_body(monkeypatch, declared, body, refused):
    reads = []

    class Response:
        headers = {} if declared is None else {'Content-Length': declared}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, maximum):
            reads.append(maximum)
            return body[:maximum]

    class Opener:
        def open(self, request, timeout):
            return Response()

    monkeypatch.setattr(urllib.request, 'build_opener', lambda *handlers: Opener())
    if refused:
        with pytest.raises(egress.PayloadRefused, match='size refused'):
            egress._get('https://api.nal.usda.gov/', {}, 20)
    else:
        assert egress._get('https://api.nal.usda.gov/', {}, 20) == body
    assert reads in ([], [egress.SOURCE_RESPONSE_MAX_BYTES + 1])


def test_RULE_29_REQ_NUT_006_injected_oversize_response_is_logged_and_refused():
    cur = Cursor()
    with pytest.raises(egress.PayloadRefused, match='size refused'):
        egress.get_json(cur, 'https://api.nal.usda.gov/', 'nutrition:source',
                        _transport=lambda *args: b'x' * (egress.SOURCE_RESPONSE_MAX_BYTES + 1))
    assert json.loads(cur.calls[-1][1][0]) == {'error': 'PayloadRefused'}
