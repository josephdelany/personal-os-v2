"""B19 §D — interrupted time series (REQ-INF-218, 219)."""
import datetime as dt

import pytest

from tools.engines.interrupted_series import (MAX_TIER, NotApplicable, applies, check_tier,
                                              result, select_control)

CHANGE = dt.date(2026, 5, 1)


def test_REQ_INF_218_it_applies_to_a_known_date_with_no_randomisation_available():
    out = applies(change_date=CHANGE, randomisation_possible=False)
    assert out["applies"] is True and out["method"] == "interrupted_time_series"
    assert isinstance(applies(change_date=CHANGE, randomisation_possible=True), NotApplicable)


def test_REQ_INF_218_without_a_known_date_the_method_degenerates_into_changepoint_hunting():
    """An ITS interrupts at a KNOWN date. Without one, the method searches for the best
    changepoint — which will always find one."""
    out = applies(change_date=None, randomisation_possible=False)
    assert isinstance(out, NotApplicable)
    assert "will always find one" in out.detail


def test_REQ_INF_218_the_control_series_is_PRINTED_and_vetoable():
    """An ITS estimate is only as good as its control, and choosing it is a judgement about Joe's
    life the system cannot make — steps is a reasonable control for sleep unless the thing that
    changed was his commute."""
    cands = [{"metric": "steps", "pre_period_correlation": 0.7},
             {"metric": "resting_hr", "pre_period_correlation": 0.3}]
    out = select_control(cands, outcome="sleep_minutes")
    assert out["control"] == "steps" and out["printed"] is True and out["vetoable"] is True
    assert "Veto it if that is wrong" in out["text"]
    assert out["alternatives"] == ("resting_hr",)


def test_REQ_INF_218_a_vetoed_control_is_not_used():
    cands = [{"metric": "steps", "pre_period_correlation": 0.7},
             {"metric": "resting_hr", "pre_period_correlation": 0.3}]
    out = select_control(cands, outcome="sleep_minutes", vetoed=("steps",))
    assert out["control"] == "resting_hr"


def test_REQ_INF_218_no_control_at_all_means_no_estimate():
    """An ITS without a control cannot separate the intervention from everything else that
    changed."""
    out = select_control([{"metric": "steps"}], outcome="sleep_minutes", vetoed=("steps",))
    assert isinstance(out, NotApplicable) and out.reason == "no_control_series"


def test_REQ_INF_219_an_its_result_is_capped_at_CONFIRMED_OBSERVATIONAL():
    """n=1, no randomisation, one intervention date. A clean discontinuity is exactly when
    somebody would want to call it an experiment."""
    out = result({"delta": -22}, control="steps", change_date=CHANGE)
    assert out["tier"] == MAX_TIER == "CONFIRMED_OBSERVATIONAL"
    assert out["randomised"] is False
    assert "cannot become experimental" in out["note"]


def test_REQ_INF_219_a_higher_tier_is_refused():
    assert check_tier("PROMOTED") and check_tier(MAX_TIER)
    with pytest.raises(ValueError, match="REQ-INF-219"):
        check_tier("EXPERIMENTAL")
