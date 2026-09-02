# ADR-0044: The restricted store is a schema with zero grants, read only by SQL inside the database

## Status
Accepted

## Date
2026-09-02

## Decision (answers LOC-Q2)
Coordinates live in a `restricted` schema (migration 0038): `location_fixes` (append-only,
INV-2, every row FK-linked to a `core.raw_captures` row for INV-1), `places` (human- or
inferred-provenance, `supersedes` for corrections, `is_home` for REQ-LOC-008), `visits`
(derived, rebuildable, centroids stay here). **The schema has zero grants** for `anon`,
`authenticated` and `service_role`, and default privileges revoke future tables too. **Its
only readers are `SECURITY DEFINER` SQL functions inside the database** (`ingest_location`,
`ingest_location_batch`, `register_place`, `assign_place`, and B5.2/B5.3's derivation and
read RPCs). **No code outside `migrations/` may name a `restricted.` table** — a lint in
`tools/validate_layout.py` (B5.2) fails the build on it, with an explicit allowlist for the
hourly `derive_visits` call. A Python job therefore cannot read a coordinate even by mistake.

Ingress writes two rows: a `core.raw_captures` row whose payload is **redacted**
(`{"kind":"location","redacted":true,"source":…}`, `trust_level` = trusted, REQ-LOC-004) for
lineage, and the coordinate row in `restricted`. The client never receives a coordinate back
in any direction: `assign_place` creates a place **from the visit centroid server-side**.

## Decisions taken inside B5.1's envelope (recorded, not silent)
1. **`processing_status = 'enriched'`**, not B5's `'extracted'`: the live CHECK on
   `core.raw_captures` allows `received | pending_enrichment | enriched | failed`. A location
   capture needs no extraction, so it is born enriched.
2. **Append-only trigger** is a copy of `core.reject_mutation()` living in `restricted`
   (B5 said copy), attached through a `DO` block because `CREATE TRIGGER` has no
   `IF NOT EXISTS` and the migration must be re-applicable.
3. **Tests use disposable twins** (RULE-01 / ADR-0022): `tests/_location_fixture.py`
   re-applies the whole chain with `core→core_pytest`, `ops→ops_pytest`, the location
   schema → `restricted_pytest`, `analysis.visits_public → analysis_pytest.visits_public`,
   inside one rolled-back transaction. Test coordinates are ocean points (0.0 / 0.01).
   The helper references the schema name only to rewrite it; it reads no coordinate.
4. **`anon` may EXECUTE `ingest_location`** (write-only, returns no data) — the Shortcut
   fallback path, mirroring `ingest_capture` (ADR-0034). `ingest_location_batch` is
   `service_role` only (the Overland edge function, ADR-0046).
5. **Legacy `public.locations` (282 rows, 2026-07-16..07-29) is not migrated** — OQ-43.

## Consequences
- Every later location surface (B5.2 derivation, B5.3 RPCs) inherits the boundary: labels,
  minutes and aggregates cross it; coordinates never do (REQ-LOC-002/007/012).
- `subject_day` is stamped at ingress with the ADR-0019 rule and the literal
  `v1-2026-08-23` shared with `tools/extract_checkins.py`, so a future rule change is
  visible, not silent.

## Alternatives considered
- Row-level security on a `public`/`core` table: rejected — RLS is bypassed by the table
  owner and by `service_role`; a schema with no grants and function-only access is the
  stronger, simpler boundary.
- Storing coordinates in `core.atoms` as `location_fix` atoms: rejected — `atoms` is
  egress-reachable (REQ-LOC-001).
