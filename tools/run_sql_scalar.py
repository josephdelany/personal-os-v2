#!/usr/bin/env python3
"""Run exactly one SQL statement from argv, print its scalar, write an ops.runs row, exit.

    PYTHONPATH=. python3 tools/run_sql_scalar.py "<statement>" [job_name]
    PYTHONPATH=. python3 tools/run_sql_scalar.py "<statement>" job --requires 'schema.fn()' --otherwise "<statement>"

`--requires/--otherwise` bridges a deploy gap: the preferred statement runs only if the named
function exists (to_regprocedure); otherwise the fallback runs, and ops.runs records which.

Built for the hourly visit derivation (B5.2, ADR-0045): the statement text lives in the
workflow, so this file never names a location table and never selects a coordinate.
Exit 0 on success (ops.runs status 'ok'), 1 on failure (status 'error' when the DB is
reachable; the error text is truncated and never includes row data).
"""
import json
import sys

from lib import db


def parse(argv):
    args, options = [], {}
    i = 1
    while i < len(argv):
        if argv[i] in ("--requires", "--otherwise"):
            if i + 1 >= len(argv):
                raise ValueError(f"{argv[i]} needs a value")
            options[argv[i][2:]] = argv[i + 1]
            i += 2
        else:
            args.append(argv[i])
            i += 1
    if not args or len(args) > 2 or (("requires" in options) != ("otherwise" in options)):
        raise ValueError("usage: run_sql_scalar.py '<statement>' [job] [--requires SIG --otherwise '<statement>']")
    return args[0], (args[1] if len(args) > 1 else "derive_visits"), options


def choose(cur, stmt, options):
    """The statement to run and a label for ops.runs detail."""
    if "requires" not in options:
        return stmt, None
    cur.execute("select to_regprocedure(%s) is not null", (options["requires"],))
    return (stmt, "preferred") if cur.fetchone()[0] else (options["otherwise"], "fallback: " + options["requires"] + " missing")


def main(argv, connect=None):
    try:
        stmt, job, options = parse(argv)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    conn = (connect or db.connect)(); cur = conn.cursor()
    try:
        stmt, path = choose(cur, stmt, options)
        cur.execute(stmt)
        row = cur.fetchone()
        val = row[0] if row else None
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values (%s, now(), 'ok', %s, %s)""",
                    (job, int(val) if isinstance(val, (int, float)) else 0,
                     json.dumps({"scalar": str(val)[:80], **({"path": path} if path else {})})))
        conn.commit()
        print(f"{job}: {val}" + (f" ({path})" if path else ""))
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
