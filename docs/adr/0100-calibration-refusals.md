# ADR-0100 — A silent instrument is not a wrong forecast

Status: accepted (`tools/engines/calibration.py`; no migration, no production write)
Date: 2026-09-09
Requirements: REQ-INF-300..309, RULE-06, RULE-07.

## The error this exists to prevent

`core.predictions` holds 32 rows, all due, none resolved. Twenty-four forecast `rhr`,
`hrv_sdnn` and `sleep_asleep_min` for early September — after the Watch stopped on 2026-08-21.
The remaining eight forecast `steps`, whose *legacy panel* ends 2026-07-17. Resolved read-only
against real data: **all 32 are unresolvable.**

Each carries `p_forecast = 0.9`. A resolver that read "no observation" as "the forecast was
wrong" would score every one at Brier 0.81, produce a catastrophic calibration record, and
under REQ-INF §E's auto-demotion demote findings on the strength of it. **An instrument failure
would become a forecasting failure, and the demotions would look earned.**

So an unobserved prediction is `Unresolvable` with its reason, excluded from every score, never
counted as false. The aggregate honours the same rule: unresolvable rows do not enter the
denominator, so 24 silent instruments cannot become 24 failed forecasts.

## Why the Brier score is never returned alone

REQ-INF-309, and it is not bureaucratic. A Brier of 0.09 sounds good and says almost nothing:
forecasting the base rate every time scores well on a rare event while carrying **no skill at
all**. Murphy's decomposition separates:

- **reliability** — are 70% forecasts right 70% of the time (lower is better)
- **resolution** — does the forecast separate outcomes at all (higher is better)
- **uncertainty** — how variable the outcome was, a property of the world and not the forecaster

`murphy()` is the only function that returns a Brier, and it cannot return one without the
other three. The identity `brier = reliability − resolution + uncertainty` is **checked, not
assumed**: a mismatch means the binning or the arithmetic is wrong, and three plausible-looking
components that do not sum to the score they decompose are worse than no decomposition. The
engine raises rather than returning them.

Tests pin both ends: a perfectly calibrated forecaster has near-zero reliability and a Brier
that is almost all uncertainty; a single-value forecaster has **exactly zero resolution**
however good its Brier looks.

## Stated decisions, not details

The log score is clamped at 1e-6, bounding a confident miss at ~13.8 rather than infinity — an
infinite penalty cannot be compared to anything. Ten bins is conventional and is returned with
the result, because a different binning gives a different reliability term. A summary below
twenty resolved predictions is refused as noise.

## The finding this surfaced

Nothing stops a forecast being issued for a metric whose capture is stale. `check_freshness.py`
knows those metrics are dark; the forecaster does not consult it. A prediction about a dark
instrument is not a forecast, it is a guess with a timestamp. Recorded as OQ-63 with a
recommendation, because adding that gate is a new requirement rather than a fix to an existing
one.
