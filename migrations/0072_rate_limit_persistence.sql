-- 0072_rate_limit_persistence.sql — a rate limit that survives the process (REQ-NUT-009,
-- REQ-NUT-011, REQ-NUT-012). Requested by the nutrition worker's handoff §3c; DDL is theirs.
--
-- WHY THIS GOT MORE SERIOUS THAN THE B12 BRIEF ANTICIPATED. The brief recorded a per-process
-- `Limits` object as an Open Food Facts politeness gap. The USDA client added this session has
-- a per-process `Quota` with the same shape, and for USDA the consequence is different in kind:
--
--   REQ-NUT-012 is a provider 429, and the cooldown it sets is FORGOTTEN WHEN THE PROCESS
--   EXITS. A second run started inside the hour will issue requests api.data.gov has already
--   refused. That risks the key itself, not merely good manners.
--
-- Two concurrent runs each believe they hold the whole ration, so the effective rate is the
-- limit times the number of processes — and nothing in the system currently stops two.
--
-- WHY TWO TABLES AND NOT A COUNTER. A sliding window is a question about the last N minutes, so
-- it needs the timestamps, not a total. A counter cannot answer "how many in the last hour"
-- without also storing when the hour started, which is the same data with a reset bug attached.
--
-- THE METER IS THE THING RATE-LIMITED, NOT THE CODE PATH THAT CALLS IT. One api.data.gov key
-- serves both the Branded and the Foundation legs, so both meter as 'usda'. Metering them
-- separately would let two legs of one cascade spend one ration twice, which is the same error
-- as counting two copies of a receipt as two corroborations.
CREATE TABLE IF NOT EXISTS __OPS__.rate_limit_events (
    event_id  BIGSERIAL PRIMARY KEY,
    meter     TEXT NOT NULL,      -- 'usda' | 'off_search' | 'off_product'
    issued_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS rate_limit_events_meter_idx
    ON __OPS__.rate_limit_events (meter, issued_at DESC);

-- REQ-NUT-012. A refusal the provider issued, remembered past the process that received it.
CREATE TABLE IF NOT EXISTS __OPS__.rate_limit_cooldowns (
    meter         TEXT PRIMARY KEY,
    blocked_until TIMESTAMPTZ NOT NULL,
    reason        TEXT NOT NULL CHECK (reason IN ('provider_429','quota_exhausted')),
    set_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE __OPS__.rate_limit_events IS
    'REQ-NUT-009/011. One row per outbound request, per meter, so a sliding window is a query '
    'rather than a per-process counter two concurrent runs would each keep separately. The '
    'meter is the rate-limited resource: one api.data.gov key serves both USDA legs, so both '
    'meter as ''usda''. Needs pruning; the schedule is not decided here.';

COMMENT ON TABLE __OPS__.rate_limit_cooldowns IS
    'REQ-NUT-012. A provider 429 outlives the process that received it. Without this a second '
    'run inside the cooldown reissues requests the provider already refused, which risks the '
    'credential rather than merely being impolite.';

REVOKE ALL ON __OPS__.rate_limit_events, __OPS__.rate_limit_cooldowns FROM anon, authenticated;
