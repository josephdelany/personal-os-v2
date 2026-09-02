# ADR-0047: `get_findings()` lists the hypothesis lifecycle as rows, never CANDIDATE

## Status
Accepted

## Date
2026-09-02

## Decision
`public.get_findings()` (migration 0041) returns the FINDINGS page beyond the EXPLORATORY
list: `watching` (registered `watch:` rows with their 30-day clocks, resolution rule and
frozen pre-registration fields), `confirmed` (with `adjustment_set` verbatim from the
register), `refuted`, `insufficient` (non-watch rows), `counts` (candidates, watching,
confirmed, refuted), and `predictions_pending` (unresolved non-forecast predictions). It
is owner-locked in the ADR-0036 pattern. **No CANDIDATE row is ever listed** — they are
counted only (REQ-TIER-035; `get_patterns` is their sole surface, REQ-TIER-053). Every
item carries its tier and a trace into `core.hypothesis_register` or `core.predictions`
(REQ-TIER-005). **E-value and negative control are not computed yet**: on a CONFIRMED row
the keys are absent, never a placeholder value, and the UI says so (REQ-TIER-023 is
satisfied for the adjustment set only — recorded, not hidden). A demotion is surfaced by
name only as far as the register records it: rows currently `REFUTED` (REQ-TIER-043);
there is no demotion-history table yet.

`days_needed` is 30 — the watch window ADR-0038 fixed for a registration to mature; it is
a registry constant, not a model choice (RULE-13).

## Not built
E-value / negative-control computation; a demotion-history table; per-row evidence
summaries (n, n_eff, coverage live on the CANDIDATE surface and the confirmation job, not
here yet).
