"""R2: a recorded training session becomes a reconstructed event (REQ-WKT-001/002/003,
REQ-REC-004/005/008/009; ADR-0138).

    <Workout> in the export -> measured atom -> registered method -> stored inferred event

WHY THIS FILE EXISTS. `tools/importers/apple_health.py` counted every `<Workout>` element and
threw it away (`workout_deferred_to_B18`). The 2026-09-10 checkpoint recorded R2 as "pending
observation, not missing implementation"; that was wrong. Thirty-two sessions sit in the export
and production holds zero workout-session atoms, because the parser dropped them.

THE LINE THESE TESTS DEFEND. A session record says a workout WAS RECORDED and how long it ran.
It says nothing about what was lifted. No set has ever been logged, and several tests here exist
only to prove that no amount of session evidence produces a load, a rep count or a volume.

Fixtures are SYNTHETIC XML mirroring the shapes the real export contains (a paused session, a
session abandoned seconds after starting). No personal data is committed (RULE-29).
"""
import datetime as dt
import os
import re
import uuid
from xml.etree import ElementTree as ET

import pytest

from tests._sql_fixture import ROOT, sql_connection
from tools.importers import apple_health as ah
from tools.reconstruct_run import (NoGatherer, load_method, rows_for, training_evidence, write)
from tools.run_migration import split_statements

S = "wkt_core_pytest"


# --- synthetic export fixtures ----------------------------------------------------------
# Shapes taken from the real export's STRUCTURE, with invented times and values.

def workout_xml(*, activity="HKWorkoutActivityTypeTraditionalStrengthTraining",
                start="2026-03-02 10:00:00 -0500", end="2026-03-02 11:30:00 -0500",
                duration="90.0", duration_unit="min", source="Joseph's Apple Watch",
                stats=(), events=()):
    parts = [f'<Workout workoutActivityType="{activity}" duration="{duration}" '
             f'durationUnit="{duration_unit}" sourceName="{source}" '
             f'startDate="{start}" endDate="{end}">']
    for t, d in events:
        parts.append(f'<WorkoutEvent type="{t}" date="{d}"/>')
    for t, attr, value, unit in stats:
        parts.append(f'<WorkoutStatistics type="{t}" {attr}="{value}" unit="{unit}"/>')
    parts.append("</Workout>")
    return ET.fromstring("".join(parts))


def parse_one(elem):
    c = ah.Counters()
    return ah._workout(elem, c), c


# --- the importer -----------------------------------------------------------------------

def test_REQ_WKT_001_a_recorded_workout_becomes_a_measured_session_atom():
    """The element the importer used to discard now becomes an atom in the `workout` lane."""
    specs, c = parse_one(workout_xml())
    assert len(specs) == 1, "one session, no statistics supplied"
    s = specs[0]
    assert s.kind == "workout"
    assert s.metric_key == "workout_session_min"
    assert s.value == 90.0
    assert s.unit == "min"
    # RULE-05 / INV-5: the Watch measured this. A measured atom is a point, which
    # `atoms_measured_is_point` enforces in the schema.
    assert s.estimate_method == "measured"
    assert s.state_class == "measurement"
    assert s.presence == "observed"
    # The activity type travels in the evidence, as the record type does for every sample.
    assert "TraditionalStrengthTraining" in s.evidence_span
    assert c["workout_session:strength_training"] == 1


def test_REQ_WKT_002_the_recorded_duration_is_never_the_wall_clock_span():
    """The real 2023-02-26 shape: paused at 16:36, resumed at 19:38, 185 active minutes in a
    375-minute span. Reading the span as the session reports training that never happened."""
    specs, _ = parse_one(workout_xml(
        start="2026-03-02 14:56:13 -0500", end="2026-03-02 21:11:56 -0500",
        duration="185.2316313008467",
        events=(("HKWorkoutEventTypePause", "2026-03-02 16:36:52 -0500"),
                ("HKWorkoutEventTypeResume", "2026-03-02 19:38:32 -0500"))))
    s = specs[0]
    span_minutes = (s.interval_end - s.interval_start).total_seconds() / 60
    assert round(span_minutes) == 376, "the wall-clock span is preserved as the interval"
    assert round(s.value, 1) == 185.2, "the VALUE is the recorded active duration"
    # The whole point: these are two different facts and the atom keeps both.
    assert s.value < span_minutes
    assert abs(span_minutes - s.value) > 180


def test_REQ_WKT_002_an_abandoned_session_is_stored_as_recorded_not_filtered():
    """The real 2025-07-29 shape: started, paused eleven seconds later, closed 10.5 hours on.

    It is plainly not a training session, and it is plainly a real record of what the Watch
    did. Filtering it here would be the importer inventing a minimum-duration definition of
    "a workout", which is a measurement definition and therefore Joe's (OQ-81), not a parser's.
    """
    specs, c = parse_one(workout_xml(
        start="2026-03-02 08:53:18 -0500", end="2026-03-02 19:26:48 -0500",
        duration="0.1753489991029104",
        stats=(("HKQuantityTypeIdentifierActiveEnergyBurned", "sum", "0.537082", "Cal"),)))
    assert len(specs) == 2
    session = next(s for s in specs if s.metric_key == "workout_session_min")
    assert round(session.value, 3) == 0.175, "stored exactly as recorded"
    assert c["workout_session:strength_training"] == 1
    # Its own numbers say what it was; nothing here judges it.
    energy = next(s for s in specs if s.metric_key == "workout_active_energy_kcal")
    assert round(energy.value, 3) == 0.537


def test_REQ_WKT_001_session_statistics_share_the_sessions_origin():
    """Active energy and average heart rate become atoms against the session's interval."""
    specs, _ = parse_one(workout_xml(stats=(
        ("HKQuantityTypeIdentifierActiveEnergyBurned", "sum", "751.909", "Cal"),
        ("HKQuantityTypeIdentifierHeartRate", "average", "88.1745", "count/min"))))
    keys = {s.metric_key for s in specs}
    assert keys == {"workout_session_min", "workout_active_energy_kcal", "workout_hr_avg_bpm"}
    # One Watch record, read once: every atom carries the same session interval.
    assert len({(s.interval_start, s.interval_end) for s in specs}) == 1
    assert all(s.estimate_method == "measured" for s in specs)


def test_REQ_WKT_001_a_missing_statistic_is_absent_not_zero():
    """A session with no heart-rate statistic yields no heart-rate atom. Missing is not zero."""
    specs, _ = parse_one(workout_xml(stats=(
        ("HKQuantityTypeIdentifierActiveEnergyBurned", "sum", "300.0", "Cal"),)))
    assert {s.metric_key for s in specs} == {"workout_session_min", "workout_active_energy_kcal"}
    assert not any(s.metric_key == "workout_hr_avg_bpm" for s in specs)
    assert not any(s.value == 0 for s in specs)


def test_REQ_WKT_001_an_unmapped_activity_is_counted_by_name_never_guessed():
    specs, c = parse_one(workout_xml(activity="HKWorkoutActivityTypeSurfing"))
    assert specs == ()
    assert c["workout_type_not_mapped:HKWorkoutActivityTypeSurfing"] == 1


def test_REQ_WKT_001_a_duration_in_an_unexpected_unit_is_refused_not_converted():
    """RULE-06: the unit is read from the file, never assumed. A gap, not a plausible value."""
    specs, c = parse_one(workout_xml(duration="5400", duration_unit="s"))
    assert specs == ()
    assert c["workout_unconvertible_duration_unit:s"] == 1


def test_REQ_WKT_001_dedupe_keys_distinguish_two_activities_in_one_interval():
    """A run and a lift recorded over the same window are two facts, not a duplicate."""
    a, _ = parse_one(workout_xml(activity="HKWorkoutActivityTypeRunning"))
    b, _ = parse_one(workout_xml(activity="HKWorkoutActivityTypeTraditionalStrengthTraining"))
    assert a[0].dedupe_key != b[0].dedupe_key


def test_REQ_WKT_001_parse_yields_workout_atoms_instead_of_counting_them_away():
    """THE ACTUAL DEFECT, through the actual entry point.

    `_workout` existing is not the fix; `parse()` emitting what it produces is. The old loop
    reached a `<Workout>` element, ran `c.bump("workout_deferred_to_B18")` and yielded nothing,
    so a test that only called the parser directly would have passed over the real bug. This
    walks a whole miniature export through the public `parse()`.
    """
    import io
    export = (
        '<HealthData>'
        '<Record type="HKQuantityTypeIdentifierAppleExerciseTime" unit="min" value="64"'
        ' startDate="2026-03-02 10:00:00 -0500" endDate="2026-03-02 10:01:00 -0500"'
        ' sourceName="Joseph\'s Apple Watch"/>'
        '<Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining"'
        ' duration="90.0" durationUnit="min" sourceName="Joseph\'s Apple Watch"'
        ' startDate="2026-03-02 10:00:00 -0500" endDate="2026-03-02 11:30:00 -0500">'
        '<WorkoutStatistics type="HKQuantityTypeIdentifierActiveEnergyBurned" sum="300.0"'
        ' unit="Cal"/>'
        '</Workout>'
        '</HealthData>')
    c = ah.Counters()
    specs = list(ah.parse(io.BytesIO(export.encode()), counters=c))
    workouts = [s for s in specs if s.kind == "workout"]
    assert len(workouts) == 2, "the session and its energy statistic both reach the caller"
    assert {s.metric_key for s in workouts} == {"workout_session_min",
                                               "workout_active_energy_kcal"}
    # The counter that used to be the ONLY trace of a workout is gone as a discard reason.
    assert "workout_deferred_to_B18" not in c
    # The ordinary record alongside it is unaffected.
    assert any(s.metric_key == "exercise_minutes" for s in specs)


def test_REQ_WKT_001_a_workout_outside_the_window_is_counted_not_yielded():
    """`--since` bounds workouts exactly as it bounds every other record."""
    import io
    export = (
        '<HealthData>'
        '<Workout workoutActivityType="HKWorkoutActivityTypeTraditionalStrengthTraining"'
        ' duration="90.0" durationUnit="min" sourceName="Watch"'
        ' startDate="2023-03-02 10:00:00 -0500" endDate="2023-03-02 11:30:00 -0500"/>'
        '</HealthData>')
    c = ah.Counters()
    specs = list(ah.parse(io.BytesIO(export.encode()), since=dt.date(2026, 1, 1), counters=c))
    assert specs == []
    assert c["outside_window"] == 1


# --- the reconstruction, through the real runner ----------------------------------------

def rebind(sql):
    sql = sql.replace("__CORE__", S).replace("__OPS__", "ops_pytest")
    for schema in ("public", "analysis", "config", "auth"):
        sql = re.sub(rf"\b{schema}\.", f"{schema}_pytest.", sql)
        sql = re.sub(rf"\bSCHEMA {schema}\b", f"SCHEMA {schema}_pytest", sql)
    return sql


@pytest.fixture
def wkt(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only")
    c = sql_connection.cursor()
    for schema in (S, "analysis_pytest", "config_pytest", "auth_pytest", "public_pytest",
                   "ops_pytest"):
        c.execute(f"CREATE SCHEMA {schema}")
    # The migrations GRANT to Supabase's roles. A disposable server has neither, and creating
    # them is part of building the real DDL rather than a weakened version of it.
    for role in ("anon", "authenticated"):
        c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if c.fetchone() is None:
            c.execute(f"CREATE ROLE {role}")
    for f in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
              "0054_inferred_events.sql", "0066_inferred_inputs.sql",
              "0069_discriminating_evidence.sql",
              # The migration under test: the three registry keys and the third method.
              "0070_workout_sessions.sql"):
        for stmt in split_statements((ROOT / "migrations" / f).read_text()):
            c.execute(rebind(stmt))
    c.execute(f"""INSERT INTO {S}.metric_registry
                  (metric_key, display_name, family, unit, state_class)
                  VALUES ('exercise_minutes','Exercise minutes','activity','min','total')
                  ON CONFLICT DO NOTHING""")
    return c


def write_atom(c, *, day, metric, value, unit, kind="workout", recorded=None, span=None,
               hour=15):
    cid, aid = uuid.uuid4(), uuid.uuid4()
    c.execute(f"""INSERT INTO {S}.raw_captures (capture_id, source, captured_at, payload,
                  trust_level) VALUES (%s,'healthkit_workout',%s,'{{}}'::jsonb,'trusted')""",
              (cid, dt.datetime(2026, 3, 2, tzinfo=dt.timezone.utc)))
    start = dt.datetime.combine(day, dt.time(hour), dt.timezone.utc)
    c.execute(f"""INSERT INTO {S}.atoms
        (id, raw_capture_id, kind, metric_key, occurred_at, valid_interval, subject_day,
         subject_day_rule_version, recorded_at, presence, value_low, value_point, value_high,
         estimate_method, unit, state_class, value_type, trust_level, provenance,
         evidence_span, code_version)
        VALUES (%s,%s,%s,%s,NULL,tstzrange(%s,%s,'[)'),%s,'v1',%s,'observed',%s,%s,%s,
                'measured',%s,'measurement','numeric','trusted','extracted',%s,'test')""",
        (aid, cid, kind, metric, start, start + dt.timedelta(minutes=90), day,
         recorded or start + dt.timedelta(days=1), value, value, value, unit,
         span or "apple_health:HKWorkoutActivityTypeTraditionalStrengthTraining;source=Watch"))
    return aid


def test_REQ_REC_004_training_session_is_read_from_the_registry_not_from_python(wkt):
    """RULE-13. The method's declaration comes out of the database that 0070 wrote."""
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    assert m.event_family == "training_session"
    assert m.required_evidence == ("workout_session_record",)
    # REQ-REC-009 by construction: there is no output the engine could use to say it did not
    # happen, so no evidence state can produce one.
    assert m.permissible_outputs == ("occurred",)
    assert "did_not_occur" not in m.permissible_outputs
    assert m.temporal_specification == "interval"


def test_REQ_REC_005_a_recorded_session_is_stored_as_an_occurred_training_event(wkt):
    """The whole chain, through the production writer: atom -> runner -> stored row."""
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=90, unit="min")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    rows = rows_for(wkt, m, core=S)
    assert len(rows) == 1
    _, r, _, _ = rows[0]
    assert r.presence == "occurred"
    assert write(wkt, rows, core=S) == 1

    wkt.execute(f"""SELECT event_family, method_key, presence, tier, subject_day
                      FROM {S}.inferred_events WHERE method_key='training_session'""")
    stored = wkt.fetchall()
    assert len(stored) == 1
    family, key, presence, tier, subject_day = stored[0]
    assert (family, key, presence) == ("training_session", "training_session", "occurred")
    assert subject_day == day


def test_REQ_REC_008_exercise_minutes_from_the_same_export_cannot_promote_the_tier(wkt):
    """One HealthKit export read twice is ONE origin.

    This is the defect that put 34 non-wear episodes at EXPLORATORY on a single observation.
    Exercise minutes corroborate the session in the ordinary sense and share its origin, so the
    engine counts one independent support and the session stays DESCRIPTIVE.
    """
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=90, unit="min")
    write_atom(wkt, day=day, metric="exercise_minutes", value=64, unit="min",
               kind="activity_sample", span="apple_health:AppleExerciseTime;source=Watch")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    rows = rows_for(wkt, m, core=S)
    _, r, ev, _ = rows[0]
    assert len(ev) == 2, "both are cited"
    assert len({e.origin_group for e in ev}) == 1, "and both came out of one export"
    assert r.independent_support == 1
    assert r.tier == "DESCRIPTIVE", "two citations from one origin are not two corroborations"


def test_REQ_REC_005_the_activity_type_reaches_the_citation(wkt):
    """The type is readable from the stored evidence without a second column to drift.

    And no activity outranks another: a recorded walk and a recorded lift both conclude that a
    workout session occurred. Ruling that one is "training" and the other is not is a
    measurement definition, and it is Joe's (OQ-81).
    """
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=90, unit="min",
               span="apple_health:HKWorkoutActivityTypeTraditionalStrengthTraining;source=Watch")
    write_atom(wkt, day=day, metric="workout_session_min", value=15, unit="min",
               span="apple_health:HKWorkoutActivityTypeWalking;source=Watch")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    rows = rows_for(wkt, m, core=S)
    assert len(rows) == 2, "two recorded sessions are two events, even on one day"
    refs = [next(e for e in ev if e.kind == "workout_session_record").ref
            for _, _, ev, _ in rows]
    assert any("TraditionalStrengthTraining" in r for r in refs)
    assert any("Walking" in r for r in refs), "the walk is its own event, not folded in"
    assert all(r.presence == "occurred" for _, r, _, _ in rows)
    # Still one origin each: one export is not two corroborations.
    assert all(r.independent_support == 1 for _, r, _, _ in rows)


def test_REQ_REC_009_a_day_with_no_session_record_is_never_did_not_occur(wkt):
    """Absence of a record is absence of capture. The Watch stopped; Joe did not necessarily."""
    write_atom(wkt, day=dt.date(2026, 3, 2), metric="workout_session_min", value=90, unit="min")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    rows = rows_for(wkt, m, core=S)
    write(wkt, rows, core=S)
    # 2026-03-03 has no session record at all. Nothing is stored about it, and in particular
    # nothing saying Joe did not train.
    wkt.execute(f"""SELECT count(*) FROM {S}.inferred_events WHERE subject_day = %s""",
                (dt.date(2026, 3, 3),))
    assert wkt.fetchone()[0] == 0
    wkt.execute(f"""SELECT count(*) FROM {S}.inferred_events WHERE presence = 'did_not_occur'""")
    assert wkt.fetchone()[0] == 0


def test_REQ_REC_005_two_sessions_on_one_day_are_two_events_not_one(wkt):
    """THE 32-INTO-30 QUESTION, locked so it cannot silently come back.

    The real export holds 32 session records on 30 distinct subject days: 2023-04-05 carries a
    120-minute lift at 14:06 and a 7.8-minute run at 21:10, and 2023-09-23 carries a 39.8-minute
    lift and a 27.7-minute run. Grouping by subject day lost neither atom — both are stored —
    but it made the event count two short of the session count, so any surface counting events
    would under-report training and nobody could see the discrepancy without re-reading atoms.

    An event count and a session count must be the same number.
    """
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=120.31, unit="min",
               span="apple_health:HKWorkoutActivityTypeTraditionalStrengthTraining;source=Watch")
    write_atom(wkt, day=day, metric="workout_session_min", value=7.83, unit="min", hour=21,
               span="apple_health:HKWorkoutActivityTypeRunning;source=Watch")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    rows = rows_for(wkt, m, core=S)
    assert write(wkt, rows, core=S) == 2

    wkt.execute(f"""SELECT count(*) FROM {S}.atoms WHERE metric_key='workout_session_min'""")
    n_sessions = wkt.fetchone()[0]
    wkt.execute(f"""SELECT count(*) FROM {S}.inferred_events
                     WHERE method_key='training_session'""")
    n_events = wkt.fetchone()[0]
    assert n_sessions == n_events == 2, "one event per recorded session, no more and no fewer"

    # And each event is timed by its OWN span, not by the day.
    wkt.execute(f"""SELECT event_time_from, event_time_to FROM {S}.inferred_events
                     WHERE method_key='training_session' ORDER BY event_time_from""")
    spans = wkt.fetchall()
    assert spans[0][0] != spans[1][0], "two events, two different start times"
    for start, end in spans:
        assert (end - start) < dt.timedelta(hours=3), (
            "the event lasts as long as the session, not all day")

    # Two sessions out of one export remain ONE origin apiece.
    wkt.execute(f"""SELECT max(independent_support) FROM {S}.v_event_independence""")
    assert wkt.fetchone()[0] == 1


def test_REQ_WKT_003_a_session_reconstruction_yields_no_load_reps_or_volume(wkt):
    """No quantity of session evidence produces a set. This is the R2 line.

    `strength_load_lb`, `strength_reps` and `strength_rpe` have been registered since B18 and
    have never received a row, because the Log Workout shortcut is not installed. A session
    record carries a duration; it does not carry what was on the bar.
    """
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=90, unit="min")
    write_atom(wkt, day=day, metric="workout_active_energy_kcal", value=751.9, unit="kcal")
    write_atom(wkt, day=day, metric="workout_hr_avg_bpm", value=88.2, unit="bpm")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    write(wkt, rows_for(wkt, m, core=S), core=S)

    # Nothing in the strength lane was created by reconstructing a session.
    wkt.execute(f"""SELECT count(*) FROM {S}.atoms
                     WHERE metric_key IN ('strength_load_lb','strength_reps','strength_rpe')""")
    assert wkt.fetchone()[0] == 0, "a session record must never stand in for a set"
    # And the method is not permitted to describe one: its family is the session, and its only
    # permissible output is that the session occurred.
    assert m.permissible_outputs == ("occurred",)


def test_REQ_REC_005_the_stored_event_is_findable_with_its_measured_duration(wkt):
    """Provenance: the stored conclusion points back at the day whose measured duration
    remains readable in the atom lane. The reconstruction never restates the number."""
    day = dt.date(2026, 3, 2)
    write_atom(wkt, day=day, metric="workout_session_min", value=185.2, unit="min")
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    write(wkt, rows_for(wkt, m, core=S), core=S)
    wkt.execute(f"""SELECT e.subject_day, a.value_point, a.unit, a.estimate_method
                      FROM {S}.inferred_events e
                      JOIN {S}.atoms a ON a.subject_day = e.subject_day
                     WHERE e.method_key = 'training_session'
                       AND a.metric_key = 'workout_session_min'""")
    subject_day, value, unit, method = wkt.fetchone()
    assert subject_day == day
    assert float(value) == 185.2 and unit == "min"
    # INV-5: the duration stays in the measured lane. The event is the inference; the minutes
    # are not.
    assert method == "measured"


def test_REQ_REC_004_a_registered_method_with_no_gatherer_is_not_reported_as_run(wkt):
    """A no-op must not look like a measurement.

    `--all-methods` used to feed every registered method the device-capture gatherer, so a
    method whose inputs nothing collects came back "examined without a conclusion" for every
    day it touched. That reads as a result. It is now a named refusal.
    """
    wkt.execute("""INSERT INTO config_pytest.reconstruction_methods
        (method_key, method_version, event_family, required_evidence, permissible_outputs,
         temporal_specification, note)
        VALUES ('not_collected_here',1,'other',ARRAY['nothing'],ARRAY['occurred'],
                'subject_day','a method this runner collects no evidence for')""")
    m = load_method(wkt, "not_collected_here", core=S, config="config_pytest")
    with pytest.raises(NoGatherer):
        rows_for(wkt, m, core=S)


def test_REQ_REC_008_a_place_visit_is_a_different_origin_and_does_promote(wkt):
    """The corroboration R2 actually names: a gym visit is a different capture path.

    Stated plainly because it matters for reading the output: this system has never captured a
    `place_visit`, so every session reconstructed from the export alone is DESCRIPTIVE. The
    promotion path is real and currently unexercised by real data.
    """
    day = dt.date(2026, 3, 2)
    ev = training_evidence(day, atom_id="a-1", activities=("TraditionalStrengthTraining",),
                           n_exercise=0, n_place_visit=1,
                           last_recorded=dt.datetime(2026, 3, 3, tzinfo=dt.timezone.utc))
    assert len({e.origin_group for e in ev}) == 2, "the gym visit is a second origin"
    m = load_method(wkt, "training_session", core=S, config="config_pytest")
    from tools.engines.reconstruct import evaluate
    r = evaluate(m, ev, as_of=dt.datetime(2026, 3, 4, tzinfo=dt.timezone.utc))
    assert r.presence == "occurred"
    assert r.independent_support == 2
    assert r.tier == "EXPLORATORY"
