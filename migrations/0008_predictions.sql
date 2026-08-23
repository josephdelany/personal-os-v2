-- 0008_predictions.sql
-- SHAPE LOCKED, NO COMPUTE. Two forecast shapes (ADR-0021, Decision 2):
--   * binary     — p_forecast/brier/log_score (REQ-INF-300, unchanged; Brier and
--                  log score are correct for a binary outcome and need no CRPS)
--   * continuous — forecast_distribution (quantiles/samples) + crps/log_score_cont
-- CRPS/log score cannot be computed from a point forecast, so the distribution is
-- stored, not a mean. Scoring compute is Phase 6.

CREATE TABLE __CORE__.predictions (
    prediction_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    hypothesis_id   TEXT,
    claim_text      TEXT NOT NULL,
    resolution_rule TEXT NOT NULL,               -- machine-evaluable predicate (REQ-INF-304)
    resolves_at     TIMESTAMPTZ NOT NULL,
    evidence_tier   TEXT NOT NULL,
    model_version   TEXT,
    feature_snapshot_hash TEXT,

    -- binary path (REQ-INF-300)
    p_forecast      NUMERIC CHECK (p_forecast IS NULL OR (p_forecast >= 0 AND p_forecast <= 1)),
    outcome_bool    BOOLEAN,
    brier           NUMERIC,
    log_score       NUMERIC,

    -- continuous path (ADR-0021)
    forecast_distribution JSONB,                 -- quantile grid or sample vector
    dist_family     TEXT,                        -- tag describing the distribution shape
    issued_at       TIMESTAMPTZ,
    horizon         INTERVAL,
    crps            NUMERIC,
    log_score_cont  NUMERIC,

    resolved_at     TIMESTAMPTZ,
    CHECK (resolves_at > created_at),            -- REQ-INF-303
    -- a prediction is EXACTLY one shape — binary or continuous, never both (their
    -- scoring semantics differ and a row with both has no defined score)
    CHECK ((p_forecast IS NOT NULL)::int + (forecast_distribution IS NOT NULL)::int = 1)
);

COMMENT ON TABLE __CORE__.predictions IS
  'ADR-0021 shape lock. Binary path (REQ-INF-300) kept; continuous path adds a '
  'stored predictive distribution. Scoring is Phase 6. Resolved predictions are '
  'never deleted or rescored under a later model (REQ-INF-328).';
