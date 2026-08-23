-- 0002_metric_registry.sql
-- The registry that makes a *general* inference layer possible: the statistics
-- iterate over registry rows, not hand-written pairs (ADR-0002).
-- ADR-0018 adds the coarsening metadata so a self-report is stored as
-- interval-censored data, not a false point (Decision 4).

CREATE TABLE __CORE__.metric_registry (
    metric_key        TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    family            TEXT NOT NULL,            -- FDR grouping (RULE-21 tree)
    unit              TEXT,
    state_class       TEXT NOT NULL
                        CHECK (state_class IN ('measurement','total','total_increasing')),
    expected_cadence  TEXT,                     -- e.g. 'daily','per_meal','irregular'
    max_staleness_days INTEGER,                 -- REQ-INF-109 no forward-fill past this
    plausible_low     NUMERIC,
    plausible_high    NUMERIC,
    -- ADR-0018 scale/rounding metadata (self-reports are coarsened, arXiv:2501.10726)
    self_report       BOOLEAN NOT NULL DEFAULT false,
    response_scale    NUMRANGE,                 -- e.g. numrange(0,10,'[]')
    n_scale_points    INTEGER,                  -- e.g. 11 for a 0..10 integer scale
    rounding_step     NUMERIC,                  -- e.g. 1 for integer responses
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (plausible_low IS NULL OR plausible_high IS NULL OR plausible_low <= plausible_high),
    CHECK (n_scale_points IS NULL OR n_scale_points > 1)
);

COMMENT ON TABLE __CORE__.metric_registry IS
  'ADR-0002 measure registry + ADR-0018 coarsening metadata. One row per measure; '
  'the inference layer iterates over these rows.';
COMMENT ON COLUMN __CORE__.metric_registry.self_report IS
  'ADR-0018: TRUE means values are coarsened interval data (response_scale + '
  'rounding_step describe the coarsening), not points.';
