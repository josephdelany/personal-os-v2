"""Run a registered reconstruction method against real evidence (REQ-REC-004..016; ADR-0134).

    python3 tools/reconstruct_run.py --method watch_non_wear            # dry run
    python3 tools/reconstruct_run.py --method watch_non_wear --commit

THE GAP THIS CLOSES. `config.reconstruction_methods` has existed since migration 0054 and was
empty, and `tools/engines/reconstruct.py` has been tested since B14R with no caller. The schema
was deployed, the engine was tested, and NOTHING RAN. This is the path from source evidence to a
stored inferred event, and it is the only writer of `core.inferred_events`.

WHAT IT REFUSES TO DO. It reads the method's declaration out of the database rather than carrying
one in Python (RULE-13). A method that is not registered cannot be run from here, and a method
whose `permissible_outputs` do not include the conclusion cannot store it — `reconstruct.to_row`
raises first and the table's CHECK constraints catch what it misses.

KNOWLEDGE TIME IS THE MOMENT THE EVIDENCE WAS RECORDED, NOT NOW. `knowledge_time` is the earliest
instant at which this system could have drawn the conclusion, which is when the last supporting
atom was ingested. Setting it to `now()` would make every historical replay report that the
system knew everything from the start, and REQ-REC-011's replay would be worthless.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

from lib import db
from tools.engines.reconstruct import Evidence, Method, evaluate, to_row

WATCH = "Watch"
PHONE = "iPhone"


def load_method(cur, key, *, core="core", config="config"):
    """RULE-13. The declaration comes from the registry, never from this file."""
    cur.execute(f"""SELECT method_key, method_version, event_family, required_evidence,
                           permissible_outputs, temporal_specification
                      FROM {config}.reconstruction_methods
                     WHERE method_key = %s AND retired_at IS NULL
                     ORDER BY method_version DESC LIMIT 1""", (key,))
    row = cur.fetchone()
    if row is None:
        raise SystemExit(
            f"REQ-REC-004: no live method {key!r} in {config}.reconstruction_methods. A method "
            f"this tool does not find registered is one it may not run.")
    return Method(key=row[0], version=row[1], event_family=row[2],
                  required_evidence=tuple(row[3]), permissible_outputs=tuple(row[4]),
                  temporal_specification=row[5])


def device_days(cur, *, core="core", since=None, until=None):
    """Per subject day: which devices produced atoms, and when the last one was ingested.

    `evidence_span` carries the device (`apple_health:...;source=Joseph's Apple Watch`), which is
    how the panel's device precedence reads it too — one representation, not two.
    """
    cur.execute(f"""
        SELECT a.subject_day,
               bool_or(a.evidence_span ILIKE %s)  AS watch,
               bool_or(a.evidence_span ILIKE %s)  AS phone,
               max(a.recorded_at)                 AS last_recorded,
               count(*)                           AS n_atoms
          FROM {core}.atoms a
         WHERE a.subject_day IS NOT NULL
           AND (%s::date IS NULL OR a.subject_day >= %s::date)
           AND (%s::date IS NULL OR a.subject_day <= %s::date)
         GROUP BY a.subject_day
         ORDER BY a.subject_day
    """, (f"%{WATCH}%", f"%{PHONE}%", since, since, until, until))
    return cur.fetchall()


def evidence_for(day, *, watch, phone, last_recorded):
    """Turn one day's capture state into citations the engine can weigh.

    `origin_group` is THE DAY'S EXPORT, not the device, and that is the whole of REQ-REC-008
    here. The phone's presence and the Watch's absence are not two independent sources — they are
    one HealthKit export read twice, and giving them separate origins made a single-source
    inference count as two corroborations and promoted every episode from DESCRIPTIVE to
    EXPLORATORY. Reading the runner's own output against production is what showed it: 34 days
    at EXPLORATORY on evidence that is one observation.

    A day with four hundred phone samples is likewise one origin, not four hundred.
    """
    ev = []
    origin = f"healthkit_export:{day.isoformat()}"
    if phone:
        ev.append(Evidence(ref=f"atoms:{day.isoformat()}:{PHONE}",
                           kind="phone_capture_present", stance="supports",
                           origin_group=origin, recorded_at=last_recorded))
    if not watch:
        ev.append(Evidence(ref=f"atoms:{day.isoformat()}:no-{WATCH}",
                           kind="watch_capture_absent", stance="supports",
                           origin_group=origin, recorded_at=last_recorded))
    else:
        # The Watch produced data, which contradicts a non-wear episode outright.
        ev.append(Evidence(ref=f"atoms:{day.isoformat()}:{WATCH}",
                           kind="watch_capture_present", stance="contradicts",
                           origin_group=origin, recorded_at=last_recorded))
    return tuple(ev)


def reconstruct_day(method, day, *, watch, phone, last_recorded):
    """One day -> a Reconstruction. `as_of` is the evidence's own recorded time.

    Passing `now()` here would let the engine see evidence it could not have had, which is the
    INV-4 violation this whole module exists to avoid.
    """
    ev = evidence_for(day, watch=watch, phone=phone, last_recorded=last_recorded)
    r = evaluate(method, ev, as_of=last_recorded)
    return r, ev


def rows_for(cur, method, *, core="core", since=None, until=None, coverage=None):
    """Rows to store. `coverage`, if given a list, receives the days examined without a
    conclusion — reported rather than stored, so coverage stays answerable without filling the
    event table with rows that assert nothing."""
    out = []
    unknown = coverage if coverage is not None else []
    for day, watch, phone, last_recorded, n_atoms in device_days(cur, core=core, since=since,
                                                                 until=until):
        r, ev = reconstruct_day(method, day, watch=watch, phone=phone,
                                last_recorded=last_recorded)
        if watch:
            # The Watch captured, so there is definitively no non-wear episode and no gap to
            # explain. This skip is keyed on the EVIDENCE rather than on the engine's reason
            # because both `contradicted` and `required_evidence_missing` arise here — the
            # first when the phone also captured, the second when it did not — and storing
            # either would bury the days that matter under a row for every ordinary day.
            #
            # A first version skipped only `contradicted`, and a read of its own output against
            # production showed 37 rows of the second kind: days the Watch captured and the
            # phone did not, recorded as `unknown` about a device that was demonstrably on.
            continue
        if r.presence == "unknown":
            # AN UNKNOWN IS NOT A CONCLUSION, AND `inferred_events` STORES CONCLUSIONS.
            #
            # REQ-REC-009 requires the ENGINE to return `unknown` rather than `did_not_occur`
            # when the required evidence is absent, and it does — that is asserted directly
            # against `reconstruct_day`. It does not require storing a row for every day about
            # which this method has nothing to say, and doing so is actively harmful.
            #
            # Found by running the full pending stack against production: the transaction
            # backfill puts legacy financial atoms into `core.atoms` going back years, so
            # `device_days` yielded 438 subject days rather than the 71 of the HealthKit era.
            # 404 of them had neither an iPhone nor a Watch atom — because on those days
            # neither device had produced anything into this system at all — and every one was
            # stored as `unknown`. The event table came out 92% rows asserting nothing, the
            # search path returned them ahead of the real episodes, and the first hit a caller
            # inspected had one citation instead of two.
            #
            # "This method cannot speak to this day" is the DEFAULT state of every day nobody
            # examined. Writing it down does not make it more true; it makes the days that do
            # carry a conclusion harder to find.
            unknown.append(day)
            continue
        start = dt.datetime.combine(day, dt.time(0), dt.timezone.utc)
        out.append((day, r, ev, to_row(
            r, method,
            event_time_from=start, event_time_to=start + dt.timedelta(days=1),
            subject_day=day,
            # REQ-REC-011 / INV-4. The earliest moment this conclusion was AVAILABLE, which is
            # when its evidence landed — not when this job happened to run.
            knowledge_time=last_recorded)))
    return out


def write(cur, rows, *, core="core"):
    written = 0
    for day, r, ev, row in rows:
        cur.execute(f"""INSERT INTO {core}.inferred_events
            (event_family, method_key, method_version, event_time_from, event_time_to,
             subject_day, knowledge_time, tier, presence, rule_score, probability,
             calibration_ref, alternatives, no_alternative_generator, unresolved_ambiguity,
             author, inferred_inputs)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING event_id""",
            (row["event_family"], row["method_key"], row["method_version"],
             row["event_time_from"], row["event_time_to"], row["subject_day"],
             row["knowledge_time"], row["tier"], row["presence"], row["rule_score"],
             row["probability"], row["calibration_ref"], json.dumps(row["alternatives"]),
             row["no_alternative_generator"], row["unresolved_ambiguity"], row["author"],
             # REQ-REC-016. Which inputs were themselves conclusions; 0066's CHECK reads it.
             row["inferred_inputs"]))
        event_id = cur.fetchone()[0]
        # REQ-REC-012. Every citation, so `get_reconstruction` can show what it stood on.
        for e in ev:
            # `evidence_ref` is GENERATED from coalesce(atom_id, external_ref) and cannot be
            # written; the citation goes in `external_ref`. There is no `evidence_kind` column,
            # so the kind travels in `note` — it is what `get_reconstruction` renders and what
            # makes "which required input was this" answerable from the stored row.
            cur.execute(f"""INSERT INTO {core}.event_evidence
                (event_id, external_ref, stance, origin_group, recorded_at, note)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (event_id, e.ref, e.stance, e.origin_group, e.recorded_at, e.kind))
        written += 1
    return written


def live_methods(cur, *, config="config"):
    """Every registered, unretired method key. RULE-13: the registry is the list, not this file."""
    cur.execute(f"""SELECT DISTINCT method_key FROM {config}.reconstruction_methods
                     WHERE retired_at IS NULL ORDER BY method_key""")
    return [r[0] for r in cur.fetchall()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--method", default="watch_non_wear")
    ap.add_argument("--all-methods", action="store_true",
                    help="run every registered method; a clean no-op when none is registered "
                         "(this is the scheduled mode)")
    ap.add_argument("--core", default="core")
    ap.add_argument("--config", default="config")
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args()

    conn = db.connect()
    cur = conn.cursor()
    try:
        if a.all_methods:
            keys = live_methods(cur, config=a.config)
            if not keys:
                # A CLEAN NO-OP, NOT A FAILURE. This is the scheduled mode, and an empty
                # registry is the correct state of a database where the method migrations have
                # not been applied yet — which is exactly production today. RULE-13 says an
                # unregistered method may not run; running none of them is that rule being
                # obeyed, so it must not turn the nightly red.
                print("no registered reconstruction methods — nothing to run (RULE-13)")
                return 0
        else:
            keys = [a.method]

        total = 0
        for key in keys:
            method = load_method(cur, key, core=a.core, config=a.config)
            coverage: list = []
            rows = rows_for(cur, method, core=a.core, since=a.since, until=a.until,
                            coverage=coverage)
            by_presence: dict = {}
            for _, r, _, _ in rows:
                by_presence[(r.presence, r.reason)] = by_presence.get((r.presence, r.reason),
                                                                      0) + 1
            print(f"method {method.key} v{method.version} ({method.event_family}), "
                  f"requires {list(method.required_evidence)}")
            for (presence, reason), n in sorted(by_presence.items()):
                print(f"  {presence:<14} {reason:<28} {n}")
            if rows:
                days = [d for d, _, _, _ in rows]
                print(f"  span {min(days)} .. {max(days)}")
            # Coverage is REPORTED, never stored. A day this method cannot speak to is the
            # default state of every day nobody examined, and a row saying so asserts nothing.
            if coverage:
                print(f"  {len(coverage)} day(s) examined without a conclusion "
                      f"({min(coverage)} .. {max(coverage)}) — reported, not stored")
            if a.commit:
                total += write(cur, rows, core=a.core)

        if not a.commit:
            print("\nDRY RUN — nothing written. Re-run with --commit.")
            return 0
        conn.commit()
        print(f"\nCOMMITTED {total} inferred event(s) with their evidence.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
