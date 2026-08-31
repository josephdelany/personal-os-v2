-- 0016_alcohol_metric_seed.sql — Missing-B alcohol metric_registry seed (ADR-0033)
--
-- Seeds the two metric_registry rows so an alcohol `consume` atom can carry
-- `alcohol_ethanol_grams` / `alcohol_standard_drinks` (REQ-ONT-016; REQ-NUT-066..068;
-- ADR-0030). metric_registry is CONFIGURATION, not personal data (INV-2 does not apply).
-- Field values are decided in ADR-0033 (Joe delegated the choices; recorded for audit).
-- Applied incrementally with:  run_migration.py --core core --ops ops --only 0016 --commit
-- g_per_standard_drink (REQ-NUT-068 divisor) is OQ-35, a reference constant, not a column.

INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class,
   expected_cadence, max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
  ('alcohol_ethanol_grams', 'Alcohol — ethanol grams',
   'substance', 'g', 'total',
   'irregular', NULL, 0, NULL, false),
  ('alcohol_standard_drinks', 'Alcohol — standard drinks',
   'substance', 'standard_drink', 'total',
   'irregular', NULL, 0, NULL, false)
ON CONFLICT (metric_key) DO NOTHING;
