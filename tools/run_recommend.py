#!/usr/bin/env python3
"""Nightly recommendation generation (ADR-0052, B10): scores yesterday's forward predictions, withdraws
recommendations whose evidence fell, generates today's, and marks the single daily instruction.
Deterministic; heartbeated to ops.runs as job_name='recommend'.
    PYTHONPATH=. python3 tools/run_recommend.py [--dry-run]
"""
import argparse
import json
import sys

from lib import db
from tools.engines import recommend


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(); cur = conn.cursor()
    try:
        stats = recommend.run(cur)
        written = stats["pattern"] + stats["standing_order"]
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('recommend', now(), 'ok', %s, %s)""",
                    (written, json.dumps(stats | {"code_version": recommend.CODE_VERSION})))
        if args.dry_run:
            conn.rollback(); print(f"DRY RUN {stats} — rolled back")
        else:
            conn.commit(); print(f"recommend committed: {stats}")
        return 0
    except Exception as e:
        conn.rollback()
        msg = e.args[0].get("M") if e.args and isinstance(e.args[0], dict) else str(e)
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values ('recommend', now(), 'error', 0, %s)""",
                        (json.dumps({"error": str(msg)[:400]}),))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
