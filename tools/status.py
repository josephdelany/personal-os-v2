#!/usr/bin/env python3
"""The legible surface (WORK_QUEUE U8): one honest read-only view of what the system
has captured, what is stale, and what is waiting — nothing computed that does not trace
to a stored row. Read-only (SELECT only); never writes, never fabricates.

    PYTHONPATH=. python3 tools/status.py

Summary-level only: it reports counts and timestamps, never raw payload contents, so it
cannot leak a coordinate or home location (RULE-29) even once real data exists.
"""
import sys
from datetime import datetime, timezone
from lib import db


def _fetch1(cur, q, args=()):
    cur.execute(q, args)
    r = cur.fetchone()
    return r[0] if r else None


def main():
    conn = db.connect()
    cur = conn.cursor()
    try:
        now = _fetch1(cur, "select now()")
        print(f"\n=== Personal OS status @ {now:%Y-%m-%d %H:%M %Z} ===\n")

        # ---- keepalive health (Gate 0): is the database being kept alive? ----
        print("LIVENESS (ops.runs — the keepalives that stop Supabase pausing):")
        cur.execute("""select job_name, max(started_at) as last, count(*) as n
                         from ops.runs
                        where job_name like 'keepalive%' or job_name = 'extract_checkins'
                        group by job_name order by 1""")
        rows = cur.fetchall()
        if not rows:
            print("  (no keepalive rows — Gate 0 not yet firing)")
        for job, last, n in rows:
            age_h = (now - last).total_seconds() / 3600
            flag = "ok" if age_h < 48 else "STALE"
            print(f"  {job:22} last {last:%Y-%m-%d %H:%M}  ({age_h:5.1f}h ago)  {n} runs  [{flag}]")

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
        print(f"  - extraction (raw_captures → atoms) needs the Cloudflare Workers AI credential to run.")
        print(f"  - {keys} metric keys seeded; more are seeded as subjects are added.")
        print()
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
