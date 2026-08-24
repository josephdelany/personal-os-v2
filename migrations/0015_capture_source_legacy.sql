-- 0015_capture_source_legacy.sql
-- A' backfill lineage (ADR-0026; Joe's ruling 2026-08-23). Legacy atoms trace to
-- ONE raw_captures row per source TABLE-LOAD (source='legacy_archive'), whose
-- payload is the manifest entry (sha256 + row count) — legitimate batch
-- provenance, never a per-row fabricated capture. This adds the enum value those
-- table-load capture rows carry.
--
-- Additive, forward-only, idempotent (IF NOT EXISTS). Since PG12 an ADD VALUE may
-- run inside a transaction, but the new value is not usable until that
-- transaction commits — so this migration ONLY adds the value; the backfill that
-- USES it (writing the ~24 table-load captures and their atoms) is a separate,
-- later run against a committed enum.

ALTER TYPE __CORE__.capture_source ADD VALUE IF NOT EXISTS 'legacy_archive';
