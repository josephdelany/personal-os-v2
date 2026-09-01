#!/usr/bin/env python3
"""Deterministic check-in extraction: core.raw_captures -> core.atoms (ADR-0035).

A check-in capture is ALREADY structured (0-10 integer scores validated by the old
Edge Function — its source: `Number.isInteger(v) && v >= 0 && v <= 10`; the shortcut
prompts themselves read "Drive (0-10)" etc.), so extraction is a pure deterministic
transform — no model call, no egress, $0 (RULE-11 trivially satisfied).

Per scored field present: one atom
  kind='self_report', metric_key='checkin_<type>_<field>' (migration 0019),
  presence='observed', ADR-0018 coarsening: an integer response v means the true
  value lies in [v-0.5, v+0.5] clamped to [0,10], estimate_method='self_report'
  (the lane: a coarsened subjective response, never 'measured'),
  state_class='measurement'. A non-empty note: one 'note' atom carrying the verbatim
  text as evidence_span.

Corrections (RULE-10 / append-only): a re-submitted check-in fires a second capture;
its atoms SUPERSEDE the prior current atom for the same metric_key+subject_day (or
prior note for the same subject_day), so `atoms_current` resolves to the newest
value instead of returning both.

Idempotent WITHOUT updating raw_captures (append-only, RULE-02): a capture is done
when atoms exist for its capture_id; re-runs skip it. An empty check-in (no scores,
no note) yields no atoms and is re-scanned each run — bounded, and honest (a gap is
recorded as nothing, never a guess). Every run writes an ops.runs heartbeat row.

    PYTHONPATH=. python3 tools/extract_checkins.py            # real run
    PYTHONPATH=. python3 tools/extract_checkins.py --dry-run  # roll back, print only
"""
import argparse
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

from lib import db

CODE_VERSION = "extract-checkins-v2"
RULE_VERSION = "v1-2026-08-23"          # ADR-0019: 04:00 ET boundary, by start
ET = ZoneInfo("America/New_York")

FIELDS = {
    "morning": ["restored", "energy", "mood", "mental_clarity", "drive", "sleep_feel"],
    "night":   ["mood", "stress", "mental_sharpness", "energy", "day_rating"],
}


def subject_day(ts: dt.datetime) -> dt.date:
    """ADR-0019: 04:00 local (ET) boundary, assignment by start instant. A night
    check-in submitted next morning lands on the submission day, which may differ
    from the day it rates — flagged as OQ-38, not silently re-ruled here; the
    capture keeps the phone's checkin_date so a future ruling can re-derive."""
    local = ts.astimezone(ET)
    d = local.date()
    if local.hour < 4:
        d -= dt.timedelta(days=1)
    return d


def _prior_current(cur, S, metric_key, sd, kind):
    """The atom the new one supersedes: the newest same-key/day atom that nothing
    else supersedes yet. Returns id or None."""
    if metric_key is None:
        cur.execute(f"""
            select a.id from {S}.atoms a
             where a.kind = %s and a.metric_key is null and a.subject_day = %s
               and not exists (select 1 from {S}.atoms b where b.supersedes = a.id)
             order by a.recorded_at desc limit 1""", (kind, sd))
    else:
        cur.execute(f"""
            select a.id from {S}.atoms a
             where a.metric_key = %s and a.subject_day = %s
               and not exists (select 1 from {S}.atoms b where b.supersedes = a.id)
             order by a.recorded_at desc limit 1""", (metric_key, sd))
    r = cur.fetchone()
    return r[0] if r else None


def extract(cur, schema: str):
    """Transform check-in captures -> atoms on an open cursor. Caller owns the
    transaction. Returns (made, n_captures, skipped). Idempotent by atom existence.
    Schema is interpolated (identifiers cannot be bind-parameters) from a closed
    allowlist, never from free input."""
    if schema not in ("core", "core_dryrun"):
        raise SystemExit(f"schema must be core or core_dryrun, got {schema!r}")
    S = schema
    made = skipped = 0
    cur.execute(f"""
        select rc.capture_id, rc.captured_at, rc.trust_level, rc.payload
          from {S}.raw_captures rc
         where rc.payload->>'kind' = 'checkin'
           and not exists (select 1 from {S}.atoms a where a.raw_capture_id = rc.capture_id)
         order by rc.captured_at""")
    rows = cur.fetchall()
    for cap_id, cap_at, trust, payload in rows:
        p = payload if isinstance(payload, dict) else json.loads(payload)
        ctype = p.get("type")
        if ctype not in FIELDS:
            skipped += 1
            continue
        sd = subject_day(cap_at)
        n_atoms = 0
        for f in FIELDS[ctype]:
            v = p.get(f)
            if v is None:
                continue
            v = float(v)
            mk = f"checkin_{ctype}_{f}"
            prior = _prior_current(cur, S, mk, sd, "self_report")
            cur.execute(f"""
                insert into {S}.atoms
                  (raw_capture_id, kind, metric_key, occurred_at, time_precision,
                   subject_day, subject_day_rule_version, presence,
                   value_low, value_point, value_high, estimate_method, unit,
                   state_class, trust_level, provenance, evidence_span,
                   code_version, supersedes)
                values (%s, 'self_report', %s, %s, 'exact', %s, %s, 'observed',
                        %s, %s, %s, 'self_report', 'score_0_10',
                        'measurement', %s, 'extracted', %s, %s, %s)""",
                (cap_id, mk, cap_at, sd, RULE_VERSION,
                 max(0.0, v - 0.5), v, min(10.0, v + 0.5),
                 trust, f, CODE_VERSION, prior))
            n_atoms += 1
        note = (p.get("note") or "").strip()
        if note:
            prior = _prior_current(cur, S, None, sd, "note")
            cur.execute(f"""
                insert into {S}.atoms
                  (raw_capture_id, kind, occurred_at, time_precision,
                   subject_day, subject_day_rule_version, presence,
                   trust_level, provenance, evidence_span, code_version, supersedes)
                values (%s, 'note', %s, 'exact', %s, %s, 'observed',
                        %s, 'extracted', %s, %s, %s)""",
                (cap_id, cap_at, sd, RULE_VERSION, trust, note[:2000],
                 CODE_VERSION, prior))
            n_atoms += 1
        made += n_atoms
        print(f"  {cap_at:%Y-%m-%d %H:%M} {ctype:8} -> {n_atoms} atoms")
    return made, len(rows), skipped


def log_run(cur, schema: str, status: str, rows_written: int, detail: dict):
    """ops.runs heartbeat (observability). The ops schema pairs with the core schema
    in dry-runs, so a probe writes only to the disposable pair."""
    ops = "ops" if schema == "core" else "ops_dryrun"
    cur.execute(f"""
        insert into {ops}.runs (job_name, finished_at, status, rows_written, detail)
        values ('extract_checkins', now(), %s, %s, %s)""",
        (status, rows_written, json.dumps(detail)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--schema", default="core", help="target schema (core_dryrun for probes)")
    args = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    try:
        made, n, skipped = extract(cur, args.schema)
        log_run(cur, args.schema, "ok", made,
                {"captures": n, "skipped": skipped, "code_version": CODE_VERSION})
        if args.dry_run:
            conn.rollback()
            print(f"DRY RUN: would create {made} atoms from {n} captures "
                  f"({skipped} skipped) — rolled back, nothing persisted")
        else:
            conn.commit()
            print(f"extracted {made} atoms from {n} captures ({skipped} skipped)")
        return 0
    except Exception as e:
        conn.rollback()
        try:
            log_run(cur, args.schema, "error", 0, {"error": str(e)[:400]})
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
