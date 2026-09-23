"""One private capture pass: saved control -> SQL progression -> durable handoff.

The caller supplies only private credentials. This process never starts providers.
"""
import argparse
import datetime as dt
import json
import os
import sys

from lib import capture_mailbox as mailbox,db
from tools.ask_jobs import owner_context
from tools.engines import capture_transcription, capture_runtime
from tools.engines.capture_mailbox import consumed,consume_control


def advance(conn,capture_id,*,model_outbox,model_results,reference_outbox,retry=False,
            schema='core',ops='ops',config='config'):
    schema=capture_transcription._private(schema)
    cur=conn.cursor()
    owner_context(cur)
    capture_transcription._lock(cur,capture_id)
    queued=[]
    for stage,table,directory in (
        ('transcribe','capture_transcription',model_outbox),
        ('extract','capture_extraction',model_outbox),
        ('reference','capture_reference',reference_outbox)):
        cur.execute(f'SELECT request_id FROM {schema}.{table}_attempts WHERE capture_id=%s',
                    (capture_id,))
        for row in cur.fetchall():
            try:request=mailbox.read(directory,str(row[0]))
            except FileNotFoundError:continue
            if stage!='reference' and not consumed(cur,request,stage=stage,schema=schema):
                try:control=mailbox.result(model_results,request)
                except FileNotFoundError:control=None
                if control is not None:
                    consume_control(cur,request,control,stage=stage,schema=schema)
            queued.append((directory,request,stage))
    result=capture_runtime.advance(cur,capture_id=capture_id,retry=retry,
                                   schema=schema,ops=ops,config=config)
    retired=[(directory,request) for directory,request,stage in queued
             if consumed(cur,request,stage=stage,schema=schema)]
    conn.commit()
    # A filesystem error after this point leaves SQL authoritative; the next
    # invocation reconstructs the same preparation or rechecks saved outcomes.
    if result.get('status')=='dispatch':
        directory={'model':model_outbox,'reference':reference_outbox}[result['worker']]
        mailbox.publish(directory,result['request'])
        result={'status':'queued','worker':result['worker'],'stage':result['stage'],
                'request_id':result['request']['request_id']}
    for directory,request in retired:
        try:mailbox.retire(directory,request)
        except FileNotFoundError:pass
    return result


def _retire_saved(conn,state,binding,*,model_outbox,reference_outbox,schema):
    """Check one mailbox entry independently of active capture status."""
    name='retirement.json'
    try:saved,_=mailbox._read(state,name)
    except FileNotFoundError:saved={'binding':binding,'after':None}
    if not isinstance(saved,dict) or set(saved)!={'binding','after'} or saved['binding']!=binding:
        raise ValueError('retirement cursor configuration mismatch')
    after=saved['after']
    if after is not None:
        role,identity=after.split(':',1)
        if role not in ('model','reference'):raise ValueError('invalid retirement cursor')
        mailbox._name(identity)
    directories={'model':model_outbox,'reference':reference_outbox}
    entries=sorted(role+':'+identity for role,directory in directories.items()
                   for identity in mailbox.pending(directory))
    if not entries:return {'status':'idle'}
    key=next((key for key in entries if after is None or key>after),entries[0])
    mailbox._write(state,name,{'binding':binding,'after':key},replace=True)
    role,identity=key.split(':',1);directory=directories[role]
    try:request=mailbox.read(directory,identity)
    except FileNotFoundError:return {'status':'absent'}
    stage='reference' if role=='reference' else request.get('call_kind')
    cur=conn.cursor();owner_context(cur)
    ready=consumed(cur,request,stage=stage,schema=schema)
    conn.commit()
    if not ready:return {'status':'awaiting_consumption'}
    try:mailbox.retire(directory,request)
    except FileNotFoundError:pass
    return {'status':'retired','request_id':identity}


def poll(conn,*,state_directory,model_outbox,model_results,reference_outbox,retry=False,
         schema='core',ops='ops',config='config'):
    """Advance one capture per tick; the nightly lane scans at most once per UTC day."""
    schema=capture_transcription._private(schema)
    if type(retry) is not bool:raise ValueError('invalid retry flag')
    paths={'model_outbox':model_outbox,'model_results':model_results,'reference_outbox':reference_outbox}
    if any(os.path.samefile(state_directory,path) for path in paths.values()):
        raise ValueError('separate private state directory required')
    binding={key:os.path.abspath(value) for key,value in paths.items()}
    binding.update(schema=schema,ops=ops,config=config)
    name='nightly.json' if retry else 'cursor.json'
    with mailbox._directory(state_directory,write=True) as state:
        try:saved,_=mailbox._read(state,name)
        except FileNotFoundError:
            saved={'binding':binding,'cursor':None,'completed_day':None,'failed':False}
        if (not isinstance(saved,dict) or set(saved)!={'binding','cursor','completed_day','failed'}
            or saved['binding']!=binding or type(saved['failed']) is not bool):
            raise ValueError('private cursor configuration mismatch')
        cur=conn.cursor();owner_context(cur)
        cur.execute("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date")
        today=cur.fetchone()[0].isoformat()
        try:
            cleanup=_retire_saved(conn,state,binding,model_outbox=model_outbox,
                reference_outbox=reference_outbox,schema=schema)
        except Exception:
            conn.rollback()
            cleanup={'status':'error','error_type':'MailboxRetirementUnavailable'}
        cleanup_failed=cleanup['status']=='error'
        if saved['completed_day'] is not None:
            dt.date.fromisoformat(saved['completed_day'])
        if retry and saved['completed_day'] is not None and saved['completed_day']>=today:
            conn.commit()
            return {'status':'incomplete' if saved['failed'] or cleanup_failed else 'already_scanned',
                    'retry':True,'cleanup':cleanup}
        if saved['cursor'] is None:saved['failed']=False
        owner_context(cur)
        queue=capture_transcription.work_queue(cur,limit=1,cursor=saved['cursor'],schema=schema)
        conn.commit()
        # Persist the next position before potentially stalled capture work.
        # Until the final write confirms a return, this sweep is incomplete.
        # On the last page the daily gate is also durable, preventing a killed
        # nightly invocation from replaying earlier captures that same day.
        failed=saved['failed'] or cleanup_failed
        saved['cursor']=queue['next_cursor']
        complete=queue['next_cursor'] is None
        if complete:saved['completed_day']=today
        saved['failed']=True
        mailbox._write(state,name,saved,replace=True)
        result={'status':'idle'}
        for item in queue['items']:
            try:
                result=advance(conn,item['capture_id'],**paths,retry=retry,schema=schema,ops=ops,config=config)
            except Exception:
                conn.rollback()
                failed=True
                result={'status':'error','error_type':'PrivateCaptureWorkerUnavailable'}
        saved['failed']=failed
        mailbox._write(state,name,saved,replace=True)
        return {'status':'incomplete' if failed else 'polled','sweep_complete':complete,
                'retry':retry,'result':result,'cleanup':cleanup}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_id',nargs='?')
    parser.add_argument('--state-directory')
    parser.add_argument('--model-outbox',required=True)
    parser.add_argument('--model-results',required=True)
    parser.add_argument('--reference-outbox',required=True)
    parser.add_argument('--retry',action='store_true')
    args=parser.parse_args()
    conn=None
    try:
        capture_transcription._private('core')
        conn=db.connect()
        values=vars(args).copy()
        capture_id=values.pop('capture_id');state=values.pop('state_directory')
        if state:
            if capture_id:raise ValueError('poll does not accept capture identity')
            result=poll(conn,state_directory=state,**values)
        else:
            if not capture_id:raise ValueError('capture identity or state directory required')
            result=advance(conn,capture_id,**values)
        print(json.dumps(result,default=str))
        return 1 if result['status']=='incomplete' else 0
    except BlockingIOError:
        if conn is not None:
            try:conn.rollback()
            except Exception:pass
        print(json.dumps({'status':'busy','error_type':'MailboxWriterActive'}),file=sys.stderr)
        return 1
    except Exception:
        if conn is not None:
            try:conn.rollback()
            except Exception:pass
        print(json.dumps({'status':'error','error_type':'PrivateCaptureWorkerUnavailable'}),file=sys.stderr)
        return 1
    finally:
        if conn is not None:conn.close()


if __name__=='__main__':sys.exit(main())
