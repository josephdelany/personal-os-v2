"""B19 §E — resolving predictions and scoring calibration (REQ-INF-300..309).

Pure: no database, no clock, no model.

THE ERROR THIS EXISTS TO PREVENT. Joe's `predictions` table holds 32 rows, all due, none
resolved. Twenty-four of them forecast `rhr`, `hrv_sdnn` and `sleep_asleep_min` for early
September — after the Watch stopped on 2026-08-21 and sleep capture ended on 2026-08-14. There
is no observation to resolve them against.

A resolver that treated "no observation" as "the prediction was wrong" would compute a Brier
score saying the system is badly calibrated, when what actually happened is that an instrument
stopped. That number would then demote findings, and the demotions would look earned. So an
unobserved prediction is UNRESOLVABLE — recorded with its reason, excluded from every score,
and never counted as false (RULE-06, RULE-07).

WHY THE BRIER SCORE IS NEVER RETURNED ALONE (REQ-INF-309). A Brier of 0.09 sounds good and says
almost nothing: forecasting the base rate every time scores well on a rare event while carrying
no skill at all. Murphy's decomposition splits it into RELIABILITY (are 70% forecasts right 70%
of the time — lower is better), RESOLUTION (does the forecast separate outcomes at all — higher
is better) and UNCERTAINTY (how variable the outcome was, which is a property of the world and
not of the forecaster). `murphy()` is the only function here that returns a Brier, and it cannot
return one without the other three.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# A log score is infinite at p=0 or p=1. Clamping is a decision, not a detail: it bounds the
# penalty for a confident miss. 1e-6 makes the worst single log score ~13.8, which dominates a
# batch without being infinite.
LOG_CLAMP = 1e-6

# REQ-INF-308's reliability diagram needs bins. Ten is conventional; the count is stated rather
# than assumed because a different binning gives a different reliability term.
DEFAULT_BINS = 10

# Below this, a calibration summary is arithmetic on too little to mean anything (RULE-06).
MIN_RESOLVED_FOR_SUMMARY = 20


@dataclass(frozen=True)
class Unresolvable:
    """REQ-INF-306/307. Why a prediction could not be scored — never a wrong answer."""
    prediction_id: str
    reason: str
    detail: str = ""


@dataclass(frozen=True)
class Resolved:
    prediction_id: str
    p_forecast: float
    outcome_bool: bool
    brier: float
    log_score: float


def score(p_forecast: float, outcome_bool: bool):
    """REQ-INF-306. The Brier and logarithmic scores for one prediction."""
    if not 0.0 <= p_forecast <= 1.0:
        raise ValueError(f"a forecast probability lies in [0, 1], not {p_forecast}")
    outcome = 1.0 if outcome_bool else 0.0
    brier = (p_forecast - outcome) ** 2
    p = min(max(p_forecast if outcome_bool else 1.0 - p_forecast, LOG_CLAMP), 1.0)
    return round(brier, 6), round(-math.log(p), 6)


def resolve(prediction, observation):
    """One prediction against the observation for its resolution day.

    `observation` is None when nothing was recorded. That is the case this function exists
    for: it returns `Unresolvable`, not a failed prediction.
    """
    pid = prediction["prediction_id"]
    if prediction.get("p_forecast") is None:
        return Unresolvable(pid, "no_forecast", "the row carries no probability to score")
    if observation is None:
        return Unresolvable(
            pid, "no_observation",
            "nothing was recorded for the resolution day; the instrument was silent, which is "
            "not evidence that the forecast was wrong")
    rule = prediction.get("resolution_rule")
    band = prediction.get("band")
    if rule != "panel value in stored band" or band is None:
        # REQ-INF-304/305: a rule this job cannot evaluate is refused, never guessed at.
        return Unresolvable(pid, "unevaluable_rule", f"resolution_rule {rule!r} with band {band!r}")
    low, high = band
    outcome = low <= observation <= high
    brier, log_score = score(float(prediction["p_forecast"]), outcome)
    return Resolved(pid, float(prediction["p_forecast"]), outcome, brier, log_score)


def murphy(resolved, bins: int = DEFAULT_BINS, min_resolved: int = MIN_RESOLVED_FOR_SUMMARY):
    """REQ-INF-309. The Brier score WITH its decomposition, or an Unresolvable-shaped refusal.

    Brier = reliability - resolution + uncertainty, exactly. The identity is asserted rather
    than assumed: if it does not hold, the binning or the arithmetic is wrong and the numbers
    should not be shown.
    """
    points = [r for r in resolved if isinstance(r, Resolved)]
    n = len(points)
    if n < min_resolved:
        return Unresolvable(
            "summary", "too_few_resolved",
            f"{n} resolved prediction(s); a calibration summary needs at least {min_resolved} "
            f"before reliability and resolution are anything but noise")

    base = sum(1 for r in points if r.outcome_bool) / n
    brier = sum(r.brier for r in points) / n

    buckets = {}
    for r in points:
        k = min(int(r.p_forecast * bins), bins - 1)
        buckets.setdefault(k, []).append(r)

    reliability = sum(len(g) / n * (sum(x.p_forecast for x in g) / len(g)
                                    - sum(1 for x in g if x.outcome_bool) / len(g)) ** 2
                      for g in buckets.values())
    resolution = sum(len(g) / n * (sum(1 for x in g if x.outcome_bool) / len(g) - base) ** 2
                     for g in buckets.values())
    uncertainty = base * (1 - base)

    # The identity is CHECKED, not assumed. Murphy's decomposition is exact, so a mismatch
    # means the binning or the arithmetic is wrong — and three plausible-looking components
    # that do not sum to the score they decompose are worse than no decomposition at all.
    if abs((reliability - resolution + uncertainty) - brier) > 1e-9:
        raise AssertionError(
            f"Murphy decomposition does not reconstruct the Brier score: "
            f"{reliability} - {resolution} + {uncertainty} != {brier}")

    return dict(
        n=n, base_rate=round(base, 4),
        brier=round(brier, 6),
        reliability=round(reliability, 6),
        resolution=round(resolution, 6),
        uncertainty=round(uncertainty, 6),
        bins=bins,
        # REQ-INF-309: the Brier alone is close to meaningless. Forecasting the base rate every
        # time scores well on a rare event while carrying no skill; `resolution` is what
        # distinguishes the two and it would be invisible without this.
        note="reliability lower is better; resolution higher is better; uncertainty is a "
             "property of the outcome, not of the forecaster")
