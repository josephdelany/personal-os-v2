#!/usr/bin/env python3
"""Run exactly one SQL statement from argv, print its scalar, write an ops.runs row, exit.

    PYTHONPATH=. python3 tools/run_sql_scalar.py "<statement>" [job_name]

Built for the hourly visit derivation (B5.2, ADR-0045): the statement text lives in the
workflow, so this file never names a location table and never selects a coordinate.
Exit 0 on success (ops.runs status 'ok'), 1 on failure (status 'error' when the DB is
reachable; the error text is truncated and never includes row data).
"""
import json
import sys

from lib import db


def main(argv):
    if len(argv) < 2:
        print("usage: run_sql_scalar.py '<one statement>' [job_name]", file=sys.stderr)
        return 2
    stmt, job = argv[1], (argv[2] if len(argv) > 2 else "derive_visits")
    conn = db.connect(); cur = conn.cursor()
    try:
        cur.execute(stmt)
        row = cur.fetchone()
        val = row[0] if row else None
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values (%s, now(), 'ok', %s, %s)""",
                    (job, int(val) if isinstance(val, (int, float)) else 0, json.dumps({"scalar": str(val)[:80]})))
        conn.commit()
        print(f"{job}: {val}")
        return 0
    except Exception as e:
        conn.rollback()
        try:
            cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                           values (%s, now(), 'error', 0, %s)""", (job, json.dumps({"error": str(e)[:300]})))
            conn.commit()
        except Exception:
            conn.rollback()
        print(f"{job}: ERROR {str(e)[:300]}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
