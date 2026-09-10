"""B19 §E — resolving predictions and scoring calibration (REQ-INF-300..309, RULE-06, RULE-07).

Pure arithmetic, exercised exhaustively. The tests are mostly about the two ways a calibration
number lies: scoring a silent instrument as a wrong forecast, and reporting a Brier score
without the decomposition that gives it meaning.
"""
import math

import pytest

from tools.engines.calibration import (DEFAULT_BINS, LOG_CLAMP, MIN_RESOLVED_FOR_SUMMARY,
                                       Resolved, Unresolvable, murphy, resolve, score)


def pred(p=0.9, band=(200.0, 400.0), rule="panel value in stored band", pid="x"):
    return dict(prediction_id=pid, p_forecast=p, resolution_rule=rule, band=band)


def test_REQ_INF_306_a_confident_hit_and_a_confident_miss_score_as_they_should():
    assert score(0.9, True) == (0.01, round(-math.log(0.9), 6))
    assert score(0.9, False) == (0.81, round(-math.log(0.1), 6))
    assert score(0.5, True)[0] == score(0.5, False)[0] == 0.25


def test_REQ_INF_306_the_log_score_is_clamped_rather_than_infinite():
    """A certainty that was wrong would otherwise poison a whole batch with an infinity, and
    an infinite penalty cannot be compared to anything."""
    _, log_score = score(0.0, True)
    assert math.isfinite(log_score)
    assert log_score == round(-math.log(LOG_CLAMP), 6)


def test_REQ_INF_306_a_probability_outside_zero_to_one_is_refused():
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        score(1.4, True)


def test_RULE_07_no_observation_is_unresolvable_and_never_a_wrong_forecast():
    """The error this module exists to prevent. Joe's 32 due predictions cover `rhr`,
    `hrv_sdnn`, `sleep_asleep_min` and `steps`; the Watch stopped 2026-08-21 and the panel for
    all four ends in July. Scoring them as wrong would produce a Brier of 0.81 apiece, demote
    findings, and make an instrument failure look like a forecasting failure."""
    r = resolve(pred(), None)
    assert isinstance(r, Unresolvable) and r.reason == "no_observation"
    assert "not evidence that the forecast was wrong" in r.detail


def test_REQ_INF_304_a_rule_this_job_cannot_evaluate_is_refused_not_guessed():
    assert isinstance(resolve(pred(rule="whatever Joe meant"), 300), Unresolvable)
    assert resolve(pred(band=None), 300).reason == "unevaluable_rule"


def test_REQ_INF_306_a_value_inside_and_outside_the_band_resolve_correctly():
    inside = resolve(pred(), 300.0)
    assert isinstance(inside, Resolved) and inside.outcome_bool is True and inside.brier == 0.01
    outside = resolve(pred(), 500.0)
    assert outside.outcome_bool is False and outside.brier == 0.81


def test_REQ_INF_306_the_band_is_inclusive_at_both_edges():
    assert resolve(pred(), 200.0).outcome_bool is True
    assert resolve(pred(), 400.0).outcome_bool is True


def _batch(n, p=0.7, hit_rate=None):
    hits = int(n * (p if hit_rate is None else hit_rate))
    out = []
    for i in range(n):
        outcome = i < hits
        b, l = score(p, outcome)
        out.append(Resolved(str(i), p, outcome, b, l))
    return out


def test_REQ_INF_309_the_brier_score_is_never_returned_without_its_decomposition():
    """A Brier of 0.09 sounds good and says almost nothing: forecasting the base rate every
    time scores well on a rare event while carrying no skill at all."""
    m = murphy(_batch(40))
    for key in ("brier", "reliability", "resolution", "uncertainty", "n", "base_rate"):
        assert key in m, key


def test_REQ_INF_309_the_decomposition_reconstructs_the_score_exactly():
    """Murphy's identity is exact. Three plausible-looking components that do not sum to the
    score they decompose are worse than no decomposition, and the engine raises rather than
    returning them."""
    m = murphy(_batch(40))
    assert abs((m["reliability"] - m["resolution"] + m["uncertainty"]) - m["brier"]) < 1e-6


def test_REQ_INF_309_a_perfectly_calibrated_forecaster_has_near_zero_reliability():
    """70% forecasts that come true 70% of the time: reliability ~0, and the Brier is then
    almost all uncertainty — which is a property of the world, not of the forecaster."""
    m = murphy(_batch(100, p=0.7, hit_rate=0.7))
    assert m["reliability"] < 1e-6
    assert abs(m["uncertainty"] - 0.7 * 0.3) < 1e-6


def test_REQ_INF_309_a_forecaster_with_no_skill_has_zero_resolution():
    """One forecast value for everything cannot separate outcomes, however good its Brier."""
    m = murphy(_batch(60, p=0.5, hit_rate=0.5))
    assert m["resolution"] == 0.0, "a single-bin forecaster resolves nothing"


def test_RULE_06_a_calibration_summary_refuses_a_sample_too_thin_to_mean_anything():
    thin = murphy(_batch(MIN_RESOLVED_FOR_SUMMARY - 1))
    assert isinstance(thin, Unresolvable) and thin.reason == "too_few_resolved"
    assert isinstance(murphy([]), Unresolvable)


def test_RULE_06_unresolvable_predictions_are_excluded_from_the_summary_not_counted_false():
    """The whole point, at the aggregate level: 24 silent instruments must not become 24
    failed forecasts."""
    mixed = _batch(30) + [Unresolvable(str(i), "no_observation") for i in range(24)]
    m = murphy(mixed)
    assert m["n"] == 30, "unresolvable rows must not enter the denominator"


def test_REQ_INF_308_the_bin_count_is_stated_because_it_changes_the_answer():
    """A different binning gives a different reliability term, so the number travels with it."""
    m = murphy(_batch(40))
    assert m["bins"] == DEFAULT_BINS
