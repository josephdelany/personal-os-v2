"""Private SQL proof required before retiring a transient transport request."""
from tools.engines import capture_transcription


def consumed(cur,request,*,stage,schema='core'):
    schema=capture_transcription._private(schema)
    table={'transcribe':'capture_transcription','extract':'capture_extraction',
           'reference':'capture_reference'}.get(stage)
    if table is None:raise ValueError('unsupported capture stage')
    cur.execute(f'''SELECT a.payload_sha256 FROM {schema}.{table}_attempts a
        JOIN {schema}.{table}_outcomes o USING(request_id)
        WHERE a.request_id=%s''',(request['request_id'],))
    row=cur.fetchone()
    if row is None:return False
    payload=request if stage=='reference' else request['payload']
    if row[0]!=capture_transcription._digest(payload):
        raise ValueError('queued payload does not match consumed attempt')
    return True


def consume_reference_receipt(cur,request,*,schema='core',ops='ops'):
    """Consume a bound durable receipt even after its capture left the active queue."""
    from tools.engines import capture_reference
    schema,ops=capture_transcription._private(schema),capture_transcription._private(ops)
    cur.execute(f'''SELECT a.payload_sha256 FROM {schema}.capture_reference_attempts a
        JOIN {ops}.reference_results r USING(request_id)
        WHERE a.request_id=%s AND (r.outcome='uncertain' OR EXISTS (
            SELECT 1 FROM {ops}.reference_response_bodies b WHERE b.request_id=a.request_id))''',
        (request['request_id'],))
    row=cur.fetchone()
    if row is None:return None
    if row[0]!=capture_transcription._digest(request):
        raise ValueError('queued payload does not match saved attempt')
    return capture_reference.consume(cur,request_id=request['request_id'],response=None,schema=schema,ops=ops)


def consume_control(cur,request,control,*,stage,schema='core'):
    """SQL receipts outrank transport metadata; only budget refusal is actionable."""
    from tools.engines import capture_model_recovery,capture_extraction
    schema=capture_transcription._private(schema)
    if stage not in ('transcribe','extract') or request.get('call_kind')!=stage:
        raise ValueError('model capture stage required')
    if not isinstance(control,dict) or control.get('request_id')!=request['request_id']:
        raise ValueError('unbound worker control')
    table='capture_transcription_attempts' if stage=='transcribe' else 'capture_extraction_attempts'
    cur.execute(f'''SELECT payload_sha256,capture_id FROM {schema}.{table}
        WHERE request_id=%s''',(request['request_id'],))
    row=cur.fetchone()
    if (row is None or row[0]!=capture_transcription._digest(request['payload'])
        or str(row[1])!=request.get('capture_id')):
        raise ValueError('queued request does not match saved attempt')
    result=capture_model_recovery.reconcile(cur,request_id=request['request_id'],stage=stage,schema=schema)
    if result.get('status')=='awaiting_dispatch' and control.get('status')=='deferred_budget':
        owner=capture_transcription if stage=='transcribe' else capture_extraction
        return owner.fail(cur,request_id=request['request_id'],error_type='BudgetExceeded',schema=schema)
    return result
