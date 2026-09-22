#!/usr/bin/env python3
"""Private Ask job stages. Output is private; never send it to CI logs/artifacts.

prepare emits a needs_model wrapper; pipe only its request to the isolated model
process. consume accepts that process's correlated result JSON on stdin. readback
recovers a committed job after an interrupted client. Every stage commits before
printing. The fixed as-of date is required until default-date selection is shared
with the SQL executor, avoiding a second temporal-default implementation.
"""
import argparse
import datetime as dt
import json
import sys
from lib import db
from tools.engines import ask_jobs as engine


def owner_context(cur):
    """Trusted backend DB login establishes the single owner's SQL context.

    This is not JWT validation for a public API. Untrusted app/model roles are
    refused even if they supply owner-shaped input. The login is the authority.
    """
    cur.execute('SELECT session_user,current_user')
    session, role = cur.fetchone()
    if session != role or role not in {'postgres','service_role'}:
        raise PermissionError('private backend identity required')
    cur.execute("SELECT set_config('request.jwt.claims',%s,true)",
                ('{"email":"joseph.delany21@gmail.com"}',))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare')
    prep.add_argument('job_id')
    prep.add_argument('question')
    prep.add_argument('--as-of', required=True, type=dt.date.fromisoformat)
    commands.add_parser('consume')
    failed = commands.add_parser('fail')
    failed.add_argument('request_id')
    failed.add_argument('error_type')
    read = commands.add_parser('readback')
    read.add_argument('job_id')
    args = parser.parse_args(argv)
    conn = None
    try:
        engine.private_process()
        conn = db.connect()
        cur = conn.cursor()
        owner_context(cur)
        if args.command == 'prepare':
            result = engine.prepare(cur, job_id=args.job_id, question=args.question, as_of=args.as_of)
        elif args.command == 'consume':
            message = json.load(sys.stdin)
            if not isinstance(message, dict) or set(message) != {'request_id','result'}:
                raise ValueError('correlated model result required')
            result = engine.consume(cur, request_id=message['request_id'], response=message['result'])
        elif args.command == 'fail':
            result = engine.fail(cur, request_id=args.request_id, error_type=args.error_type)
        else:
            result = engine.readback(cur, job_id=args.job_id)
        conn.commit()
        print(json.dumps(result, default=str))
        return 0
    except Exception as error:
        if conn is not None:
            try: conn.rollback()
            except Exception: pass
        print(json.dumps({'status':'error','error_type':type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass

if __name__ == '__main__':
    sys.exit(main())
