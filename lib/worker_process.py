"""Shared bounded process ownership; no DB credentials or network operations."""
import contextlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[1]

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


def run(request_id,body,*,command,env,deadline,reconcile,outcomes,
        ack_env,allow_budget=False):
    if type(deadline) not in (int,float) or not math.isfinite(deadline) or not 0<deadline<=90:
        raise ValueError('invalid worker deadline')
    read_fd,write_fd=os.pipe()
    child=None
    stderr=b''
    timed_out=False
    try:
        env=dict(env)
        env['PYTHONPATH']=str(ROOT)
        env[ack_env]=str(write_fd)
        child=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.PIPE,
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
            if allow_budget and not timed_out and child.returncode==1 and isinstance(error,dict) and error.get('error_type')=='BudgetExceeded':
                return {'request_id':request_id,'status':'deferred_budget'}
            return {'request_id':request_id,'status':'unconfirmed'}
        try: outcome=reconcile(request_id)
        except Exception:
            return {'request_id':request_id,'status':'settlement_unconfirmed'}
        if outcome not in outcomes:
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
