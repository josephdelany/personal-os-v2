#!/usr/bin/env python3
"""Isolated model dispatcher: prepared request on stdin, result on stdout.

Run in a process with MODEL_EGRESS_DB_URL and CF credentials only; no private DB
credential. Output contains provider data for the private result consumer, so pipe
it directly there, never to a CI log or public artifact. Errors expose codes only.
"""
import json
import sys
from lib import db, egress


def main():
    conn = None
    try:
        request = json.load(sys.stdin)
        required = {'request_id', 'model_id', 'call_kind', 'payload', 'estimated_neurons'}
        if not isinstance(request, dict) or not required <= request.keys() or request.keys()-required-{'capture_id'}:
            raise ValueError('invalid request')
        conn = db.connect_model_egress()
        result = egress.dispatch(conn, **request)
        print(json.dumps({'request_id': request['request_id'], 'result': result}))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error_type': type(exc).__name__}), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
