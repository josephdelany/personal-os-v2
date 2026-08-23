-- 0003_entities.sql
-- ADR-0004 (table shape ONLY). The resolution algorithm — blocking keys, match
-- thresholds, the review queue — is Phase 4 and is deliberately absent here.
-- This table shape is authored by ADR because no spec defines entities: the
-- ontology spec is unwritten (OQ-16). `public.entities` (old stack) is a
-- different table in a different schema and is not touched.
--
-- Bitemporal + provenance + RULE-10 human-correction lineage: once Joe corrects
-- an entity match, no automated layer may re-guess it, so corrections are
-- first-class superseding rows, never edits.

CREATE TABLE __CORE__.entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type     TEXT NOT NULL,            -- 'merchant','place','food','person',... (open pending ontology spec, OQ-16)
    canonical_name  TEXT NOT NULL,
    attributes      JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- provenance
    provenance      TEXT NOT NULL
                      CHECK (provenance IN ('extracted','inferred','defaulted','human')),
    confidence      NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    code_version    TEXT,
    -- transaction time: recorded_at anchors when learned; currency is DERIVED from
    -- supersedes (a row is current iff nothing supersedes it), not a stored
    -- expired_at — same INV-2 reasoning as atoms (the guard treats entities as
    -- append-only; a stored expiry would need a forbidden UPDATE).
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes      UUID REFERENCES __CORE__.entities(id),
    -- RULE-10: a human correction outranks every automated layer, permanently
    corrected_by_human BOOLEAN NOT NULL DEFAULT false
);

CREATE INDEX entities_type_name_idx ON __CORE__.entities (entity_type, canonical_name);
CREATE INDEX entities_supersedes_idx ON __CORE__.entities (supersedes);

CREATE VIEW __CORE__.entities_current AS
    SELECT e.* FROM __CORE__.entities e
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.entities s WHERE s.supersedes = e.id);

COMMENT ON TABLE __CORE__.entities IS
  'ADR-0004 table shape only; resolution algorithm is Phase 4. No spec defines '
  'this table (ontology spec unwritten, OQ-16). Corrections supersede, never edit '
  '(RULE-10).';
