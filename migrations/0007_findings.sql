-- 0007_findings.sql
-- SHAPE LOCKED, NO COMPUTE. The e-value is the family-wide FDR currency (e-BH),
-- stored native as a power-for-anytime-validity trade (ADR-0007, Decision 1).
-- The statistics that populate these columns are Phase 6. Locking the shape now
-- avoids a migration over history later.

CREATE TABLE __CORE__.findings (
    finding_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hypothesis_id   TEXT,                        -- FK added when hypothesis_register is populated (Phase 6)
    claim_text      TEXT NOT NULL,
    tier            TEXT NOT NULL                -- RULE-16 six-tier ladder
                      CHECK (tier IN ('DESCRIPTIVE','CANDIDATE','PROMOTED',
                                      'CONFIRMED_OBSERVATIONAL','EXPERIMENTAL','INSUFFICIENT')),
    -- e-BH currency (ADR-0007) + sufficient statistics to recompute it
    e_value         NUMERIC,
    e_value_method  TEXT,
    e_process_params JSONB,                      -- test type, statistic, etc.
    p_value         NUMERIC,                     -- stored where one exists, for interpretability only
    family_size     INTEGER,                     -- REQ-INF-106 persisted family size
    n               INTEGER,
    n_eff           NUMERIC,                     -- RULE-21: never n without n_eff
    rho             NUMERIC,
    maxlags         INTEGER,
    code_version    TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'
                      CHECK (status IN ('active','refuted','superseded')),
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes      UUID REFERENCES __CORE__.findings(finding_id),
    CHECK (e_value IS NULL OR e_value >= 0)
);

COMMENT ON TABLE __CORE__.findings IS
  'ADR-0007 shape lock. e_value is the e-BH family-wide currency (Decision 1). '
  'No compute this phase; populated in Phase 6. CANDIDATE never reaches a screen '
  '(RULE-17).';
