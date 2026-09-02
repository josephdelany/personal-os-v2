#!/usr/bin/env python3
"""Nightly watch resolver (ADR-0048, E11): turns a matured `watch:` row into
CONFIRMED_OBSERVATIONAL / REFUTED / expired-INSUFFICIENT per its frozen rule.
Deterministic; heartbeated to ops.runs as job_name='resolve_watches'.
    PYTHONPATH=. python3 tools/run_resolve.py [--dry-run]
"""
import argparse
import json
import sys
from lib import db
from tools.engines import resolve


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    conn = db.connect(); cur = conn.cursor()
    try:
        stats = resolve.run(cur)
        changed = stats["promoted"] + stats["refuted"] + stats["expired"]
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('resolve_watches', now(), 'ok', %s, %s)""",
                    (changed, json.dumps(stats | {"code_version": resolve.CODE_VERSION})))
        if args.dry_run:
            conn.rollback(); print(f"DRY RUN {stats} — rolled back")
        else:
            conn.commit(); print(f"resolve committed: {stats}")
        return 0
    except Exception as e:
        conn.rollback()
        # only the server's message field ('M'), never the failing-row detail ('D'), reaches
        # ops.runs — a constraint failure's detail would carry metric values (reviewer #17)
        msg = e.args[0].get("M") if e.args and isinstance(e.args[0], dict) else str(e)
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values ('resolve_watches', now(), 'error', 0, %s)""",
                        (json.dumps({"error": str(msg)[:400]}),))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
