#!/usr/bin/env python3
"""Isolated model dispatcher: prepared request on stdin, result on stdout.

Run in a process with MODEL_EGRESS_DB_URL and CF credentials only; no private DB
credential. Output contains provider data for the private result consumer, so pipe
it directly there, never to a CI log or public artifact. Errors expose codes only.
"""
import json
import os
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
        receipt_fd = os.environ.get('PERSONAL_OS_MODEL_RESERVATION_FD')
        def reserved(request_id):
            if receipt_fd is not None:
                raw = json.dumps({'request_id':request_id,'reserved':True}).encode()+b'\n'
                if os.write(int(receipt_fd),raw) != len(raw):
                    raise RuntimeError('reservation acknowledgement incomplete')
        result = egress.dispatch(conn, **request, _on_reserved=reserved)
        print(json.dumps({'request_id': request['request_id'], 'result': result}))
        return 0
    except Exception as exc:
        known = (egress.BudgetExceeded, egress.DispatchRefused, egress.DispatchUncertain, egress.PayloadRefused)
        code = type(exc).__name__ if isinstance(exc, known) else 'DispatcherUnavailable'
        error = {'status': 'error', 'error_type': code}
        provider_status = getattr(exc,'provider_status',None)
        if isinstance(exc,egress.DispatchUncertain) and type(provider_status) is int and 300 <= provider_status <= 599:
            error['provider_status'] = provider_status
        print(json.dumps(error), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
