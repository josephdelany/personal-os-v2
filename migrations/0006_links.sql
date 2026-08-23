-- 0006_links.sql
-- ADR-0004 (table shape ONLY). Edges between atoms and entities (e.g. this meal
-- atom was AT this merchant entity; this charge atom PAID this merchant). The
-- edge-inference algorithm is Phase 4; this is the shape only. No spec defines
-- it (ontology spec unwritten, OQ-16).

CREATE TABLE __CORE__.links (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_atom  UUID REFERENCES __CORE__.atoms(id),
    subject_entity UUID REFERENCES __CORE__.entities(id),
    predicate     TEXT NOT NULL,               -- 'at','paid','about','confounds',...
    object_atom   UUID REFERENCES __CORE__.atoms(id),
    object_entity UUID REFERENCES __CORE__.entities(id),
    -- provenance + bitemporal
    provenance    TEXT NOT NULL
                    CHECK (provenance IN ('extracted','inferred','defaulted','human')),
    confidence    NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    code_version  TEXT,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    supersedes    UUID REFERENCES __CORE__.links(id),  -- currency derived from this (append-only, INV-2)
    corrected_by_human BOOLEAN NOT NULL DEFAULT false,  -- RULE-10
    -- an edge needs exactly one subject endpoint and one object endpoint
    CHECK ((subject_atom IS NOT NULL)::int + (subject_entity IS NOT NULL)::int = 1),
    CHECK ((object_atom  IS NOT NULL)::int + (object_entity  IS NOT NULL)::int = 1)
);

CREATE INDEX links_subject_atom_idx  ON __CORE__.links (subject_atom);
CREATE INDEX links_subject_entity_idx ON __CORE__.links (subject_entity);
CREATE INDEX links_object_entity_idx ON __CORE__.links (object_entity);
CREATE INDEX links_supersedes_idx ON __CORE__.links (supersedes);

CREATE VIEW __CORE__.links_current AS
    SELECT l.* FROM __CORE__.links l
    WHERE NOT EXISTS (SELECT 1 FROM __CORE__.links s WHERE s.supersedes = l.id);
