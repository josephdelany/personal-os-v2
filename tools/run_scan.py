#!/usr/bin/env python3
"""Weekly contrast scan (ADR-0038): full sweep + null twin -> CANDIDATE rows,
contrast stats, calibration ledger. Deterministic; heartbeated.
    PYTHONPATH=. python3 tools/run_scan.py [--stride N] [--dry-run]
"""
import argparse
import datetime as dt
import json
import sys
from lib import db
from tools.engines import scan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(); cur = conn.cursor()
    try:
        run_date = dt.datetime.now(dt.timezone.utc).date()
        stats = scan.run(cur, run_date, stride=args.stride)
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('contrast_scan', now(), 'ok', %s, %s)""",
                    (stats["kept"], json.dumps(stats | {"stride": args.stride,
                                                        "code_version": scan.CODE_VERSION})))
        if args.dry_run:
            conn.rollback(); print(f"DRY RUN {stats} — rolled back")
        else:
            conn.commit(); print(f"scan committed: {stats}")
        return 0
    except Exception as e:
        conn.rollback()
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values ('contrast_scan', now(), 'error', 0, %s)""",
                        (json.dumps({"error": str(e)[:400]}),))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
