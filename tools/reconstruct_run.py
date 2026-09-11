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
import re
import sys

from lib import db
from tools.engines.reconstruct import Evidence, Method, evaluate, to_row

class NoGatherer(Exception):
    """A registered method this runner cannot collect evidence for.

    Not a failure and not a silent success. `sleep_gap_explained` is registered by 0067 and its
    evidence (`sleep_record_absent`, `watch_non_wear_inferred`) is collected by
    `tools/reconstruction_acceptance.py`, not here. Before this existed, `--all-methods` ran it
    through the device-capture gatherer, which supplies neither input, so every day came back
    `required_evidence_missing` and was reported as "examined without a conclusion" — a no-op
    presented as a measurement. Raising turns that into one visible line; `main` keeps going, so
    the scheduled job does not go red over a method nobody claimed this tool ran.
    """


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


def training_days(cur, *, core="core", since=None, until=None):
    """ONE ROW PER RECORDED SESSION, with what else that day holds.

    **It is one row per session, not per day, and that was a deliberate correction.** Grouping by
    subject day made 32 real records into 30 events, because 2023-04-05 and 2023-09-23 each carry
    a lift AND a run, hours apart. Nothing was lost — all 32 atoms are stored either way — but an
    event count would then silently be two short of a session count, and a surface reporting
    "30 training sessions" would be wrong about a number nobody could check without re-reading
    the atoms. R2 asks to reconstruct a SESSION; this reconstructs a session.

    `workout_session_min` atoms are written by `tools/importers/apple_health.py` from the
    export's `<Workout>` elements.

    IT DOES NOT READ THE DURATIONS. The reconstruction concludes that a session occurred; the
    minutes stay in the measured lane where they were recorded (INV-5). Copying them onto the
    inferred event would put a measured number in an inferred row and give a reader two places
    to find one fact, which is how the two disagree later.
    """
    cur.execute(f"""
        SELECT w.id                                        AS atom_id,
               w.subject_day,
               lower(w.valid_interval)                     AS started_at,
               upper(w.valid_interval)                     AS ended_at,
               w.recorded_at                               AS last_recorded,
               -- The activity type lives in `evidence_span`, the way the record type and
               -- device do for every Apple Health atom. One representation, not two.
               w.evidence_span                             AS spans,
               -- Corroboration from the SAME export. Counted as a citation and deliberately
               -- NOT as an independent origin; see `training_evidence`.
               (SELECT count(*) FROM {core}.atoms x
                 WHERE x.subject_day = w.subject_day
                   AND x.metric_key = 'exercise_minutes')  AS n_exercise,
               -- Corroboration from a DIFFERENT capture path. This is the only thing here that
               -- can raise the tier, and this system has never captured one.
               (SELECT count(*) FROM {core}.atoms x
                 WHERE x.subject_day = w.subject_day
                   AND x.kind = 'place_visit')             AS n_place_visit
          FROM {core}.atoms w
         WHERE w.kind = 'workout'
           AND w.metric_key = 'workout_session_min'
           AND w.subject_day IS NOT NULL
           AND (%s::date IS NULL OR w.subject_day >= %s::date)
           AND (%s::date IS NULL OR w.subject_day <= %s::date)
         ORDER BY lower(w.valid_interval)
    """, (since, since, until, until))
    return cur.fetchall()


ACTIVITY = re.compile(r"apple_health:HKWorkoutActivityType([A-Za-z]+)")


def activities_in(spans):
    """The activity types recorded on a day, read out of the citations' own evidence spans.

    The type is not a column and deliberately does not become one: it lives in `evidence_span`
    exactly as the record type and source device do for every Apple Health atom, so there is one
    representation of it rather than two that can drift.
    """
    return tuple(sorted(set(ACTIVITY.findall(spans or ""))))


def training_evidence(day, *, atom_id=None, activities=(), n_exercise, n_place_visit,
                      last_recorded):
    """One training day's capture state -> citations.

    THE ACTIVITY TYPE IS CARRIED IN THE CITATION, and the method does not rank activities. A
    recorded walk and a recorded lift both produce `occurred` for *a recorded workout session*.
    Deciding that 25 minutes of walking is not "training" while 26 minutes of cycling is would be
    inventing a measurement definition, which is Joe's (OQ-81). What this owes the reader instead
    is the type, in the evidence, where a correction can act on it.

    **THE EXERCISE MINUTES SHARE THE SESSION'S ORIGIN AND CANNOT PROMOTE IT.** Both come out of
    one HealthKit export, so `origin_group` is the same string for both, and
    `independent_origins` counts them once. This is REQ-REC-008 doing its job rather than being
    asserted: without it, every session would arrive with two "independent" supports and be
    promoted to EXPLORATORY on what is one observation read twice — the identical defect that
    put 34 non-wear episodes at EXPLORATORY before it was caught.

    The consequence is worth stating plainly rather than engineering around: **every session
    reconstructed from this export alone lands at DESCRIPTIVE.** A gym `place_visit` is a
    genuinely different capture path and would promote it. This system has never captured one.
    """
    origin = f"healthkit_export:{day.isoformat()}"
    label = ",".join(activities) if activities else "unspecified"
    # THE CITATION NAMES THE SESSION'S OWN ATOM. `event_evidence`'s primary key is
    # (event_id, origin_group, evidence_ref), so a day-wide reference would make the lift and
    # the run on 2023-04-05 the same citation.
    ev = [Evidence(ref=f"atoms:{atom_id or day.isoformat()}:workout_session:{label}",
                   kind="workout_session_record", stance="supports",
                   origin_group=origin, recorded_at=last_recorded)]
    if n_exercise:
        ev.append(Evidence(ref=f"atoms:{day.isoformat()}:exercise_minutes",
                           kind="exercise_minutes_same_day", stance="supports",
                           origin_group=origin,          # SAME export: not a second origin
                           recorded_at=last_recorded))
    if n_place_visit:
        ev.append(Evidence(ref=f"atoms:{day.isoformat()}:place_visit",
                           kind="place_visit_same_day", stance="supports",
                           origin_group=f"location_capture:{day.isoformat()}",
                           recorded_at=last_recorded))
    return tuple(ev)


def rows_for_training(cur, method, *, core="core", since=None, until=None, coverage=None):
    """Training-session rows to store (R2, REQ-REC-004/005/009).

    WHAT THIS REFUSES TO PRODUCE. No load, no reps, no volume, no e1RM, and no opinion about
    whether a short session "really counts". The session record carries a duration and nothing
    else about the training; `strength_load_lb`, `strength_reps` and `strength_rpe` have been
    registered since B18 and have never received a row. A caller asking for a derived strength
    measure is refused by `public.derivation_support` (0068), which names the missing inputs.
    """
    out = []
    unknown = coverage if coverage is not None else []
    for (atom_id, day, started_at, ended_at, last_recorded, spans, n_exercise,
         n_place_visit) in training_days(cur, core=core, since=since, until=until):
        ev = training_evidence(day, atom_id=atom_id, activities=activities_in(spans),
                               n_exercise=n_exercise, n_place_visit=n_place_visit,
                               last_recorded=last_recorded)
        r = evaluate(method, ev, as_of=last_recorded)
        if r.presence == "unknown":
            # Same rule as every other method: an unknown is not a conclusion, and
            # `inferred_events` stores conclusions. Reported, not written.
            unknown.append(day)
            continue
        # The event's time is THE SESSION'S OWN wall-clock span, not midnight to midnight. The
        # day-wide interval the first version used was wrong twice over: it claimed a 24-hour
        # extent for a 90-minute event, and it made two sessions on one day indistinguishable.
        out.append((day, r, ev, to_row(
            r, method,
            event_time_from=started_at, event_time_to=ended_at,
            subject_day=day,
            knowledge_time=last_recorded)))
    return out


def rows_for(cur, method, *, core="core", since=None, until=None, coverage=None):
    """Rows to store, dispatched on the method. `coverage`, if given a list, receives the days
    examined without a conclusion — reported rather than stored, so coverage stays answerable
    without filling the event table with rows that assert nothing.

    DISPATCH IS EXPLICIT AND AN UNKNOWN METHOD RAISES. Before this, every method key ran the
    device-capture gatherer regardless of what it declared, so `--all-methods` fed
    `sleep_gap_explained` evidence it does not accept and reported every day it examined as
    inconclusive — a no-op that looked like a measurement. A method with no gatherer is now a
    visible error rather than a quiet nothing.
    """
    if method.key == "training_session":
        return rows_for_training(cur, method, core=core, since=since, until=until,
                                 coverage=coverage)
    if method.key != "watch_non_wear":
        raise NoGatherer(method.key)
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
             author, inferred_inputs, discriminating_evidence, no_discriminating_evidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING event_id""",
            (row["event_family"], row["method_key"], row["method_version"],
             row["event_time_from"], row["event_time_to"], row["subject_day"],
             row["knowledge_time"], row["tier"], row["presence"], row["rule_score"],
             row["probability"], row["calibration_ref"], json.dumps(row["alternatives"]),
             row["no_alternative_generator"], row["unresolved_ambiguity"], row["author"],
             # REQ-REC-016. Which inputs were themselves conclusions; 0066's CHECK reads it.
             row["inferred_inputs"],
             # REQ-REC-015. What would settle it, or an explicit statement that nothing would.
             row["discriminating_evidence"], row["no_discriminating_evidence"]))
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
            try:
                rows = rows_for(cur, method, core=a.core, since=a.since, until=a.until,
                                coverage=coverage)
            except NoGatherer:
                # Said out loud, and counted as nothing. REQ-REC-004: a method whose inputs
                # nothing collects has not run, and must not be reported as though it had.
                print(f"method {method.key} v{method.version} ({method.event_family}): "
                      f"NOT RUN — this tool collects no evidence for it")
                continue
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
