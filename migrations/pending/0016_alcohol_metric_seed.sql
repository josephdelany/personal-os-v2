-- 0016_alcohol_metric_seed.sql — Missing-B alcohol metric_registry seed
--
-- STATUS: NOT YET APPLIED, and deliberately HELD OUT of the auto-applied sequence.
-- This is the Missing-B data write Joe asked to inspect before it runs (sessions 13-14).
-- It seeds two metric_registry rows so an alcohol `consume` atom can carry
-- `alcohol_ethanol_grams` / `alcohol_standard_drinks` (REQ-ONT-016; REQ-NUT-066..068;
-- ADR-0030). metric_registry is CONFIGURATION, not personal data, and INV-2 does not
-- apply to it — but it is a real INSERT, so this file lives in migrations/pending/,
-- which run_migration.py's numbered glob does NOT pick up. To apply: confirm the fields
-- marked PROVISIONAL, move this file to migrations/ keeping the 0016 prefix, and run
--   python3 tools/run_migration.py --core core --ops ops --commit
--
-- FIXED (ADR-0030 / schema):    metric_key, unit, state_class='total', plausible_low=0
-- PROVISIONAL (Joe to confirm): family (the RULE-21 FDR group), plausible_high,
--                               expected_cadence, max_staleness_days, self_report
-- The REQ-NUT-068 divisor g_per_standard_drink=14 is OQ-35, a reference constant, not a
-- column here — it does not appear in this seed.
--
-- Dry-run verified 2026-08-31: applied to core_dryrun/ops_dryrun end to end with all
-- prior migrations, invariants ALL PASS, rolled back — nothing persisted (RULE-01).

INSERT INTO __CORE__.metric_registry
  (metric_key, display_name, family, unit, state_class,
   expected_cadence, max_staleness_days, plausible_low, plausible_high, self_report)
VALUES
  ('alcohol_ethanol_grams', 'Alcohol — ethanol grams',
   'substance',        -- PROVISIONAL family (RULE-21 FDR tree); ADR-0030 requires a family, does not name it
   'g', 'total',       -- state_class total = per subject-day total (ADR-0030)
   'irregular',        -- PROVISIONAL cadence (alcohol is not a daily measurement)
   NULL,               -- PROVISIONAL max_staleness_days (an event total is not forward-filled; NULL = no limit)
   0, NULL,            -- plausible_low=0 fixed; plausible_high PROVISIONAL (no data-sanity ceiling set yet)
   false),             -- PROVISIONAL self_report: ethanol grams is derived from volume, not a coarsened scale
  ('alcohol_standard_drinks', 'Alcohol — standard drinks',
   'substance',        -- PROVISIONAL family, as above
   'standard_drink', 'total',
   'irregular',        -- PROVISIONAL cadence
   NULL,               -- PROVISIONAL max_staleness_days
   0, NULL,            -- plausible_low=0 fixed; plausible_high PROVISIONAL
   false);             -- PROVISIONAL self_report; a DIRECTLY-LOGGED count ("2 drinks") is a coarsened
                       -- self-report (ADR-0018) and may warrant self_report=true or a separate key — Joe decides
