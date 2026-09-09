-- 0053_source_inventory.sql — B14R step 1-2: the source inventory and the derivation
-- catalogue (REQ-REC-001..004, ADR-0084, docs/INTENT_COVERAGE.md).
--
-- WHY THIS EXISTS. The project's own record of "what data do we have" has been prose in
-- five documents that disagreed with each other and with the code. On 2026-09-09 the
-- freshness report said 0 of 17 metrics fresh while `apple_watch` had rows on 29 of the
-- last 30 days: both statements were true of different name spaces and the prose could not
-- tell them apart. An inventory that is a document drifts silently; an inventory that is a
-- table with constraints cannot claim a source is used when no parser reads it.
--
-- WHAT IS DELIBERATELY NOT HERE. No counts, no date ranges, no record types with volumes.
-- Those are personal data (a record count IS an observation about Joe) and they are
-- populated at runtime by tools/build_inventory.py, which reads the gitignored seed and
-- the live database. This file is shape and rules only, so the migration is safe to commit.
--
-- RULE-01: every row here describes a SOURCE, not an observation. Counts are scanned, never
-- estimated; a type whose count has not been scanned carries NULL and says so in scan_method.


-- REQ-REC-003. The closed disposition vocabulary. A record type is in exactly one of these
-- states and there is no "misc" — an unclassifiable type is a gap, and a gap has an owner.
DO $$ BEGIN
    CREATE TYPE config.source_disposition AS ENUM (
        'used',                   -- a parser reads it and it lands in core.atoms
        'pending_implementation', -- we want it, nothing reads it yet, an owner is named
        'duplicate',              -- the same originating records as another entry
        'historical_derived',     -- an old stack's OUTPUT, not a source record
        'unavailable',            -- looked for it, it is not there
        'excluded');              -- deliberately not taken, with a reason
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- REQ-REC-002. Whether we LOOKED, as distinct from what we found. An asset named only in a
-- historical design document is 'unverified_mentioned' until its artifact is opened. The
-- constraint below forbids reporting counts for one, which is the whole point: the old
-- documents are full of confident volumes for assets nobody has located.
DO $$ BEGIN
    CREATE TYPE config.source_availability AS ENUM (
        'verified_present', 'verified_absent', 'unverified_mentioned');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS config.source_inventory (
    source_family        TEXT NOT NULL,
    record_type          TEXT NOT NULL,
    availability         config.source_availability NOT NULL,
    disposition          config.source_disposition  NOT NULL,
    disposition_reason   TEXT NOT NULL,
    owner                TEXT NOT NULL,        -- the build unit that closes this gap
    parser_supported     BOOLEAN NOT NULL,     -- DERIVED FROM CODE, never asserted by hand
    metric_key           TEXT REFERENCES __CORE__.metric_registry(metric_key),
    record_count         BIGINT,
    event_date_from      DATE,
    event_date_to        DATE,
    count_in_window      BIGINT,               -- records inside the active recovery window
    atoms_stored         BIGINT,               -- what actually landed, for reconciliation
    observed_freshness   DATE,                 -- newest subject_day in core.atoms
    import_status        TEXT NOT NULL,
    duplicate_of         TEXT,
    analytical_consumers TEXT[] NOT NULL DEFAULT '{}',
    scan_method          TEXT NOT NULL,        -- how the numbers above were obtained
    scanned_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_family, record_type),

    -- REQ-REC-003: a source cannot be "used" if nothing reads it. This is the constraint the
    -- prose version could not have: three documents described types as in use that no parser
    -- had ever mapped.
    CONSTRAINT used_requires_a_parser
        CHECK (disposition <> 'used' OR (parser_supported AND metric_key IS NOT NULL)),

    -- REQ-REC-002: no counts for something nobody opened. An unverified asset with a record
    -- count is exactly the failure mode this table exists to stop.
    CONSTRAINT unverified_carries_no_numbers
        CHECK (availability <> 'unverified_mentioned'
               OR (record_count IS NULL AND event_date_from IS NULL
                   AND event_date_to IS NULL AND count_in_window IS NULL)),

    -- An absent source has no rows to count either.
    CONSTRAINT absent_carries_no_numbers
        CHECK (availability <> 'verified_absent' OR record_count IS NULL),

    -- REQ-REC-003: the reason is the deliverable, so it may not be empty or a placeholder.
    CONSTRAINT reason_is_substantive CHECK (length(btrim(disposition_reason)) >= 12),
    CONSTRAINT owner_is_named        CHECK (length(btrim(owner)) >= 2),

    CONSTRAINT duplicate_names_its_original
        CHECK (disposition <> 'duplicate' OR duplicate_of IS NOT NULL),
    CONSTRAINT dates_are_ordered
        CHECK (event_date_from IS NULL OR event_date_to IS NULL OR event_date_from <= event_date_to),
    -- RULE-04. A scan cannot discover records dated after the scan.
    CONSTRAINT no_future_coverage
        CHECK (event_date_to IS NULL OR event_date_to <= (scanned_at AT TIME ZONE 'America/New_York')::date)
);
COMMENT ON TABLE config.source_inventory IS
 'REQ-REC-001..003. One row per (source family, record type). Populated by '
 'tools/build_inventory.py from scans; never hand-edited, because a hand-edited '
 'inventory is the prose it replaces.';

-- REQ-REC-004. What each derived measure is MADE OF. Without this, a measure's definition
-- lives in whichever function last computed it, and two functions can disagree while both
-- look authoritative (RULE-12: one owner per measure).
CREATE TABLE IF NOT EXISTS config.derivation_catalogue (
    measure              TEXT PRIMARY KEY REFERENCES __CORE__.metric_registry(metric_key),
    input_fields         TEXT[] NOT NULL,
    method               TEXT NOT NULL,
    method_version       TEXT NOT NULL,
    unit                 TEXT NOT NULL,
    -- RULE-08. An accumulating quantity is a fact about an interval; a reading is a fact
    -- about an instant. Storing which is which is what stops "3 steps at 08:14" being read
    -- as a point measurement. See OQ-54: the 2026-09-09 import got this wrong.
    time_specification   TEXT NOT NULL
        CHECK (time_specification IN ('instant','interval','subject_day_aggregate')),
    missingness_rule     TEXT NOT NULL,
    earliest_supported_event_date DATE,
    analytical_consumers TEXT[] NOT NULL DEFAULT '{}',
    owner                TEXT NOT NULL,
    CONSTRAINT inputs_are_named       CHECK (cardinality(input_fields) > 0),
    CONSTRAINT missingness_is_stated  CHECK (length(btrim(missingness_rule)) >= 8)
);
COMMENT ON TABLE config.derivation_catalogue IS
 'REQ-REC-004. Input fields, method version, units, time specification and missingness '
 'rule for every derived measure, with its consumers.';

-- "Map every omission to an implementation owner" (EXECUTION_PLAN, ADR-0084) made queryable.
CREATE OR REPLACE VIEW config.v_inventory_gaps AS
SELECT source_family, record_type, availability, disposition, owner, disposition_reason,
       record_count, event_date_from, event_date_to
  FROM config.source_inventory
 WHERE disposition <> 'used'
 ORDER BY disposition, coalesce(record_count, 0) DESC, record_type;

-- REQ-REC-004: a measure that atoms exist for but the catalogue does not describe. This is
-- the drift detector: the 2026-09-09 import created 25 metric keys and the catalogue must
-- account for all of them or name who will.
CREATE OR REPLACE VIEW config.v_uncatalogued_measures AS
SELECT DISTINCT a.metric_key
  FROM __CORE__.atoms a
  LEFT JOIN config.derivation_catalogue d ON d.measure = a.metric_key
 WHERE a.metric_key IS NOT NULL AND d.measure IS NULL
 ORDER BY 1;

REVOKE ALL ON config.source_inventory, config.derivation_catalogue FROM anon, authenticated;
REVOKE ALL ON config.v_inventory_gaps, config.v_uncatalogued_measures FROM anon, authenticated;

