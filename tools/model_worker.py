#!/usr/bin/env python3
"""One bounded model worker, with model credentials only. No private-row access.

stdin is a prepared request; stdout is control metadata, never provider content.
The service manager supplies this worker's own credentials. It must not load the
private or reference worker's secrets into this process.
"""
import contextlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid
from lib import db
from lib.model_contract import request_bytes

ROOT = Path(__file__).resolve().parents[1]
DEADLINE_SECONDS = 90
MAX_REQUEST_BYTES = 72 * 1024 * 1024
FOREIGN_CREDENTIALS = ('SUPABASE_DB_URL','SUPABASE_SERVICE_ROLE_KEY',
    'SUPABASE_STORAGE_READ_JWT','REFERENCE_EGRESS_DB_URL','USDA_FDC_API_KEY','PERSONAL_OS_USDA_API_KEY')
MODEL_ENV = ('MODEL_EGRESS_DB_URL','CF_API_TOKEN','CF_ACCOUNT_ID')


def _command():
    return [sys.executable,'-m','tools.model_egress']


def _stop_and_reap(child):
    # Kill the new group before reaping its leader so the PID cannot be reused
    # between wait() and killpg(). No provider cleanup may outlive the deadline.
    try: os.killpg(child.pid,signal.SIGKILL)
    except ProcessLookupError: pass
    child.wait()


@contextlib.contextmanager
def _settlement_deadline():
    if threading.current_thread() is not threading.main_thread() or signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):
        raise RuntimeError('exclusive main-thread deadline required')
    previous=signal.getsignal(signal.SIGALRM)
    def expired(*args): raise TimeoutError('settlement deadline')
    signal.signal(signal.SIGALRM,expired)
    try:
        signal.setitimer(signal.ITIMER_REAL,10)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        signal.signal(signal.SIGALRM,previous)


def _reconcile(request_id):
    conn=None
    with _settlement_deadline():
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
    read_fd,write_fd=os.pipe()
    child=None
    stderr=b''
    timed_out=False
    try:
        env={key:os.environ[key] for key in MODEL_ENV if key in os.environ}
        env['PYTHONPATH']=str(ROOT)
        env['PERSONAL_OS_MODEL_RESERVATION_FD']=str(write_fd)
        child=subprocess.Popen(_command(),cwd=ROOT,env=env,stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,pass_fds=(write_fd,),start_new_session=True)
        os.close(write_fd);write_fd=None
        try:
            _,stderr=child.communicate(body,timeout=deadline)
        except subprocess.TimeoutExpired:
            timed_out=True
            _stop_and_reap(child)
            # No post-timeout read waits for EOF from inherited pipe handles.
            stderr=b''
        finally:
            # Reconciliation below must never precede proof of child termination.
            if child.poll() is None: _stop_and_reap(child)
        os.set_blocking(read_fd,False)
        try: acknowledgement=os.read(read_fd,4096)
        except BlockingIOError: acknowledgement=b''
        try: owned=json.loads(acknowledgement)=={'request_id':request_id,'reserved':True}
        except (ValueError,UnicodeError): owned=False
        if not owned:
            # Budget refusal is safe to relay; no reservation was ever issued.
            # All other unowned outcomes remain ambiguous, including duplicates.
            try: error=json.loads(stderr)
            except (ValueError,UnicodeError): error={}
            if not timed_out and child.returncode==1 and error.get('error_type')=='BudgetExceeded':
                return {'request_id':request_id,'status':'deferred_budget'}
            return {'request_id':request_id,'status':'unconfirmed'}
        try: outcome=_reconcile(request_id)
        except Exception:
            return {'request_id':request_id,'status':'settlement_unconfirmed'}
        if outcome not in ('ok','error'):
            return {'request_id':request_id,'status':'settlement_unconfirmed'}
        return {'request_id':request_id,'status':'settled','outcome':outcome,'timed_out':timed_out}
    finally:
        if child is not None and child.poll() is None: _stop_and_reap(child)
        if child is not None:
            for stream in (child.stdin,child.stderr):
                if stream is not None:
                    try: stream.close()
                    except OSError: pass
        os.close(read_fd)
        if write_fd is not None: os.close(write_fd)


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
