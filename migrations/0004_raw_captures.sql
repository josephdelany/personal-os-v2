-- 0004_raw_captures.sql
-- The immutable ingest landing. Every derived row ultimately traces here (INV-1).
-- Append-only: UPDATE/DELETE denied at the grant level (0012) AND by trigger
-- (ADR-0010). REQ-CAP-006/011/012/013/015.
--
-- capture_source: the spec's four values (REQ-CAP-006) plus notification_parse
-- and reserved values for the net-new feeds (Decision 8). trust_level at ingest
-- (ADR-0020): anything authored by a third party is 'untrusted'.

CREATE TYPE __CORE__.capture_source AS ENUM (
    'shortcut_voice', 'shortcut_photo', 'shortcut_text', 'pwa_text',  -- REQ-CAP-006
    'notification_parse',                                             -- Decision 8
    'healthkit_workout', 'email_receipt', 'location'                 -- reserved (net-new feeds, Phase 3/4)
);

CREATE TYPE __CORE__.trust_level AS ENUM ('trusted', 'untrusted');   -- ADR-0020

CREATE TABLE __CORE__.raw_captures (
    capture_id        UUID PRIMARY KEY,          -- UUIDv7 generated on device (REQ-CAP-006)
    captured_at       TIMESTAMPTZ NOT NULL,      -- device clock at capture (REQ-CAP-006)
    recorded_at       TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when the system landed it
    source            __CORE__.capture_source NOT NULL,
    trust_level       __CORE__.trust_level NOT NULL,       -- ADR-0020, set at ingest
    payload           JSONB NOT NULL,            -- text and/or media reference; immutable
    transcript        TEXT,                      -- retained indefinitely (REQ-CAP-013)
    -- extraction provenance (REQ-CAP-015)
    model_id          TEXT,
    prompt_version    TEXT,
    -- processing lifecycle (REQ-CAP-025..027)
    processing_status TEXT NOT NULL DEFAULT 'received'
                        CHECK (processing_status IN
                          ('received','pending_enrichment','enriched','failed')),
    last_error        TEXT
);

CREATE INDEX raw_captures_captured_at_idx ON __CORE__.raw_captures (captured_at);
CREATE INDEX raw_captures_source_idx ON __CORE__.raw_captures (source);

COMMENT ON TABLE __CORE__.raw_captures IS
  'Immutable ingest landing (REQ-CAP-012/013). Append-only: grants (0012) + '
  'ADR-0010 trigger. trust_level set at ingest (ADR-0020). Every atom FKs here '
  '(INV-1). Full capture transport contract is ADR-0008, deferred to Phase 3.';
