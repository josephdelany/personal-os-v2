"""B19 §D — interrupted time series (REQ-INF-218, 219).

Pure: no database, no clock, no model.

WHEN THIS APPLIES. A discrete one-off change on a known date that cannot be randomised: Joe moved
house, changed job, started a medication. There is exactly one unit and exactly one intervention,
so a trial is impossible and the only question is whether the series changed at that date more
than it changes at other dates.

WHY THE CONTROL SERIES IS PRINTED AND VETOABLE (REQ-INF-218). An ITS estimate is only as good as
its control: a series that should NOT have been affected by the intervention, moving the same way
the outcome does for every other reason. Choosing it is a judgement about Joe's life that the
system cannot make -- steps is a reasonable control for sleep unless the thing that changed was
his commute. So the chosen control is stated, and Joe can veto it, because a control he knows is
wrong invalidates the estimate silently.

WHY THE TIER IS CAPPED AT CONFIRMED_OBSERVATIONAL (REQ-INF-219). n=1, no randomisation, and a
single intervention date. It can be a good observational estimate and it can never be an
experiment, however clean the discontinuity looks -- and a clean discontinuity is exactly when
somebody would want to call it one.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_TIER = "CONFIRMED_OBSERVATIONAL"      # REQ-INF-219


@dataclass(frozen=True)
class NotApplicable:
    reason: str
    detail: str = ""


def applies(*, change_date, randomisation_possible):
    """REQ-INF-218. A discrete one-off change on a KNOWN date, with no randomisation available.

    Both conditions. Without a known date there is nothing to interrupt the series at, and the
    method degenerates into searching for the best changepoint — which will always find one.
    """
    if randomisation_possible:
        return NotApplicable("randomisation_available",
                             "a randomized trial answers this better and reaches EXPERIMENTAL")
    if change_date is None:
        return NotApplicable(
            "no_known_change_date",
            "an interrupted time series interrupts at a KNOWN date; without one the method "
            "degenerates into searching for the best changepoint, which will always find one")
    return {"applies": True, "change_date": change_date, "method": "interrupted_time_series"}


def select_control(candidates, *, outcome, vetoed=()):
    """REQ-INF-218. The chosen control is PRINTED, and Joe can veto it.

    An ITS estimate is only as good as its control: a series that should not have been affected
    by the intervention but moves the same way the outcome does for every other reason. Choosing
    it is a judgement about Joe's life the system cannot make — steps is a reasonable control for
    sleep unless the thing that changed was his commute.
    """
    available = [c for c in candidates if c["metric"] not in set(vetoed)
                 and c["metric"] != outcome]
    if not available:
        return NotApplicable(
            "no_control_series",
            "every candidate control was vetoed or is the outcome itself; an ITS without a "
            "control cannot separate the intervention from everything else that changed")
    best = max(available, key=lambda c: c.get("pre_period_correlation", 0))
    return {"control": best["metric"],
            "pre_period_correlation": best.get("pre_period_correlation"),
            "printed": True, "vetoable": True,
            "alternatives": tuple(sorted(c["metric"] for c in available
                                         if c["metric"] != best["metric"])),
            "text": (f"Using {best['metric']} as the control series. It tracked "
                     f"{outcome} before the change and should not have been affected by it. "
                     f"Veto it if that is wrong.")}


def result(estimate, *, control, change_date):
    """REQ-INF-219. Never above CONFIRMED_OBSERVATIONAL.

    n=1, no randomisation, one intervention date. It can be a good observational estimate and it
    can never be an experiment — however clean the discontinuity looks, and a clean discontinuity
    is exactly when somebody would want to call it one.
    """
    return {**estimate, "tier": MAX_TIER, "max_tier": MAX_TIER,
            "method": "interrupted_time_series", "control_series": control,
            "change_date": change_date, "randomised": False,
            "note": ("One unit, one intervention, no randomisation. This is an observational "
                     "estimate and cannot become experimental however clean the discontinuity "
                     "looks.")}


def check_tier(proposed_tier):
    """REQ-INF-219, enforced rather than trusted."""
    from tools.engines.tier_contract import rank
    if rank(proposed_tier) > rank(MAX_TIER):
        raise ValueError(
            f"REQ-INF-219: an interrupted-time-series result is capped at {MAX_TIER}; "
            f"{proposed_tier} claims a design this method does not have")
    return True
