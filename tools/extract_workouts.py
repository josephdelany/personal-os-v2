#!/usr/bin/env python3
"""Deterministic strength-set extraction: core.raw_captures -> core.atoms (REQ-WKT-003/005/007).

THE GAP THIS CLOSES. `tools/make_shortcut_workout.py` already generates a "Log Workout"
shortcut that posts one SET per run — `{kind:'workout', exercise, weight_lb, reps, rpe}` —
and `core.metric_registry` already carries `strength_load_lb`, `strength_reps` and
`strength_rpe`. Nothing turned the first into the second, so a tapped set landed in
`raw_captures` and stopped there. Strength is the stated primary objective and the Watch has
recorded 25 sessions in four years (ADR-0087), so this path is the capture, not a convenience.

SHAPE (OQ-33 option (a)): one atom per attribute, all sharing a set key. That is not a
preference — it is the only shape the built model expresses. An `atoms` row carries a single
`value_point`, so a composite set atom would need a schema change, and the registry already
holds three per-attribute keys. Joe's ruling is a confirmation, not a deliberation.

LANES (RULE-05, REQ-WKT-007). Load and reps are MEASURED: Joe reads them off the bar. RPE is
a coarsened SELF-REPORT on the registry's declared 21-point [0,10] scale — a 0.5 step, so a
stated v means the true value lies in [v-0.25, v+0.25] (ADR-0018). Storing an RPE as measured
would put a feeling in the same lane as a plate.

WHAT THIS DELIBERATELY DOES NOT DO (RULE-09, REQ-WKT-003):
  * No e1RM and no volume. Those are derived measures with their own owner and code_version
    (REQ-WKT-008/011), and a capture path that computes them makes the number untraceable.
  * No exercise-entity resolution. REQ-WKT-006 requires a single canonical entity per movement
    and that is B14's job; the verbatim text is stored as evidence and nothing is canonicalised,
    so "Bench Press" and "bench press" remain two strings until B14 rules. REQ-WKT-006 is
    therefore NOT satisfied by this tool and is not claimed to be.
  * No zero load. REQ-WKT-004 requires a bodyweight or assisted movement to be MARKED, and the
    shortcut has no field to mark one, so a 0 lb entry is counted and skipped rather than
    written as a real load of zero. That is a shortcut gap, recorded, not papered over.

    PYTHONPATH=. python3 tools/extract_workouts.py            # real run
    PYTHONPATH=. python3 tools/extract_workouts.py --dry-run  # roll back, print only
"""
import argparse
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

from lib import db

CODE_VERSION = "extract-workouts-v1"
RULE_VERSION = "v1-2026-08-23"          # ADR-0019: 04:00 ET boundary, by start
ET = ZoneInfo("America/New_York")

# The registry's own numbers, not a copy of them: read at run time so a scale change in the
# registry cannot silently disagree with the coarsening applied here (RULE-12).
RPE_KEY, LOAD_KEY, REPS_KEY = "strength_rpe", "strength_load_lb", "strength_reps"


def subject_day(ts: dt.datetime) -> dt.date:
    return (ts.astimezone(ET) - dt.timedelta(hours=4)).date()


def rpe_interval(v: float, low: float, high: float, n_points: int):
    """ADR-0018. A response on an n-point scale over [low, high] is coarse: it names a bin,
    not a point. Half the step on each side, clamped to the instrument."""
    if n_points and n_points > 1:
        half = (high - low) / (n_points - 1) / 2.0
    else:
        half = 0.5
    return max(low, v - half), min(high, v + half)


def _prior_current(cur, S, metric_key, set_key):
    """RULE-10 / append-only. A re-logged set for the same set key supersedes the previous
    atom rather than sitting beside it, so `atoms_current` resolves to the correction."""
    cur.execute(f"""
        select a.id from {S}.atoms a
         where a.kind = 'workout' and a.metric_key = %s
           and a.evidence_span like %s
           and not exists (select 1 from {S}.atoms b where b.supersedes = a.id)
         order by a.recorded_at desc limit 1""", (metric_key, f"%set={set_key}%"))
    row = cur.fetchone()
    return row[0] if row else None


def _num(payload, key):
    v = payload.get(key)
    if v is None:
        return None
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None          # non-numeric: a gap, never a guess (RULE-06)


def extract(cur, schema: str, ops_schema: str):
    S = schema
    cur.execute(f"""select metric_key, plausible_low, plausible_high, response_scale, n_scale_points
                      from {S}.metric_registry where metric_key in (%s, %s, %s)""",
                (RPE_KEY, LOAD_KEY, REPS_KEY))
    reg = {r[0]: r for r in cur.fetchall()}
    missing = [k for k in (RPE_KEY, LOAD_KEY, REPS_KEY) if k not in reg]
    if missing:
        # REQ-WKT-005: the metric_key foreign key makes a set unwritable until its registry
        # rows land. Refusing loudly beats writing two of the three attributes.
        raise SystemExit(f"strength registry rows absent: {missing}")

    cur.execute(f"""
        select c.capture_id, c.captured_at, c.trust_level, c.payload
          from {S}.raw_captures c
         where c.payload->>'kind' = 'workout'
           and not exists (select 1 from {S}.atoms a where a.raw_capture_id = c.capture_id)
         order by c.captured_at""")
    captures = cur.fetchall()

    written, counters = 0, {}

    def bump(k):
        counters[k] = counters.get(k, 0) + 1

    for cap_id, cap_at, trust, payload in captures:
        p = payload if isinstance(payload, dict) else json.loads(payload)
        sd = subject_day(cap_at)
        # RULE-10. A capture is its own set unless it names one. A re-log that carries the
        # original `set_key` is a CORRECTION of that set — its atoms supersede the earlier
        # ones rather than sitting beside them, because two current loads for one set leave
        # a later reader unable to tell which Joe meant.
        set_key = str(p.get("set_key") or cap_id)
        exercise = (p.get("exercise") or "").strip()
        if not exercise:
            bump("set_without_an_exercise")
            continue

        load, reps, rpe = _num(p, "weight_lb"), _num(p, "reps"), _num(p, "rpe")
        if load is not None and load == 0:
            # REQ-WKT-004: mark a bodyweight or assisted movement, never record zero load.
            # The shortcut cannot mark one, so this is a capture gap, not a load of nothing.
            bump("zero_load_unmarkable_see_REQ_WKT_004")
            load = None

        for key, value, lane, unit in (
                (LOAD_KEY, load, "measured", "lb"),
                (REPS_KEY, reps, "measured", "rep"),
                (RPE_KEY, rpe, "self_report", "rpe")):
            if value is None:
                bump(f"absent:{key}")
                continue
            _, plow, phigh, scale, n_points = reg[key]
            if not (float(plow) <= value <= float(phigh)):
                # Out of the instrument's range: skipped, never clamped into the data.
                bump(f"out_of_range:{key}")
                continue
            if lane == "self_report":
                lo, hi = rpe_interval(value, float(plow), float(phigh), n_points)
            else:
                lo = hi = value
            prior = _prior_current(cur, S, key, set_key)
            cur.execute(f"""
                insert into {S}.atoms
                  (raw_capture_id, kind, metric_key, occurred_at, time_precision,
                   subject_day, subject_day_rule_version, presence,
                   value_low, value_point, value_high, estimate_method, unit,
                   state_class, trust_level, provenance, evidence_span,
                   code_version, supersedes)
                values (%s, 'workout', %s, %s, 'exact', %s, %s, 'observed',
                        %s, %s, %s, %s, %s, 'measurement', %s, 'extracted', %s, %s, %s)""",
                (cap_id, key, cap_at, sd, RULE_VERSION, lo, value, hi, lane, unit, trust,
                 # The set key binds the attributes into one set (REQ-WKT-005) and the
                 # exercise rides verbatim, unresolved (REQ-WKT-006 is B14's).
                 f"set={set_key};exercise={exercise[:200]}", CODE_VERSION, prior))
            written += 1
        bump("sets_extracted")
    return written, counters, len(captures)


def log_run(cur, ops_schema, status, rows, detail):
    cur.execute(f"""insert into {ops_schema}.runs (job, trigger, status, rows_written, detail)
                    values ('extract_workouts', 'manual', %s, %s, %s)""",
                (status, rows, json.dumps(detail)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--core", default="core")
    ap.add_argument("--ops", default="ops")
    a = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    try:
        written, counters, seen = extract(cur, a.core, a.ops)
        print(json.dumps({"captures_seen": seen, "atoms_written": written,
                          "counters": counters}, sort_keys=True))
        if a.dry_run:
            conn.rollback()
            print("DRY RUN (rolled back)")
            return 0
        log_run(cur, a.ops, "ok", written, counters)
        conn.commit()
        print(f"COMMITTED {written} atoms")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
