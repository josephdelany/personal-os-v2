# ADR-0037: Workout and health capture families; OQ-33 implemented as (a)

## Status
Accepted (proof rolled back; migration 0022 staged for Joe's apply command).

## Date
2026-09-01

## Decision
Two new capture families through the live ingress, extracted deterministically:
- **kind='workout'** (Log Workout shortcut; one run = one SET per REQ-ONT-017):
  one atom per attribute — `strength_load_lb` / `strength_reps` (measured) /
  `strength_rpe` (self-report, half-point ADR-0018 coarsening [v±0.25]) — sharing
  the set's `raw_capture_id` as the set key, exercise name verbatim on each
  (entity resolution is Phase 4). **This implements OQ-33 option (a)** — the only
  shape expressible against the built atom (single value_point) without a
  migration; flagged for Joe's one-word ratification, losslessly re-derivable if
  he rules (b).
- **kind='health'** (Shortcuts "Find Health Samples" harvest; free, no app):
  `{samples:[{metric, value}]}` → measured atoms under seeded keys
  (steps/sleep_minutes/resting_hr/hrv_sdnn_ms/weight_lb/active_energy_kcal/
  exercise_minutes), kind mapped per taxonomy (activity_sample/sleep/
  vital_sample/heart_rate_variability/body_measurement). Unknown metrics and
  out-of-rail values are skipped — a gap, never a guess (RULE-06).
Migration 0022 seeds the ten keys. Proof (rolled back): bench 185×8@7.5 → 3
correctly-laned atoms; steps+resting_hr landed; 'nonsense' metric skipped;
invariants ALL PASS.

## Also this session
The dead Mac collectors' revival is packaged as ~/personalos-edge/RECONNECT.sh
(TCC root cause; classifier requires Joe to run persistence himself). Shortcuts
"Log Food", "Night Check-in v2", "Log Workout" generated programmatically,
signed, imports queued (Apple requires one human click each).
