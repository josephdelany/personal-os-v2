"""Apple Health `export.xml` -> AtomSpec (B13, ADR-0058).

The export is a single XML document, hundreds of megabytes, with one `<Record>` element per
sample and seven years of them. It is parsed with `iterparse` and each element is cleared as
soon as it is consumed, so peak memory is a function of the widest element, not of the file.
Loading it whole is the obvious way to write this and would need several gigabytes.

Two things this module refuses to do:

* **It never converts a unit by assumption.** Apple writes the unit into every record and it
  is locale-dependent — the same `HKQuantityTypeIdentifierBodyMass` arrives as `lb` on one
  phone and `kg` on another. Every conversion below is keyed on the unit string Apple
  actually wrote. A record whose unit is not in the table for its type is skipped and
  counted as unconvertible, never guessed at (RULE-06: a gap, not a plausible value).
* **It never clamps.** A value outside the registry's instrument range is dropped and
  counted, because a clamped reading is a fabricated one (RULE-01).

Sleep is the one type that becomes an interval atom: each `<Record>` of
`HKCategoryTypeIdentifierSleepAnalysis` is one stage segment, kept as its own atom with
`valid_interval` = [start, end) and value = its duration in minutes. Its subject day is the
**wake** day (ADR-0058) — the night beginning 23:40 on the 8th is the 9th's sleep.
"""
import datetime as dt
import re
from xml.etree import ElementTree as ET

from tools.importers.common import AtomSpec, subject_day

CODE_VERSION = "import-apple-health-v1"

# Apple writes "2026-09-08 10:00:00 -0400".
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ([+-]\d{4})$")


def parse_ts(s: str):
    """Apple's timestamp format -> aware datetime, or None if it is not that format."""
    if not s:
        return None
    m = _TS.match(s.strip())
    if not m:
        return None
    naive = dt.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    off = m.group(2)
    delta = dt.timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
    if off[0] == "-":
        delta = -delta
    return naive.replace(tzinfo=dt.timezone(delta))


# --- unit conversion -------------------------------------------------------------------
# Keyed on the unit string Apple wrote. `None` means the value passes through unchanged.
def _identity(v):
    return v


CONVERSIONS = {
    "count":        _identity,
    "count/min":    _identity,
    "ms":           _identity,
    "min":          _identity,
    "kcal":         _identity,
    "Cal":          _identity,
    "cm":           _identity,
    "in":           lambda v: v * 2.54,
    "lb":           _identity,
    "kg":           lambda v: v * 2.2046226218,
    "km":           _identity,
    "mi":           lambda v: v * 1.609344,
    "m/s":          _identity,
    "km/hr":        lambda v: v / 3.6,
    "mi/hr":        lambda v: v * 0.44704,
    "degC":         _identity,
    "degF":         lambda v: (v - 32.0) * 5.0 / 9.0,
    "%":            _identity,
    "dBASPL":       _identity,
    "mL/min·kg":    _identity,
    "ml/min·kg":    _identity,
}

# HealthKit record type -> (metric_key, unit, state_class, {accepted Apple units}).
# The accepted-unit set is the guard: a record arriving in a unit this type has no
# conversion for is skipped and counted, so a locale change shows up as a reported
# unconvertible count instead of as silently wrong numbers.
HK = {
    "HKQuantityTypeIdentifierStepCount":
        ("steps", "count", "total", {"count"}),
    "HKQuantityTypeIdentifierActiveEnergyBurned":
        ("active_energy_kcal", "kcal", "total", {"kcal", "Cal"}),
    "HKQuantityTypeIdentifierAppleExerciseTime":
        ("exercise_minutes", "min", "total", {"min"}),
    "HKQuantityTypeIdentifierFlightsClimbed":
        ("flights_climbed", "count", "total", {"count"}),
    "HKQuantityTypeIdentifierDistanceWalkingRunning":
        ("walking_running_distance_km", "km", "total", {"km", "mi"}),
    "HKQuantityTypeIdentifierHeartRate":
        ("heart_rate_bpm", "bpm", "measurement", {"count/min"}),
    "HKQuantityTypeIdentifierRestingHeartRate":
        ("resting_hr", "bpm", "measurement", {"count/min"}),
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN":
        ("hrv_sdnn_ms", "ms", "measurement", {"ms"}),
    "HKQuantityTypeIdentifierRespiratoryRate":
        ("respiratory_rate_bpm", "breaths_min", "measurement", {"count/min"}),
    "HKQuantityTypeIdentifierOxygenSaturation":
        ("spo2_pct", "pct", "measurement", {"%"}),
    "HKQuantityTypeIdentifierVO2Max":
        ("vo2max_ml_kg_min", "ml_kg_min", "measurement", {"mL/min·kg", "ml/min·kg"}),
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature":
        ("wrist_temperature_c", "degC", "measurement", {"degC", "degF"}),
    "HKQuantityTypeIdentifierBodyMass":
        ("weight_lb", "lb", "measurement", {"lb", "kg"}),
    "HKQuantityTypeIdentifierWalkingSpeed":
        ("walking_speed_m_s", "m_s", "measurement", {"km/hr", "mi/hr", "m/s"}),
    "HKQuantityTypeIdentifierWalkingStepLength":
        ("walking_step_length_cm", "cm", "measurement", {"cm", "in"}),
    "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage":
        ("walking_double_support_pct", "pct", "measurement", {"%"}),
    "HKQuantityTypeIdentifierWalkingAsymmetryPercentage":
        ("walking_asymmetry_pct", "pct", "measurement", {"%"}),
    "HKQuantityTypeIdentifierAppleWalkingSteadiness":
        ("walking_steadiness_pct", "pct", "measurement", {"%"}),
    "HKQuantityTypeIdentifierHeadphoneAudioExposure":
        ("headphone_audio_exposure_db", "dbA", "measurement", {"dBASPL"}),
}

# HealthKit's percent unit is a 0..1 FRACTION, so a record written with unit="%" is always
# multiplied by 100 — unconditionally, for every such type.
#
# The first version of this branched per value ("if it is <= 1.0 treat it as a fraction"),
# which is wrong and was caught in review. Walking asymmetry is legitimately below 1%, so two
# adjacent readings of 0.8 and 1.2 landed as 80.0 and 1.2 — 78.8 apart, on two different
# scales, in one column, with nothing recording which branch fired. A deterministic
# conversion plus range rejection is the correct shape: the conversion never guesses, and a
# genuinely impossible result is dropped as a gap instead of stored.
FRACTION_PCT_UNIT = "%"

# A new sleep SESSION begins when this much time separates one segment from the next.
# Intra-night gaps are minutes (and Apple records wake periods as their own Awake segments),
# while consecutive nights are separated by twelve hours or more, so three hours divides the
# two cleanly and still treats an afternoon nap as its own session rather than folding it
# into the following night.
SLEEP_SESSION_GAP = dt.timedelta(hours=3)

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisInBed":            "sleep_inbed_min",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "sleep_asleep_min",
    "HKCategoryValueSleepAnalysisAsleep":           "sleep_asleep_min",
    "HKCategoryValueSleepAnalysisAsleepCore":       "sleep_core_min",
    "HKCategoryValueSleepAnalysisAsleepDeep":       "sleep_deep_min",
    "HKCategoryValueSleepAnalysisAsleepREM":        "sleep_rem_min",
    "HKCategoryValueSleepAnalysisAwake":            "sleep_awake_min",
}


# --- workouts (B18/R2) ----------------------------------------------------------------
# A `<Workout>` is a SESSION, not a sample, and until now the importer counted every one and
# threw it away (`workout_deferred_to_B18`). Thirty-two of them sit in the export -- 25
# TraditionalStrengthTraining spanning 2023-02 to 2026-06 -- and strength is the stated primary
# objective, so "deferred" was costing the whole recorded training history.
#
# THE DURATION IS NOT THE SPAN, AND THE TWO ARE NEVER CONFLATED. Apple writes `duration` (the
# ACTIVE minutes, pauses excluded) alongside `startDate`/`endDate` (wall clock). They routinely
# disagree, and not slightly: the 2023-02-26 session carries duration=185.2 min inside a
# 14:56->21:11 span of 375 minutes, because the Watch was paused at 16:36 and resumed at 19:38.
# Reading the span as the session would have reported a three-hour training block that never
# happened. So the VALUE is the recorded active duration and the INTERVAL is the wall-clock
# span, stored as two different facts, which is what they are.
#
# WHAT IS DELIBERATELY NOT DERIVED HERE (RULE-09, REQ-WKT-003). No load, no reps, no volume, no
# e1RM, and no judgement about whether a session "counts". A session record says a workout was
# recorded and how long it ran; it says NOTHING about what was lifted. No set has ever been
# logged, and a session record must never be allowed to stand in for one.
WORKOUT_TYPES = {
    "HKWorkoutActivityTypeTraditionalStrengthTraining": "strength_training",
    "HKWorkoutActivityTypeFunctionalStrengthTraining":  "strength_training",
    "HKWorkoutActivityTypeRunning":                     "running",
    "HKWorkoutActivityTypeWalking":                     "walking",
    "HKWorkoutActivityTypeCycling":                     "cycling",
    "HKWorkoutActivityTypeHighIntensityIntervalTraining": "hiit",
    "HKWorkoutActivityTypeCoreTraining":                "core_training",
    "HKWorkoutActivityTypeElliptical":                  "elliptical",
    "HKWorkoutActivityTypeRowing":                      "rowing",
    "HKWorkoutActivityTypeSwimming":                    "swimming",
    "HKWorkoutActivityTypeYoga":                        "yoga",
}

# `<WorkoutStatistics>` the session record carries. Each is a real measurement made across the
# session by the same device, so each becomes its own atom against the session's interval.
# They share the session's origin and are NOT independent corroboration of it (REQ-REC-008).
WORKOUT_STATS = {
    "HKQuantityTypeIdentifierActiveEnergyBurned":
        ("workout_active_energy_kcal", "kcal", "sum", {"Cal", "kcal"}),
    "HKQuantityTypeIdentifierHeartRate":
        ("workout_hr_avg_bpm", "bpm", "average", {"count/min"}),
}


class Counters(dict):
    """Why records did not become atoms. Reported at the end of every import so a silent
    drop is impossible: 'skipped' is a number Joe sees, not a branch nobody takes."""
    def bump(self, k, n=1):
        self[k] = self.get(k, 0) + n


def parse(path, since=None, until=None, counters=None):
    """Stream `export.xml`, yielding AtomSpec. `since`/`until` bound the subject day, so the
    43-day gap can be recovered without re-importing seven years.

    Range rejection is NOT done here. It lives at a single choke point in
    `import_drop.bounded`, so that every importer gets it and no importer can forget it — the
    first version put it in this parser only, left it defaulted off, and applied it to
    quantity records but not to sleep segments or transactions.

    Quantity samples are yielded as they are read. Sleep segments are held back and emitted at
    the end, because a segment's subject day is not knowable until the session it belongs to
    has finished (see `_sleep_sessions`). Review correction: this is tens of segments per
    night, not "a few hundred a year" — a seven-year export holds ~100k of them, measured at
    ~64 MB, which is acceptable but is not what the first version of this comment claimed.
    Every sleep segment in the file is held until grouping, including ones outside `--since`:
    a session is only complete once the whole file has been read, so the window cannot be
    applied earlier. Measured at ~100k segments / ~64 MB for a seven-year export.
    """
    c = counters if counters is not None else Counters()
    sleep_segments = []
    # `iterparse` on 'end' gives a fully populated element; clearing it and detaching it from
    # its parent is what keeps the tree from growing to the size of the file.
    context = ET.iterparse(path, events=("start", "end"))
    _, root = next(context)
    for event, elem in context:
        if event != "end" or elem.tag not in ("Record", "Workout"):
            continue
        try:
            if elem.tag == "Record":
                spec = _record(elem, c)
                if spec is None:
                    continue
                if spec.kind == "sleep":
                    sleep_segments.append(spec)
                elif _in_window(spec, since, until):
                    yield spec
                else:
                    c.bump("outside_window")
            else:
                # A `<Workout>` is a session and yields SEVERAL specs (the session, plus each
                # statistic it recorded), so it is iterated rather than yielded singly.
                for spec in _workout(elem, c):
                    if _in_window(spec, since, until):
                        yield spec
                    else:
                        c.bump("outside_window")
        finally:
            elem.clear()
            # Detach every consumed child, not just the ones this element swept past.
            # A real export emits ActivitySummary elements after the Record block; clearing
            # only up to the current Record left those accumulating on the root.
            del root[:]

    for spec in _sleep_sessions(sleep_segments):
        if _in_window(spec, since, until):
            yield spec
        else:
            c.bump("outside_window")


def _sleep_sessions(segments):
    """Assign every segment of one night the subject day of that night's wake instant.

    Segments are grouped into sessions by the gap between them, and each session's subject
    day is the 04:00-rule day of the LAST instant in the session — the moment Joe woke. All
    of that session's segments then carry it, so a night is one day's fact even though its
    segments straddle midnight and 04:00.
    """
    if not segments:
        return
    segments = sorted(segments, key=lambda s: (s.interval_start, s.interval_end))
    session, session_end = [], None
    for seg in segments:
        if session and seg.interval_start - session_end > SLEEP_SESSION_GAP:
            yield from _close_session(session, session_end)
            session, session_end = [], None
        session.append(seg)
        session_end = seg.interval_end if session_end is None else max(session_end, seg.interval_end)
    if session:
        yield from _close_session(session, session_end)


def _close_session(session, session_end):
    from dataclasses import replace
    day = subject_day(session_end)
    for seg in session:
        yield replace(seg, subject_day_override=day)


def _in_window(spec, since, until):
    d = spec.subject_day
    if since and d < since:
        return False
    if until and d > until:
        return False
    return True


def _record(elem, c):
    rtype = elem.get("type")
    start = parse_ts(elem.get("startDate"))
    end = parse_ts(elem.get("endDate"))
    if start is None:
        c.bump("unparseable_start")
        return None
    source_name = elem.get("sourceName") or "unknown"

    if rtype == SLEEP_TYPE:
        return _sleep(elem, start, end, source_name, c)

    spec = HK.get(rtype)
    if spec is None:
        c.bump("type_not_mapped")
        return None
    metric_key, unit, state_class, accepted = spec

    raw_unit = (elem.get("unit") or "").strip()
    if raw_unit not in accepted:
        c.bump(f"unconvertible_unit:{rtype}:{raw_unit or 'missing'}")
        return None
    try:
        value = float(elem.get("value"))
    except (TypeError, ValueError):
        c.bump("non_numeric_value")
        return None

    value = CONVERSIONS[raw_unit](value)
    if raw_unit == FRACTION_PCT_UNIT:
        value = value * 100.0

    return AtomSpec(
        kind=_kind_for(rtype),
        metric_key=metric_key,
        occurred_at=start,
        value=value,
        unit=unit,
        state_class=state_class,
        # The sample is what the sensor measured. RULE-05: the lane is 'measured', and a
        # measured atom is a point (the atoms_measured_is_point constraint enforces it).
        estimate_method="measured",
        time_precision="exact",
        # `endDate` is carried in the evidence rather than dropped. Apple emits bucketed
        # quantities (a StepCount of 500 covering 10:00-10:05), and two buckets sharing a
        # start with different ends and the same value are two different facts — without the
        # end in the key they collide and the second is discarded as a duplicate.
        evidence_span=(f"apple_health:{rtype};source={source_name}"
                       + (f";end={end.isoformat()}" if end is not None and end != start else "")),
    )


def _kind_for(rtype):
    if rtype in ("HKQuantityTypeIdentifierHeartRateVariabilitySDNN",):
        return "heart_rate_variability"
    if rtype in ("HKQuantityTypeIdentifierBodyMass",):
        return "body_measurement"
    if rtype in ("HKQuantityTypeIdentifierStepCount",
                 "HKQuantityTypeIdentifierActiveEnergyBurned",
                 "HKQuantityTypeIdentifierAppleExerciseTime",
                 "HKQuantityTypeIdentifierFlightsClimbed",
                 "HKQuantityTypeIdentifierDistanceWalkingRunning",
                 "HKQuantityTypeIdentifierWalkingSpeed",
                 "HKQuantityTypeIdentifierWalkingStepLength",
                 "HKQuantityTypeIdentifierWalkingDoubleSupportPercentage",
                 "HKQuantityTypeIdentifierWalkingAsymmetryPercentage",
                 "HKQuantityTypeIdentifierAppleWalkingSteadiness",
                 "HKQuantityTypeIdentifierVO2Max"):
        return "activity_sample"
    if rtype == "HKQuantityTypeIdentifierHeadphoneAudioExposure":
        return "environment_sample"
    return "vital_sample"


def _workout(elem, c):
    """One `<Workout>` -> a tuple of AtomSpec: the session, plus each statistic it recorded.

    Returns () and counts the reason when the element cannot become an atom. A workout type
    this map does not know is counted by name (`workout_type_not_mapped:<type>`) rather than
    silently dropped, so a new activity shows up as a reported number the way an unmapped
    record type does.

    THE DEGENERATE SESSION IS STORED, NOT FILTERED. The export holds a
    TraditionalStrengthTraining record starting 2025-07-29 08:53:18 that was paused eleven
    seconds later, never resumed, and closed at 19:26 -- duration 0.175 min, active energy
    0.54 Cal. It is obviously not a training session. It is equally obviously a real record of
    what the Watch did, and INV-2 makes captures append-only. Dropping it here would be this
    importer inventing a minimum-duration definition of "a workout", which is a MEASUREMENT
    DEFINITION and therefore Joe's (CLAUDE.md), not a parser's. It is stored exactly as
    recorded, and its own numbers say what it was. See OQ-81.
    """
    activity = elem.get("workoutActivityType")
    kind_label = WORKOUT_TYPES.get(activity)
    if kind_label is None:
        c.bump(f"workout_type_not_mapped:{activity or 'missing'}")
        return ()
    start = parse_ts(elem.get("startDate"))
    end = parse_ts(elem.get("endDate"))
    if start is None or end is None or end < start:
        c.bump("workout_without_interval")
        return ()
    if (elem.get("durationUnit") or "").strip() != "min":
        # The unit is written into the file and is not assumed, exactly as for every quantity
        # record. An unexpected one is reported, never converted by guess (RULE-06).
        c.bump(f"workout_unconvertible_duration_unit:{elem.get('durationUnit') or 'missing'}")
        return ()
    try:
        duration = float(elem.get("duration"))
    except (TypeError, ValueError):
        c.bump("workout_non_numeric_duration")
        return ()

    source_name = elem.get("sourceName") or "unknown"
    # The activity type travels in the evidence, the way the record type and device already do
    # for every sample. It is part of the dedupe key, so two different activities in one
    # interval remain two facts.
    span = f"apple_health:{activity};source={source_name}"
    specs = [AtomSpec(
        kind="workout",
        metric_key="workout_session_min",
        interval_start=start,
        interval_end=end,
        # RULE-05 / INV-5: the Watch measured this. The value is the ACTIVE duration and the
        # interval is the wall-clock span; see the note on WORKOUT_TYPES for why conflating
        # them reports training that did not happen.
        value=duration,
        unit="min",
        state_class="measurement",
        estimate_method="measured",
        time_precision="exact",
        evidence_span=span,
    )]
    c.bump(f"workout_session:{kind_label}")

    for stat in elem.findall("WorkoutStatistics"):
        mapped = WORKOUT_STATS.get(stat.get("type"))
        if mapped is None:
            continue
        metric_key, unit, attr, accepted = mapped
        raw_unit = (stat.get("unit") or "").strip()
        if raw_unit not in accepted:
            c.bump(f"workout_stat_unconvertible_unit:{stat.get('type')}:{raw_unit or 'missing'}")
            continue
        try:
            value = float(stat.get(attr))
        except (TypeError, ValueError):
            # A statistic the session did not record (no heart rate on an untracked workout)
            # is absent, not zero. Missing is not zero.
            continue
        specs.append(AtomSpec(
            kind="workout",
            metric_key=metric_key,
            interval_start=start,
            interval_end=end,
            value=CONVERSIONS[raw_unit](value),
            unit=unit,
            state_class="measurement",
            estimate_method="measured",
            time_precision="exact",
            # Same origin as the session: one Watch record, read once. Sharing the span keeps
            # REQ-REC-008 true downstream -- these are not independent corroborations of the
            # session, they are parts of it.
            evidence_span=f"{span};stat={attr}",
        ))
    return tuple(specs)


def _sleep(elem, start, end, source_name, c):
    if end is None or end <= start:
        c.bump("sleep_segment_without_duration")
        return None
    metric_key = SLEEP_STAGES.get((elem.get("value") or "").strip())
    if metric_key is None:
        c.bump("sleep_stage_not_mapped")
        return None
    minutes = (end - start).total_seconds() / 60.0
    return AtomSpec(
        kind="sleep",
        metric_key=metric_key,
        interval_start=start,
        interval_end=end,
        value=minutes,
        unit="min",
        state_class="total",
        estimate_method="measured",
        time_precision="minute",
        evidence_span=f"apple_health:sleep;source={source_name}",
        # subject_day_override is filled in by _sleep_sessions once the whole night is known.
    )
