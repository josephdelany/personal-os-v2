#!/usr/bin/env python3
"""Nightly confirmation gate (ADR-0050 / ADR-0051, B9): PROMOTED -> CONFIRMED_OBSERVATIONAL when every
REQ-TIER-013 check passes, REFUTED when a negative control or a refutation test fails, demoted when a
monthly re-check no longer holds. Also scores the forward predictions (RULE-20 / OQ-44 (a)).

The ops.runs row is created FIRST so its run_id can be stamped on every ledger row the gate writes
(REQ-TIER-042: the id of the job that performed the change).

    PYTHONPATH=. python3 tools/run_confirm.py [--dry-run]
"""
import argparse
import json
import sys

from lib import db
from tools.engines import confirm


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    run_id = None
    try:
        cur.execute("insert into ops.runs (job_name, status) values ('confirm_gate', 'running') returning run_id")
        run_id = cur.fetchone()[0]
        stats = confirm.run(cur, run_id=run_id)
        changed = stats["confirmed"] + stats["refuted"] + stats["demoted"] + stats["insufficient"]
        cur.execute("""update ops.runs set finished_at = now(), status = 'ok', rows_written = %s, detail = %s
                        where run_id = %s""",
                    (changed, json.dumps(stats | {"code_version": confirm.CODE_VERSION}), run_id))
        if args.dry_run:
            conn.rollback()
            print(f"DRY RUN {stats} — rolled back")
        else:
            conn.commit()
            print(f"confirm committed: {stats}")
        return 0
    except Exception as e:
        conn.rollback()
        msg = e.args[0].get("M") if e.args and isinstance(e.args[0], dict) else str(e)
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values ('confirm_gate', now(), 'error', 0, %s)""",
                        (json.dumps({"error": str(msg)[:400], "run_id": str(run_id)}),))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
