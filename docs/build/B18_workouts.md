# B18 — Workouts: the objective function gets its numbers (migration 0058)

**What this is.** `specs/07-workout/requirements.md` §B–§E. Sets are captured today
(Log Workout Shortcut → `workout` atoms with load / reps / RPE); nothing derives from
them. This build adds the exercise entity resolution (B14's cascade, workout branch),
e1RM as an interval, per-exercise and per-session volume, ACWR on registry windows,
rest-day presence, and the SOURCES envelope for `workouts`. One session.

**Requirement IDs satisfied:** REQ-WKT-005..022 (001–004 are the capture path, already
live — re-verify with tests), REQ-ONT-001, RULE-06/07/08/14/15/24, INV-3/4.
**ADR:** ADR-0068 (formula choice recorded in the registry; windows).

## Decisions (record in ADR-0068; both are registry rows, not code constants)
- **e1RM formula:** Epley `load × (1 + reps/30)`, valid for reps 1–10 (REQ-WKT-010:
  outside → no e1RM, omission recorded). Stored in `metric_registry` as
  `e1rm_lb` with `estimate_method='epley_v1'` named in the row's attributes; the interval
  width per REQ-WKT-009: ±5 % at reps ≤ 5, ±10 % at 6–10 (state as provisional, OQ-10).
- **ACWR windows:** acute 7 days, chronic 28 days, from `metric_registry` rows
  `acwr_7_28` with `window_acute_days=7`, `window_chronic_days=28`; computed on
  per-session volume; reported only when chronic coverage ≥ 0.60 (RULE-06).
- **Unit:** pounds canonical (REQ-WKT-004); kilograms converted at capture with the
  stated unit kept in `evidence_span`.
- **Rest days (REQ-WKT-019):** the Night check-in gains an optional "rest day / skipped"
  field → `observed_absent` workout presence atom; unlogged days stay `unknown`.

## Migration `migrations/0058_workouts.sql`
Registry rows: `e1rm_lb`, `session_volume_lb_reps`, `exercise_volume_lb_reps`,
`acwr_7_28`, `training_days_7d` (coverage figure, REQ-WKT-016). Table
`analysis.derived_measures` (the Phase-5 carrier REQ-LOC-010 and REQ-WKT-013 name:
`(day, metric, entity_id?, value_lo, value_point, value_hi, estimate_method, window_from,
window_to, n_inputs, code_version, computed_at)`, rebuildable) — this table is shared by
B5's mobility metrics going forward (move `away_min`/`home_min`/`places_distinct` writes
here in the same session; one carrier).

## Engine — `tools/engines/workouts.py`, nightly
Per set → e1RM interval (or omission row); per exercise per day → best e1RM, volume;
per day → session volume; ACWR; 7-day training days; every row point-in-time correct
(no set with `occurred_at` after the window). Human corrections (REQ-WKT-020) are
superseding atoms; the engine reads `atoms_current` so replays honour them.

## `get_domain('workouts')` additions (additive)
`hero` = `session_volume_lb_reps` (already the config hero) — plus modules:
`exercises:[{exercise, sets_90d, best_e1rm:{lo,point,hi,day,method}, e1rm_trend:[{day,point,lo,hi}], volume_28d}]`,
`load:{acwr:{value, window:'7/28', coverage, note}, training_days_7d}`,
`presence:{days_trained_28d, rest_days_logged_28d, unknown_days_28d}` (RULE-07, three
numbers, never a streak). `get_entity('exercise', key)` gains the same per-exercise block.

## Tests
```
test_REQ_WKT_008_009_e1rm_epley_interval_with_method
test_REQ_WKT_010_reps_outside_range_records_omission_not_extrapolation
test_REQ_WKT_011_volume_is_sum_load_times_reps_one_owner
test_REQ_WKT_012_acwr_windows_from_registry_not_code
test_REQ_WKT_013_no_set_after_window_close_counts            (INV-4)
test_REQ_WKT_018_skipped_session_is_not_zero_volume
test_REQ_WKT_019_rest_day_is_observed_absent_not_unknown
test_REQ_WKT_020_human_correction_replays_over_rebuild
test_REQ_WKT_014_016_envelope_has_no_streak_or_score_field
test_REQ_WKT_006_exercise_spellings_resolve_to_one_entity
```

## Done when
Migration; engine in nightly; `get_domain('workouts')` pasted (real sets exist since
the Shortcut went live — if none, the empty-state envelope is the paste and WHAT I DID
NOT DO says so); tests; ADR-0068; PROGRESS.
