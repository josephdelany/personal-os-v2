"""B19 §E — scored forward predictions and auto-demotion (REQ-INF-300..331).

Pure: no database, no clock, no model. Scoring itself lives in `calibration.py` and is imported
rather than restated.

WHY A FINDING MUST CARRY A PREDICTION (REQ-INF-301/302). A claim that never commits to anything
observable cannot be wrong, and a system full of unfalsifiable claims looks exactly like a system
full of correct ones. So the moment a finding reaches PROMOTED it must also insert a row saying
what it expects to see and when -- IN THE SAME TRANSACTION, so there is no window in which a
promoted finding exists without a commitment attached.

A finding at PROMOTED or above with no prediction is REFUSED ON EVERY SURFACE. Not warned about:
refused. The absence is not a display bug, it is the claim having no exposure to being wrong.

WHY DEMOTION HAS NO OVERRIDE (REQ-INF-322). "SHALL NOT provide any interface that suppresses,
defers, or overrides" -- so there is no `force`, no `skip`, no `reason_to_keep`. The moment such
an argument exists, the demotions that get suppressed are exactly the ones about findings
somebody liked. The absence of the parameter IS the requirement.

WHY MISCALIBRATION WIDENS INTERVALS RATHER THAN HIDING CLAIMS (REQ-INF-325/326). A bucket where
"70% likely" comes true half the time is not a bucket to suppress -- it is a bucket whose numbers
mean something different from what they say. So the interval widens, the EFSA term is downgraded
to the band matching the OBSERVED frequency, and the surface says why. The claim survives; its
confidence does not.

WHY AN UNRESOLVABLE PREDICTION IS NOT A FALSE ONE (REQ-INF-329). Joe's Watch stopped on
2026-08-21 and twenty-four predictions about `rhv`, `rhr` and sleep came due afterwards with
nothing to resolve against. Counting those as wrong would compute a Brier score saying the system
is badly calibrated when what actually happened is that an instrument stopped -- and the
resulting demotions would look earned.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from tools.engines.calibration import Resolved, Unresolvable, score

# REQ-INF-300. The columns a prediction must carry to be scoreable and auditable.
PREDICTION_FIELDS = ("prediction_id", "created_at", "hypothesis_id", "claim_text",
                     "resolution_rule", "resolves_at", "p_forecast", "evidence_tier",
                     "model_version", "feature_snapshot_hash", "resolved_at", "outcome_bool",
                     "brier", "log_score")

PREDICTION_REQUIRED_TIERS = ("PROMOTED", "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")
NO_FINDING = "No finding available."

DEMOTE_MIN_RESOLVED = 3           # REQ-INF-320
DEMOTE_FALSE_RATE = 0.50
REFUTE_MIN_RESOLVED = 5           # REQ-INF-321
REFUTE_FALSE_RATE = 0.60

MISCALIBRATION_GAP = 0.15         # REQ-INF-325
MISCALIBRATION_MIN_N = 20
UNRESOLVABLE_CEILING = 0.25       # REQ-INF-330
UNRESOLVABLE_WINDOW_DAYS = 90

TIERS = ("REFUTED", "INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY", "PROMOTED",
         "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")


class PredictionRejected(Exception):
    """REQ-INF-305. Rejected AT INSERT, because an unparseable rule can never resolve."""


def make_prediction(**kw):
    """REQ-INF-300/303/305. Every field, a future resolution, and a rule that can be evaluated."""
    missing = [f for f in PREDICTION_FIELDS if f not in kw]
    if missing:
        raise PredictionRejected(f"REQ-INF-300: a prediction carries {missing} too")
    if not (kw["resolves_at"] > kw["created_at"]):
        # REQ-INF-303. A prediction that resolves at or before its creation is a description of
        # the past wearing a forecast's clothes.
        raise PredictionRejected("REQ-INF-303: resolves_at must be strictly after created_at")
    if not kw.get("resolution_rule"):
        raise PredictionRejected("REQ-INF-305: a prediction with no resolution rule cannot be "
                                 "evaluated and is rejected at insert")
    return dict(kw)


def check_resolution_rule(rule, *, parser):
    """REQ-INF-305. Parsed at INSERT time, not at resolution time.

    Discovering at resolution that a rule cannot be evaluated means the finding has been
    PROMOTED for weeks on the strength of a commitment nobody could ever check.
    """
    try:
        parser(rule)
    except Exception as e:                    # noqa: BLE001 — any parse failure is a rejection
        raise PredictionRejected(
            f"REQ-INF-305: {rule!r} cannot be parsed and evaluated by the resolution job "
            f"({e}); the prediction is rejected at insert and the finding is not promoted")
    return True


def promote_with_prediction(finding, predictions):
    """REQ-INF-301. The prediction is inserted in the SAME transaction as the promotion.

    Not "shortly after": in the same transaction, so there is no window in which a promoted
    finding exists with no commitment attached.
    """
    if finding.get("tier") in PREDICTION_REQUIRED_TIERS and not predictions:
        raise PredictionRejected(
            "REQ-INF-301: a finding reaching PROMOTED or above inserts at least one prediction "
            "in the same transaction; a claim that commits to nothing observable cannot be wrong")
    return {"finding": finding, "predictions": tuple(predictions), "atomic": True}


def render_finding(finding, predictions):
    """REQ-INF-302. Refused on every surface, not warned about.

    The absence of a prediction is not a display bug — it is the claim having no exposure to
    being wrong, and a system full of unfalsifiable claims looks exactly like a system full of
    correct ones.
    """
    if finding.get("tier") in PREDICTION_REQUIRED_TIERS and not predictions:
        return {"rendered": False, "text": NO_FINDING,
                "reason": "REQ-INF-302: no forward prediction is attached to this finding"}
    return {"rendered": True, "finding": finding}


def resolve_against_snapshot(prediction, *, snapshot_hash, observations):
    """REQ-INF-307. The feature state as it WAS, plus observations after `resolves_at`.

    Resolving against today's feature state would let a later correction change whether a past
    prediction came true, which makes the track record a function of the present.
    """
    if prediction.get("feature_snapshot_hash") != snapshot_hash:
        raise PredictionRejected(
            "REQ-INF-307: a prediction resolves against the feature state reconstructible from "
            "its own feature_snapshot_hash, never against the current one")
    after = [o for o in observations if o["day"] >= prediction["resolves_at"].date()]
    if not after:
        # REQ-INF-329. Nothing to resolve against is not a false prediction.
        return Unresolvable(prediction_id=prediction["prediction_id"],
                            reason="no_observation_after_resolves_at")
    outcome = bool(after[0].get("outcome"))
    brier, log_score = score(prediction["p_forecast"], outcome)
    return Resolved(prediction_id=prediction["prediction_id"],
                    p_forecast=prediction["p_forecast"], outcome_bool=outcome,
                    brier=brier, log_score=log_score)


def false_rate(resolved):
    scored = [r for r in resolved if isinstance(r, Resolved)]
    if not scored:
        return 0, 0.0
    false_n = sum(1 for r in scored if not r.outcome_bool)
    return len(scored), false_n / len(scored)


def auto_demotion(finding, resolved):
    """REQ-INF-320/321/322/323. Demote at 3+/50%, refute at 5+/60%, and NO override exists.

    There is deliberately no `force`, no `skip`, no `reason_to_keep` parameter. REQ-INF-322 says
    the layer "SHALL NOT provide any interface that suppresses, defers, or overrides" — and the
    moment such an argument exists, the demotions that get suppressed are exactly the ones about
    findings somebody liked. The absence of the parameter IS the requirement.
    """
    n, rate = false_rate(resolved)
    ids = tuple(r.prediction_id for r in resolved if isinstance(r, Resolved))
    if n >= REFUTE_MIN_RESOLVED and rate >= REFUTE_FALSE_RATE:
        return {"tier": "REFUTED", "status": "REFUTED", "acted": True,
                "human_confirmation": False,
                "tier_history": {"reason": "failed_forward_predictions",
                                 "prediction_ids": ids, "observed_false_rate": round(rate, 3),
                                 "n_resolved": n}}
    if n >= DEMOTE_MIN_RESOLVED and rate >= DEMOTE_FALSE_RATE:
        i = TIERS.index(finding["tier"])
        return {"tier": TIERS[max(0, i - 1)], "acted": True, "human_confirmation": False,
                "tier_history": {"reason": "failed_forward_predictions",
                                 "prediction_ids": ids, "observed_false_rate": round(rate, 3),
                                 "n_resolved": n}}
    return {"tier": finding["tier"], "acted": False, "n_resolved": n,
            "observed_false_rate": round(rate, 3)}


def demotion_brief_entry(finding, demotion):
    """REQ-INF-324. Named in the next brief: the original claim, the failures, the new tier.

    A demotion nobody is told about is indistinguishable from a claim that was never made. The
    brief entry is what makes the system's own record of being wrong visible to the person it
    was wrong at.
    """
    if not demotion.get("acted"):
        return None
    h = demotion["tier_history"]
    failed = round(h["observed_false_rate"] * h["n_resolved"])
    return {"claim": finding.get("claim_text"), "failed_predictions": failed,
            "n_resolved": h["n_resolved"], "new_tier": demotion["tier"],
            "text": (f"{finding.get('claim_text')} — {failed} of {h['n_resolved']} forward "
                     f"predictions resolved false. Now {demotion['tier']}.")}


# ---------------------------------------------------------------- calibration-driven downgrade

def miscalibrated_buckets(buckets):
    """REQ-INF-325. Observed frequency below nominal by more than 0.15, over 20+ resolved."""
    out = {}
    for name, b in (buckets or {}).items():
        if b.get("n", 0) < MISCALIBRATION_MIN_N:
            continue
        gap = float(b["nominal"]) - float(b["observed"])
        if gap > MISCALIBRATION_GAP:
            out[name] = {"gap": round(gap, 3), "n": b["n"], "nominal": b["nominal"],
                         "observed": b["observed"]}
    return out


def apply_miscalibration(claim, bucket_stats):
    """REQ-INF-325/326. Widen the interval, downgrade the term to the OBSERVED band, say why.

    A bucket where "70% likely" comes true half the time is not a bucket to suppress: it is one
    whose numbers mean something different from what they say. The claim survives; its confidence
    does not.
    """
    from tools.engines.tier_contract import verbal_probability
    if not bucket_stats:
        return claim
    observed = float(bucket_stats["observed"]) * 100.0
    lo, hi = claim["interval"]
    widen = (hi - lo) * float(bucket_stats["gap"])
    return {**claim,
            "interval": [round(lo - widen, 4), round(hi + widen, 4)],
            "verbal_probability": verbal_probability(observed),
            "interval_widened": True,
            "disclosure": (f"Forecasts in this band have come true {observed:.0f}% of the time "
                           f"against a stated {float(bucket_stats['nominal']) * 100:.0f}% over "
                           f"{bucket_stats['n']} resolved predictions. The interval is widened "
                           f"and the wording follows the observed rate, not the stated one.")}


def track_record(resolved, *, on_demand=True):
    """REQ-INF-327/328. Every prediction, its forecast, its outcome, its scores — and immutable.

    Nothing is deleted and no stored score is recomputed under a later model version: a track
    record that improves when the model changes is not a track record, it is a redraft.
    """
    rows = []
    for r in resolved:
        if isinstance(r, Resolved):
            rows.append({"prediction_id": r.prediction_id, "p_forecast": r.p_forecast,
                         "outcome": r.outcome_bool, "brier": r.brier,
                         "log_score": r.log_score, "recomputed": False})
        else:
            rows.append({"prediction_id": r.prediction_id, "outcome": "unresolvable",
                         "reason": r.reason, "excluded_from_scoring": True})
    return {"available_on_demand": on_demand, "rows": tuple(rows), "deletions": 0,
            "note": ("Scores are stored as computed under the model version that made them. A "
                     "track record that improves when the model changes is a redraft.")}


def unresolvable_rate(resolved):
    total = len(resolved)
    if not total:
        return 0.0
    return sum(1 for r in resolved if isinstance(r, Unresolvable)) / total


def calibration_report(resolved):
    """REQ-INF-329/330. Above a quarter unresolvable, the system reports its OWN calibration
    at INSUFFICIENT.

    Joe's Watch stopped on 2026-08-21 and twenty-four predictions came due afterwards with
    nothing to resolve against. Counting those as wrong would compute a Brier score saying the
    system is badly calibrated when an instrument stopped — and the resulting demotions would
    look earned.
    """
    rate = unresolvable_rate(resolved)
    if rate > UNRESOLVABLE_CEILING:
        return {"tier": "INSUFFICIENT", "unresolvable_rate": round(rate, 3),
                "scored": False,
                "text": (f"{rate:.0%} of predictions in the trailing {UNRESOLVABLE_WINDOW_DAYS} "
                         f"days could not be resolved, so this system's track record cannot "
                         f"currently be assessed.")}
    return {"tier": "DESCRIPTIVE", "unresolvable_rate": round(rate, 3), "scored": True}


def recommendation_with_prediction(recommendation, *, tier, tier_floor, effect_delta,
                                   min_effect, prediction):
    """REQ-INF-331. A recommendation carries its own scored forward prediction.

    The recommendation-side analogue of REQ-INF-301: advice that commits to nothing is advice
    that can never be found wrong, and advice is the output with the most direct effect on what
    Joe actually does.
    """
    from tools.engines.tier_contract import rank
    if rank(tier) < rank(tier_floor) or effect_delta <= min_effect:
        return None
    if not prediction:
        raise PredictionRejected(
            "REQ-INF-331: a recommendation carries its own scored forward prediction, so that a "
            "recommendation whose prediction later resolves false is demoted like any finding")
    return {**recommendation, "tier": tier, "prediction": prediction, "provisional": True}
