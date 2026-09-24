#!/usr/bin/env python3
"""Apply an owner correction from JSON stdin; stdout is private.

SUPABASE_DB_URL must identify a separately provisioned capture_owner-capable
login. Automated service credentials cannot authorize this command. The command
commits before printing success; provisioning and production use are separate
deployment actions.
"""
import argparse
import json
import sys

from lib import db
from tools.engines import capture_corrections
from tools.engines.capture_transcription import _private


def main(argv=None):
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    conn = None
    try:
        _private('core')
        payload = capture_corrections.validate_request(json.load(sys.stdin))
        conn = db.connect()
        result = capture_corrections.apply(conn.cursor(), payload)
        conn.commit()
        print(json.dumps(result))
        return 0
    except Exception as error:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        # Database exceptions may contain private request data or credentials.
        print(json.dumps({'status': 'error', 'error_type': type(error).__name__}), file=sys.stderr)
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


if __name__ == '__main__':
    sys.exit(main())
