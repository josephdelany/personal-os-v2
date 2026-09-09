#!/usr/bin/env python3
"""The legible surface (WORK_QUEUE U8): one honest read-only view of what the system
has captured, what is stale, and what is waiting — nothing computed that does not trace
to a stored row. Read-only (SELECT only); never writes, never fabricates.

    PYTHONPATH=. python3 tools/status.py

Summary-level only: it reports counts and timestamps, never raw payload contents, so it
cannot leak a coordinate or home location (RULE-29) even once real data exists.
"""
import sys
from lib import db


def report_liveness(cur):
    """Report terminal evidence, never equating an attempt with success.

    The existing 48-hour status threshold is unchanged. Missing expected jobs
    must remain visible even when the runs table has no rows for them.
    """
    cur.execute("""WITH expected(job_name) AS (
                       VALUES ('keepalive_supabase'), ('keepalive_github'),
                              ('extract_checkins')
                   )
                   SELECT e.job_name, latest.started_at, latest.finished_at,
                          latest.status,
                          (SELECT max(r.finished_at) FROM ops.runs r
                            WHERE r.job_name = e.job_name AND r.status = 'ok'
                              AND r.finished_at >= r.started_at
                              AND r.finished_at <= statement_timestamp()) AS last_success,
                          clock_timestamp() AS checked_at
                     FROM expected e
                     LEFT JOIN LATERAL (
                         SELECT started_at, finished_at, status FROM ops.runs r
                          WHERE r.job_name = e.job_name
                          ORDER BY started_at DESC, run_id DESC LIMIT 1
                     ) latest ON true
                    ORDER BY e.job_name""")
    healthy = True
    for job, started, finished, status, last_success, now in cur.fetchall():
        if started is None:
            flag = "MISSING"
        elif status != "ok":
            flag = f"NOT OK: {status}"
        elif finished is None:
            flag = "INCOMPLETE: no finish time"
        elif finished > now or started > finished:
            flag = "INVALID: run timestamps"
        elif (now - finished).total_seconds() >= 48 * 3600:
            flag = "STALE"
        else:
            flag = "ok"
        healthy = healthy and flag == "ok"
        last = f"{last_success:%Y-%m-%d %H:%M}" if last_success else "never"
        print(f"  {job:22} last successful finish: {last}  [{flag}]")
    return healthy


def _fetch1(cur, q, args=()):
    cur.execute(q, args)
    r = cur.fetchone()
    return r[0] if r else None


def main():
    conn = db.connect()
    cur = conn.cursor()
    try:
        cur.execute("SET TRANSACTION READ ONLY")
        now = _fetch1(cur, "select now()")
        print(f"\n=== Personal OS status @ {now:%Y-%m-%d %H:%M %Z} ===\n")

        # ---- keepalive health (Gate 0): is the database being kept alive? ----
        print("LIVENESS (ops.runs — the keepalives that stop Supabase pausing):")
        healthy = report_liveness(cur)

        # ---- capture: what has landed ----
        print("\nCAPTURE (core.raw_captures — every logged capture, immutable):")
        total = _fetch1(cur, "select count(*) from core.raw_captures")
        print(f"  total captures: {total}")
        if total:
            cur.execute("""select source, processing_status, count(*)
                             from core.raw_captures group by 1,2 order by 1,2""")
            for src, st, n in cur.fetchall():
                print(f"    {src:20} {st:12} {n}")
            last_cap = _fetch1(cur, "select max(captured_at) from core.raw_captures")
            print(f"  most recent capture: {last_cap:%Y-%m-%d %H:%M}")
            pending = _fetch1(cur, "select count(*) from core.raw_captures where processing_status='received'")
            print(f"  waiting for extraction: {pending}")
        else:
            print("  nothing captured yet — the ingress is live and waiting for the first Shortcut tap.")

        # ---- derived spine ----
        print("\nSPINE (derived rows — each traces to a capture, INV-1):")
        for label, tbl in [("atoms", "core.atoms"), ("entities", "core.entities"),
                           ("findings", "core.findings"), ("metric keys", "core.metric_registry")]:
            print(f"  {label:14} {_fetch1(cur, f'select count(*) from {tbl}')}")

        # ---- what is missing / owed ----
        print("\nMISSING / OWED:")
        if not total:
            print("  - no captures yet → start the Shortcut (docs/CAPTURE_SHORTCUT.md), then tap once.")
        keys = _fetch1(cur, "select count(*) from core.metric_registry")
        print("  - model credential availability is not checked by this status command.")
        print(f"  - {keys} metric keys seeded; more are seeded as subjects are added.")
        print()
        return 0 if healthy else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
