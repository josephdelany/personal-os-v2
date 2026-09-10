-- 0057_entities_and_merchants.sql — B14.1: descriptor normalisation and merchant resolution
-- (REQ-ONT-005/006, REQ-FIN-060..062, REQ-FIN-070..074, RULE-10, INV-2; ADR-0090).
--
-- The B14 brief calls this "migration 0052_entities.sql". 0052 is the neuron ledger and is
-- live; briefs are not authoritative on migration numbers (CLAUDE.md). Reserved from Git.
--
-- NO PERSONAL DATA IN THIS FILE. The brief proposes seeding merchant patterns from Joe's top
-- 100 descriptors. A merchant descriptor is an observation about Joe — where he was and what
-- he bought — and this repository is public, so the patterns are DISCOVERED at run time by
-- tools/engines/resolve_merchants.py into the tables below, exactly as the source inventory's
-- counts are (ADR-0088). This file is shape and rules only.

-- REQ-ONT-005/006 NEEDS NOTHING HERE, and an earlier draft of this file added it anyway.
--
-- I read 0003_entities.sql — which has no CHECK and carries OQ-16's "taxonomy lost" comment —
-- read OQ-16, and concluded the constraint was missing. It is not: 0014_ontology_checks.sql
-- has enforced exactly this closed six since Phase 2 as `entities_type_taxonomy`. The
-- duplicate I added under a different name was redundant, and it broke
-- test_REQ_ONT_002_entity_type_taxonomy_enforced, which asserts the constraint BY NAME —
-- the existing gate doing its job. The lesson is the standing one: a later migration can
-- answer a question an earlier file's comment leaves open, so read the chain, not one file.

-- REQ-FIN-070/071/074. The pattern table. A row here is an ASSERTION that a descriptor means
-- a merchant, and REQ-FIN-073 forbids a provisional guess from ever landing in it.
CREATE TABLE IF NOT EXISTS config.merchant_patterns (
    pattern       TEXT NOT NULL,
    canonical     TEXT NOT NULL,
    is_regex      BOOLEAN NOT NULL DEFAULT false,
    -- REQ-FIN-071: regex patterns are evaluated in DESCENDING specificity. Without an
    -- explicit order a broad catch-all like '^SH' silently swallows every merchant that
    -- happens to share two letters with it.
    specificity   INTEGER NOT NULL DEFAULT 0,
    provenance    TEXT NOT NULL CHECK (provenance IN ('human','seed','discovered')),
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (pattern, is_regex),
    CONSTRAINT a_regex_pattern_declares_its_specificity
        CHECK (NOT is_regex OR specificity > 0)
);
REVOKE ALL ON config.merchant_patterns FROM anon, authenticated;

-- REQ-FIN-060. The discovered city vocabulary. A token that follows MANY different merchants
-- is a location; one that follows a single merchant is part of its name. Learned from Joe's
-- own descriptors rather than from a gazetteer, so it is reproducible, inspectable, and adds
-- no dependency for one field.
CREATE TABLE IF NOT EXISTS config.location_tokens (
    token             TEXT PRIMARY KEY,
    distinct_prefixes INTEGER NOT NULL,
    discovered_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT a_location_token_needs_evidence CHECK (distinct_prefixes >= 4)
);
REVOKE ALL ON config.location_tokens FROM anon, authenticated;

-- The categorisation cascade's data (Finance §B.3).
CREATE TABLE IF NOT EXISTS config.category_rules (
    merchant_canonical TEXT PRIMARY KEY,
    category           TEXT NOT NULL,
    necessity_default  TEXT,
    provenance         TEXT NOT NULL CHECK (provenance IN ('human','seed','discovered'))
);
REVOKE ALL ON config.category_rules FROM anon, authenticated;

-- RULE-10 + INV-2. Joe's corrections, and every automated resolution, as an APPEND-ONLY
-- ledger. A correction supersedes; it never edits. `resolved_by` records which cascade step
-- produced the row, which is what makes the confidence interpretable later — 'fuzzy at 0.83'
-- and 'Joe said so' are not the same claim and must never be stored as if they were.
CREATE TABLE IF NOT EXISTS __CORE__.entity_aliases (
    alias_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias          TEXT NOT NULL,               -- the NORMALIZED descriptor
    raw_descriptor TEXT,                        -- REQ-FIN-061: the original, verbatim
    canonical      TEXT NOT NULL,
    entity_id      UUID REFERENCES __CORE__.entities(id),
    resolved_by    TEXT NOT NULL
        CHECK (resolved_by IN ('human','pattern_exact','pattern_regex','fuzzy','provisional')),
    confidence     NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    normalization_rules TEXT[] NOT NULL DEFAULT '{}',   -- REQ-FIN-062
    unconfirmed    BOOLEAN NOT NULL DEFAULT false,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes     UUID REFERENCES __CORE__.entity_aliases(alias_id),
    -- REQ-FIN-073: a provisional resolution has no confidence to report. A number here would
    -- be read downstream as evidence, and there is none.
    CONSTRAINT provisional_has_no_confidence
        CHECK (resolved_by <> 'provisional' OR confidence IS NULL),
    -- RULE-10: a human answer is certain by definition; anything else claiming 1.0 must have
    -- earned it from an exact rule, never from a fuzzy comparison.
    CONSTRAINT only_a_rule_or_a_human_is_certain
        CHECK (resolved_by IN ('human','pattern_exact','pattern_regex')
               OR confidence IS NULL OR confidence < 1.0 OR resolved_by = 'fuzzy')
);
CREATE INDEX IF NOT EXISTS entity_aliases_alias_idx ON __CORE__.entity_aliases (alias, recorded_at DESC);
REVOKE ALL ON __CORE__.entity_aliases FROM anon, authenticated;

CREATE OR REPLACE FUNCTION __CORE__.entity_aliases_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'RULE-02/INV-2: % on entity_aliases is forbidden; supersede the row instead',
        TG_OP USING ERRCODE = '42501';
END $$;
DROP TRIGGER IF EXISTS entity_aliases_append_only ON __CORE__.entity_aliases;
CREATE TRIGGER entity_aliases_append_only BEFORE UPDATE OR DELETE
    ON __CORE__.entity_aliases FOR EACH ROW EXECUTE FUNCTION __CORE__.entity_aliases_append_only();

-- RULE-10, enforced rather than intended: the resolver may revise itself but may not
-- supersede Joe. Without this the next hourly run reverts every correction he ever made and
-- the ledger presents it as an improvement.
CREATE OR REPLACE FUNCTION __CORE__.entity_alias_precedence() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE prior text;
BEGIN
    IF NEW.supersedes IS NULL THEN RETURN NEW; END IF;
    SELECT resolved_by INTO prior FROM __CORE__.entity_aliases WHERE alias_id = NEW.supersedes;
    IF prior = 'human' AND NEW.resolved_by <> 'human' THEN
        RAISE EXCEPTION 'RULE-10: an automated resolution may not supersede a human correction (alias %)',
            NEW.supersedes USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS entity_aliases_precedence ON __CORE__.entity_aliases;
CREATE TRIGGER entity_aliases_precedence BEFORE INSERT
    ON __CORE__.entity_aliases FOR EACH ROW EXECUTE FUNCTION __CORE__.entity_alias_precedence();

-- The current resolution for each descriptor: the head of every supersede chain. Consumers
-- read this, never the raw table, so a corrected merchant stops being served.
CREATE OR REPLACE VIEW __CORE__.v_current_aliases AS
SELECT a.* FROM __CORE__.entity_aliases a
 WHERE NOT EXISTS (SELECT 1 FROM __CORE__.entity_aliases s WHERE s.supersedes = a.alias_id);
REVOKE ALL ON __CORE__.v_current_aliases FROM anon, authenticated;

-- REQ-FIN-073. What Joe is asked to confirm. A provisional merchant waits here; it does not
-- quietly become a fact.
CREATE TABLE IF NOT EXISTS __CORE__.merchant_review_queue (
    review_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias          TEXT NOT NULL UNIQUE,
    raw_descriptor TEXT,
    n_transactions INTEGER NOT NULL DEFAULT 1,
    considered     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- RULE-18: what it nearly matched
    status         TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open','confirmed','dismissed')),
    raised_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
REVOKE ALL ON __CORE__.merchant_review_queue FROM anon, authenticated;
