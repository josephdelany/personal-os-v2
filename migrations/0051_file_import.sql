-- 0051_file_import.sql — B13: the drop-folder import path (ADR-0057, ADR-0058, ADR-0059).
--
-- WHY THIS EXISTS. On 2026-07-28 the device-side capture path stopped. Everything that
-- depended on it went dark together: public.intraday (hr, hrv_window, spo2, sleep_stage,
-- resp_rate, walking_*), public.events (chrome_visit, youtube_watch) and public.locations.
-- The derived apple_sleep / apple_hrv / apple_circadian / apple_vitals feeds are not
-- themselves broken — their input died. Server-side pulls (weather, gmail, calendar) kept
-- running, which is why ops.runs stayed green while nothing was being captured.
--
-- The samples for that gap still exist on the phone (Apple Health) and in Google's export
-- (Chrome/YouTube). They are recoverable by file export, and this migration opens the path
-- that lets them land in core.* as first-class atoms. It adds nothing to the analysis
-- layer; it is a capture path only.
--
-- Two objects:
--   1. capture_source gains 'file_import'. A file import is not a shortcut, not a PWA
--      write, and not a legacy archive read: it is a file Joe exported and dropped, and it
--      needs its own provenance value so a later audit can tell the three apart.
--   2. core.metric_registry gains the health metrics the Apple Health importer emits.
--      core.atoms.metric_key is a foreign key into this table, so an atom for a metric with
--      no registry row cannot be inserted at all. These rows are the registry half of that
--      contract. plausible_low/high are instrument ranges used for range rejection, never
--      for clamping: an out-of-range sample is dropped as a documented gap (RULE-06), never
--      squeezed into the nearest legal value.
--
-- Forward-only. No data row is written by this migration (RULE-01): metric_registry is
-- configuration, not observation.

-- 1. The new capture source. ------------------------------------------------------------
-- PG 12+ permits ALTER TYPE ... ADD VALUE inside a transaction block; the new label may not
-- be *used* until that transaction commits. Nothing below uses it, so this is safe under
-- the dry-run runner (which rolls back) as well as under the real apply.
ALTER TYPE __CORE__.capture_source ADD VALUE IF NOT EXISTS 'file_import';

-- 2. The metrics the Apple Health importer emits. ----------------------------------------
-- ON CONFLICT DO NOTHING so the migration is re-runnable and so it never silently rewrites
-- a unit or a plausible range that some existing atom was already validated against.
INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class, expected_cadence,
   max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
  -- Cardiac and autonomic.
  ('heart_rate_bpm',              'Heart rate',                'vitals',   'bpm',        'measurement', 'intraday', 2,   25,   230,  false),
  ('respiratory_rate_bpm',        'Respiratory rate',          'vitals',   'breaths_min','measurement', 'intraday', 3,    4,    60,  false),
  ('spo2_pct',                    'Blood oxygen',              'vitals',   'pct',        'measurement', 'intraday', 7,   70,   100,  false),
  ('vo2max_ml_kg_min',            'VO2 max',                   'fitness',  'ml_kg_min',  'measurement', 'sporadic', 90,  10,    90,  false),
  ('wrist_temperature_c',         'Wrist temperature',         'vitals',   'degC',       'measurement', 'nightly',  7,   28,    42,  false),
  -- Sleep. One atom per stage segment, valid_interval carries the segment (ADR-0058).
  ('sleep_inbed_min',             'Time in bed',               'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  ('sleep_asleep_min',            'Asleep (unspecified)',      'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  ('sleep_core_min',              'Core sleep',                'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  ('sleep_deep_min',              'Deep sleep',                'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  ('sleep_rem_min',               'REM sleep',                 'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  ('sleep_awake_min',             'Awake during sleep',        'sleep',    'min',        'total',       'nightly',  3,    0,  1440,  false),
  -- Gait and mobility.
  ('walking_speed_m_s',           'Walking speed',             'mobility', 'm_s',        'measurement', 'intraday', 7,  0.1,   4.0,  false),
  ('walking_step_length_cm',      'Walking step length',       'mobility', 'cm',         'measurement', 'intraday', 7,   10,   150,  false),
  ('walking_double_support_pct',  'Double support time',       'mobility', 'pct',        'measurement', 'intraday', 7,    5,    60,  false),
  ('walking_asymmetry_pct',       'Walking asymmetry',         'mobility', 'pct',        'measurement', 'intraday', 7,    0,   100,  false),
  ('walking_steadiness_pct',      'Walking steadiness',        'mobility', 'pct',        'measurement', 'sporadic', 30,   0,   100,  false),
  -- Activity volume.
  ('flights_climbed',             'Flights climbed',           'activity', 'count',      'total',       'daily',    3,    0,   500,  false),
  ('walking_running_distance_km', 'Walking + running distance','activity', 'km',         'total',       'daily',    3,    0,   100,  false),
  ('headphone_audio_exposure_db', 'Headphone audio exposure',  'context',  'dbA',        'measurement', 'intraday', 7,   20,   120,  false),
  -- Money. One atom per posted transaction (ADR-0059); sign follows the source ledger,
  -- negative = money out. The plausible range rejects a mis-parsed column, not a real
  -- large transfer, so it is deliberately wide.
  ('transaction_amount_usd',      'Transaction amount',        'finance',  'usd',        'total',       'sporadic', 7, -1000000, 1000000, false)
ON CONFLICT (metric_key) DO NOTHING;
