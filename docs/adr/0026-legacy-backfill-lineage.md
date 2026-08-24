# ADR-0026: Legacy-backfill lineage (A′) and gait classification

## Status

Accepted

## Date

2026-08-23

## Context

`docs/PHASE2_BACKFILL_PLAN.md` §6 and ADR-0025 named three judgement calls owed
as rulings *before* the legacy backfill migration is written. This ADR records
the two Joe settled on 2026-08-23 (Phase 2, session 5). The third — confirming
the OVERLAP tables are strict subsets of their canonical — is not merely
confirmed but **enlarged** by a correctness finding this session (see
Consequences), and remains open.

Every atom must reference a `raw_captures` row (**INV-1**, enforced as a NOT-NULL
FK, `migrations/0005_atoms.sql:30`). Backfilled atoms have no original device
capture — the old stack already consumed it — so the lineage must be
reconstructed honestly, not fabricated. Two reconstructions were on the table:

- **B — one `raw_captures` per source row (~625k).** True in-database row-level
  lineage, but adds ~625k JSONB rows to a Supabase Free database already ~44%
  of the 500 MB read-only ceiling (**OQ-20**), duplicating bytes the
  `sha256`-verified Parquet archive already holds, and overstating capture grain
  (a bulk import dressed as 625k discrete real-time captures).
- **A′ — one `raw_captures` per source TABLE-LOAD (~24), plus a per-atom
  source-row locator.**

Separately, ADR-0023 placed `walking_hr` under `vital_sample` but left the five
gait *movement* series (`walking_speed`, `walking_step_length`,
`walking_double_support`, `walking_asymmetry`, `walking_steadiness`)
unclassified — O-Q2.

## Decision

**1. INV-1 legacy lineage = A′.** One `raw_captures` row per source table-load,
`source = 'legacy_archive'` (enum value added by migration 0015), `payload` = the
manifest entry for that table (name, `sha256`, `rows_source`, snapshot id),
`recorded_at` = the ingest instant (never `now()` faked as capture time). **Every
atom carries its source-row locator in `evidence_span`** (source table + natural
/ row key), so row-level audit survives without 625k capture rows: the chain is
`atom → evidence_span row-key → the sha256-pinned Parquet file (named on the
table-load capture) → the exact source row`. The Parquet archive is the
row-of-record for legacy data; A′ points at it rather than paying to duplicate it
inside a 500 MB box.

**2. Gait = `activity_sample`.** The five gait series are **movement** measures,
not cardiorespiratory/thermoregulatory ones; `vital_sample` is reserved for the
latter. `walking_hr` stays `vital_sample` (it is a heart-rate measure that
happens to be recorded while walking). Both are valid members of the `atoms.kind`
CHECK (migration 0014). The specific metric stays in `metric_key`, not the kind.

## Consequences

**Good.** INV-1 satisfied by the FK; ~24 capture rows instead of ~625k; the storage
cost of row-level lineage lands on a short `evidence_span` TEXT column, not
625k JSONB payloads; no double-paying for the archive's bytes.

**The main practical benefit beyond storage — recoverability (Joe's point,
recorded per his instruction).** Because every atom retains its **source table**
(and row key) in `evidence_span`, a kind or metric boundary that later proves
wrong — the gait `activity_sample` call, a `self_report`-vs-`mood` split, any
metric_key assignment — is fixable by **re-deriving** the affected atoms from the
still-present, `sha256`-verified archive, rather than by re-running the whole
backfill or forensically reconstructing which atoms came from where. This is what
makes settling O-Q2 now (rather than agonising) safe: the decision is reversible
by re-derivation. The reversal itself is still an append-only correction (new
superseding atoms, INV-2) — cheaper than a re-backfill, not free.

**Dependency / flagged.** A′ leans on the Parquet archive remaining permanent and
immutable (it is the Gate-0 artifact, gitignored forever, `sha256` in the
manifests). If that archive were ever discarded, A′ degrades to table-grain
lineage. B does not carry that dependency — so if the archive's permanence is
ever in doubt, A′ must be revisited.

**Newly surfaced this session — the backfill MAP is not yet safe to execute
(reported to Joe, ruling owed; does NOT affect this ADR's two decisions).**
Reading the actual archive (not the manifests `backfill_map.py` relied on)
showed the plan double-counts at ~450k-row scale: the Supabase `intraday` table
and the sqlite `health__*` tables are the **same Apple Health export**,
double-stored (value-level set match confirmed on `wrist_temp`: identical 64
`(ts, value)` pairs; counts identical to the row across ≥10 series), and
`events.kind` (`youtube_watch`/`chrome_visit`/`calendar`) overlaps
`pos__youtube_history`/`pos__chrome_history`/`pos__calendar_events`. Sleep shows
233 disjoint rows, so the duplicates are not always strict subsets. Also:
`metric_registry` is empty and is a hard FK for every metric-bearing atom, and it
**cannot** be mapped from the legacy `metric_catalog` (that table is the old
stack's derived-feature catalog — `feature/domain/validity` — not a units
registry); and `locations` cannot become a scalar atom (no coordinate columns;
RULE-29 forbids storing coordinates). These are execution-map corrections, owed
as rulings before any atom is written; the A′ lineage mechanism and the gait
classification above stand regardless of how they are resolved.

## Alternatives considered

- **B (per-row captures).** Rejected: ~625k JSONB rows against the 500 MB ceiling
  (OQ-20), duplicating the archive's bytes, for row-level lineage that A′ already
  delivers via `evidence_span` + the pinned Parquet.
- **Gait = `vital_sample`.** Rejected: gait is movement, not a vital sign;
  conflating them would pollute the cardiorespiratory family used by the RULE-21
  FDR tree.
