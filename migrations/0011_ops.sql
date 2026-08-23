-- 0011_ops.sql
-- Operational spine. ops.runs is the heartbeat every job writes to; ops.egress_log
-- records every outbound model call (RULE-29); ops.job_registry names the jobs and
-- their staleness limits. These are operational, not personal data.

CREATE TABLE __OPS__.job_registry (
    job_name        TEXT PRIMARY KEY,
    description     TEXT NOT NULL,
    schedule        TEXT,                        -- cron expression or 'on_demand'
    max_staleness_hours INTEGER,                 -- staleness alerting (Phase 4)
    enabled         BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE __OPS__.runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name        TEXT NOT NULL,               -- soft ref to job_registry (jobs may run before registration)
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running','ok','error')),
    rows_written    INTEGER,
    detail          JSONB,
    CHECK (finished_at IS NULL OR finished_at >= started_at)
);
CREATE INDEX runs_job_started_idx ON __OPS__.runs (job_name, started_at DESC);

CREATE TABLE __OPS__.egress_log (
    egress_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    destination     TEXT NOT NULL,               -- 'cloudflare_workers_ai', originating source API, ...
    purpose         TEXT NOT NULL,
    request_bytes   INTEGER,
    response_bytes  INTEGER,
    run_id          UUID REFERENCES __OPS__.runs(run_id),
    -- RULE-29: home coordinates never appear in a prompt; this log proves what left.
    detail          JSONB
);
CREATE INDEX egress_log_occurred_idx ON __OPS__.egress_log (occurred_at DESC);

COMMENT ON TABLE __OPS__.egress_log IS
  'RULE-29: every outbound model call writes a row here. No location data, ever.';
