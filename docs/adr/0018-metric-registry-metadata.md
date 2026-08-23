# ADR-0018: Metric-registry scale and rounding metadata

## Status

Accepted (extends ADR-0002's metric_registry)

## Date

2026-08-23

## Context

Self-reported values are **coarsened observations of a latent continuum**, not
points: a 0–10 mood rating rounded to an integer is interval-censored data. The
number of response categories demonstrably changes the analysis (van Praag, Hop,
Greene, "Estimation of Linear Models from Coarsened Observations: A Method of
Moments Approach," Psychometrika 2025, arXiv:2501.10726 — a GMM **estimation**
paper). The coarsened-latent framing is mainstream/orthodox.

**Attribution honesty.** Storing scale metadata *as schema* is our reasonable
extrapolation — it is **not** a claim in that paper, which is about estimation, not
schema design. Recorded as our engineering decision, grounded in the coarsening
framing, not attributed to the paper.

`metric_registry` (ADR-0002) already carries `scale_type` and `legal_transforms`
conceptually but does not enumerate the coarsening per variable.

## Decision

Add to `core.metric_registry`, per variable: `self_report BOOLEAN`,
`response_scale NUMRANGE` (e.g. `numrange(0,10,'[]')`), `n_scale_points INTEGER`
(e.g. 11), `rounding_step NUMERIC` (e.g. 1). A self-report value then carries its
coarsening, so downstream code treats it as interval-censored, not a point, and
never asserts precision the response scale cannot support.

## Consequences

**Good.** Coarsening is data, not a hardcoded assumption in analysis code. A
change of instrument (7-point → 11-point) is a registry edit, and the estimator
can read the number of categories rather than guessing it.

**Bad.** Every registered self-report metric must have its scale metadata filled
in; a NULL `n_scale_points` on a `self_report=true` metric is a latent gap the
inference layer must refuse rather than assume. (A CHECK enforces `n_scale_points
> 1` when present; completeness is a Phase-5/6 registry-population concern.)

## Alternatives considered

- **Infer the scale from observed values.** Rejected: RULE-06 (never impute); the
  scale is metadata about the instrument, not something to estimate from data.
- **Store only `scale_type` as a label.** Rejected: a label does not carry the
  rounding step an interval-censored likelihood needs.
