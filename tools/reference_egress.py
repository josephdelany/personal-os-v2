#!/usr/bin/env python3
"""Isolated source dispatcher. Pipe private output to cache consumption, never logs."""
import json
import sys
from lib import db
from tools.engines import reference_dispatch


def main():
    conn = None
    try:
        text = sys.stdin.read(4097)
        if len(text.encode())>4096:
            raise ValueError('reference request too large')
        request = json.loads(text)
        reference_dispatch.validate(request)
        conn = db.connect_reference_egress()
        result = reference_dispatch.dispatch(conn,request)
        print(json.dumps({'request_id':request['request_id'],'result':result}))
        return 0
    except Exception as exc:
        allowed = {'DispatchRefused','DispatchUncertain','ApiKeyMissing','ContactMissing','PayloadRefused'}
        kind = type(exc).__name__
        print(json.dumps({'status':'error','error_type':kind if kind in allowed else 'ReferenceUnavailable'}),file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass


if __name__=='__main__':
    sys.exit(main())
