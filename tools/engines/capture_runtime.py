"""Private capture progression. Commit each returned action before exporting it.

This owner never launches an outbound worker or loads its credentials. A scheduler
routes only a prepared request to its separately credentialed worker, then polls
this operation again. Provider receipts, not scheduler claims, advance the stage.
"""
import uuid
from tools.engines import (capture_transcription as transcription, capture_extraction,
    capture_model_recovery, capture_reference, capture_resolution, capture_food_context, nutrition)


def advance(cur, *, capture_id, retry=False, schema='core', ops='ops', config='config'):
    schema,ops,config=map(transcription._private,(schema,ops,config))
    capture_id=str(uuid.UUID(str(capture_id)))
    if type(retry) is not bool: raise ValueError('invalid retry flag')
    transcription._lock(cur,capture_id)
    # A call can consume two saved model stages, then a bounded source result.
    # External work always returns immediately as a committed dispatch action.
    for _ in range(4):
        saved=transcription.readback(cur,capture_id=capture_id,schema=schema)
        status=saved['processing_status']
        if status in ('enriched','failed','extraction_quarantined'):
            return {'status':'complete' if status=='enriched' else 'review_required','capture_id':capture_id}
        if status=='deferred_budget':
            cur.execute(f'''SELECT (recorded_at AT TIME ZONE 'UTC')::date <
                (clock_timestamp() AT TIME ZONE 'UTC')::date FROM {schema}.capture_processing_events
                WHERE event_id=%s''',(saved['processing_event_id'],))
            row=cur.fetchone()
            if row is None or not row[0]:
                return {'status':'deferred_budget','capture_id':capture_id}
        stage=('transcribe' if saved['transcription'] is None else
               'extract' if saved['extraction'] is None else 'resolve')
        if stage!='resolve':
            table='capture_transcription_attempts' if stage=='transcribe' else 'capture_extraction_attempts'
            cur.execute(f'''SELECT request_id FROM {schema}.{table}
                WHERE capture_id=%s AND expected_event_id IS NOT DISTINCT FROM %s
                ORDER BY recorded_at,request_id LIMIT 1''',(capture_id,saved['processing_event_id']))
            attempt=cur.fetchone()
            if attempt is None and status=='pending_enrichment' and not retry:
                return {'status':'retry_pending','capture_id':capture_id}
            request_id=str(attempt[0]) if attempt is not None else str(uuid.uuid4())
            if attempt is not None:
                result=capture_model_recovery.reconcile(cur,request_id=request_id,stage=stage,schema=schema)
                if result.get('status')!='awaiting_dispatch':
                    if result.get('processing_status') in ('transcribed','extracted'):
                        continue
                    if result.get('processing_status')=='extraction_quarantined':
                        return {'status':'review_required','capture_id':capture_id}
                    return {'status':result.get('status','retry_pending'),'capture_id':capture_id,
                            'stage':stage,'request_id':request_id}
            prepare=transcription.prepare_media if stage=='transcribe' else capture_extraction.prepare
            request=prepare(cur,request_id=request_id,capture_id=capture_id,schema=schema)
            return {'status':'dispatch','worker':'model','stage':stage,'request':request}
        if status=='pending_enrichment' and saved['last_error']!='resolution_incomplete' and not retry:
            return {'status':'retry_pending','capture_id':capture_id}
        extraction=saved['extraction']
        obsolete=capture_reference.consume_obsolete(cur,capture_id=capture_id,
            extraction_request_id=extraction['request_id'],schema=schema,ops=ops)
        if obsolete is not None:
            return {'status':'progress','capture_id':capture_id,'stage':'reference','outcome':obsolete['status']}
        waiting=None
        for field in extraction['fields']:
            if field['name']!='name' or field['provenance']!='extracted' or field['value'] is None:
                continue  # the resolution owner records the actual refusal
            outcomes=capture_reference.source_outcomes(cur,capture_id=capture_id,
                extraction_request_id=extraction['request_id'],item_index=field['item_index'],schema=schema)
            if not retry and any(v['status']=='deferred' for v in outcomes.values()):
                waiting='retry_pending'
                continue
            try:
                request=capture_reference.prepare(cur,request_id=uuid.uuid4(),capture_id=capture_id,
                    extraction_request_id=extraction['request_id'],item_index=field['item_index'],
                    schema=schema,ops=ops)
            except (capture_food_context.ContextUnresolved,nutrition.Unresolved):
                continue  # same shared owner persists this review during resolution
            if request.get('status')=='awaiting_result':
                cur.execute(f'SELECT 1 FROM {ops}.reference_results WHERE request_id=%s',
                            (request['request_id'],))
                if cur.fetchone() is None:
                    waiting=waiting or 'awaiting_result'
                    continue
                result=capture_reference.consume(cur,request_id=request['request_id'],response=None,
                                                  schema=schema,ops=ops)
                # Re-read cache/source order next invocation; do not create a new
                # processing head while other source requests bind to this one.
                return {'status':'progress','capture_id':capture_id,'stage':'reference',
                        'outcome':result['status']}
            if 'status' not in request:
                return {'status':'dispatch','worker':'reference','stage':'reference','request':request}
        if waiting:
            return {'status':waiting,'capture_id':capture_id}
        result=capture_resolution.resolve(cur,request_id=uuid.uuid4(),capture_id=capture_id,
            extraction_request_id=extraction['request_id'],schema=schema,ops=ops,config=config)
        return {'status':'complete' if result['processing_status']=='enriched' else 'retry_pending',
                'capture_id':capture_id,'stage':'resolve','result':result}
    return {'status':'progress','capture_id':capture_id}
