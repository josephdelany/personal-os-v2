#!/usr/bin/env python3
"""One bounded model worker, with model credentials only. No private-row access.

stdin is a prepared request; stdout is control metadata, never provider content.
The service manager supplies this worker's own credentials. It must not load the
private or reference worker's secrets into this process.
"""
import json
import math
import os
from pathlib import Path
import sys
import uuid
from lib import db, worker_process as process
from lib.model_contract import request_bytes

ROOT = Path(__file__).resolve().parents[1]
DEADLINE_SECONDS = 90
MAX_REQUEST_BYTES = 72 * 1024 * 1024
FOREIGN_CREDENTIALS = ('SUPABASE_DB_URL','SUPABASE_SERVICE_ROLE_KEY',
    'SUPABASE_STORAGE_READ_JWT','REFERENCE_EGRESS_DB_URL','USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY')
MODEL_ENV = ('MODEL_EGRESS_DB_URL','CF_API_TOKEN','CF_ACCOUNT_ID')


def _command():
    return [sys.executable,'-m','tools.model_egress']


def _reconcile(request_id):
    conn=None
    with process._settlement_deadline():
        try:
            conn=db.connect_model_egress()
            cur=conn.cursor()
            cur.execute('SELECT session_user,current_user')
            if tuple(cur.fetchone())!=('model_egress','model_egress'):
                raise RuntimeError('dedicated model identity required')
            cur.execute('SELECT public.reconcile_stopped_model_call(%s)',(request_id,))
            outcome=cur.fetchone()[0]
            conn.commit()
            return outcome
        finally:
            if conn is not None:
                try: conn.close()
                except Exception: pass


def run(request, *, deadline=DEADLINE_SECONDS):
    if os.environ.get('PERSONAL_OS_TEST_SOCKET'):
        raise ValueError('disposable environment cannot launch model provider worker')
    if any(os.environ.get(key) for key in FOREIGN_CREDENTIALS):
        raise ValueError('foreign credentials present')
    if type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline<=DEADLINE_SECONDS:
        raise ValueError('invalid deadline')
    required={'request_id','model_id','call_kind','payload','estimated_neurons'}
    if not isinstance(request,dict) or not required<=request.keys() or request.keys()-required-{'capture_id'}:
        raise ValueError('invalid prepared request')
    request_id=str(uuid.UUID(str(request['request_id'])))
    if request_id!=request['request_id']: raise ValueError('canonical request identity required')
    body=request_bytes(request)
    if len(body)>MAX_REQUEST_BYTES: raise ValueError('prepared request too large')
    return process.run(request_id,body,command=_command(),
        env={key:os.environ[key] for key in MODEL_ENV if key in os.environ},
        deadline=deadline,reconcile=_reconcile,outcomes=('ok','error'),
        ack_env='PERSONAL_OS_MODEL_RESERVATION_FD',allow_budget=True)


def main():
    try:
        body=sys.stdin.buffer.read(MAX_REQUEST_BYTES+1)
        if len(body)>MAX_REQUEST_BYTES: raise ValueError('oversized request')
        result=run(json.loads(body))
        print(json.dumps(result))
        return 0 if result['status'] in ('settled','deferred_budget') else 1
    except Exception:
        print(json.dumps({'status':'error','error_type':'ModelWorkerUnavailable'}),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
