"""Private saved-food lookup preparation and receipt-bound source cache publication.

No source credentials or external requests. Caller commits before payload export.
Name-search ordering uses persisted outcomes; brand/barcode evidence remains open.
"""
import datetime as dt
import hashlib
import json
import re
import uuid

from lib.model_contract import request_bytes
from tools.engines import nutrition, nutrition_off as off, nutrition_usda as usda
from tools.engines.reference_dispatch import validate
from tools.engines.capture_transcription import _private, _lock

SOURCE_ORDER = ('usda_foundation','usda_branded','off_search')
SOURCES = set(SOURCE_ORDER)
ACTIVE = {'extracted','pending_enrichment','deferred_budget'}


def _digest(value):
    return hashlib.sha256(request_bytes(value)).hexdigest()


def _current(cur, capture_id, schema):
    cur.execute(f'''SELECT x.request_id,p.event_id,p.processing_status
        FROM {schema}.capture_extraction_current x
        JOIN {schema}.capture_processing_current p USING(capture_id)
        WHERE x.capture_id=%s''',(capture_id,))
    return cur.fetchone()


def source_outcomes(cur, *, capture_id, extraction_request_id, item_index, schema='core'):
    schema = _private(schema)
    cur.execute(f'''SELECT DISTINCT ON (a.source) a.source,a.request_id,o.status,o.reason
        FROM {schema}.capture_reference_attempts a
        LEFT JOIN {schema}.capture_reference_outcomes o USING(request_id)
        WHERE a.capture_id=%s AND a.extraction_request_id=%s AND a.item_index=%s
        ORDER BY a.source,a.attempt_no DESC''',(capture_id,extraction_request_id,item_index))
    return {source:{'request_id':str(rid),'status':status,'reason':reason}
            for source,rid,status,reason in cur.fetchall()}


def prepare(cur, *, request_id, capture_id, extraction_request_id, item_index, source='auto', schema='core', ops='ops'):
    schema,ops = _private(schema),_private(ops)
    request_id,capture_id,extraction_request_id = map(lambda v:str(uuid.UUID(str(v))),
                                                   (request_id,capture_id,extraction_request_id))
    if type(item_index) is not int or item_index<0 or source not in SOURCES|{'auto'}:
        raise ValueError('invalid reference item or source')
    _lock(cur,capture_id)
    current = _current(cur,capture_id,schema)
    if current is None or str(current[0])!=extraction_request_id or current[2] not in ACTIVE:
        raise ValueError('current unresolved extraction required')
    cur.execute(f'''SELECT capture_id,extraction_request_id,item_index,source,payload
        FROM {schema}.capture_reference_attempts WHERE request_id=%s''',(request_id,))
    old = cur.fetchone()
    if old is not None:
        if ((str(old[0]),str(old[1]),old[2]) != (capture_id,extraction_request_id,item_index)
            or (source!='auto' and old[3]!=source)):
            raise ValueError('reference request identity reused')
        result=_prepared_or_done(cur,request_id,old[4],schema)
        if source=='auto' and 'status' not in result:
            cur.execute(f'SELECT 1 FROM {ops}.reference_requests WHERE request_id=%s',(request_id,))
            if cur.fetchone() is not None:
                return {'status':'awaiting_result','request_id':request_id}
        return result
    cur.execute(f'''SELECT value,provenance FROM {schema}.capture_extraction_fields
        WHERE request_id=%s AND item_index=%s AND name='name' ''',(extraction_request_id,item_index))
    name = cur.fetchone()
    if name is None or name[1]!='extracted' or not isinstance(name[0],str) or not name[0].strip():
        raise ValueError('verified saved food name required')
    cached,_ = nutrition.lookup_cached(cur,name[0],schema)
    if cached is not None:
        return {'status':'cached','food_id':cached['food_id']}
    if source=='auto':
        outcomes=source_outcomes(cur,capture_id=capture_id,extraction_request_id=extraction_request_id,
                                 item_index=item_index,schema=schema)
        for candidate in SOURCE_ORDER:
            outcome=outcomes.get(candidate)
            if outcome is not None and outcome['status']=='unresolved':
                continue
            if outcome is not None and outcome['status'] is None:
                cur.execute(f'SELECT 1 FROM {ops}.reference_requests WHERE request_id=%s',
                            (outcome['request_id'],))
                if cur.fetchone() is not None:
                    return {'status':'awaiting_result','request_id':outcome['request_id']}
            source=candidate
            break
        else:
            return {'status':'unresolved','reason':'no_source_match',
                    'sources':[{'source':name,**outcomes[name]} for name in SOURCE_ORDER]}
    # Reuse a pending request even when another processing event advanced the
    # head; source polling must not create multiple billable requests per item.
    cur.execute(f'''SELECT a.request_id,a.payload FROM {schema}.capture_reference_attempts a
        LEFT JOIN {schema}.capture_reference_outcomes o USING(request_id)
        WHERE a.capture_id=%s AND a.extraction_request_id=%s AND a.item_index=%s AND a.source=%s
          AND (o.request_id IS NULL OR (a.expected_event_id=%s AND o.status='unresolved'))
        ORDER BY a.recorded_at DESC,a.request_id LIMIT 1''',
        (capture_id,extraction_request_id,item_index,source,current[1]))
    pending = cur.fetchone()
    if pending is not None:
        return _prepared_or_done(cur,str(pending[0]),pending[1],schema)
    cur.execute(f'''SELECT coalesce(max(attempt_no),0)+1 FROM {schema}.capture_reference_attempts
        WHERE capture_id=%s AND extraction_request_id=%s AND item_index=%s AND source=%s''',
        (capture_id,extraction_request_id,item_index,source))
    number = cur.fetchone()[0]
    payload = {'request_id':request_id,'source':source,'query':name[0],'brand':None,'barcode':None}
    validate(payload)
    cur.execute(f'''INSERT INTO {schema}.capture_reference_attempts
        (request_id,capture_id,extraction_request_id,item_index,source,expected_event_id,attempt_no,payload,payload_sha256)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
        (request_id,capture_id,extraction_request_id,item_index,source,current[1],number,json.dumps(payload),_digest(payload)))
    return payload


def _prepared_or_done(cur,request_id,payload,schema):
    cur.execute(f'SELECT status,applied,food_id,reason FROM {schema}.capture_reference_outcomes WHERE request_id=%s',(request_id,))
    done = cur.fetchone()
    return _result(request_id,done) if done is not None else payload


def _cache_row(payload, response):
    """Reparse and exactly match source-owned raw data; no copied nutrient values."""
    if not isinstance(response,dict) or set(response)!={'status','row'}:
        raise ValueError('invalid reference result')
    row = response['row']
    if not isinstance(row,dict):
        raise ValueError('invalid source row')
    when = dt.datetime.fromisoformat(row['fetched_at'])
    if when.utcoffset() is None:
        raise ValueError('source timestamp requires timezone')
    source = payload['source']
    if source.startswith('usda_'):
        food = row['raw']['usda_food']
        match = usda.select_exact_match(payload['query'],[food],source,brand=payload['brand'])
        expected = usda.cache_row(match,source,fetched_at=when)
    else:
        product = row['raw']['off_product']
        match = off.select_exact_match(payload['query'],[product],brand=payload['brand'])
        expected = off.cache_row(match,fetched_at=when)
    expected['fetched_at'] = when.isoformat()
    if request_bytes(expected)!=request_bytes(row):
        raise ValueError('source row differs from deterministic parser')
    return expected


def _result(request_id,row):
    status,applied,food_id,reason = row
    return {'request_id':request_id,'status':status,'applied':applied,
            'food_id':str(food_id) if food_id is not None else None,'reason':reason}


def consume(cur, *, request_id, response, schema='core', ops='ops'):
    schema,ops = _private(schema),_private(ops)
    request_id = str(uuid.UUID(str(request_id)))
    body = request_bytes(response) if response is not None else None
    if body is not None and len(body)>4*1024*1024:
        raise ValueError('reference result too large')
    digest = hashlib.sha256(body).hexdigest() if body is not None else None
    receipt_kind = 'settled' if body is not None else 'uncertain'
    cur.execute(f'''SELECT capture_id,extraction_request_id,source,payload,payload_sha256
        FROM {schema}.capture_reference_attempts WHERE request_id=%s''',(request_id,))
    attempt = cur.fetchone()
    if attempt is None:
        raise ValueError('unknown private reference request')
    capture,extraction,source,payload,payload_hash = attempt
    _lock(cur,capture)
    if response is None:
        cur.execute('SELECT public.reconcile_reference_call(%s)',(request_id,))
        cur.execute(f'SELECT response_body FROM {ops}.reference_response_bodies WHERE request_id=%s',(request_id,))
        saved = cur.fetchone()
        if saved is not None:
            response = json.loads(saved[0])
            body = request_bytes(response)
            if body.decode('utf-8')!=saved[0]:
                raise ValueError('noncanonical saved reference response')
            digest = hashlib.sha256(body).hexdigest()
            receipt_kind = 'settled'
    cur.execute(f'''SELECT response_sha256,status,applied,food_id,reason
        FROM {schema}.capture_reference_outcomes WHERE request_id=%s''',(request_id,))
    old = cur.fetchone()
    if old is not None:
        if old[0]!=digest:
            raise ValueError('reference outcome identity reused')
        return _result(request_id,old[1:])
    cur.execute(f'''SELECT r.source,r.payload_sha256,s.response_sha256,s.outcome,s.provider_status,s.recorded_at
        FROM {ops}.reference_requests r JOIN {ops}.reference_results s USING(request_id)
        WHERE r.request_id=%s''',(request_id,))
    receipt = cur.fetchone()
    if receipt is None or tuple(receipt[:4])!=(source,payload_hash,digest,receipt_kind):
        raise ValueError('matching settled source receipt required')
    if _digest(payload)!=payload_hash:
        raise ValueError('private request digest mismatch')
    validate(payload)
    status,reason,row = 'deferred','reference_dispatch_uncertain',None
    if response is not None:
        if not isinstance(response,dict) or response.get('status') not in {'resolved','unresolved','deferred'}:
            raise ValueError('invalid source outcome')
        status,reason = response['status'],None
        if receipt[4] is not None and status!='deferred':
            raise ValueError('failed source cannot publish a resolved outcome')
        if status=='resolved':
            row = _cache_row(payload,response)
            # The database's receipt clock owns cache freshness, not the worker
            # machine's wall clock. The original worker timestamp stays hash-bound.
            row['fetched_at'] = receipt[5]
        else:
            if set(response)!={'status','reason'} or not isinstance(response['reason'],str) or not re.fullmatch('[a-z0-9_]{1,128}',response['reason']):
                raise ValueError('invalid source refusal')
            reason = response['reason']
    current = _current(cur,capture,schema)
    applied = current is not None and str(current[0])==str(extraction) and current[2] in ACTIVE
    food_id = None
    cur.execute('SAVEPOINT capture_reference')
    try:
        if not applied:
            status,reason = 'stale','extraction_changed'
        elif row is not None:
            food_id = off.insert_cache_row(cur,row,schema=schema,refresh=True)
            if food_id is None:
                food_id = nutrition.cached_food_id(cur,row,schema=schema)
                if food_id is not None:
                    cur.execute(f'''SELECT brand,nutrients_per_100g,serving_g,raw,fetched_at
                        FROM {schema}.foods_cache WHERE food_id=%s''',(food_id,))
                    old_cache = cur.fetchone()
                    expected = (row['brand'],row['nutrients_per_100g'],row['serving_g'],row['raw'])
                    actual = (old_cache[0],old_cache[1],None if old_cache[2] is None else float(old_cache[2]),old_cache[3])
                    expired = (receipt[5]-old_cache[4]).total_seconds()>365*86400 and row['source'] in ('usda_branded','off_product')
                    if actual!=expected or expired:
                        raise ValueError('cache version conflict requires refresh')
            if food_id is None:
                raise ValueError('cache publication did not persist')
            nutrition.remember_alias(cur,payload['query'],row,food_id=food_id,schema=schema)
        cur.execute(f'''INSERT INTO {schema}.capture_reference_outcomes
            (request_id,response_sha256,receipt_outcome,status,applied,food_id,reason) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (request_id,digest,receipt_kind,status,applied,food_id,reason))
    except Exception:
        cur.execute('ROLLBACK TO SAVEPOINT capture_reference')
        cur.execute('RELEASE SAVEPOINT capture_reference')
        raise
    cur.execute('RELEASE SAVEPOINT capture_reference')
    return _result(request_id,(status,applied,food_id,reason))


def readback(cur, *, capture_id, schema='core'):
    schema = _private(schema)
    cur.execute(f'''SELECT a.request_id,a.extraction_request_id,a.item_index,a.source,
        o.status,o.applied,o.food_id,o.reason FROM {schema}.capture_reference_attempts a
        LEFT JOIN {schema}.capture_reference_outcomes o USING(request_id)
        WHERE a.capture_id=%s ORDER BY a.recorded_at,a.request_id''',(capture_id,))
    return [{'request_id':str(rid),'extraction_request_id':str(extraction),'item_index':index,
             'source':source,'status':status or 'awaiting_result','applied':applied,
             'food_id':str(food) if food is not None else None,'reason':reason}
            for rid,extraction,index,source,status,applied,food,reason in cur.fetchall()]
