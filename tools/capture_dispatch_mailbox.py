"""Run one prepared mailbox request under exactly one outbound role's identity.

The private owner retains the request until its SQL consumption commits. Repeated
delivery is safe through the dispatcher's reservation identity, not a file claim.
Service-manager invocations must provision separate OS identities and secrets.
"""
import argparse
import json
import os
import sys

from lib import capture_mailbox as mailbox


def dispatch(role,request_directory,result_directory,request_id):
    if role=='model':
        from tools.model_worker import run
    elif role=='reference':
        from tools.reference_worker import run
    else:raise ValueError('unknown outbound role')
    request=mailbox.read(request_directory,request_id)
    try:previous=mailbox.result(result_directory,request)
    except FileNotFoundError:previous=None
    if previous is not None and previous.get('status') in ('settled','deferred_budget'):
        return previous
    result=run(request)
    mailbox.store_result(result_directory,request,result)
    return result


def poll(role,request_directory,result_directory,state_directory,*,limit=1):
    """Bounded round-robin scan; persist position before each potentially lost call.

    A killed scheduler can retry that request on the next wrap. SQL reservation
    identity prevents duplicate provider execution. State has one owner per role.
    """
    if role not in ('model','reference') or type(limit) is not int or not 1<=limit<=10:
        raise ValueError('invalid worker poll')
    directories=(request_directory,result_directory,state_directory)
    if any(os.path.samefile(left,right) for index,left in enumerate(directories)
           for right in directories[index+1:]):
        raise ValueError('separate request, result and state directories required')
    binding={'role':role,'requests':os.path.abspath(request_directory),
             'results':os.path.abspath(result_directory)}
    with mailbox._directory(state_directory,write=True) as state:
        try:saved,_=mailbox._read(state,'cursor.json')
        except FileNotFoundError:saved={'binding':binding,'after':None}
        if not isinstance(saved,dict) or set(saved)!={'binding','after'} or saved['binding']!=binding:
            raise ValueError('worker cursor configuration mismatch')
        after=saved['after']
        if after is not None:mailbox._name(after)
        cleanup={'status':'idle'}
        try:
            try:retired,_=mailbox._read(state,'retirement.json')
            except FileNotFoundError:retired={'binding':binding,'after':None}
            if not isinstance(retired,dict) or set(retired)!={'binding','after'} or retired['binding']!=binding:
                raise ValueError('control retirement cursor mismatch')
            previous=retired['after']
            if previous is not None:mailbox._name(previous)
            controls=mailbox.pending(result_directory)
            if controls:
                identity=next((identity for identity in controls if previous is None or identity>previous),controls[0])
                mailbox._write(state,'retirement.json',{'binding':binding,'after':identity},replace=True)
                removed=mailbox.retire_control(request_directory,result_directory,identity)
                cleanup={'status':'retired' if removed else 'retained','request_id':identity}
        except Exception:
            cleanup={'status':'error','error_type':'ControlRetirementUnavailable'}
        identities=mailbox.pending(request_directory)
        ordered=identities if after is None else (
            [identity for identity in identities if identity>after]+
            [identity for identity in identities if identity<=after])
        results=[]
        for identity in ordered[:limit]:
            mailbox._write(state,'cursor.json',{'binding':binding,'after':identity},replace=True)
            try:result=dispatch(role,request_directory,result_directory,identity)
            except FileNotFoundError:
                result={'request_id':identity,'status':'unavailable'}
            except Exception:
                result={'request_id':identity,'status':'error','error_type':'MailboxDispatchUnavailable'}
            results.append(result)
        ok=cleanup['status']!='error' and all(item.get('status') in ('settled','deferred_budget') for item in results)
        return {'status':'polled' if ok else 'incomplete','items':results,'cleanup':cleanup}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('role',choices=('model','reference'))
    parser.add_argument('request_directory')
    parser.add_argument('result_directory')
    parser.add_argument('request_id',nargs='?')
    parser.add_argument('--state-directory')
    parser.add_argument('--limit',type=int,default=1)
    args=parser.parse_args()
    try:
        if args.state_directory:
            if args.request_id:raise ValueError('poll does not accept request identity')
            result=poll(args.role,args.request_directory,args.result_directory,args.state_directory,limit=args.limit)
        else:
            if not args.request_id:raise ValueError('request identity or state directory required')
            result=dispatch(args.role,args.request_directory,args.result_directory,args.request_id)
        print(json.dumps(result))
        return 0 if result['status'] in ('settled','deferred_budget','polled') else 1
    except BlockingIOError:
        print(json.dumps({'status':'busy','error_type':'MailboxWriterActive'}),file=sys.stderr)
        return 1
    except Exception:
        print(json.dumps({'status':'error','error_type':'MailboxDispatchUnavailable'}),file=sys.stderr)
        return 1


if __name__=='__main__':sys.exit(main())
