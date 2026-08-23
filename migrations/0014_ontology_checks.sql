-- 0014_ontology_checks.sql
-- REQ-ONT-001/002 (ADR-0023). Close the atoms.kind and entities.entity_type
-- taxonomies with CHECK constraints. NOT native ENUMs: these sets grow as feeds
-- are added, and a CHECK is extended by a cheap forward migration (drop + recreate
-- over an append-only table), whereas ALTER TYPE ... ADD VALUE cannot run in a
-- transaction and cannot retire a value. The truly-fixed vocabularies (presence,
-- provenance, state_class, time_precision, trust_level) stay native ENUMs.
--
-- Applied over EMPTY tables (RULE-01) — no historical-row validation, the cheapest
-- this will ever be (OQ-23). `kind` is the coarse observation class; the specific
-- measure lives in metric_key (metric_registry). Membership derivation + the
-- recorded guesses are in ADR-0023.

-- atoms.kind — 19 members: 7 spec/ADR-cited + 12 archive-derived (ADR-0023).
ALTER TABLE __CORE__.atoms
    ADD CONSTRAINT atoms_kind_taxonomy CHECK (kind IN (
        -- cited by REQ-FIN / ADR-0019
        'transaction', 'consume', 'mood', 'place_visit',
        'workout', 'sleep', 'screen_session',
        -- derived from the 34 archived tables
        'vital_sample', 'heart_rate_variability', 'body_measurement',
        'activity_sample', 'location_fix', 'web_visit', 'media_play',
        'calendar_event', 'environment_sample', 'self_report', 'note',
        'context_fact'
    ));

-- entities.entity_type — 6 members (ADR-0004 named 4; +2 archive-derived, ADR-0023).
ALTER TABLE __CORE__.entities
    ADD CONSTRAINT entities_type_taxonomy CHECK (entity_type IN (
        'merchant', 'place', 'food', 'person', 'media_channel', 'website'
    ));

COMMENT ON CONSTRAINT atoms_kind_taxonomy ON __CORE__.atoms IS
  'REQ-ONT-001 / ADR-0023. Closed coarse-kind taxonomy (19). A new member is a '
  'forward migration + REQ-ONT edit + ADR (REQ-ONT-003), never a silent value. '
  'The specific measure is metric_key (registry), not a new kind.';
COMMENT ON CONSTRAINT entities_type_taxonomy ON __CORE__.entities IS
  'REQ-ONT-002 / ADR-0023. Closed entity_type taxonomy (6). Extension rule as '
  'atoms_kind_taxonomy. entities remain shape-only until Phase 4 (ADR-0004).';
