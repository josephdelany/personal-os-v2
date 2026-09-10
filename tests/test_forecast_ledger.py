"""B19 §E — scored forward predictions and auto-demotion (REQ-INF-300..331).

A claim that never commits to anything observable cannot be wrong, and a system full of
unfalsifiable claims looks exactly like a system full of correct ones.
"""
import datetime as dt

import pytest

from tools.engines.calibration import Resolved, Unresolvable
from tools.engines.forecast_ledger import (DEMOTE_MIN_RESOLVED, MISCALIBRATION_GAP,
                                           MISCALIBRATION_MIN_N, NO_FINDING, PREDICTION_FIELDS,
                                           PredictionRejected, REFUTE_MIN_RESOLVED,
                                           UNRESOLVABLE_CEILING, apply_miscalibration,
                                           auto_demotion, calibration_report,
                                           check_resolution_rule, demotion_brief_entry,
                                           make_prediction, miscalibrated_buckets,
                                           promote_with_prediction,
                                           recommendation_with_prediction, render_finding,
                                           resolve_against_snapshot, track_record,
                                           unresolvable_rate)

NOW = dt.datetime(2026, 9, 1, 12, 0)


def prediction(**kw):
    base = {f: None for f in PREDICTION_FIELDS}
    base.update(prediction_id="P-1", created_at=NOW, hypothesis_id="H-1",
                claim_text="RHR falls after a long sleep", resolution_rule="rhr < baseline",
                resolves_at=NOW + dt.timedelta(days=7), p_forecast=0.7,
                evidence_tier="PROMOTED", model_version="v1", feature_snapshot_hash="abc")
    base.update(kw)
    return base


def resolved(n_true, n_false):
    out = [Resolved(f"T{i}", 0.7, True, 0.09, 0.36) for i in range(n_true)]
    out += [Resolved(f"F{i}", 0.7, False, 0.49, 1.2) for i in range(n_false)]
    return out


def test_REQ_INF_300_a_prediction_carries_every_field_that_makes_it_scoreable():
    assert make_prediction(**prediction())
    incomplete = prediction()
    del incomplete["brier"]
    with pytest.raises(PredictionRejected, match="REQ-INF-300"):
        make_prediction(**incomplete)


def test_REQ_INF_303_a_prediction_must_resolve_strictly_after_it_was_made():
    """A prediction that resolves at or before its creation is a description of the past wearing
    a forecast's clothes."""
    with pytest.raises(PredictionRejected, match="REQ-INF-303"):
        make_prediction(**prediction(resolves_at=NOW))
    with pytest.raises(PredictionRejected, match="REQ-INF-303"):
        make_prediction(**prediction(resolves_at=NOW - dt.timedelta(days=1)))


def test_REQ_INF_305_an_unparseable_rule_is_rejected_at_INSERT_not_at_resolution():
    """Discovering at resolution that a rule cannot be evaluated means the finding has been
    PROMOTED for weeks on the strength of a commitment nobody could ever check."""
    def parser(rule):
        if "<" not in rule:
            raise ValueError("no comparison")
    assert check_resolution_rule("rhr < baseline", parser=parser)
    with pytest.raises(PredictionRejected, match="REQ-INF-305"):
        check_resolution_rule("it will be better", parser=parser)
    with pytest.raises(PredictionRejected, match="REQ-INF-305"):
        make_prediction(**prediction(resolution_rule=None))


def test_REQ_INF_301_promotion_inserts_the_prediction_in_the_SAME_transaction():
    """Not "shortly after": in the same transaction, so there is no window in which a promoted
    finding exists with no commitment attached."""
    out = promote_with_prediction({"tier": "PROMOTED"}, [prediction()])
    assert out["atomic"] is True and len(out["predictions"]) == 1
    with pytest.raises(PredictionRejected, match="REQ-INF-301"):
        promote_with_prediction({"tier": "PROMOTED"}, [])


def test_REQ_INF_301_a_descriptive_finding_needs_no_prediction():
    assert promote_with_prediction({"tier": "DESCRIPTIVE"}, [])["atomic"] is True


def test_REQ_INF_302_a_promoted_finding_with_no_prediction_is_REFUSED_on_every_surface():
    """The absence is not a display bug — it is the claim having no exposure to being wrong."""
    out = render_finding({"tier": "CONFIRMED_OBSERVATIONAL"}, [])
    assert out["rendered"] is False and out["text"] == NO_FINDING
    assert "REQ-INF-302" in out["reason"]
    assert render_finding({"tier": "PROMOTED"}, [prediction()])["rendered"] is True


def test_REQ_INF_307_a_prediction_resolves_against_its_OWN_snapshot():
    """Resolving against today's feature state would let a later correction change whether a past
    prediction came true, which makes the track record a function of the present."""
    p = prediction()
    obs = [{"day": (NOW + dt.timedelta(days=7)).date(), "outcome": True}]
    r = resolve_against_snapshot(p, snapshot_hash="abc", observations=obs)
    assert isinstance(r, Resolved) and r.outcome_bool is True
    with pytest.raises(PredictionRejected, match="REQ-INF-307"):
        resolve_against_snapshot(p, snapshot_hash="different", observations=obs)


def test_REQ_INF_329_nothing_to_resolve_against_is_UNRESOLVABLE_not_false():
    """Joe's Watch stopped on 2026-08-21 and twenty-four predictions came due afterwards with
    nothing to resolve against. Counting those as wrong would compute a Brier score saying the
    system is badly calibrated when an instrument stopped."""
    r = resolve_against_snapshot(prediction(), snapshot_hash="abc", observations=[])
    assert isinstance(r, Unresolvable)
    assert r.reason == "no_observation_after_resolves_at"


def test_REQ_INF_320_three_resolved_at_fifty_percent_false_demotes_one_tier():
    out = auto_demotion({"tier": "CONFIRMED_OBSERVATIONAL"}, resolved(1, 2))
    assert out["acted"] is True and out["tier"] == "PROMOTED"
    assert out["tier_history"]["reason"] == "failed_forward_predictions"
    assert DEMOTE_MIN_RESOLVED == 3


def test_REQ_INF_320_below_the_threshold_nothing_happens():
    assert auto_demotion({"tier": "PROMOTED"}, resolved(2, 1))["acted"] is False
    assert auto_demotion({"tier": "PROMOTED"}, resolved(1, 1))["acted"] is False


def test_REQ_INF_321_five_resolved_at_sixty_percent_false_sets_REFUTED():
    out = auto_demotion({"tier": "CONFIRMED_OBSERVATIONAL"}, resolved(2, 3))
    assert out["status"] == "REFUTED" and out["tier"] == "REFUTED"
    assert REFUTE_MIN_RESOLVED == 5


def test_REQ_INF_322_there_is_no_interface_that_suppresses_defers_or_overrides_a_demotion():
    """"SHALL NOT provide any interface that suppresses, defers, or overrides." The moment such
    an argument exists, the demotions that get suppressed are exactly the ones about findings
    somebody liked. The absence of the parameter IS the requirement."""
    import inspect
    params = set(inspect.signature(auto_demotion).parameters)
    for banned in ("force", "skip", "override", "defer", "suppress", "reason_to_keep",
                   "human_confirmation", "approve"):
        assert banned not in params, f"auto_demotion accepts {banned!r}"
    assert auto_demotion({"tier": "PROMOTED"}, resolved(0, 3))["human_confirmation"] is False


def test_REQ_INF_323_the_tier_history_row_names_the_predictions_and_the_observed_rate():
    out = auto_demotion({"tier": "PROMOTED"}, resolved(1, 2))
    h = out["tier_history"]
    assert h["observed_false_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert set(h["prediction_ids"]) == {"T0", "F0", "F1"}


def test_REQ_INF_324_a_demotion_is_named_in_the_next_brief():
    """A demotion nobody is told about is indistinguishable from a claim that was never made."""
    finding = {"tier": "PROMOTED", "claim_text": "Late caffeine shortens sleep"}
    entry = demotion_brief_entry(finding, auto_demotion(finding, resolved(1, 2)))
    assert entry["failed_predictions"] == 2 and entry["n_resolved"] == 3
    assert "Late caffeine shortens sleep" in entry["text"]
    assert entry["new_tier"] in entry["text"]
    assert demotion_brief_entry(finding, auto_demotion(finding, resolved(3, 0))) is None


def test_REQ_INF_325_a_bucket_needs_twenty_resolved_and_a_gap_over_fifteen_points():
    buckets = {"0.7": {"n": MISCALIBRATION_MIN_N, "nominal": 0.7, "observed": 0.5},
               "0.8": {"n": MISCALIBRATION_MIN_N, "nominal": 0.8, "observed": 0.70},
               "0.9": {"n": MISCALIBRATION_MIN_N - 1, "nominal": 0.9, "observed": 0.1}}
    out = miscalibrated_buckets(buckets)
    assert set(out) == {"0.7"}, "0.8 gap is exactly 0.10; 0.9 has too few resolved"
    assert MISCALIBRATION_GAP == 0.15


def test_REQ_INF_325_326_a_miscalibrated_claim_widens_and_downgrades_its_wording():
    """A bucket where "70% likely" comes true half the time is not a bucket to suppress — it is
    one whose numbers mean something different from what they say."""
    claim = {"interval": [10.0, 20.0], "verbal_probability": {"term": "likely"}}
    out = apply_miscalibration(claim, {"gap": 0.2, "n": 30, "nominal": 0.7, "observed": 0.5})
    assert out["interval"][0] < 10.0 and out["interval"][1] > 20.0
    assert out["interval_widened"] is True
    assert out["verbal_probability"]["term"] == "about as likely as not", \
        "the term follows the OBSERVED 50%, not the nominal 70%"
    assert "not the stated one" in out["disclosure"]


def test_REQ_INF_326_a_well_calibrated_claim_is_untouched():
    claim = {"interval": [10.0, 20.0]}
    assert apply_miscalibration(claim, None) == claim


def test_REQ_INF_327_328_the_track_record_is_complete_and_never_recomputed():
    """A track record that improves when the model changes is not a track record, it is a
    redraft."""
    rows = track_record(resolved(2, 1) + [Unresolvable("U1", "watch_stopped")])
    assert rows["available_on_demand"] is True and rows["deletions"] == 0
    assert len(rows["rows"]) == 4
    assert all(r.get("recomputed") is False for r in rows["rows"] if "brier" in r)
    assert any(r.get("excluded_from_scoring") for r in rows["rows"])


def test_REQ_INF_330_above_a_quarter_unresolvable_the_system_reports_its_OWN_calibration_as_INSUFFICIENT():
    many_unresolvable = resolved(2, 1) + [Unresolvable(f"U{i}", "watch_stopped")
                                          for i in range(4)]
    assert unresolvable_rate(many_unresolvable) > UNRESOLVABLE_CEILING
    out = calibration_report(many_unresolvable)
    assert out["tier"] == "INSUFFICIENT" and out["scored"] is False
    assert "cannot currently be assessed" in out["text"]


def test_REQ_INF_330_a_healthy_rate_is_scored_normally():
    out = calibration_report(resolved(8, 2) + [Unresolvable("U1", "x")])
    assert out["tier"] == "DESCRIPTIVE" and out["scored"] is True


def test_REQ_INF_331_a_recommendation_carries_its_own_scored_forward_prediction():
    """Advice that commits to nothing can never be found wrong, and advice is the output with the
    most direct effect on what Joe actually does."""
    rec = {"text": "Move caffeine before 14:00"}
    out = recommendation_with_prediction(rec, tier="CONFIRMED_OBSERVATIONAL",
                                         tier_floor="PROMOTED", effect_delta=20, min_effect=10,
                                         prediction=prediction())
    assert out["provisional"] is True and out["prediction"]["prediction_id"] == "P-1"
    with pytest.raises(PredictionRejected, match="REQ-INF-331"):
        recommendation_with_prediction(rec, tier="CONFIRMED_OBSERVATIONAL",
                                       tier_floor="PROMOTED", effect_delta=20, min_effect=10,
                                       prediction=None)


def test_REQ_INF_331_below_the_floor_or_the_effect_threshold_no_recommendation_is_emitted():
    rec = {"text": "x"}
    assert recommendation_with_prediction(rec, tier="EXPLORATORY", tier_floor="PROMOTED",
                                          effect_delta=99, min_effect=1,
                                          prediction=prediction()) is None
    assert recommendation_with_prediction(rec, tier="PROMOTED", tier_floor="PROMOTED",
                                          effect_delta=1, min_effect=10,
                                          prediction=prediction()) is None
