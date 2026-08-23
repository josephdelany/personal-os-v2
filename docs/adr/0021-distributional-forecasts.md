# ADR-0021: Distributional forecasts — continuous predictions store a distribution, not a point

## Status

Accepted (extends RULE-20). Split from ADR-0016 to fix a double-booked number.

## Date

2026-08-23

## Context

RULE-20 requires every promoted finding to emit a scored forward prediction. The
spec's `predictions` table (REQ-INF-300..330) stores `p_forecast` (a scalar
probability), `outcome_bool`, `brier`, `log_score` — **correct for a binary
outcome**. Two facts (Decision 2):

- **CRPS and the continuous log score cannot be computed from a point forecast.**
  Verified, with a nuance: CRPS of a point mass equals MAE (graceful), but the
  **log score is undefined/infinite for a point** (no graceful case). A single
  number is a lie about precision.
- CRPS is for **continuous** outcomes (tomorrow's weight, next week's mean sleep).
  The existing binary path does not need CRPS and must not be thrown away — Brier
  and log score are the right scores there.

So this is not "the table is wrong"; it is "the table covers only binary outcomes,
and continuous forecasts need a second shape."

## Decision

Support two forecast shapes in `core.predictions`:

- **Binary** — keep `p_forecast`, `outcome_bool`, `brier`, `log_score`
  (REQ-INF-300, unchanged).
- **Continuous** — add `forecast_distribution JSONB` (a quantile grid *or* a
  sample vector), `dist_family` (a tag for the distribution shape), `issued_at`,
  `horizon`, `resolves_at` (already present), and score columns `crps`,
  `log_score_cont`. **Store the distribution, not a mean.**

A CHECK requires at least one shape present. Shape locked this phase; the scoring
**compute** is Phase 6 (`scoringrules` 0.11.0, Apache-2.0 — a heavier optional
dependency, to be justified in a RULE-28 dependency ADR before it is added).

## Consequences

**Good.** Continuous forecasts are scorable with proper rules; the binary path is
untouched; resolved predictions are never rescored under a later model
(REQ-INF-328).

**Bad.** Two shapes mean resolution/scoring code branches on which is populated.
Locking columns now avoids a migration over prediction history later.

## Alternatives considered

- **One unified scalar-score column.** Rejected: the log score is infinite for a
  point mass, so a unified column cannot degrade gracefully across shapes.
- **Replace the binary path with CRPS everywhere.** Rejected: Brier/log score are
  correct and standard for binary outcomes; CRPS does not apply there.
