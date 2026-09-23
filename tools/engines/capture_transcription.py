"""Private transcription stages. Caller commits before dispatch or display.

Media acquisition/orchestration supplies a prepared payload; this component binds
that exact request to immutable capture history and verifies settled responses.
It has no network capability and never updates the original capture.
"""
import datetime as dt
import hashlib
import json
import os
import re
import uuid
from decimal import Decimal
from lib.model_contract import request_bytes, audio_neurons
from tools.engines.capture_budget import (TRANSCRIPTION_MODEL, TRANSCRIPTION_PARAMS,
    EMPTY_TRANSCRIPT_MIN_SECONDS, validate_transcription)
from tools.engines.capture_processing import record_outcome

VERSION = 'capture-transcription-v1'
FAILURES = {'BudgetExceeded', 'DispatchRefused', 'DispatchUncertain',
            'PayloadRefused', 'DispatcherUnavailable'}


def _private(schema):
    if any(os.environ.get(key) for key in ('CF_API_TOKEN', 'MODEL_EGRESS_DB_URL', 'REFERENCE_EGRESS_DB_URL',
                                                 'USDA_FDC_API_KEY', 'PERSONAL_OS_USDA_API_KEY')):
        raise RuntimeError('provider capability present in private capture process')
    if not isinstance(schema,str) or not re.fullmatch('[a-z_][a-z0-9_]*',schema):
        raise ValueError('invalid schema')
    return schema


def _lock(cur, capture_id):
    cur.execute("SELECT current_setting('transaction_isolation')")
    if cur.fetchone()[0] != 'read committed':
        raise ValueError('READ COMMITTED required')
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,76))',(str(capture_id),))


def _digest(value):
    return hashlib.sha256(request_bytes(value)).hexdigest()


def prepare(cur, *, request_id, capture_id, payload, schema='core'):
    """Bind an already prepared media request; payload export follows caller commit.

    This is not evidence that the supplied media was downloaded from Storage.
    The media adapter must provide that binding before deployment.
    """
    schema = _private(schema)
    request_id, capture_id = str(uuid.UUID(str(request_id))), str(uuid.UUID(str(capture_id)))
    if (not isinstance(payload,dict) or not payload.get('audio')
        or any(payload.get(k) != v or type(payload.get(k)) is not type(v)
               for k,v in TRANSCRIPTION_PARAMS.items())):
        raise ValueError('invalid transcription request')
    digest = _digest(payload)
    _lock(cur,capture_id)
    cur.execute(f'''SELECT capture_id,payload_sha256,model_id,call_kind,estimated_neurons
        FROM {schema}.capture_transcription_attempts WHERE request_id=%s''',(request_id,))
    old = cur.fetchone()
    if old:
        if str(old[0]) != capture_id or old[1] != digest:
            raise ValueError('request identity reused')
        model,kind,cost = old[2:]
    else:
        cur.execute(f'''SELECT r.source,r.payload,c.processing_status,c.event_id
            FROM {schema}.raw_captures r JOIN {schema}.capture_processing_current c USING(capture_id)
            WHERE r.capture_id=%s''',(capture_id,))
        row = cur.fetchone()
        if row is None or row[0] != 'shortcut_voice' or row[2] not in ('received','pending_enrichment','deferred_budget'):
            raise ValueError('capture is not awaiting transcription')
        # Duration is the capture's immutable declared value, never model arithmetic.
        if not isinstance(row[1],dict):
            raise ValueError('invalid capture payload')
        cur.execute(f'SELECT 1 FROM {schema}.capture_transcription_current WHERE capture_id=%s',(capture_id,))
        if cur.fetchone() is not None:
            raise ValueError('capture already has a usable transcript')
        duration = row[1].get('duration_s')
        if isinstance(duration,bool) or not isinstance(duration,(int,float)):
            raise ValueError('capture duration required')
        duration = Decimal(str(duration))
        if not duration.is_finite() or duration <= 0:
            raise ValueError('invalid capture duration')
        cost = Decimal(str(audio_neurons(duration)))
        if cost > 10000:
            raise ValueError('single capture exceeds hard budget')
        model,kind = TRANSCRIPTION_MODEL,'transcribe'
        cur.execute(f'''INSERT INTO {schema}.capture_transcription_attempts
            (request_id,capture_id,expected_event_id,model_id,call_kind,payload_sha256,
             duration_seconds,estimated_neurons,processor_version)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (request_id,capture_id,row[3],model,kind,digest,duration,Decimal(str(float(cost))),VERSION))
    return {'request_id':request_id,'capture_id':capture_id,'model_id':model,
            'call_kind':kind,'estimated_neurons':float(cost),'payload':payload}


def _attempt(cur, request_id, schema):
    cur.execute(f'''SELECT capture_id,expected_event_id,model_id,call_kind,payload_sha256,
        duration_seconds,estimated_neurons,processor_version
        FROM {schema}.capture_transcription_attempts WHERE request_id=%s''',(request_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('unknown transcription request')
    _lock(cur,row[0])
    return row


def _previous(cur,request_id,schema,digest,failure):
    cur.execute(f'''SELECT o.response_sha256,o.failure_code,o.event_id,e.applied,e.processing_status
        FROM {schema}.capture_transcription_outcomes o JOIN {schema}.capture_processing_events e
        ON e.event_id=o.event_id WHERE o.request_id=%s''',(request_id,))
    row = cur.fetchone()
    if row is None:
        return None
    if row[0] != digest or (digest is None and row[1] != failure):
        raise ValueError('transcription outcome identity reused')
    return {'event_id':row[2],'applied':row[3],'processing_status':row[4]}


def _persist(cur,request_id,attempt,schema,digest,failure,transcript=None,segments=None):
    capture,expected,model,kind,payload_hash,duration,cost,version = attempt
    status = 'transcribed' if failure is None else ('deferred_budget' if failure=='BudgetExceeded' else 'pending_enrichment')
    # A savepoint prevents callers that catch a persistence error from committing
    # the processing event without its corresponding immutable result.
    cur.execute('SAVEPOINT transcript_result')
    try:
        event = record_outcome(cur,capture_id=capture,attempt_id=request_id,expected_event_id=expected,
            status=status,error=failure,processor_version=version)
        cur.execute(f'''INSERT INTO {schema}.capture_transcription_outcomes
            (request_id,capture_id,event_id,response_sha256,transcript,segments,failure_code)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (request_id,capture,event['event_id'],digest,transcript,
             json.dumps(segments,allow_nan=False) if segments is not None else None,failure))
        if failure == 'empty_transcript' and event['applied']:
            cur.execute('SELECT public.review_empty_transcript(%s,%s)',(capture,event['event_id']))
    except Exception:
        cur.execute('ROLLBACK TO SAVEPOINT transcript_result')
        cur.execute('RELEASE SAVEPOINT transcript_result')
        raise
    cur.execute('RELEASE SAVEPOINT transcript_result')
    return {'event_id':event['event_id'],'applied':event['applied'],'processing_status':status}


def consume(cur, *, request_id, response, schema='core'):
    schema = _private(schema)
    request_id = str(uuid.UUID(str(request_id)))
    digest = _digest(response)
    attempt = _attempt(cur,request_id,schema)
    previous = _previous(cur,request_id,schema,digest,None)
    if previous is not None:
        return previous
    capture,expected,model,kind,payload_hash,duration,cost,version = attempt
    cur.execute(f'''SELECT n.outcome,n.model_id,n.call_kind,n.capture_id,n.estimated_neurons,
        r.payload_sha256,s.response_sha256 FROM {schema}.model_call_reservations r
        JOIN {schema}.neuron_ledger n USING(ledger_id)
        JOIN {schema}.model_call_results s USING(request_id) WHERE r.request_id=%s''',(request_id,))
    receipt = cur.fetchone()
    if receipt is None or tuple(receipt) != ('ok',model,kind,capture,cost,payload_hash,digest):
        raise ValueError('matching settled transcription receipt required')
    try:
        if not isinstance(response,dict) or response.get('success') is not True:
            raise ValueError('invalid_transcription_envelope')
        result = validate_transcription(response.get('result'))
    except ValueError:
        return _persist(cur,request_id,attempt,schema,digest,'invalid_transcription')
    failure = ('empty_transcript' if not result['transcript'].strip()
               and duration > EMPTY_TRANSCRIPT_MIN_SECONDS else None)
    return _persist(cur,request_id,attempt,schema,digest,failure,result['transcript'],result['segments'])


def fail(cur, *, request_id, error_type, provider_status=None, schema='core'):
    schema = _private(schema)
    if error_type not in FAILURES:
        raise ValueError('unsupported dispatcher failure')
    request_id = str(uuid.UUID(str(request_id)))
    attempt = _attempt(cur,request_id,schema)
    code = error_type
    if provider_status is not None:
        if error_type != 'DispatchUncertain' or type(provider_status) is not int or not 300 <= provider_status <= 599:
            raise ValueError('invalid provider status')
        capture,expected,model,kind,payload_hash,duration,cost,version = attempt
        cur.execute(f'''SELECT n.outcome,n.model_id,n.call_kind,n.capture_id,n.estimated_neurons,
            r.payload_sha256,h.http_status FROM {schema}.model_call_reservations r
            JOIN {schema}.neuron_ledger n USING(ledger_id)
            JOIN {schema}.model_http_failures h USING(request_id) WHERE r.request_id=%s''',(request_id,))
        receipt = cur.fetchone()
        if receipt is None or tuple(receipt) != ('error',model,kind,capture,cost,payload_hash,provider_status):
            raise ValueError('matching provider failure receipt required')
        code = str(provider_status)
    return (_previous(cur,request_id,schema,None,code)
            or _persist(cur,request_id,attempt,schema,None,code))


def readback(cur, *, capture_id, schema='core'):
    schema = _private(schema)
    cur.execute(f'''SELECT c.capture_id,c.processing_status,c.last_error,c.event_id,
        t.request_id,t.event_id,t.transcript,t.segments,t.model_id,t.processor_version
        FROM {schema}.capture_processing_current c
        LEFT JOIN {schema}.capture_transcription_current t USING(capture_id)
        WHERE c.capture_id=%s''',(str(uuid.UUID(str(capture_id))),))
    row = cur.fetchone()
    if row is None:
        raise ValueError('unknown capture')
    cur.execute(f'''SELECT request_id,event_id,processor_version FROM {schema}.capture_extraction_current
        WHERE capture_id=%s''',(str(row[0]),))
    extracted=cur.fetchone()
    extraction=None
    if extracted is not None:
        cur.execute(f'''SELECT item_index,name,value,provenance,reason,evidence,evidence_start
            FROM {schema}.capture_extraction_fields WHERE request_id=%s ORDER BY item_index,name''',
            (extracted[0],))
        extraction={'request_id':str(extracted[0]),'event_id':extracted[1],'processor_version':extracted[2],
                    'fields':[dict(zip(('item_index','name','value','provenance','reason','evidence','evidence_start'),f))
                              for f in cur.fetchall()]}
        cur.execute(f'''SELECT i.item_id,i.item_index,i.occurred_at,i.subject_day,i.time_precision,
            i.time_provenance,i.time_reason,i.resolution FROM {schema}.capture_resolved_items i
            WHERE i.extraction_request_id=%s ORDER BY i.item_index''',(extracted[0],))
        resolved=[]
        for item in cur.fetchall():
            cur.execute(f'''SELECT id,metric_key,value_low,value_point,value_high,unit,estimate_method,
                provenance,code_version,capture_component,event_time_provenance,quantity_provenance FROM {schema}.atoms a WHERE capture_item_id=%s
                AND NOT EXISTS(SELECT 1 FROM {schema}.atoms b WHERE b.supersedes=a.id)
                ORDER BY metric_key''',(item[0],))
            atoms=[dict(zip(('atom_id','metric_key','value_low','value_point','value_high','unit',
                             'estimate_method','provenance','code_version','component','time_provenance','quantity_provenance'),a)) for a in cur.fetchall()]
            resolved.append({**dict(zip(('item_id','item_index','occurred_at','subject_day','time_precision',
                                         'time_provenance','time_reason','resolution'),item)), 'atoms':atoms})
        extraction['resolved_items']=resolved
    from tools.engines import capture_reference
    return {'capture_id':str(row[0]),'processing_status':row[1],'last_error':row[2],
            'reference_attempts':capture_reference.readback(cur,capture_id=str(row[0]),schema=schema),
            'processing_event_id':row[3], 'extraction':extraction, 'transcription': None if row[4] is None else {
                'request_id':str(row[4]),'event_id':row[5],'text':row[6],
                'segments':row[7],'model_id':row[8],'processor_version':row[9]}}


def work_queue(cur, *, limit=100, cursor=None, schema='core'):
    """Enumerate a run's initial captures/retries without starving later failures.

    The opaque cursor fixes an insertion cutoff and advances by capture time/UUID.
    It is pagination, not a claim or concurrency/commit-visibility guarantee.
    """
    schema = _private(schema)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    after_time,after_id = None,None
    if cursor is None:
        cur.execute('SELECT clock_timestamp()')
        through=cur.fetchone()[0]
    else:
        if not isinstance(cursor,dict) or set(cursor)!={'through','captured_at','capture_id'}:
            raise ValueError('invalid queue cursor')
        through=dt.datetime.fromisoformat(cursor['through'])
        after_time=dt.datetime.fromisoformat(cursor['captured_at'])
        after_id=str(uuid.UUID(cursor['capture_id']))
        if through.utcoffset() is None or after_time.utcoffset() is None:
            raise ValueError('queue cursor timezone required')
    cur.execute(f'''SELECT c.capture_id,c.event_id,c.processing_status,t.request_id,c.captured_at,x.request_id
        FROM {schema}.capture_processing_current c
        JOIN {schema}.raw_captures r USING(capture_id)
        LEFT JOIN {schema}.capture_transcription_current t USING(capture_id)
        LEFT JOIN {schema}.capture_extraction_current x USING(capture_id)
        WHERE c.source='shortcut_voice' AND r.recorded_at <= %s
          AND c.processing_status IN ('received','pending_enrichment','deferred_budget','transcribed','extracted')
          AND (%s::timestamptz IS NULL OR (c.captured_at,c.capture_id) > (%s::timestamptz,%s::uuid))
        ORDER BY c.captured_at,c.capture_id LIMIT %s''',
        (through,after_time,after_time,after_id,limit+1))
    rows=cur.fetchall()
    selected=rows[:limit]
    next_cursor=None
    if len(rows)>limit:
        last=selected[-1]
        next_cursor={'through':through.isoformat(),'captured_at':last[4].isoformat(),'capture_id':str(last[0])}
    return {'items':[{'capture_id':str(cid),'event_id':event,'processing_status':status,
                     'next_stage':'resolve' if extraction is not None else ('extract' if transcript is not None else 'transcribe'),
                     'extraction_request_id':str(extraction) if extraction is not None else None}
                    for cid,event,status,transcript,captured_at,extraction in selected],
            'next_cursor':next_cursor}


def prepare_media(cur, *, request_id, capture_id, schema='core'):
    """Build the request from hash-bound private media, never caller-supplied audio."""
    import base64
    from lib import db
    schema = _private(schema)
    capture_id = str(uuid.UUID(str(capture_id)))
    cur.execute(f'SELECT source,payload FROM {schema}.raw_captures WHERE capture_id=%s',(capture_id,))
    row = cur.fetchone()
    if row is None or row[0]!='shortcut_voice' or not isinstance(row[1],dict):
        raise ValueError('voice capture required')
    path,digest = row[1].get('media_path'),row[1].get('media_sha256')
    if digest is None:
        # Recover a missing envelope hash only from an already verified immutable
        # upload receipt for this exact capture/path. Never update raw evidence.
        cur.execute(f'''SELECT u.sha256 FROM {schema}.capture_media_uploads u
            JOIN {schema}.capture_media_receipts r USING(capture_id,sha256)
            WHERE u.capture_id=%s AND u.media_path=%s''',(capture_id,path))
        receipt=cur.fetchone()
        if receipt is None:
            raise ValueError('verified media binding required')
        digest=receipt[0]
    body = db.read_capture_media(capture_id,path,digest)
    payload = {'audio':base64.b64encode(body).decode('ascii'),**TRANSCRIPTION_PARAMS}
    return prepare(cur,request_id=request_id,capture_id=capture_id,payload=payload,schema=schema)


def reconcile_media(cur, *, capture_id, schema='core'):
    """Verify ambiguous upload completion privately, then append its receipt.

    Caller commits before returning acknowledgement. This requires a previously
    recorded expected digest; it does not invent provenance for unknown old blobs.
    """
    from lib import db
    schema=_private(schema)
    capture_id=str(uuid.UUID(str(capture_id)))
    cur.execute(f'''SELECT media_path,sha256,size_bytes FROM {schema}.capture_media_uploads
        WHERE capture_id=%s''',(capture_id,))
    row=cur.fetchone()
    if row is None:
        raise ValueError('known upload identity required')
    body=db.read_capture_media(capture_id,row[0],row[1])
    if len(body)!=row[2]:
        raise ValueError('media size mismatch')
    cur.execute('SELECT public.reconcile_capture_media_upload(%s,%s)',(capture_id,row[1]))
    return cur.fetchone()[0]
