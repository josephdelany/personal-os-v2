#!/usr/bin/env python3
"""Private capture stages; stdout contains private data, never publish it in logs.

prepare accepts {request_id,capture_id,payload} on stdin and emits the exact model
request only after commit. consume accepts isolated dispatch's {request_id,result}.
fail records a correlated dispatch failure. readback/queue recover persisted work.
Media upload/Storage provisioning and a supervisor with separately scoped environments are required
before these stages form a deployed voice-to-atom path.
"""
import argparse
import json
import sys
from lib import db
from tools.ask_jobs import owner_context
from tools.engines import capture_transcription as engine


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    advance=commands.add_parser('advance')
    advance.add_argument('capture_id')
    advance.add_argument('--retry',action='store_true')
    advance.add_argument('--model-outbox')
    advance.add_argument('--reference-outbox')
    retire=commands.add_parser('retire-request')
    retire.add_argument('stage',choices=('transcribe','extract','reference'))
    retire.add_argument('directory')
    retire.add_argument('request_id')
    control=commands.add_parser('consume-control')
    control.add_argument('stage',choices=('transcribe','extract'))
    control.add_argument('request_directory')
    control.add_argument('result_directory')
    control.add_argument('request_id')
    commands.add_parser('prepare')
    media=commands.add_parser('prepare-media')
    media.add_argument('request_id')
    media.add_argument('capture_id')
    extraction=commands.add_parser('prepare-extraction')
    extraction.add_argument('request_id')
    extraction.add_argument('capture_id')
    commands.add_parser('consume')
    commands.add_parser('consume-extraction')
    model_reconcile=commands.add_parser('reconcile-model')
    model_reconcile.add_argument('stage',choices=('transcribe','extract'))
    model_reconcile.add_argument('request_id')
    reference=commands.add_parser('prepare-reference')
    reference.add_argument('request_id')
    reference.add_argument('capture_id')
    reference.add_argument('extraction_request_id')
    reference.add_argument('item_index',type=int)
    reference.add_argument('source',nargs='?',default='auto',choices=('auto','usda_foundation','usda_branded','off_search'))
    commands.add_parser('consume-reference')
    reference_reconcile=commands.add_parser('reconcile-reference')
    reference_reconcile.add_argument('request_id')
    resolve=commands.add_parser('resolve')
    resolve.add_argument('request_id')
    resolve.add_argument('capture_id')
    resolve.add_argument('extraction_request_id')
    reconcile=commands.add_parser('reconcile-media')
    reconcile.add_argument('capture_id')
    failed=commands.add_parser('fail')
    failed.add_argument('request_id')
    failed.add_argument('error_type')
    failed.add_argument('--provider-status',type=int)
    extraction_failed=commands.add_parser('fail-extraction')
    extraction_failed.add_argument('request_id')
    extraction_failed.add_argument('error_type')
    extraction_failed.add_argument('--provider-status',type=int)
    read=commands.add_parser('readback')
    read.add_argument('capture_id')
    queue=commands.add_parser('queue')
    queue.add_argument('--limit',type=int,default=100)
    queue.add_argument('--cursor',type=json.loads)
    args=parser.parse_args(argv)
    if args.command=='advance' and bool(args.model_outbox)!=bool(args.reference_outbox):
        parser.error('both role outboxes are required together')
    conn=None
    try:
        engine._private('core')
        conn=db.connect()
        cur=conn.cursor()
        owner_context(cur)
        if args.command in {'prepare','consume','consume-extraction','consume-reference'}:
            message=json.load(sys.stdin)
            required=({'request_id','capture_id','payload'} if args.command=='prepare' else {'request_id','result'})
            if not isinstance(message,dict) or set(message)!=required:
                raise ValueError('invalid correlated message')
            if args.command=='prepare':
                result=engine.prepare(cur,**message)
            elif args.command=='consume-extraction':
                from tools.engines import capture_extraction
                result=capture_extraction.consume(cur,request_id=message['request_id'],response=message['result'])
            elif args.command=='consume-reference':
                from tools.engines import capture_reference
                result=capture_reference.consume(cur,request_id=message['request_id'],response=message['result'])
            else:
                result=engine.consume(cur,request_id=message['request_id'],response=message['result'])
        elif args.command=='consume-control':
            from lib import capture_mailbox
            from tools.engines.capture_mailbox import consume_control
            queued_request=capture_mailbox.read(args.request_directory,args.request_id)
            control=capture_mailbox.result(args.result_directory,queued_request)
            result=consume_control(cur,queued_request,control,stage=args.stage)
        elif args.command=='retire-request':
            from lib import capture_mailbox
            from tools.engines.capture_mailbox import consumed
            queued_request=capture_mailbox.read(args.directory,args.request_id)
            ready=consumed(cur,queued_request,stage=args.stage)
            result={'status':'retired' if ready else 'awaiting_consumption','request_id':args.request_id}
        elif args.command=='advance':
            from tools.engines import capture_runtime
            result=capture_runtime.advance(cur,capture_id=args.capture_id,retry=args.retry)
        elif args.command=='prepare-media':
            result=engine.prepare_media(cur,request_id=args.request_id,capture_id=args.capture_id)
        elif args.command=='prepare-extraction':
            from tools.engines import capture_extraction
            result=capture_extraction.prepare(cur,request_id=args.request_id,capture_id=args.capture_id)
        elif args.command=='prepare-reference':
            from tools.engines import capture_reference
            result=capture_reference.prepare(cur,request_id=args.request_id,capture_id=args.capture_id,
                extraction_request_id=args.extraction_request_id,item_index=args.item_index,source=args.source)
        elif args.command=='reconcile-model':
            from tools.engines import capture_model_recovery
            result=capture_model_recovery.reconcile(cur,request_id=args.request_id,stage=args.stage)
        elif args.command=='reconcile-reference':
            from tools.engines import capture_reference
            result=capture_reference.consume(cur,request_id=args.request_id,response=None)
        elif args.command=='resolve':
            from tools.engines import capture_resolution
            result=capture_resolution.resolve(cur,request_id=args.request_id,capture_id=args.capture_id,
                                              extraction_request_id=args.extraction_request_id)
        elif args.command=='reconcile-media':
            result=engine.reconcile_media(cur,capture_id=args.capture_id)
        elif args.command=='fail':
            result=engine.fail(cur,request_id=args.request_id,error_type=args.error_type,
                               provider_status=args.provider_status)
        elif args.command=='fail-extraction':
            from tools.engines import capture_extraction
            result=capture_extraction.fail(cur,request_id=args.request_id,error_type=args.error_type,
                                          provider_status=args.provider_status)
        elif args.command=='readback':
            result=engine.readback(cur,capture_id=args.capture_id)
        else:
            result=engine.work_queue(cur,limit=args.limit,cursor=args.cursor)
        conn.commit()
        if args.command=='retire-request' and ready:
            capture_mailbox.retire(args.directory,queued_request)
        if args.command=='advance' and args.model_outbox and result.get('status')=='dispatch':
            from lib import capture_mailbox
            directory={'model':args.model_outbox,'reference':args.reference_outbox}[result['worker']]
            capture_mailbox.publish(directory,result['request'])
            result={'status':'queued','worker':result['worker'],'stage':result['stage'],
                    'request_id':result['request']['request_id']}
        print(json.dumps(result,default=str))
        return 0
    except Exception as error:
        if conn is not None:
            try: conn.rollback()
            except Exception: pass
        print(json.dumps({'status':'error','error_type':type(error).__name__}),file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass


if __name__=='__main__':
    sys.exit(main())
