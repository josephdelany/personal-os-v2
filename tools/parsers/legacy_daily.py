#!/usr/bin/env python3
"""Load the seven-year legacy daily series into analysis.legacy_daily (ADR-0038).

Source: the old workspace's 05_archive/daily_series.csv — 2,382 days
(2019-09-03 →), columns d,hrv,rhr,resp,kcal,exmin,steps,asleep,inbed,deep,rem,
core,awake,onset,wake_min. Sparse-honest: empty cells stay NULL (RULE-06).
Idempotent: full DELETE+reload of this rebuildable analysis table (NOT core;
append-only rules don't apply to derived/rebuildable data, ADR-0038).

    PYTHONPATH=. python3 tools/parsers/legacy_daily.py [--dry-run]
"""
import argparse
import csv
import json
import sys
from pathlib import Path

from lib import db

CODE_VERSION = "legacy-daily-v1"
CSV = Path.home() / "Documents/Claude/Projects/Personal Survilance/05_archive/daily_series.csv"
COLS = ["hrv", "rhr", "resp", "kcal", "exmin", "steps", "asleep", "inbed",
        "deep", "rem", "core", "awake", "onset", "wake_min"]
DB_COLS = ["hrv", "rhr", "resp", "kcal", "exmin", "steps", "asleep", "inbed",
           "deep", "rem", "core_min", "awake", "onset", "wake_min"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = []
    with open(CSV, newline="") as f:
        for r in csv.DictReader(f):
            day = r["d"].strip()
            if not day:
                continue
            vals = [float(r[c]) if r.get(c, "").strip() != "" else None for c in COLS]
            if all(v is None for v in vals):
                continue                     # an all-empty day carries nothing
            rows.append([day] + vals)
    conn = db.connect(); cur = conn.cursor()
    try:
        cur.execute("delete from analysis.legacy_daily")
        for row in rows:
            cur.execute(
                f"""insert into analysis.legacy_daily (day, {', '.join(DB_COLS)})
                    values ({', '.join(['%s'] * (1 + len(DB_COLS)))})""", row)
        cur.execute("""insert into ops.runs (job_name, finished_at, status, rows_written, detail)
                       values ('legacy_daily_load', now(), 'ok', %s, %s)""",
                    (len(rows), json.dumps({"source": str(CSV.name), "code_version": CODE_VERSION})))
        if args.dry_run:
            conn.rollback(); print(f"DRY RUN: {len(rows)} days parsed — rolled back")
        else:
            conn.commit(); print(f"loaded {len(rows)} legacy days into analysis.legacy_daily")
        return 0
    except Exception:
        conn.rollback(); raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
