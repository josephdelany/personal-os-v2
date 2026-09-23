#!/usr/bin/env python3
"""Bounded reference-only worker. Prepared request in; control metadata out."""
import json
import os
import sys
from lib import db, worker_process as process
from tools.engines import reference_dispatch

REFERENCE_ENV=('REFERENCE_EGRESS_DB_URL','USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY',
               'PERSONAL_OS_CONTACT_EMAIL','OFF_CONTACT_EMAIL')


def _command():
    return [sys.executable,'-m','tools.reference_egress']


def _reconcile(request_id):
    conn=None
    with process._settlement_deadline():
        try:
            conn=db.connect_reference_egress()
            cur=conn.cursor()
            cur.execute('SELECT session_user,current_user')
            if tuple(cur.fetchone())!=('reference_egress','reference_egress'):
                raise RuntimeError('dedicated reference identity required')
            cur.execute('SELECT public.reconcile_stopped_reference_call(%s)',(request_id,))
            outcome=cur.fetchone()[0]
            conn.commit()
            return outcome
        finally:
            if conn is not None:
                try: conn.close()
                except Exception: pass


def run(request,*,deadline=90):
    if os.environ.get('PERSONAL_OS_TEST_SOCKET'):
        raise ValueError('disposable environment cannot launch reference provider worker')
    if any(os.environ.get(key) for key in reference_dispatch.PRIVATE_CREDENTIALS):
        raise ValueError('private or model credentials present')
    body=reference_dispatch.validate(request)
    return process.run(request['request_id'],body,command=_command(),
        env={key:os.environ[key] for key in REFERENCE_ENV if key in os.environ},
        deadline=deadline,reconcile=_reconcile,outcomes=('settled','uncertain'),
        ack_env='PERSONAL_OS_REFERENCE_RESERVATION_FD')


def main():
    try:
        body=sys.stdin.buffer.read(4097)
        if len(body)>4096: raise ValueError('oversized reference request')
        result=run(json.loads(body))
        print(json.dumps(result))
        return 0 if result['status']=='settled' else 1
    except Exception:
        print(json.dumps({'status':'error','error_type':'ReferenceWorkerUnavailable'}),file=sys.stderr)
        return 1


if __name__=='__main__':
    sys.exit(main())
