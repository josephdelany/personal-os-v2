# ADR-0025: Gate-2 backfill means reconciliation, not row-count equality

## Status

Accepted

## Date

2026-08-23

## Context

ROADMAP Gate 2 says: *"Backfilled row count matches the Parquet archive."* The archive is
**810,933 rows across 63 tables** (426,282 Supabase + 384,651 local; verified against the
`_legacy_snapshot/` manifests, which carry per-table counts and `sha256`).

Read as equality — `atoms == 810,933` — the gate is unsatisfiable without breaking the
constitution (full map: `docs/PHASE2_BACKFILL_PLAN.md`, tool: `tools/backfill_map.py`):

- **~111,113 rows (17 tables) are the old stack's DERIVED outputs** (`signals`,
  `insights`, `hypotheses`, `inferred_events`, forecasts, baselines, …). Importing them
  as atoms fabricates `raw_captures` lineage they never had (**INV-1**) and stores
  inferred values as if measured (**INV-5, RULE-01**).
- **~72,108 rows (6 tables) are cross-archive DUPLICATES** — the same facts in two
  snapshots (a backup table duplicating a canonical Supabase table is counted once, as a
  duplicate). Ingesting both double-counts.
- **~2,639 rows are reference/registry data** → `core.entities` / `metric_registry`.
- **7 tables are empty.**
- The largest table, `intraday` (250,069), is a **multi-metric stream that fans out**:
  one archived row becomes several atoms, so even for kept data the count is not 1:1.

## Decision

**Gate 2's row-count criterion is satisfied by RECONCILIATION, not equality.** Gate 2
passes when **every archived row is accounted for** — mapped to one or more atoms, or
excluded with a **recorded reason** — and the accounting is **exact and per-source-table**:
for each table, `rows_in = atoms_out (after documented split/dedup) + excluded_with_reason`.

The reconciliation is a re-runnable artifact (`tools/backfill_map.py`), which asserts the
63 tables' dispositions sum to 810,933 with zero unaccounted rows. A backfill migration is
complete when, table by table, its atom output plus its recorded exclusions reproduce the
manifest counts — a stronger, auditable claim than a single global integer match.

This **amends the wording of ROADMAP Gate 2** (a director ruling, recorded here, not a
weakening — RULE-00: nothing is lowered; the check becomes stricter and honest). The
excluded classes may re-enter later only as their proper thing: DERIVED rows as Phase-5/6
`derived_measures` computed by *our* owned jobs from *our* atoms (never imported as
someone else's numbers); reference rows via Phase-4 entity resolution.

## Consequences

**Good.** The gate becomes provable and honest: no derived data is laundered into atoms,
no fact is double-counted, and every one of 810,933 rows has a disposition on record. The
audit is code, re-runnable at execution time against the same manifests.

**Bad / flagged.** The atom count is **not knowable until the `intraday`/`events`
per-metric split is written**, so Gate 2 can only be evaluated after the backfill
migration exists (execution session). Three judgement calls still owe a ruling before
that migration: the INV-1 lineage mechanism for legacy atoms (one `raw_captures` per
table-load vs per-row), the gait `vital_sample`↔`activity_sample` boundary (~170k rows,
O-Q2), and confirmation that OVERLAP tables are strict subsets of their canonical. All
are named in the backfill plan's WHAT I DID NOT DO.

## Alternatives considered

- **Literal equality (`atoms == 810,933`).** Rejected: unconstitutional for the derived
  and duplicate rows; would require fabricating lineage and double-counting.
- **Atoms-only, no ledger.** Rejected: silently dropping 185,875 rows with no recorded
  reason is exactly the "gate passes while missing data" failure Phase 0 was built to
  prevent. The exclusion reasons are the point.
- **Defer the wording ruling to execution.** Considered (it was offered as an option);
  Joe chose to fix the semantics now via this ADR so the execution session builds against
  a settled definition.
