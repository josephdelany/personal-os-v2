"""Private Ask stages; caller commits before exporting a request or displaying a result."""
import hashlib
import json
import os
import re
import uuid
from lib.model_contract import request_bytes
from tools import ask
from tools.engines import ask_planner as planner


def private_process():
    if any(os.environ.get(key) for key in ('CF_API_TOKEN', 'MODEL_EGRESS_DB_URL')):
        raise RuntimeError('provider capability present in private Ask process')


def _schema(value):
    if not re.fullmatch('[a-z_][a-z0-9_]*', value):
        raise ValueError('invalid schema')
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _write_snapshot(cur):
    cur.execute("SELECT current_setting('transaction_isolation')")
    if cur.fetchone()[0] != 'read committed':
        raise ValueError('READ COMMITTED required for Ask job transitions')


def _request(request_id, payload, model_id, call_kind, estimated):
    return {'request_id': str(request_id), 'model_id': model_id,
            'call_kind': call_kind, 'estimated_neurons': float(estimated),
            'payload': payload}


def prepare(cur, *, job_id, question, as_of, schema='core', config='config'):
    private_process()
    schema = _schema(schema)
    if not question or as_of is None:
        raise ValueError('question and explicit as_of required')
    job_id = str(uuid.UUID(str(job_id)))
    _write_snapshot(cur)
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,78))', (job_id,))
    cur.execute(f'SELECT question,as_of FROM {schema}.ask_planning_jobs WHERE job_id=%s', (job_id,))
    old = cur.fetchone()
    if old:
        if old[0] != question or old[1] != as_of:
            raise ValueError('job identity reused with different question or date')
        return readback(cur, job_id=job_id, schema=schema)
    cur.execute('SELECT clock_timestamp()')
    known_at = cur.fetchone()[0]
    fallback = _answer(cur, question, as_of, known_at)
    operations, metrics = planner.registry_options(cur, schema, _schema(config))
    cur.execute(f'''INSERT INTO {schema}.ask_planning_jobs
        (job_id,question,as_of,known_at,operations,metrics,fallback) VALUES (%s,%s,%s,%s,%s,%s,%s)''',
        (job_id,question,as_of,known_at,_json(operations),_json(metrics),_json(fallback)))
    if not ask._grammar_missed(fallback):
        return {'state': 'complete', 'provenance': 'deterministic', 'answer': fallback}
    return _attempt(cur, schema, job_id, 1, planner.build_prompt(question, operations, metrics))


def _answer(cur, question, as_of, known_at):
    cur.execute('SELECT public.ask(%s,%s,%s)', (question,as_of,known_at))
    return cur.fetchone()[0]


def _attempt(cur, schema, job_id, number, payload):
    request_id = str(uuid.uuid4())
    cur.execute(f'''INSERT INTO {schema}.ask_planning_attempts
        (request_id,job_id,attempt_no,payload,model_id,call_kind,estimated_neurons)
        VALUES (%s,%s,%s,%s,%s,%s,%s)''',
        (request_id,job_id,number,_json(payload),planner.MODEL_ID,'plan',planner.ESTIMATED_NEURONS_PER_PLAN))
    return {'state': 'needs_model', 'request': _request(request_id, payload, planner.MODEL_ID,'plan',planner.ESTIMATED_NEURONS_PER_PLAN)}


def readback(cur, *, job_id, schema='core'):
    private_process()
    schema = _schema(schema)
    cur.execute(f'''SELECT a.request_id,a.payload,o.result,a.model_id,a.call_kind,a.estimated_neurons FROM {schema}.ask_planning_attempts a
        LEFT JOIN {schema}.ask_planning_outcomes o USING(request_id)
        WHERE a.job_id=%s ORDER BY a.attempt_no DESC LIMIT 1''', (job_id,))
    row = cur.fetchone()
    if row:
        return row[2] or {'state': 'needs_model', 'request': _request(row[0],row[1],row[3],row[4],row[5])}
    cur.execute(f'SELECT fallback FROM {schema}.ask_planning_jobs WHERE job_id=%s', (job_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('unknown Ask job')
    return {'state': 'complete', 'provenance': 'deterministic', 'answer': row[0]}


def consume(cur, *, request_id, response, schema='core'):
    private_process()
    schema = _schema(schema)
    request_id = str(uuid.UUID(str(request_id)))
    _write_snapshot(cur)
    digest = hashlib.sha256(_json(response).encode()).hexdigest()
    cur.execute(f'SELECT job_id FROM {schema}.ask_planning_attempts WHERE request_id=%s', (request_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('unknown model request')
    job_id = str(row[0])
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,78))', (job_id,))
    cur.execute(f'SELECT response_sha256,result FROM {schema}.ask_planning_outcomes WHERE request_id=%s', (request_id,))
    old = cur.fetchone()
    if old:
        if old[0] != digest:
            raise ValueError('response identity reused with different content')
        return old[1]
    cur.execute(f'''SELECT j.question,j.as_of,j.known_at,j.operations,j.metrics,j.fallback,a.attempt_no,a.payload,a.model_id,a.call_kind,a.estimated_neurons
        FROM {schema}.ask_planning_attempts a JOIN {schema}.ask_planning_jobs j USING(job_id)
        WHERE request_id=%s''', (request_id,))
    question, as_of, known_at, operations, metrics, fallback, number, payload, model_id, call_kind, estimated = cur.fetchone()
    # Only a settled reservation for this exact prepared payload can produce a plan.
    # Match dispatch's serialized bytes, not JSONB's object ordering.
    cur.execute(f'''SELECT n.outcome,n.model_id,n.call_kind,r.payload_sha256,
                          n.estimated_neurons,n.capture_id,s.response_sha256
        FROM {schema}.model_call_reservations r JOIN {schema}.neuron_ledger n USING(ledger_id)
        JOIN {schema}.model_call_results s USING(request_id)
        WHERE r.request_id=%s''', (request_id,))
    receipt = cur.fetchone()
    expected = hashlib.sha256(request_bytes(payload)).hexdigest()
    if (receipt is None or receipt[0] != 'ok'
        or tuple(receipt[1:3]) != (model_id,call_kind) or receipt[3] != expected
        or receipt[4] != estimated or receipt[5] is not None
        or receipt[6] != digest):
        raise ValueError('matching settled model reservation required')
    try:
        clean = planner.validate(planner._extract_plan(response), question, operations, metrics)
        canonical = planner.to_question(clean, metrics)
    except (planner.PlanRefused, TypeError, ValueError) as error:
        reason = error.reason.split(':',1)[0] if isinstance(error,planner.PlanRefused) else 'malformed_plan_fields'
        nearest = error.nearest if isinstance(error,planner.PlanRefused) else []
        if number < planner.MAX_ITERATIONS:
            payload = dict(payload)
            payload['messages'] = payload['messages'] + [{
                'role':'user','content':f'That plan was rejected: {reason}. Reply using only the listed values.'}]
            result = _attempt(cur,schema,job_id,number+1,payload)
        else:
            result = {'state':'complete','provenance':'planner_refused','answer':{
                'refusal':'I cannot compute that.','nearest':nearest or sorted(set(operations)-planner.NOT_PLANNABLE),
                'planner':{'used':False,'reason':'iteration_cap_reached','attempts':number}}}
    else:
        envelope = _answer(cur, canonical, as_of, known_at)
        envelope['planner'] = {'used':True,'attempts':number,'plan':clean,
            'asked_as':canonical,'original_question':question}
        result = {'state':'complete','provenance':'planned','answer':envelope}
    cur.execute(f'''INSERT INTO {schema}.ask_planning_outcomes(request_id,response_sha256,result)
        VALUES (%s,%s,%s)''', (request_id,digest,_json(result)))
    return result


def fail(cur, *, request_id, error_type, schema='core'):
    """Trusted private coordinator ends an unavailable-model attempt with saved fallback."""
    private_process()
    schema = _schema(schema)
    request_id = str(uuid.UUID(str(request_id)))
    if error_type not in {'BudgetExceeded','DispatchRefused','DispatchUncertain','PayloadRefused','DispatcherUnavailable','RuntimeError'}:
        raise ValueError('unsupported dispatch failure')
    _write_snapshot(cur)
    cur.execute(f'SELECT job_id FROM {schema}.ask_planning_attempts WHERE request_id=%s', (request_id,))
    row = cur.fetchone()
    if row is None:
        raise ValueError('unknown model request')
    job_id = str(row[0])
    cur.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,78))', (job_id,))
    digest = hashlib.sha256(_json({'dispatch_error':error_type}).encode()).hexdigest()
    cur.execute(f'SELECT response_sha256,result FROM {schema}.ask_planning_outcomes WHERE request_id=%s', (request_id,))
    old = cur.fetchone()
    if old:
        if old[0] != digest:
            raise ValueError('attempt already has a different outcome')
        return old[1]
    cur.execute(f'SELECT fallback FROM {schema}.ask_planning_jobs WHERE job_id=%s', (job_id,))
    fallback = dict(cur.fetchone()[0])
    fallback['planner'] = {'used':False,'reason':error_type}
    result = {'state':'complete','provenance':'deterministic_after_planner_refused','answer':fallback}
    cur.execute(f'INSERT INTO {schema}.ask_planning_outcomes(request_id,response_sha256,result) VALUES (%s,%s,%s)',
                (request_id,digest,_json(result)))
    return result
