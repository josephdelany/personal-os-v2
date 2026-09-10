-- 0061_strength_measures.sql — the derived strength measures, and where their SPECIFICATION
-- lives (REQ-WKT-008, REQ-WKT-011, REQ-WKT-012, RULE-12, RULE-13; ADR-0097).
--
-- REQ-WKT-008 says the e1RM formula is "recorded in the metric registry" and REQ-WKT-012 says
-- the ACWR windows are "drawn from the metric registry, never chosen by the model at query
-- time". `core.metric_registry` has no column for either, and adding a `formula` column to a
-- table describing 43 metrics — of which three are formulas — would be the wrong shape.
--
-- `config.derivation_catalogue` (0053) already owns exactly this: input fields, method,
-- method version, units, time specification, missingness. It gains a `parameters` column so a
-- method's numbers are DATA beside it rather than constants in Python. That is what makes
-- RULE-13 true rather than intended: the windows and the formula set can be changed without a
-- code change, and any figure can cite the version that produced it.

ALTER TABLE config.derivation_catalogue
    ADD COLUMN IF NOT EXISTS parameters JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN config.derivation_catalogue.parameters IS
  'RULE-13. The numbers a method needs — formula names, window lengths, validated ranges — as '
  'data, so they are inspectable and changeable without editing code, and never chosen at '
  'query time.';

-- REQ-WKT-009: an e1RM is an INTERVAL, so its state_class is `measurement` (a reading-like
-- quantity at a point in time) and its lane is `resolved`, never `measured` — nobody lifted it.
-- REQ-WKT-011: volume accumulates over a session, so it is a `total`.
-- REQ-WKT-012: the ACWR is a dimensionless ratio, a `measurement`, and it carries NO plausible
-- band: the windows are provisional (OQ-36), so a band would imply a threshold this system has
-- not earned.
INSERT INTO __CORE__.metric_registry
    (metric_key, display_name, family, unit, state_class, expected_cadence,
     max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
    ('strength_e1rm_lb',   'Strength — estimated 1RM', 'strength', 'lb',    'measurement',
     'irregular', NULL, 0, 1500, false),
    ('strength_volume_lb', 'Strength — session volume', 'strength', 'lb',   'total',
     'irregular', NULL, 0, 200000, false),
    ('strength_acwr',      'Strength — acute:chronic', 'strength', 'ratio', 'measurement',
     'irregular', NULL, NULL, NULL, false)
ON CONFLICT (metric_key) DO NOTHING;

-- REQ-WKT-004/018: a missing training input is never imputed, and the wording is per measure
-- because the three fail differently.
-- INSERT ... SELECT, guarded on the parameterised core BEING the real core.
--
-- `config.*` is not schema-parameterised; `__CORE__` is. When the spine test applies the chain
-- to a throwaway core schema, a plain VALUES insert put the registry row in the PYTEST registry
-- and the catalogue row in the SHARED `config.derivation_catalogue`, whose foreign key still
-- points at `core.metric_registry` — 73 errors, and it would also have leaked pytest-only
-- measures into a shared table.
--
-- Guarding on "the registry row exists in __CORE__" does not work and the first attempt proved
-- it: the row DOES exist there, in the pytest registry, while the constraint checks the real
-- one. The condition that matters is whether the parameterised core IS the core the foreign key
-- targets, so that is what is asked.
--
-- The deeper wrinkle is 0053's: a shared `config` table holding a foreign key into a
-- parameterised schema cannot be right in both worlds. This guard makes 0061 safe; the
-- inconsistency itself is recorded as OQ-64.
INSERT INTO config.derivation_catalogue
    (measure, input_fields, method, method_version, unit, time_specification,
     missingness_rule, analytical_consumers, owner, parameters)
SELECT v.* FROM (VALUES
    ('strength_e1rm_lb',
     ARRAY['strength_load_lb','strength_reps'],
     'formula_spread', 'strength-v1', 'lb', 'instant',
     'a set outside the formulas'' validated repetition range yields NO e1RM and a recorded '
     'omission, never an extrapolated number (REQ-WKT-010); a bodyweight set has an UNDEFINED '
     'e1RM, never zero, because zero would sort as the weakest set ever performed',
     ARRAY['tools/engines/strength.py'], 'B18',
     jsonb_build_object(
       'formulas', jsonb_build_array('brzycki', 'epley'),
       'valid_reps', jsonb_build_array(1, 10),
       'interval', 'the spread across the registered formulas, not an invented percentage '
                   'band; at 225 lb x 5 they differ by 9.38 lb, and reporting either alone '
                   'states a precision the method does not have')),
    ('strength_volume_lb',
     ARRAY['strength_load_lb','strength_reps'],
     'sum_of_load_times_reps', 'strength-v1', 'lb', 'subject_day_aggregate',
     'a set with reps and no load contributes no volume and is counted as excluded; treating '
     'its load as zero would make a hard session look light (REQ-WKT-004)',
     ARRAY['tools/engines/strength.py'], 'B18', '{}'::jsonb),
    ('strength_acwr',
     ARRAY['strength_volume_lb'],
     'acute_over_chronic_rate', 'strength-v1', 'ratio', 'subject_day_aggregate',
     'a day absent from the record is UNKNOWN, not zero: a skipped session is not zero volume '
     'and an unlogged day is not a rest day (REQ-WKT-018/019). Both sides are per-logged-day '
     'RATES, so absent days divide out of both windows instead of dragging the ratio down',
     ARRAY['tools/engines/strength.py'], 'B18',
     jsonb_build_object(
       'acute_days', 7, 'chronic_days', 28, 'windows_calibrated', false,
       'note', 'OQ-36. Provisional placeholders, not calibrated to Joe. The ratio orders '
               'sessions against each other and carries no threshold; it must not be rendered '
               'beside one until calibrated (REQ-WKT-012).'))
) AS v(measure, input_fields, method, method_version, unit, time_specification,
       missingness_rule, analytical_consumers, owner, parameters)
 WHERE to_regclass('__CORE__.metric_registry') = to_regclass('core.metric_registry')
ON CONFLICT (measure) DO NOTHING;

-- NOT DONE HERE, deliberately. `config.domains.hero_metric` for the workouts domain is
-- `strength_volume` — no suffix — and `strength_volume_lb` now exists. They are probably the
-- same measure. Pointing the domain at it is a MEASUREMENT DECISION and belongs to OQ-60 with
-- the other seven; the string similarity that makes it look obvious is the same similarity
-- that proposes `sleep_awake_min` for `away_min` (ADR-0095).
