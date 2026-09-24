"""Validate a Chase US credit export locally, or explicitly persist it privately.

    python -m tools.import_v0_card --file /private/path/activity.CSV --account UUID
    python -m tools.import_v0_card --file /private/path/activity.CSV --account UUID --apply

Default is validation only. No original rows, amounts, paths or credentials are logged.
"""
import argparse
import json
import os
from pathlib import Path

from tools.importers.v0_card import CardFileError, MAX_BYTES, prepare
from tools.importers.v0_card_store import import_bytes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--account', required=True, help='stable owner-assigned UUID for this card')
    parser.add_argument('--apply', action='store_true', help='write through configured private database connection')
    args = parser.parse_args(argv)
    try:
        with args.file.open('rb') as source:
            data = source.read(MAX_BYTES+1)
        request = prepare(data,args.account)
    except OSError:
        print(json.dumps({'status':'error','message':'source file could not be read'}))
        return 1
    except CardFileError as exc:
        print(json.dumps({'status':'error','message':str(exc)}))
        return 1
    if not args.apply:
        print(json.dumps(dict(status='validated_not_saved',mapping_version=request['mapping_version'],
                              source_rows=len(request['rows']))))
        return 0
    if any(os.environ.get(key) for key in ('CF_API_TOKEN','MODEL_EGRESS_DB_URL','REFERENCE_EGRESS_DB_URL')):
        print(json.dumps({'status':'error','message':'run the private importer without provider capabilities'}))
        return 1
    conn = None
    try:
        from lib.db import connect
        conn = connect()
        receipt = import_bytes(conn.cursor(),data,args.account)
        conn.commit()
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        # Commit acknowledgement can be lost after durable commit. Never claim
        # rollback is certain: exact-file retry obtains the same saved receipt.
        print(json.dumps({'status':'unconfirmed','message':'import not confirmed; retry the same file and account'}))
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    print(json.dumps(receipt))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
