-- 0010_hypothesis_register.sql
-- SHAPE LOCKED. REQ-INF-100/102/103; RULE-19 pre-registration is a DB constraint,
-- not a promise. The exploratory pass that fills it runs in Phase 6; the table +
-- constraints exist now so it is impossible to confirm a hypothesis on data that
-- already existed when it was registered.
--
-- The UPDATE-rejecting trigger for the pre-registration columns (REQ-INF-103) is
-- created in 0012 alongside the other immutability triggers.

CREATE TABLE __CORE__.hypothesis_register (
    hypothesis_id         TEXT PRIMARY KEY,
    exposure_metric       TEXT NOT NULL,
    outcome_metric        TEXT NOT NULL,
    lag_days              INTEGER NOT NULL,
    direction             TEXT NOT NULL,
    transformation        TEXT NOT NULL,
    adjustment_set        JSONB NOT NULL,
    test_statistic        TEXT NOT NULL,
    preregistered_at      TIMESTAMPTZ NOT NULL,
    confirmation_data_from TIMESTAMPTZ NOT NULL,
    resolution_rule       TEXT NOT NULL,
    status                TEXT NOT NULL DEFAULT 'PROMOTED'
                            CHECK (status IN ('PROMOTED','CONFIRMED_OBSERVATIONAL',
                                              'EXPERIMENTAL','REFUTED','INSUFFICIENT')),
    -- provenance marker so the CHECK provably prevents confirming an exploratory
    -- hypothesis on the same pre-existing data it was mined from (Decision 9 note)
    mined_from_preexisting BOOLEAN NOT NULL DEFAULT false,
    CHECK (confirmation_data_from >= preregistered_at)   -- REQ-INF-102
);

COMMENT ON TABLE __CORE__.hypothesis_register IS
  'REQ-INF-100/102/103. Pre-registration as a DB constraint (RULE-19). '
  'Pre-registration columns are UPDATE-rejected by trigger (0012). Populated in '
  'Phase 6.';
