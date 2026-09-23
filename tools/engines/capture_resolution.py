"""Private saved-extraction -> deterministic nutrition -> immutable atoms.

Caller commits before readback. Model output never supplies nutrient values.
The existing nutrition owner owns reference lookup, arithmetic and atom writes.
"""
import json
import re
import uuid
import math
from decimal import Decimal

from lib.mass_units import MASS_UNITS_TO_G

from tools.engines import nutrition, capture_food_context
from tools.engines.capture_transcription import _private, _lock
from tools.engines.capture_processing import record_outcome
from tools.engines.extraction import resolve_time
from tools.importers.common import ET, subject_day

VERSION = 'capture-food-resolution-v3'
COUNT_UNITS = {'each','item','items','serving','servings','piece','pieces'}


def event_time(fields, captured_at):
    temporal = fields.get((-1, 'temporal_evidence'))
    span = temporal['value'] if temporal and temporal['provenance']=='extracted' else None
    field = resolve_time(span, captured_at.astimezone(ET))
    instant = field.value
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ET)
    precision = 'unknown'
    if field.provenance == 'extracted':
        precision = ('minute' if re.search(r'\d:\d', span)
                     else 'hour' if re.search(r'\d\s*(?:am|pm)|\bhours?\b', span, re.I) else 'day')
    return instant, precision, field.provenance, field.reason


def _quantity(fields, index, name):
    quantity, unit = fields[(index,'quantity')], fields[(index,'quantity_unit')]
    if quantity['value'] is None:
        if quantity['evidence'] is not None or quantity['reason'] in ('span_mismatch','value_not_in_span'):
            raise nutrition.Unresolved(name,[],reason='unverified_quantity',review_reason='unverified_quantity')
        return {}
    if quantity['provenance'] != 'extracted':
        raise nutrition.Unresolved(name,[],reason='unverified_quantity',review_reason='unverified_quantity')
    mass_unit = str(unit['value']).strip().lower()
    if mass_unit in MASS_UNITS_TO_G:
        # Require one complete literal amount/unit pair. Finding the number and
        # unit separately would misread "150 ml and 200 g" as 150 g.
        evidence = quantity['evidence'] or ''
        pair = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s+([a-z]+)\s*', evidence, re.I)
        value = quantity['value']
        if (unit['provenance'] == 'extracted'
                and unit['evidence'] == evidence and pair
                and pair[2].lower() == mass_unit
                and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
                and math.isfinite(value) and value > 0
                and Decimal(pair[1]) == Decimal(str(value))):
            grams = float(value) * MASS_UNITS_TO_G[mass_unit]
            if math.isfinite(grams) and grams > 0:
                return {'grams': grams}
        raise nutrition.Unresolved(name,[],reason='unverified_quantity',review_reason='unverified_quantity')
    if unit['value'] is None or str(unit['value']).lower() in COUNT_UNITS:
        # A missing model unit is not proof of a count. Accept a bounded count
        # phrase, rather than treating every unknown dimension as item count.
        evidence = quantity['evidence'] or ''
        count_number = r'(?:\d+(?:\.\d+)?|a|an|one|two|three|four|five|six|seven|eight|nine|ten|zero)'
        count_label = '|'.join(re.escape(label) for label in sorted(COUNT_UNITS | {name.casefold()}))
        count_pair = re.fullmatch(r'\s*'+count_number+r'(?:\s+('+count_label+r'))?\s*',evidence,re.I)
        if count_pair is None:
            raise nutrition.Unresolved(name,[],reason='quantity_unit_unresolved',review_reason='quantity_unit_unresolved')
        label = (count_pair[1] or '').casefold()
        if ((label in ('serving','servings')) != (mass_unit in ('serving','servings'))
                or (unit['value'] is not None and unit['provenance'] != 'extracted')):
            raise nutrition.Unresolved(name,[],reason='quantity_unit_unresolved',review_reason='quantity_unit_unresolved')
        return {('servings' if mass_unit in ('serving','servings') else 'item_count'):quantity['value']}
    raise nutrition.Unresolved(name,[],reason='quantity_unit_unresolved',review_reason='quantity_unit_unresolved')


def resolve(cur, *, request_id, capture_id, extraction_request_id, schema='core',
            config='config', ops='ops'):
    schema, config, ops = _private(schema), _private(config), _private(ops)
    # Private-row readers cannot perform source-API egress (ADR0020). Missing
    # reference data remains pending for a separately scoped fetch/cache stage.
    sources = nutrition.build_sources(cur,schema=schema,config=config,ops=ops,usda=False,off=False)
    request_id, capture_id, extraction_request_id = map(lambda value:str(uuid.UUID(str(value))),
                                                      (request_id,capture_id,extraction_request_id))
    _lock(cur,capture_id)
    cur.execute(f'''SELECT capture_id,extraction_request_id,result
        FROM {schema}.capture_resolution_outcomes WHERE request_id=%s''',(request_id,))
    previous=cur.fetchone()
    if previous is not None:
        if (str(previous[0]),str(previous[1])) != (capture_id,extraction_request_id):
            raise ValueError('resolution request identity reused')
        return previous[2]
    cur.execute(f'''SELECT x.request_id,c.event_id,c.processing_status,r.captured_at,r.trust_level
        FROM {schema}.capture_extraction_current x
        JOIN {schema}.capture_processing_current c USING(capture_id)
        JOIN {schema}.raw_captures r USING(capture_id) WHERE x.capture_id=%s''',(capture_id,))
    current=cur.fetchone()
    if current is None or str(current[0]) != extraction_request_id:
        raise ValueError('current saved extraction required')
    _,head,status,captured_at,trust = current
    if status == 'enriched':
        cur.execute(f'''SELECT result FROM {schema}.capture_resolution_outcomes
            WHERE capture_id=%s AND extraction_request_id=%s AND event_id=%s''',
            (capture_id,extraction_request_id,head))
        completed=cur.fetchone()
        if completed is not None:
            return completed[0]
    if status not in ('extracted','pending_enrichment','deferred_budget'):
        raise ValueError('capture is not awaiting resolution')
    cur.execute(f'''SELECT 1 FROM {schema}.capture_resolved_items
        WHERE capture_id=%s AND extraction_request_id<>%s LIMIT 1''',(capture_id,extraction_request_id))
    if cur.fetchone() is not None:
        raise ValueError('existing resolved capture requires explicit supersession')
    cur.execute(f'''SELECT item_index,name,value,provenance,reason,evidence,evidence_start
        FROM {schema}.capture_extraction_fields WHERE request_id=%s ORDER BY item_index,name''',
        (extraction_request_id,))
    fields={}
    for index,name,value,provenance,reason,evidence,offset in cur.fetchall():
        fields[(index,name)]={'value':value,'provenance':provenance,'reason':reason,
                              'evidence':evidence,'evidence_start':offset}
    when,precision,time_provenance,time_reason = event_time(fields,captured_at)
    day=subject_day(when)
    items=[]
    pending=False
    cur.execute('SAVEPOINT capture_resolution')
    try:
        for index in sorted({index for index,name in fields if index>=0}):
            name=fields[(index,'name')]
            if name['provenance']!='extracted' or not name['value']:
                items.append({'item_index':index,'status':'rejected','reason':'unverified_name'})
                pending=True
                continue
            cur.execute(f'''SELECT item_id,resolution FROM {schema}.capture_resolved_items
                WHERE extraction_request_id=%s AND item_index=%s''',(extraction_request_id,index))
            old=cur.fetchone()
            if old is not None:
                items.append({'item_index':index,'item_id':str(old[0]),'status':'resolved'})
                continue
            try:
                try:
                    context=capture_food_context.load(cur,extraction_request_id=extraction_request_id,
                                                     item_index=index,schema=schema)
                except capture_food_context.ContextUnresolved as error:
                    raise nutrition.Unresolved(name['value'],[],reason=str(error),review_reason=str(error)) from None
                quantity=_quantity(fields,index,name['value'])
                selected_sources=({'joe':nutrition.CacheLeg(cur,schema,owner_only=True)}
                                  if context.get('owner_correction') else
                                  {**sources,'joe':nutrition.CacheLeg(cur,schema,allow_unbranded_owner=False)})
                resolved=nutrition.resolve_item(cur,context['query'],schema=schema,config=config,ops=ops,
                                                sources=selected_sources,brand=context['brand'],**quantity)
                resolved['food_context']=context
            except nutrition.Unresolved as missing:
                if missing.reason=='no_source_available':
                    from tools.engines import capture_reference
                    attempts=capture_reference.source_outcomes(cur,capture_id=capture_id,
                        extraction_request_id=extraction_request_id,item_index=index,schema=schema)
                    if all(attempts.get(source,{}).get('status')=='unresolved'
                           for source in capture_reference.source_order(context['brand'])):
                        missing=nutrition.Unresolved(name['value'],
                            [{'source':source,**attempts[source]} for source in capture_reference.source_order(context['brand'])],
                            reason='no_source_match',review_reason='no_source_match',brand=context['brand'])
                nutrition.record_unresolved(cur,missing,raw_capture_id=capture_id,subject_day=day,schema=schema,
                                             extraction_request_id=extraction_request_id,item_index=index)
                items.append({'item_index':index,'status':'unresolved','reason':missing.reason})
                # Source outages and unsupported evidence must remain retryable;
                # a reference miss is a normal, explicitly unresolved food outcome.
                pending |= missing.reason in ('no_source_available','unverified_quantity','quantity_unit_unresolved',
                                              'no_branded_serving','no_quantity')
                continue
            item_id=str(uuid.uuid5(uuid.UUID(extraction_request_id),str(index)))
            cur.execute(f'''INSERT INTO {schema}.capture_resolved_items
                (item_id,capture_id,extraction_request_id,item_index,occurred_at,subject_day,
                 time_precision,time_provenance,time_reason,resolution)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (item_id,capture_id,extraction_request_id,index,when,day,precision,time_provenance,time_reason,
                 json.dumps(resolved,default=str,allow_nan=False)))
            nutrition.persist_resolution(cur,resolved,raw_capture_id=capture_id,occurred_at=when,subject_day=day,
                evidence_span=name['evidence'],schema=schema,trust_level=trust,
                time_precision=precision,capture_item_id=item_id)
            nutrition.close_capture_unresolved(cur,capture_id=capture_id,extraction_request_id=extraction_request_id,
                                                item_index=index,schema=schema)
            items.append({'item_index':index,'item_id':item_id,'status':'resolved'})
        pending |= not items
        event=record_outcome(cur,capture_id=capture_id,attempt_id=request_id,expected_event_id=head,
            status='pending_enrichment' if pending else 'enriched',
            error='resolution_incomplete' if pending else None,processor_version=VERSION)
        if not event['applied']:
            raise ValueError('resolution predecessor changed')
        result={'capture_id':capture_id,'extraction_request_id':extraction_request_id,
                'event_id':event['event_id'],'processing_status':'pending_enrichment' if pending else 'enriched',
                'items':items}
        cur.execute(f'''INSERT INTO {schema}.capture_resolution_outcomes
            (request_id,capture_id,extraction_request_id,expected_event_id,event_id,result)
            VALUES (%s,%s,%s,%s,%s,%s)''',
            (request_id,capture_id,extraction_request_id,head,event['event_id'],json.dumps(result)))
    except Exception:
        cur.execute('ROLLBACK TO SAVEPOINT capture_resolution')
        cur.execute('RELEASE SAVEPOINT capture_resolution')
        raise
    cur.execute('RELEASE SAVEPOINT capture_resolution')
    return result
