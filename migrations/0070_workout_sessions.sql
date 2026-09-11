-- 0070_workout_sessions.sql — the recorded training history becomes data, and a session
-- becomes a reconstructable event (REQ-WKT-001/002, REQ-REC-004/005/009; R2; ADR-0138).
--
-- WHAT WAS WRONG. `tools/importers/apple_health.py` counted every `<Workout>` element and threw
-- it away under `workout_deferred_to_B18`. Thirty-two of them are in the export — 25
-- TraditionalStrengthTraining spanning 2023-02-26 to 2026-06-30 — and strength is the stated
-- primary objective, so "deferred" was quietly discarding the entire recorded training history.
-- The 2026-09-10 checkpoint recorded R2 as "pending observation, not missing implementation".
-- That was wrong: production holds zero workout-session atoms because the parser drops them,
-- not because the Watch never recorded any.
--
-- THE DISTINCTION THIS MIGRATION EXISTS TO PROTECT. A session record says a workout WAS
-- RECORDED and how long it ran. It says nothing whatever about what was lifted. No set has ever
-- been logged — `strength_load_lb`, `strength_reps` and `strength_rpe` have been registered
-- since B18 and have never received a row — and a session record must never be allowed to stand
-- in for one. Hence `workout_session_min` is registered in its own family, and the method below
-- may conclude only that a session occurred.
--
--   "a strength session was recorded"   is not   "Joe lifted X for Y reps"
--   "no session record on this day"     is not   "Joe did not train"
--
-- THE DURATION IS NOT THE SPAN. Apple writes `duration` (active minutes, pauses excluded)
-- alongside startDate/endDate (wall clock), and they routinely disagree: the 2023-02-26 session
-- carries 185.2 active minutes inside a 375-minute span, because the Watch was paused at 16:36
-- and resumed at 19:38. The atom's VALUE is the active duration; its `valid_interval` is the
-- span. Two facts, stored separately, because reading the span as the session would report a
-- three-hour training block that never happened.

-- ---------------------------------------------------------------------------------------
-- 1. The measures a session record actually carries.
-- ---------------------------------------------------------------------------------------
-- `workout` is its own family, not `strength`. Putting a session duration in the strength
-- family would let a per-domain surface answer "how is strength going?" with a count of
-- sessions, which is the exact substitution REQ-WKT-003 forbids: a workout timestamp is not a
-- lifting set.
INSERT INTO __CORE__.metric_registry
    (metric_key, display_name, family, unit, state_class, expected_cadence,
     max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
    -- Cadence is `irregular`: training is not daily and a staleness alarm on it would fire
    -- permanently and be ignored. NULL max_staleness_days, exactly as the strength keys.
    ('workout_session_min', 'Workout — recorded duration', 'workout', 'min',
     'measurement', 'irregular', NULL, 0, 1440, false),
    ('workout_active_energy_kcal', 'Workout — active energy', 'workout', 'kcal',
     'measurement', 'irregular', NULL, 0, 10000, false),
    ('workout_hr_avg_bpm', 'Workout — average heart rate', 'workout', 'bpm',
     'measurement', 'irregular', NULL, 20, 250, false)
ON CONFLICT (metric_key) DO NOTHING;

-- ---------------------------------------------------------------------------------------
-- 2. The third registered reconstruction method.
-- ---------------------------------------------------------------------------------------
-- REQ-REC-016 requires acceptance across multiple event families. `watch_non_wear`
-- (device_state) and `sleep_gap_explained` (data_coverage) are both facts about THE RECORD.
-- This is the first method that reconstructs an EVENT IN JOE'S LIFE, which is what R2 asks for
-- and what the two existing families could not demonstrate.
--
-- REQUIRED EVIDENCE is the session record alone. Corroboration — exercise minutes on the same
-- subject day, a gym place_visit — raises the tier when it comes from an independent origin,
-- but it is not required, because the Watch record is itself sufficient evidence that a session
-- was recorded. Demanding corroboration would refuse 25 real sessions for want of a gym visit
-- this system has never captured.
--
-- PERMISSIBLE OUTPUTS is `occurred` and nothing else. There is deliberately no `did_not_occur`:
-- the Watch stopped in five stages ending 2026-08-21, so a day with no session record is
-- overwhelmingly a day the Watch was not worn. Absence of a record is absence of capture
-- (REQ-REC-009), and this method is given no way to say otherwise.
INSERT INTO config.reconstruction_methods
    (method_key, method_version, event_family, required_evidence, permissible_outputs,
     temporal_specification, note)
VALUES (
    'training_session', 1, 'training_session',
    ARRAY['workout_session_record'],
    ARRAY['occurred'],
    'subject_day',
    'REQ-REC-004/005. Concludes that a training session occurred on a subject day, from a '
    'recorded workout session, with its MEASURED active duration. Corroborating evidence from '
    'an independent origin (exercise minutes, a place visit) raises the tier; none is required, '
    'because the session record is itself the observation. '
    'IT MAY NOT CONCLUDE ANYTHING ABOUT LOAD, REPS OR VOLUME. Those need per-set records, no '
    'set has ever been logged, and REQ-WKT-003 forbids deriving them from a session. A caller '
    'asking for them is refused by public.derivation_support (0068) naming the missing inputs. '
    'No did_not_occur: the Watch stopped in five stages ending 2026-08-21, so a day without a '
    'record is a day without capture (REQ-REC-009).'
)
ON CONFLICT (method_key, method_version) DO NOTHING;
