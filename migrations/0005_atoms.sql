-- 0005_atoms.sql
-- The atom (ADR-0002) with the ADR-0019 temporal amendment. Append-only (INV-2):
-- grants (0012) + a mutation-rejecting trigger + a BEFORE INSERT trigger that
-- forces the system-set columns. Sections are predicates over atoms evaluated at
-- read time, never containers.
--
-- ADR-0019 temporal model (Joe's ruling 2026-08-23):
--   * point events:  occurred_at + time_precision  (valid_interval NULL)
--   * durational:    valid_interval tstzrange       (workout, sleep, screen session)
--   * subject_day:   application-computed STORED column + subject_day_rule_version
--                    (04:00 local, by START instant, EXCEPT sleep by wake day).
--
-- CORRECTION to ADR-0019 (this session, flagged for Joe): transaction time is NOT
-- a stored `expired_at`. A stored expiry would have to be stamped onto the old row
-- when a correction supersedes it — an UPDATE, which INV-2 forbids and the RULE-02
-- trigger blocks. The invariant wins over the convenience column. Currency is
-- therefore DERIVED from the supersedes graph: a row is current iff no other row
-- supersedes it. `recorded_at` is the transaction-time anchor and is system-set at
-- INSERT (forced by trigger in 0012), never client-set — the guarantee ADR-0002
-- asserts and B1 of this session's review found unenforced.

CREATE TYPE __CORE__.time_precision AS ENUM ('exact','minute','hour','day','unknown');
CREATE TYPE __CORE__.presence       AS ENUM ('observed','observed_absent','unknown');  -- RULE-07
CREATE TYPE __CORE__.provenance     AS ENUM ('extracted','inferred','defaulted');
CREATE TYPE __CORE__.state_class    AS ENUM ('measurement','total','total_increasing'); -- ADR-0002 (Home Assistant)

CREATE TABLE __CORE__.atoms (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- INV-1: every atom traces to the immutable capture it derives from
    raw_capture_id  UUID NOT NULL REFERENCES __CORE__.raw_captures(capture_id),

    -- What kind of thing. The closed 20-member taxonomy of ADR-0002 lived in the
    -- lost ontology spec (OQ-16) and is NOT re-invented here: kind is TEXT until
    -- the taxonomy is ruled, then a CHECK/enum is added by a forward migration.
    kind            TEXT NOT NULL,
    metric_key      TEXT REFERENCES __CORE__.metric_registry(metric_key),

    -- Time — ADR-0019
    occurred_at     TIMESTAMPTZ,                 -- instant for a point event
    time_precision  __CORE__.time_precision NOT NULL DEFAULT 'unknown',
    valid_interval  TSTZRANGE,                   -- durational atoms only; NULL for points
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),  -- system-set at INSERT (trigger-forced), never client-set
    subject_day     DATE NOT NULL,               -- STORED, application-computed
    subject_day_rule_version TEXT NOT NULL,      -- versions the 04:00/by-start/sleep-by-wake rule
    supersedes      UUID REFERENCES __CORE__.atoms(id),  -- correction lineage; currency derived from this

    -- Presence — three-valued (RULE-07)
    presence        __CORE__.presence NOT NULL,

    -- Value — an interval with its method (RULE-08). measured => low=point=high.
    value_low       NUMERIC,
    value_point     NUMERIC,
    value_high      NUMERIC,
    estimate_method TEXT,                        -- 'measured','labelled','weighed',...  (the value's lane)
    unit            TEXT,

    -- Aggregation legality in the schema (ADR-0002)
    state_class     __CORE__.state_class,
    value_type      TEXT,                        -- incl. 'time_from_midnight','time_from_midday'

    -- Trust (ADR-0020) — set at ingest
    trust_level     __CORE__.trust_level NOT NULL,

    -- Provenance — mandatory (ADR-0002, RULE-05)
    provenance      __CORE__.provenance NOT NULL,
    evidence_span   TEXT,                        -- verbatim source text where a value came from a transcript
    confidence      NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    code_version    TEXT NOT NULL,
    confirmed_at    TIMESTAMPTZ,
    corrected_at    TIMESTAMPTZ,

    -- either a point instant or a durational interval must be present
    CONSTRAINT atoms_time_present CHECK (occurred_at IS NOT NULL OR valid_interval IS NOT NULL),
    -- interval ordering (RULE-08)
    CONSTRAINT atoms_value_ordered CHECK (
        (value_low IS NULL OR value_point IS NULL OR value_low <= value_point) AND
        (value_point IS NULL OR value_high IS NULL OR value_point <= value_high)),
    -- ADR-0002: a measured quantity collapses the interval to a point
    CONSTRAINT atoms_measured_is_point CHECK (
        estimate_method IS DISTINCT FROM 'measured'
        OR (value_low IS NOT DISTINCT FROM value_point
            AND value_point IS NOT DISTINCT FROM value_high)),
    -- INV-5 / RULE-05: a stored value always carries its lane (method + aggregation legality)
    CONSTRAINT atoms_value_has_lane CHECK (
        value_point IS NULL OR (estimate_method IS NOT NULL AND state_class IS NOT NULL)),
    -- RULE-07: an 'unknown' presence cannot carry a value (that would collapse the
    -- three-valued distinction back into a number)
    CONSTRAINT atoms_unknown_has_no_value CHECK (
        presence <> 'unknown'
        OR (value_low IS NULL AND value_point IS NULL AND value_high IS NULL))
);

CREATE INDEX atoms_subject_day_idx  ON __CORE__.atoms (subject_day);
CREATE INDEX atoms_metric_key_idx   ON __CORE__.atoms (metric_key);
CREATE INDEX atoms_raw_capture_idx  ON __CORE__.atoms (raw_capture_id);
CREATE INDEX atoms_supersedes_idx   ON __CORE__.atoms (supersedes);   -- currency derivation
-- GiST over the durational interval, so overlap (&&) analyses are exact and fast.
-- No overlap-forbidding exclusion constraint: overlapping atoms are legitimate
-- (a meal during a workout).
CREATE INDEX atoms_valid_interval_gist ON __CORE__.atoms
    USING gist (valid_interval) WHERE valid_interval IS NOT NULL;

-- Currency as a view (derived, append-only-safe): a row is current iff nothing
-- supersedes it. This delivers ADR-0019's "what do we currently believe" without a
-- mutable expired_at column. Point-in-time-as-of-D is a Phase-5/6 function over
-- recorded_at + this graph.
CREATE VIEW __CORE__.atoms_current AS
    SELECT a.* FROM __CORE__.atoms a
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.atoms s WHERE s.supersedes = a.id);

COMMENT ON COLUMN __CORE__.atoms.subject_day IS
  'ADR-0019: stored, application-computed. 04:00 local boundary, assigned by '
  'START instant, EXCEPT sleep atoms which are assigned to the wake day.';
COMMENT ON COLUMN __CORE__.atoms.recorded_at IS
  'Transaction-time anchor; system-set at INSERT by trigger (0012), never client-set. '
  'Currency is derived from supersedes (see atoms_current), not a stored expired_at, '
  'because INV-2 forbids the UPDATE a stored expiry would require.';
