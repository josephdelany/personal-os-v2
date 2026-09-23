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
    commands.add_parser('prepare')
    media=commands.add_parser('prepare-media')
    media.add_argument('request_id')
    media.add_argument('capture_id')
    commands.add_parser('consume')
    reconcile=commands.add_parser('reconcile-media')
    reconcile.add_argument('capture_id')
    failed=commands.add_parser('fail')
    failed.add_argument('request_id')
    failed.add_argument('error_type')
    failed.add_argument('--provider-status',type=int)
    read=commands.add_parser('readback')
    read.add_argument('capture_id')
    queue=commands.add_parser('queue')
    queue.add_argument('--limit',type=int,default=100)
    queue.add_argument('--cursor',type=json.loads)
    args=parser.parse_args(argv)
    conn=None
    try:
        engine._private('core')
        conn=db.connect()
        cur=conn.cursor()
        owner_context(cur)
        if args.command in {'prepare','consume'}:
            message=json.load(sys.stdin)
            required=({'request_id','capture_id','payload'} if args.command=='prepare' else {'request_id','result'})
            if not isinstance(message,dict) or set(message)!=required:
                raise ValueError('invalid correlated message')
            if args.command=='prepare':
                result=engine.prepare(cur,**message)
            else:
                result=engine.consume(cur,request_id=message['request_id'],response=message['result'])
        elif args.command=='prepare-media':
            result=engine.prepare_media(cur,request_id=args.request_id,capture_id=args.capture_id)
        elif args.command=='reconcile-media':
            result=engine.reconcile_media(cur,capture_id=args.capture_id)
        elif args.command=='fail':
            result=engine.fail(cur,request_id=args.request_id,error_type=args.error_type,
                               provider_status=args.provider_status)
        elif args.command=='readback':
            result=engine.readback(cur,capture_id=args.capture_id)
        else:
            result=engine.work_queue(cur,limit=args.limit,cursor=args.cursor)
        conn.commit()
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
