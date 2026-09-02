# ADR-0038: The conversation layer — analysis schema, engines, and the plan of record

## Status
Accepted (Joe approved the full blueprint 2026-09-01; archived copy at
`docs/PLAN_CONVERSATION_LAYER.md`).

## Date
2026-09-01

## Decision
A derived-compute home `analysis` (rebuildable, provenance-carrying, NOT
append-only — every row re-derivable from immutable sources; reads only via
owner-locked RPCs) hosting: the unified daily panel (signals + 7-year legacy
daily series + atoms aggregates), baselines/state (ported median/MAD/EWMA dual-z
+ changepoint-aware engine), contrast-scan output with full statistics, and the
scan null-calibration ledger. Engines E1-E11 per the approved blueprint: Timeline,
Baseline/State+guardian, Contrast Scan (seeded manifest + discovery; quartile
contrasts, weekday-partialled, n_eff, BH-FDR) feeding CANDIDATE rows, Event
Studies, Conformal Forecasts wired to core.predictions, Regime Chapters, Ask v1
(closed ops), Probe engine (recovered 13-question bank), Brief compositor,
KEYSTONE aggregator, weekly Confirmation job (post-registration data only).
CANDIDATE rows are never mutated into registrations — a Watch creates a NEW
pre-registered row (freeze-trigger enforced).

## Consequences
Good: hundreds of honest insights live over 7 years of data; the loop makes
strong language earnable; everything $0/unattended. Cost: analysis tables must
never be read directly by clients (enforced by grants); scan quality bounded by
panel coverage — gaps render as gaps.
