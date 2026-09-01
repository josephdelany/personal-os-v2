-- 0022_workout_health_seed.sql — metric keys for the two new capture families
-- (ADR-0037): strength sets (Log Workout shortcut; REQ-WKT/REQ-ONT-017, atom
-- shape per OQ-33 ruling (a): one atom per attribute sharing the set's capture)
-- and phone-harvested health samples (Shortcuts "Find Health Samples" -> POST).
-- All measured quantities; plausible bounds are wide sanity rails, not clinical
-- judgments. state_class: measurement = point-in-time; total = per-subject-day.

INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class,
   expected_cadence, max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
  -- strength (per set; the objective function finally gets a feed)
  ('strength_load_lb',   'Strength — set load',       'strength', 'lb',    'measurement', 'irregular', NULL, 0, 1500, false),
  ('strength_reps',      'Strength — set reps',       'strength', 'rep',   'measurement', 'irregular', NULL, 0, 200,  false),
  ('strength_rpe',       'Strength — set RPE',        'strength', 'rpe',   'measurement', 'irregular', NULL, 0, 10,   true),
  -- (RPE coarsening set below; the convention uses half-point steps)
  -- health harvest (phone HealthKit via Shortcuts; measured device samples)
  ('steps',              'Steps',                     'activity', 'count', 'total',       'daily', 3, 0, 200000, false),
  ('sleep_minutes',      'Sleep duration',            'sleep',    'min',   'total',       'daily', 3, 0, 1440,   false),
  ('resting_hr',         'Resting heart rate',        'vitals',   'bpm',   'measurement', 'daily', 3, 20, 200,   false),
  ('hrv_sdnn_ms',        'HRV (SDNN)',                'vitals',   'ms',    'measurement', 'daily', 3, 0, 400,    false),
  ('weight_lb',          'Body weight',               'body',     'lb',    'measurement', 'irregular', NULL, 50, 800, false),
  ('active_energy_kcal', 'Active energy',             'activity', 'kcal',  'total',       'daily', 3, 0, 10000,  false),
  ('exercise_minutes',   'Exercise minutes',          'activity', 'min',   'total',       'daily', 3, 0, 1440,   false)
ON CONFLICT (metric_key) DO NOTHING;

-- ADR-0018 coarsening for RPE: a 0-10 scale reported in half-point steps
UPDATE __CORE__.metric_registry
   SET response_scale = numrange(0,10,'[]'), n_scale_points = 21, rounding_step = 0.5
 WHERE metric_key = 'strength_rpe' AND response_scale IS NULL;
