"""One isolated source lookup; never reads private captures, aliases or foods_cache.

Reservation commits before source egress. A returned result has a separately
committed digest receipt. Private preparation/cache consumption own the other side.
"""
import datetime as dt
import hashlib
import os
import time
import uuid
from contextlib import contextmanager

from lib import egress
from lib.model_contract import request_bytes
from tools.engines import nutrition_off as off, nutrition_usda as usda

PRIVATE_CREDENTIALS = ('SUPABASE_DB_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'SUPABASE_STORAGE_READ_JWT',
                       'MODEL_EGRESS_DB_URL', 'CF_API_TOKEN')
SOURCES = {'usda_foundation', 'usda_branded', 'off_search', 'off_product'}


def validate(request):
    if not isinstance(request, dict) or set(request) != {'request_id','source','query','brand','barcode'}:
        raise ValueError('invalid reference request')
    if str(uuid.UUID(str(request['request_id']))) != request['request_id'] or request['source'] not in SOURCES:
        raise ValueError('invalid reference identity')
    for key in ('query','brand'):
        value = request[key]
        if value is not None and (not isinstance(value,str) or not value.strip() or len(value)>512):
            raise ValueError('invalid reference text')
    if request['source']=='off_product':
        if request['query'] is not None or request['brand'] is not None:
            raise ValueError('barcode request cannot carry text')
        if off.normalise_barcode(request['barcode']) != request['barcode']:
            raise ValueError('invalid barcode')
    elif request['query'] is None or request['barcode'] is not None:
        raise ValueError('name request required')
    if request['source']=='usda_foundation' and request['brand'] is not None:
        raise ValueError('generic source cannot answer a branded query')
    body = request_bytes(request)
    if len(body)>4096:
        raise ValueError('reference request too large')
    egress.screen_payload({key:request[key] for key in ('query','brand','barcode')})
    return body


def dispatch(conn, request, *, _transport=None, _monotonic=time.monotonic, env=None,
             ops='ops', config='config', _on_reserved=None):
    body = validate(request)
    if any(os.environ.get(key) for key in PRIVATE_CREDENTIALS):
        raise egress.DispatchRefused('private or model capability present')
    if os.environ.get('PERSONAL_OS_TEST_SOCKET') and _transport is None:
        raise egress.DispatchRefused('disposable run requires an injected source transport')
    # Configuration is checked before reserving a quota slot; no key is exported.
    env = os.environ if env is None else env
    source = request['source']
    if source.startswith('usda_'):
        usda.api_key(env)
    else:
        off.user_agent(env)
    cur = conn.cursor()
    cur.execute('SELECT session_user,current_user')
    if tuple(cur.fetchone()) != ('reference_egress','reference_egress'):
        raise egress.DispatchRefused('dedicated reference identity required')
    with _serialized(cur):
        return _dispatch_reserved(conn,cur,request,source,body,env,ops,config,_transport,_monotonic,_on_reserved)


@contextmanager
def _serialized(cur):
    # Hold across reservation commit, HTTP and settlement. A429 is persisted
    # before the next dispatcher can reserve; queued permits cannot race it.
    # Connection closure also releases this lock if the supervisor kills us.
    cur.execute('SELECT pg_advisory_lock(791554)')
    try:
        yield
    finally:
        cur.execute('SELECT pg_advisory_unlock(791554)')


def _dispatch_reserved(conn,cur,request,source,body,env,ops,config,_transport,_monotonic,_on_reserved):
    try:
        started = _monotonic()
        cur.execute('SELECT public.reserve_reference_call(%s,%s,%s,%s)',
                    (request['request_id'],source,hashlib.sha256(body).hexdigest(),len(body)))
        permit = cur.fetchone()[0]
        if not permit.get('allowed'):
            # Refusal may also persist discovery of an interrupted predecessor
            # and its conservative cooldown. Do not roll that maintenance back.
            conn.commit()
            raise egress.DispatchRefused(permit.get('reason','reference reservation refused'))
        if permit.get('request_id') != request['request_id']:
            raise egress.DispatchRefused('reference reservation mismatch')
        reserved = dt.datetime.fromisoformat(permit['reserved_at'])
        expires = dt.datetime.fromisoformat(permit['valid_before'])
        lifetime = (expires-reserved).total_seconds()
        if reserved.utcoffset() is None or expires.utcoffset() is None or not 0<lifetime<=60:
            raise egress.DispatchRefused('reference reservation lifetime refused')
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise egress.DispatchRefused('reference reservation not confirmed') from None
    if _on_reserved is not None:
        _on_reserved(request['request_id'])
    if _monotonic()-started >= lifetime:
        raise egress.DispatchRefused('reference reservation expired')

    provider_status = None
    def transport(url, headers, timeout):
        nonlocal provider_status
        # The persisted permit precedes any source request; get_json adds its
        # detailed per-HTTP audit in this settlement transaction, never private data.
        if _monotonic()-started >= lifetime:
            raise egress.DispatchRefused('reference reservation expired')
        try:
            return (_transport or egress._get)(url,headers,timeout)
        except Exception as exc:
            code = getattr(exc,'code',None)
            if type(code) is int and 300<=code<=599:
                provider_status = code
            raise
    try:
        kw = {'env':env,'ops':ops,'config':config,'_transport':transport}
        if source.startswith('usda_'):
            row = usda.lookup_by_name(cur,request['query'],source,brand=request['brand'],
                                      quota=usda.Quota(),**kw)
        elif source=='off_product':
            row = off.lookup_by_barcode(cur,request['barcode'],limits=off.Limits(),**kw)
        else:
            row = off.lookup_by_name(cur,request['query'],brand=request['brand'],limits=off.Limits(),**kw)
        row['fetched_at'] = row['fetched_at'].isoformat()
        result = {'status':'resolved','row':row}
    except (usda.UsdaUnusable,off.OffUnusable) as exc:
        transient = isinstance(exc,(usda.UsdaTransient,off.OffTransient))
        result = {'status':'deferred' if transient else 'unresolved', 'reason':exc.reason}
    except Exception:
        result = {'status':'deferred','reason':'reference_dispatch_failed'}
    response = request_bytes(result)
    try:
        cur.execute('SELECT public.settle_reference_response(%s,%s,%s)',
                    (request['request_id'],response.decode('utf-8'),provider_status))
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise egress.DispatchUncertain('reference settlement not confirmed') from None
    return result
