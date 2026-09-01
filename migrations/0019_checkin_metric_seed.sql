-- 0019_checkin_metric_seed.sql — self-report check-in metric keys (ADR-0035)
--
-- The morning/night check-in shortcuts collect 0-10 subjective scores. These are
-- coarsened self-reports (ADR-0018): stored with response_scale [0,10], 11 points,
-- rounding_step 1 — never as false-precision points. Morning and night variants are
-- distinct metrics (mood-at-wake and mood-at-night are different variables; this also
-- preserves comparability with the legacy signals convention `${type}_${field}`).
-- state_class='measurement' (a point-in-time reading, not a daily total).

INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class, expected_cadence,
   max_staleness_days, plausible_low, plausible_high,
   self_report, response_scale, n_scale_points, rounding_step)
VALUES
  ('checkin_morning_restored',        'Morning — restored',        'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_morning_energy',          'Morning — energy',          'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_morning_mood',            'Morning — mood',            'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_morning_mental_clarity',  'Morning — mental clarity',  'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_morning_drive',           'Morning — drive',           'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_morning_sleep_feel',      'Morning — sleep feel',      'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_night_mood',              'Night — mood',              'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_night_stress',            'Night — stress',            'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_night_mental_sharpness',  'Night — mental sharpness',  'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_night_energy',            'Night — energy',            'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1),
  ('checkin_night_day_rating',        'Night — day rating',        'self_report', 'score_0_10', 'measurement', 'daily', 2, 0, 10, true, numrange(0,10,'[]'), 11, 1)
ON CONFLICT (metric_key) DO NOTHING;
