#!/usr/bin/env python3
"""Reliability keepalives (REQ-NFR-001..004, ADR-0024).

Two jobs, one script:

  --job supabase : the 7-day Supabase-pause keepalive. An authenticated write to the
                   database resets Supabase Free's 7-day inactivity clock. The write
                   IS the row this job commits to ops.runs — no separate ping needed.
  --job github   : the 60-day GitHub-Actions keepalive proof-of-life. The commit that
                   actually resets GitHub's 60-day schedule-disable clock is made by the
                   workflow (.github/workflows/keepalive.yml, heartbeat-commit step);
                   this records that the scheduled job ran.

Both write exactly one row to <ops>.runs (REQ-NFR-003): opened 'running', closed 'ok'.
On failure the row is closed 'error' when the database is reachable, and the process
exits non-zero in every failure case (REQ-NFR-004) so a keepalive death is never silent.
`started_at`/`finished_at` use clock_timestamp() (wall-clock at each statement), not now()
(fixed for the whole transaction), so finished_at is the real completion instant and not a
copy of started_at. A keepalive writes no DATA rows, so
rows_written is 0 — the run row is an operational heartbeat recording a true "this job
ran at T" event, not fabricated data (RULE-01; heartbeat-rows-are-legit ruling, ADR-0024).

    PYTHONPATH=. python3 ops/keepalive.py --job supabase --trigger "$GITHUB_EVENT_NAME"  # CI: schedule|workflow_dispatch
    PYTHONPATH=. python3 ops/keepalive.py --job supabase --dry-run             # persists nothing

perform() takes an open cursor and a schema, so a test can drive it (success AND failure)
against a disposable ops_pytest schema and roll the whole transaction back (ADR-0022).
"""
import argparse
import json
import sys

from lib import db

VALID_JOBS = ("supabase", "github")


def open_run(cur, ops_schema, job_name, detail):
    """INSERT a 'running' row stamped with clock_timestamp(); return its run_id."""
    cur.execute(
        f"INSERT INTO {ops_schema}.runs (job_name, started_at, status, detail) "
        f"VALUES (%s, clock_timestamp(), 'running', %s::jsonb) RETURNING run_id",
        (job_name, json.dumps(detail)),
    )
    return cur.fetchone()[0]


def close_run(cur, ops_schema, run_id, status, rows_written, detail):
    """Close an open run row with a terminal status and a real finished_at."""
    cur.execute(
        f"UPDATE {ops_schema}.runs "
        f"SET finished_at = clock_timestamp(), status = %s, rows_written = %s, "
        f"    detail = %s::jsonb "
        f"WHERE run_id = %s",
        (status, rows_written, json.dumps(detail), run_id),
    )


def record_run(cur, ops_schema, job_name, trigger):
    """Open a run, do the trivial authenticated round-trip, close it 'ok'. Returns
    run_id. Does NOT commit — the caller owns the transaction."""
    run_id = open_run(cur, ops_schema, job_name,
                      {"purpose": "reliability keepalive", "job": job_name, "trigger": trigger})
    cur.execute("SELECT 1")          # the authenticated round-trip that keeps PG warm
    cur.fetchone()
    close_run(cur, ops_schema, run_id, "ok", 0,
              {"result": "warm", "job": job_name, "trigger": trigger})
    return run_id


def perform(cur, ops_schema, job_name, trigger):
    """Run the keepalive on an open cursor inside a savepoint. On failure, roll the
    savepoint back so the aborted work is undone, write an 'error' row on the SAME
    (still-reachable) connection (REQ-NFR-004), and re-raise. Caller owns commit."""
    cur.execute("SAVEPOINT ka")
    try:
        run_id = record_run(cur, ops_schema, job_name, trigger)
        cur.execute("RELEASE SAVEPOINT ka")
        return run_id
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT ka")
        rid = open_run(cur, ops_schema, job_name,
                       {"job": job_name, "trigger": trigger, "phase": "failed"})
        close_run(cur, ops_schema, rid, "error", 0,
                  {"error": f"{type(exc).__name__}: {exc}", "job": job_name, "trigger": trigger})
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description="Reliability keepalive (REQ-NFR-001..004).")
    ap.add_argument("--job", required=True, choices=VALID_JOBS)
    ap.add_argument("--ops", default="ops", help="ops schema name (default: ops)")
    ap.add_argument("--trigger", default="manual",
                    help="what fired this run, recorded verbatim in ops.runs.detail. CI passes "
                         "github.event_name ('schedule' = cron, 'workflow_dispatch' = manual "
                         "dispatch); local use: 'manual', 'manual_smoke'.")
    ap.add_argument("--dry-run", action="store_true",
                    help="roll back instead of commit — proves the path, persists nothing")
    args = ap.parse_args(argv)
    job_name = f"keepalive_{args.job}"

    # If the database is unreachable, there is no ops.runs to write to; the visible
    # signal is this non-zero exit and the failed CI run (REQ-NFR-004).
    try:
        conn = db.connect()
    except Exception as e:
        print(f"ERROR {job_name}: cannot reach database: {type(e).__name__}: {e}",
              file=sys.stderr)
        sys.exit(1)
    cur = conn.cursor()
    try:
        run_id = perform(cur, args.ops, job_name, args.trigger)
        if args.dry_run:
            conn.rollback()
            print(f"DRY RUN {job_name}: run {run_id} rolled back — nothing persisted")
        else:
            conn.commit()
            print(f"OK {job_name}: wrote run {run_id} to {args.ops}.runs")
    except Exception as e:
        try:
            conn.commit()          # keep the 'error' row perform() wrote on this connection
        except Exception:
            conn.rollback()
        print(f"ERROR {job_name}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
