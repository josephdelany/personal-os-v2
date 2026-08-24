# ADR-0028: Legacy history is Parquet-authoritative; the Postgres load is deferred

## Status

Accepted

## Date

2026-08-23

## Context

The legacy backfill was fully built and **DB-verified** this session: `tools/backfill_run.py`
generates 309,826 atoms + 30 `metric_registry` rows + 8 table-load captures (A′,
ADR-0026) with the modeling of ADR-0027; inserted into a rolled-back copy schema
(`core_dryrun`, all 15 migrations applied in-transaction) they pass **every**
CHECK/FK/trigger and all invariants, and the disposition **reconciles to 810,933
(Δ=0)** with `DUP_INTERNAL` = 305,485 named (ADR-0025). The transforms are proven.

The remaining question was whether to *commit* them. Measured, decision-relevant
storage:

| | MB | % of 500 |
|---|--:|--:|
| current DB | 200.5 | 40.1 |
| + 309,826 atoms (data + 5 indexes, **measured**) | +113.2 | — |
| projected after commit | **313.7** | **62.7** |
| headroom now → after | 299.5 → 186.3 | — |

The decisive fact: **`public.intraday` (94 MB) is still live and still being
written** by the old cron stack (OQ-17), and it is the *same* Apple-Health history
these atoms derive from. Committing now would store that history in one 500 MB
database three ways — `public.intraday` + `core.atoms` + the Parquet archive —
before the old stack is retired. And **nothing before Phase 5/6 reads legacy
atoms** (the Big Mac slice and all of Phase 3 are net-new capture). RULE-02 makes
`atoms` append-only: 113 MB committed cannot come back out.

## Decision

**(c) — commit no legacy atoms now. Legacy history is Parquet-authoritative.**

- The `sha256`-verified `_legacy_snapshot/` Parquet archive is the record of legacy
  data. It is **not** loaded into `core.atoms` this phase; `core.atoms` stays 0.
- `tools/backfill_run.py` is the **proven, re-runnable, DB-verified loader**, held
  ready. It is the documented path to load any legacy stream when one is actually
  needed.
- **Gate 2 is satisfied by RECONCILIATION with physical load DEFERRED** — the same
  named-not-silent deferral pattern as RULE-04 (OQ-22). Every archived row is
  provably accounted for (mapped-or-excluded, Δ=0), and the transforms are
  DB-verified, whether or not the rows sit in Postgres.
- Historical/analytical reads use **DuckDB-over-Parquet-on-R2** per ADR-0016 — so
  legacy-in-Parquet is the intended architecture, not a workaround.

## Consequences

**Good.** 113 irreversible MB not spent on a consumer that will not exist until
Phase 5/6; no triple-storage while `public.intraday` is still live; headroom
preserved as the old stack keeps growing; the placement decision stays open until
Phase 5/6's real needs are known; and because the loader + reconciliation are
proven, the eventual load is a sized, verified operation, not a fresh build.

**Cost (named, not hidden).** "Sections are predicates over atoms" (ADR-0002) does
not span history until a load happens — a `core.atoms` query over 2023 returns
nothing until then. DuckDB-over-Parquet (ADR-0016) serves historical analysis in
the interim. This is the whole downside and it binds on no work before Phase 5/6.

**Trigger + sizing** are recorded in **OQ-29**.

## Alternatives considered

- **(a) commit all 309,826 now.** Rejected: 113 irreversible MB, triple-stores the
  still-live `public.intraday` history, serves no consumer before Phase 5/6.
- **(b) commit only the near-term subset.** Collapses to (c) *today* — near-term
  legacy need is zero (Big Mac + Phase 3 are net-new). The standing loader is (b)'s
  per-need hatch at Phase 5/6, so (c)-with-loader dominates.
