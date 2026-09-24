"""Owner correction contract (ADR-0161).

Validation is not authorization. The persistence entry point must separately require
the private owner database capability; actor metadata grants no permission.
"""
import json
import math
import uuid
from decimal import Decimal

from tools.engines import nutrition
from tools.engines.capture_transcription import _private, _lock


VERSION = 'capture-owner-correction-v1'
_IDENTITY = {'request_id', 'capture_id', 'expected_item_id', 'actor', 'operation'}


def validate_request(payload):
    """Return a detached, canonical request suitable for payload-bound replay.

Replacement quantities use the nutrition owner's input dimensions. Source IDs
identify immutable cache versions, never a name that can resolve differently later.
Removal is explicit: zero is neither deletion nor a missing observation.
"""
    if not isinstance(payload, dict):
        raise ValueError('correction request must be an object')
    operation = payload.get('operation')
    required = _IDENTITY | ({'food_id', 'quantity'} if operation == 'replace' else set())
    if operation not in ('replace', 'remove') or set(payload) != required:
        raise ValueError('invalid correction request fields')
    if payload['actor'] != 'joe':
        raise ValueError('owner actor required; database authorization is also required')
    result = dict(payload)
    for key in ('request_id', 'capture_id', 'expected_item_id', *(['food_id'] if operation == 'replace' else [])):
        try:
            result[key] = str(uuid.UUID(str(payload[key])))
        except (ValueError, TypeError, AttributeError):
            raise ValueError(f'invalid {key}') from None
    if operation == 'replace':
        quantity = payload['quantity']
        if (not isinstance(quantity, dict) or len(quantity) != 1
                or not set(quantity) <= {'grams', 'servings', 'item_count'}):
            raise ValueError('one explicit quantity dimension required')
        value = next(iter(quantity.values()))
        try:
            valid = (not isinstance(value, bool) and isinstance(value, (int, float))
                     and math.isfinite(value) and value > 0)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError('positive finite numeric quantity required')
        result['quantity'] = dict(quantity)
    # No arbitrary extension fields or non-JSON objects enter the immutable ledger.
    return json.loads(json.dumps(result, allow_nan=False, sort_keys=True))


def apply(cur, payload, *, schema='core', config='config', ops='ops'):
    """Append one complete correction; caller commits before displaying success.

    The capture lock serializes automatic resolution and owner corrections. A
    savepoint protects callers that catch an error and subsequently commit.
    No provider request or mutable food alias is involved.
    """
    schema, config, ops = map(_private, (schema, config, ops))
    request = validate_request(payload)
    cur.execute("SELECT pg_has_role(current_user,'capture_owner','USAGE')")
    if not cur.fetchone()[0]:
        raise PermissionError('private owner capability required')
    _lock(cur, request['capture_id'])
    quantity = request.get('quantity', {})
    dimension, amount = next(iter(quantity.items())) if quantity else (None, None)
    identity = (request['capture_id'], request['expected_item_id'], request['actor'],
                request['operation'], request.get('food_id'), dimension,
                Decimal(str(amount)) if amount is not None else None)
    cur.execute(f'''SELECT capture_id,expected_item_id,actor,operation,food_id,quantity_kind,quantity
        FROM {schema}.capture_owner_corrections WHERE request_id=%s''', (request['request_id'],))
    previous = cur.fetchone()
    if previous is not None:
        previous = tuple(str(value) if index in (0, 1, 4) and value is not None else value
                         for index, value in enumerate(previous))
        if previous != identity:
            raise ValueError('correction request identity reused')
        cur.execute(f'SELECT result FROM {schema}.capture_correction_outcomes WHERE request_id=%s',
                    (request['request_id'],))
        saved = cur.fetchone()
        if saved is None:
            raise ValueError('incomplete correction request')
        return saved[0]
    cur.execute(f'''SELECT i.extraction_request_id,i.item_index,i.occurred_at,i.subject_day,
        i.time_precision,i.time_provenance,i.time_reason,r.trust_level
        FROM {schema}.capture_resolved_items_current i
        JOIN {schema}.raw_captures r USING(capture_id)
        JOIN {schema}.capture_extraction_current x ON x.capture_id=i.capture_id
            AND x.request_id=i.extraction_request_id
        WHERE i.item_id=%s AND i.capture_id=%s''',
        (request['expected_item_id'], request['capture_id']))
    prior = cur.fetchone()
    if prior is None:
        raise ValueError('stale or unknown correction predecessor')
    extraction_id, index, when, day, precision, time_source, time_reason, trust = prior
    cur.execute(f'''SELECT metric_key,capture_component,id FROM {schema}.atoms_current
        WHERE capture_item_id=%s''', (request['expected_item_id'],))
    predecessors = {(key, component): atom for key, component, atom in cur.fetchall()}
    cur.execute('SAVEPOINT capture_owner_correction')
    try:
        resolved = {'status': 'removed'}
        if request['operation'] == 'replace':
            cur.execute(f'SELECT canonical_name,brand,serving_g FROM {schema}.foods_cache WHERE food_id=%s',
                        (request['food_id'],))
            food = cur.fetchone()
            if food is None:
                raise ValueError('correction source version does not exist')
            if dimension == 'servings' and not food[2]:
                raise ValueError('correction servings require a pinned serving mass')
            resolved = nutrition.resolve_item(cur, food[0], brand=food[1], **quantity,
                sources={'joe': nutrition.PinnedCacheLeg(cur, request['food_id'], schema=schema)},
                schema=schema, config=config, ops=ops)
        resolved['owner_correction'] = request
        item_id = str(uuid.uuid5(uuid.UUID(request['request_id']), 'corrected-item'))
        cur.execute(f'''INSERT INTO {schema}.capture_owner_corrections
            (request_id,capture_id,expected_item_id,actor,operation,food_id,quantity_kind,quantity)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', (request['request_id'], *identity))
        cur.execute(f'''INSERT INTO {schema}.capture_resolved_items
            (item_id,capture_id,extraction_request_id,item_index,occurred_at,subject_day,
             time_precision,time_provenance,time_reason,resolution,supersedes_item_id,correction_request_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)''',
            (item_id, request['capture_id'], extraction_id, index, when, day, precision,
             time_source, time_reason, json.dumps(resolved, default=str, allow_nan=False),
             request['expected_item_id'], request['request_id']))
        if request['operation'] == 'replace':
            nutrition.persist_resolution(cur, resolved, raw_capture_id=request['capture_id'],
                occurred_at=when, subject_day=day, time_precision=precision, trust_level=trust,
                evidence_span='owner correction ' + request['request_id'], schema=schema,
                code_version=VERSION, capture_item_id=item_id,
                correction_request_id=request['request_id'], supersedes_by_component=predecessors)
        # Anything left current on the predecessor was omitted or changed shape.
        # Retire it explicitly without inventing a nutrient measurement.
        cur.execute(f'''INSERT INTO {schema}.atoms
            (raw_capture_id,kind,metric_key,occurred_at,subject_day,subject_day_rule_version,
             presence,trust_level,provenance,code_version,capture_item_id,capture_component,
             supersedes,correction_request_id,is_retraction)
            SELECT raw_capture_id,kind,metric_key,occurred_at,subject_day,subject_day_rule_version,
              'unknown',trust_level,provenance,%s,capture_item_id,capture_component,id,%s,true
            FROM {schema}.atoms_current WHERE capture_item_id=%s''',
            (VERSION, request['request_id'], request['expected_item_id']))
        result = {'request_id': request['request_id'], 'capture_id': request['capture_id'],
                  'previous_item_id': request['expected_item_id'], 'item_id': item_id,
                  'status': 'removed' if request['operation'] == 'remove' else 'resolved'}
        cur.execute(f'''INSERT INTO {schema}.capture_correction_outcomes(request_id,result)
            VALUES (%s,%s::jsonb)''', (request['request_id'], json.dumps(result)))
    except Exception:
        cur.execute('ROLLBACK TO SAVEPOINT capture_owner_correction')
        cur.execute('RELEASE SAVEPOINT capture_owner_correction')
        raise
    cur.execute('RELEASE SAVEPOINT capture_owner_correction')
    return result
