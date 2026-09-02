-- 0026_analysis_schema.sql — the conversation layer's compute home (ADR-0038)
--
-- `analysis` holds DERIVED, REBUILDABLE data: the daily panel, baselines, scan
-- results, forecasts scaffolding. It is deliberately NOT append-only (unlike
-- core): every row is re-derivable from immutable sources (core.* + public.* +
-- archived files), carries provenance (source tag + code_version), and a full
-- rebuild is one job run. INV-3 holds: surfaced numbers trace to these rows,
-- which trace to their sources. anon/authenticated get NO direct access — reads
-- go through owner-locked RPCs only (ADR-0020/0036 posture).

CREATE SCHEMA IF NOT EXISTS analysis;
REVOKE ALL ON SCHEMA analysis FROM anon, authenticated;

-- The legacy seven-year daily series (loaded from 05_archive/daily_series.csv by
-- tools/parsers/legacy_daily.py; 2,382 days 2019-09-03..2026, sparse-honest).
CREATE TABLE IF NOT EXISTS analysis.legacy_daily (
    day        DATE PRIMARY KEY,
    hrv        NUMERIC, rhr      NUMERIC, resp    NUMERIC,
    kcal       NUMERIC, exmin    NUMERIC, steps   NUMERIC,
    asleep     NUMERIC, inbed    NUMERIC, deep    NUMERIC,
    rem        NUMERIC, core_min NUMERIC, awake   NUMERIC,
    onset      NUMERIC, wake_min NUMERIC,
    source     TEXT NOT NULL DEFAULT 'daily_series_csv_2026-06',
    loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The unified daily panel: one row per (day, metric). Rebuilt by the panel
-- engine from public.signals + analysis.legacy_daily + core.atoms aggregates.
CREATE TABLE IF NOT EXISTS analysis.panel (
    day          DATE NOT NULL,
    metric       TEXT NOT NULL,        -- canonical panel-dictionary name
    value        NUMERIC NOT NULL,
    src          TEXT NOT NULL,        -- 'signals:<source>' | 'legacy_daily' | 'atoms'
    code_version TEXT NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, metric)
);
CREATE INDEX IF NOT EXISTS panel_metric_idx ON analysis.panel (metric, day);

-- Baselines & state per (day, metric): the E2 engine's output.
CREATE TABLE IF NOT EXISTS analysis.baselines (
    day          DATE NOT NULL,
    metric       TEXT NOT NULL,
    value        NUMERIC,
    z_fast       NUMERIC,              -- 7d scale
    z_slow       NUMERIC,              -- 28d scale
    band_lo      NUMERIC,              -- personal p10 (trailing 90d)
    band_hi      NUMERIC,              -- personal p90
    run_len      INTEGER,              -- consecutive days outside band (sign of z_fast)
    code_version TEXT NOT NULL,
    computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (day, metric)
);

-- Scan output detail (the CANDIDATE rows in core.hypothesis_register carry the
-- registered identity; this holds the full contrast statistics for rendering).
CREATE TABLE IF NOT EXISTS analysis.contrasts (
    contrast_id   TEXT PRIMARY KEY,    -- driver|outcome|lag|run_date
    run_date      DATE NOT NULL,
    driver        TEXT NOT NULL,
    outcome       TEXT NOT NULL,
    lag_days      INTEGER NOT NULL,
    seeded        BOOLEAN NOT NULL,    -- from the named manifest vs discovery
    n_hi          INTEGER NOT NULL,    -- top-quartile driver days with outcome
    n_lo          INTEGER NOT NULL,
    med_hi        NUMERIC NOT NULL,    -- outcome median on high-driver days
    med_lo        NUMERIC NOT NULL,
    delta         NUMERIC NOT NULL,
    p_raw         NUMERIC NOT NULL,    -- Mann-Whitney
    q_fdr         NUMERIC NOT NULL,    -- BH across the run family
    n_eff_hi      NUMERIC, n_eff_lo NUMERIC,
    rho_outcome   NUMERIC,             -- lag-1 autocorr used for n_eff
    weekday_partialled BOOLEAN NOT NULL DEFAULT true,
    hypothesis_id TEXT,                -- the CANDIDATE row it registered, if surviving
    code_version  TEXT NOT NULL,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS contrasts_run_idx ON analysis.contrasts (run_date, q_fdr);

-- Null-calibration ledger (III.1a): per scan run, observed vs shuffled discovery.
CREATE TABLE IF NOT EXISTS analysis.scan_calibration (
    run_date       DATE PRIMARY KEY,
    n_pairs_tested INTEGER NOT NULL,
    observed_sig   INTEGER NOT NULL,   -- q<0.05 on real panel
    null_sig       INTEGER NOT NULL,   -- q<0.05 on circularly-shifted panel
    code_version   TEXT NOT NULL,
    computed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
