"""Bound one private polling invocation; never interpret timeout as SQL rollback."""
import argparse
import json
import math
import os
import subprocess
import sys

from lib.worker_process import ROOT,_stop_and_reap
from tools.engines.capture_transcription import _private

PRIVATE_ENV=('SUPABASE_DB_URL','SUPABASE_URL','SUPABASE_ANON_KEY','SUPABASE_STORAGE_READ_JWT')
DEADLINE_SECONDS=120


def _command(options):
    command=[sys.executable,'-m','tools.capture_private_worker']
    for name in ('state_directory','model_outbox','model_results','reference_outbox'):
        command.extend(['--'+name.replace('_','-'),os.fspath(options[name])])
    if options['retry']:command.append('--retry')
    return command


def run(*,state_directory,model_outbox,model_results,reference_outbox,retry=False,
        deadline=DEADLINE_SECONDS):
    _private('core')
    if os.environ.get('PERSONAL_OS_TEST_SOCKET'):
        raise ValueError('disposable environment cannot launch private service')
    if (type(retry) is not bool or type(deadline) not in (int,float)
        or not math.isfinite(deadline) or not 0<deadline<=DEADLINE_SECONDS):
        raise ValueError('invalid private service settings')
    options=dict(state_directory=state_directory,model_outbox=model_outbox,
                 model_results=model_results,reference_outbox=reference_outbox,retry=retry)
    env={key:os.environ[key] for key in PRIVATE_ENV if key in os.environ}
    env['PYTHONPATH']=str(ROOT)
    child=None
    try:
        child=subprocess.Popen(_command(options),cwd=ROOT,env=env,start_new_session=True,
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:code=child.wait(timeout=deadline)
        except subprocess.TimeoutExpired:
            _stop_and_reap(child)
            return {'status':'unconfirmed','timed_out':True}
        return {'status':'invocation_finished' if code==0 else 'unconfirmed','timed_out':False}
    finally:
        if child is not None and child.poll() is None:_stop_and_reap(child)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('state-directory','model-outbox','model-results','reference-outbox'):
        parser.add_argument('--'+name,required=True)
    parser.add_argument('--retry',action='store_true')
    args=parser.parse_args()
    try:result=run(**vars(args))
    except Exception:result={'status':'unconfirmed','error_type':'PrivateServiceUnavailable'}
    print(json.dumps(result))
    return 0 if result['status']=='invocation_finished' else 1


if __name__=='__main__':sys.exit(main())
