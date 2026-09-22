#!/usr/bin/env python3
"""Persist stalled enrichment reviews (REQ-CAP-027), without model credentials.

    PYTHONPATH=. python3 tools/capture_processing.py          # rollback preview
    PYTHONPATH=. python3 tools/capture_processing.py --commit # explicitly write

Counts only on stdout: no capture IDs, payloads, provider bodies or credentials.
This maintains the review queue; it does not claim that enrichment was attempted.
"""
import argparse
import datetime as dt
import json
import sys

from lib import db
from tools.engines import capture_processing as processing


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', action='store_true')
    args = parser.parse_args(argv)
    conn = None
    try:
        conn = db.connect()
        summary = processing.maintain_reviews(conn.cursor(), now=utc_now())
        if args.commit:
            conn.commit()
        else:
            conn.rollback()
        summary['committed'] = args.commit
        if not args.commit:
            summary['reviews_would_add'] = summary.pop('reviews_added')
            summary['reviews_added'] = 0
        print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception as exc:
        # Exception messages can contain a row or credential. Only the class leaves.
        error_type = type(exc).__name__
        if conn is not None:
            try:
                conn.rollback()
                if args.commit:
                    cur = conn.cursor()
                    cur.execute('SELECT public.fail_capture_processing_maintenance(%s)',
                                (error_type,))
                    conn.commit()
            except Exception:
                print('capture_processing: error heartbeat unavailable', file=sys.stderr)
        print(json.dumps({'status': 'error', 'error_type': error_type}), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                print('capture_processing: connection close failed', file=sys.stderr)


if __name__ == '__main__':
    sys.exit(main())
