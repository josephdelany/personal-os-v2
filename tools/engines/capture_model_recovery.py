"""Private receipt recovery. An issued reservation is never assumed abandoned."""
import json
import uuid
from tools.engines import capture_transcription, capture_extraction


def reconcile(cur, *, request_id, stage, schema='core'):
    schema = capture_transcription._private(schema)
    if stage not in ('transcribe', 'extract'):
        raise ValueError('unsupported capture stage')
    request_id = str(uuid.UUID(str(request_id)))
    table = 'capture_transcription_attempts' if stage == 'transcribe' else 'capture_extraction_attempts'
    cur.execute(f'''SELECT capture_id,model_id,payload_sha256,estimated_neurons
        FROM {schema}.{table} WHERE request_id=%s''', (request_id,))
    attempt = cur.fetchone()
    if attempt is None:
        raise ValueError('saved capture attempt required')
    capture_transcription._lock(cur, attempt[0])
    ops = 'ops' + schema.removeprefix('core') if schema.startswith('core') else None
    if ops is None:
        raise ValueError('unsupported private schema')
    cur.execute(f'''SELECT n.outcome,n.capture_id,n.model_id,r.payload_sha256,n.estimated_neurons,
        n.call_kind,b.response_body,h.http_status
        FROM {schema}.model_call_reservations r
        JOIN {schema}.neuron_ledger n USING(ledger_id)
        LEFT JOIN {ops}.model_response_bodies b USING(request_id)
        LEFT JOIN {schema}.model_http_failures h USING(request_id)
        WHERE r.request_id=%s''', (request_id,))
    receipt = cur.fetchone()
    if receipt is None:
        return {'status':'awaiting_dispatch','request_id':request_id}
    outcome, capture, model, digest, cost, kind, body, status = receipt
    if (capture,model,digest,cost) != tuple(attempt) or kind != stage:
        raise ValueError('model receipt does not match capture attempt')
    if outcome == 'issued':
        return {'status':'awaiting_result','request_id':request_id}
    engine = capture_transcription if stage == 'transcribe' else capture_extraction
    if outcome == 'ok':
        if body is None:
            return {'status':'response_unavailable','request_id':request_id}
        # The existing consumer independently verifies the canonical digest and
        # applies its original evidence/schema checks and idempotency contract.
        return engine.consume(cur,request_id=request_id,response=json.loads(body),schema=schema)
    if outcome == 'error':
        return engine.fail(cur,request_id=request_id,error_type='DispatchUncertain',
                           provider_status=status,schema=schema)
    raise ValueError('unsupported model receipt outcome')
