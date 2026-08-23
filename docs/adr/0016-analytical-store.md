# ADR-0016: Analytical store — Postgres authoritative, Parquet-on-R2 the mirror

## Status

Accepted (decision record; no R2/DuckDB code this phase). References OQ-20.

## Date

2026-08-23

## Context

Supabase Free caps the database at **500 MB and flips read-only at the limit**, and
pauses a project after 7 days' inactivity (both verified). The live DB is **197 MB**
before the new schema exists — ~40% of the ceiling gone. TimescaleDB is deprecated
on PG17 Supabase and absent on the live instance; `pg_duckdb`/`pg_ducklake` are
**not installable on hosted Supabase** (confirmed via `pg_available_extensions`).
R2 Free is **10 GB, zero egress**. DuckDB 1.5.5 / DuckLake / pg_ducklake ≥ 1.0 make
Parquet-with-a-catalog a $0 pattern — but DuckDB must live in the GitHub Actions
runner, not in Postgres.

Two unpriced consequences (Decision 7):

1. **The $0 guarantee's real leak is R2 Class-A operations** (writes/lists), capped
   at 1M/month free then $4.50/M. A chatty writer — many tiny Parquet files, heavy
   `LIST` — is the most plausible way this quietly leaves $0. Mitigation is a
   **design rule**: batch and compact Parquet writes; no per-row PUTs; avoid
   `LIST`-heavy scans.
2. **The system-of-record seam** — INV-1 (trace to `raw_captures`) and RULE-12
   (compute once, one owner) must hold *across* the two stores.

## Decision (Joe's ruling, 2026-08-23)

**Postgres is the authoritative store** for `atoms`, `raw_captures`, `findings`,
`ops.*` — that is where immutability, grants, the append-only triggers, and
point-in-time queries have teeth. **R2/Parquet is the analytical mirror + scratch
space** for the heavy statistical passes that would blow the 500 MB ceiling or need
columnar scans, computed in the Actions runner via DuckDB. **Results are written
back to Postgres with full provenance and `code_version`** (RULE-12), still tracing
to a `raw_captures` row (INV-1). One owner per number; one trace to raw; both inside
one enforceable store.

**No R2/DuckDB code this phase.** The analytical store does not block the operational
spine, and premature R2 wiring adds a consistency surface before there is anything to
analyse. Build it after the spine exists and the ceiling is actually in sight.

**This decision opens OQ-20** and must be read with it: Postgres is authoritative
*and* `atoms` are append-only (RULE-02), so "delete old rows" is not an available
remedy when the 500 MB wall approaches. An options memo (evict-to-R2 vs
archive-and-truncate-legacy vs accept-and-monitor, with row/byte projections) is
owed **before** the wall, ruled by Joe, not at it.

## Consequences

**Good.** Immutability and point-in-time correctness stay on the store that can
enforce them; the columnar/heavy work runs where compute is unmetered (public-repo
Actions).

**Bad.** A write-back path spanning two stores is a new failure surface (a finding
computed in the runner must land in Postgres with provenance or it violates
RULE-12). The two-store row/byte migration is unpriced and owed with the OQ-20 memo.

## Alternatives considered

- **R2 authoritative, Postgres a thin operational cache.** Defensible, and it
  changes Phase-2's entire migration target — rejected because immutability and
  grant enforcement have no teeth on an R2-authoritative copy.
- **Stay entirely in Postgres.** Rejected: the heavy statistical passes and the
  500 MB ceiling make a columnar mirror necessary before long.
