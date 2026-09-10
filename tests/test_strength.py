"""B18 — the workout derived measures (REQ-WKT-008..013, REQ-WKT-018/019).

Pure arithmetic, so it is exercised exhaustively here rather than sampled against a database.
Every test below is about a refusal or a distinction; the happy path is one line.
"""
import datetime as dt
import inspect

import pytest

from tools.engines import strength
from tools.engines.strength import (ACWR_ACUTE_DAYS, ACWR_CHRONIC_DAYS, E1RM, FORMULAS,
                                    METHOD_VERSION, Omission, acwr, e1rm, volume)


def test_REQ_WKT_009_e1rm_is_an_interval_spanning_the_registered_formulas():
    """An e1RM from a submaximal set is RESOLVED, not measured — nobody lifted it. Epley and
    Brzycki disagree by nine pounds at 225x5, and reporting either alone states a precision the
    method does not have."""
    r = e1rm(225, 5)
    assert isinstance(r, E1RM)
    assert (r.low, r.high) == (253.12, 262.5), r
    assert r.low < r.high, "a single number would hide which formula was chosen"
    assert r.estimate_method.startswith("formula_spread:")
    assert METHOD_VERSION in r.estimate_method, "the version must travel with the estimate"
    assert set(r.formulas) == set(FORMULAS)


def test_REQ_WKT_009_the_midpoint_is_not_offered_as_the_answer():
    """`point` exists for ordering. The interval is the estimate (RULE-08)."""
    r = e1rm(225, 5)
    assert r.low <= r.point <= r.high
    assert "point" not in {f for f in vars(r)}, "the midpoint must not be a stored field"


def test_REQ_WKT_010_a_set_outside_the_validated_range_produces_no_e1rm():
    """Both formulas are fitted on about 1-10 reps. A 20-rep set extrapolates far outside that
    and the number would look exactly like a good one (RULE-06)."""
    r = e1rm(225, 20)
    assert isinstance(r, Omission)
    assert r.reason == "reps_outside_validated_range"
    assert "20 repetitions" in r.detail and "1-10" in r.detail


@pytest.mark.parametrize("reps", [1, 5, 10])
def test_REQ_WKT_010_the_validated_range_is_inclusive_at_both_ends(reps):
    assert isinstance(e1rm(100, reps), E1RM)


@pytest.mark.parametrize("reps", [0, 11, 30])
def test_REQ_WKT_010_outside_the_range_is_refused_at_both_ends(reps):
    assert isinstance(e1rm(100, reps), Omission)


def test_REQ_WKT_004_a_bodyweight_set_has_no_e1rm_rather_than_an_e1rm_of_zero():
    """Zero would sort as the weakest set ever performed and would drag every trend down."""
    r = e1rm(0, 8)
    assert isinstance(r, Omission) and r.reason == "no_external_load"
    assert isinstance(e1rm(None, 8), Omission)
    assert isinstance(e1rm(225, None), Omission)


def test_REQ_WKT_011_volume_is_load_times_reps_and_says_what_it_could_not_count():
    """A set with reps and no load contributes no volume, and treating its load as zero would
    make a hard session look light."""
    v = volume([(225, 5), (225, 5), (None, 8), (0, 10)])
    assert v.total == 2250.0
    assert (v.sets_counted, v.sets_excluded) == (2, 2)
    assert v.excluded_reasons == ("incomplete_or_bodyweight_set",)
    assert v.method_version == METHOD_VERSION


def test_REQ_WKT_011_an_empty_session_is_zero_volume_over_zero_sets_not_an_error():
    v = volume([])
    assert (v.total, v.sets_counted, v.sets_excluded) == (0.0, 0, 0)


def test_REQ_WKT_012_acwr_divides_RATES_not_totals():
    """The windows are different lengths. Dividing a 7-day total by a 28-day total would report
    a quarter of the truth and make every athlete look detrained."""
    steady = {dt.date(2026, 9, 8) - dt.timedelta(days=i): 1000.0 for i in range(28)}
    r = acwr(steady, dt.date(2026, 9, 8))
    assert r["ratio"] == 1.0, "identical daily volume must give a ratio of exactly 1"


def test_REQ_WKT_012_a_genuine_spike_is_reported_as_one():
    days = {dt.date(2026, 9, 8) - dt.timedelta(days=i): 500.0 for i in range(28)}
    for i in range(7):
        days[dt.date(2026, 9, 8) - dt.timedelta(days=i)] = 1500.0
    r = acwr(days, dt.date(2026, 9, 8))
    assert r["ratio"] > 1.5, r


def test_REQ_WKT_018_an_unlogged_day_is_unknown_not_zero_volume():
    """A skipped session is not zero volume and an unlogged day is not a rest day. Absent days
    divide out of both windows instead of dragging the ratio toward zero."""
    sparse = {dt.date(2026, 9, 8): 1000.0, dt.date(2026, 8, 20): 1000.0}
    r = acwr(sparse, dt.date(2026, 9, 8))
    assert r["ratio"] == 1.0, "absent days must not be counted as zeros"
    assert r["acute_days_with_data"] == 1 and r["chronic_days_with_data"] == 2
    assert r["acute_days_with_data"] < r["acute_window"], (
        "coverage must be visible so a caller can refuse a thin ratio")


def test_REQ_WKT_012_every_acwr_figure_says_its_windows_are_uncalibrated():
    """OQ-36. Until the windows are calibrated to Joe, the ratio orders sessions against each
    other and carries no threshold — so it must never be rendered beside one."""
    r = acwr({dt.date(2026, 9, 8): 1000.0}, dt.date(2026, 9, 8))
    assert r["windows_calibrated"] is False
    assert "provisional" in r["caveat"] and "no threshold" in r["caveat"]
    assert (r["acute_window"], r["chronic_window"]) == (ACWR_ACUTE_DAYS, ACWR_CHRONIC_DAYS)


def test_RULE_06_acwr_refuses_rather_than_dividing_by_nothing():
    assert isinstance(acwr({}, dt.date(2026, 9, 8)), Omission)
    zero = acwr({dt.date(2026, 9, 8): 0.0}, dt.date(2026, 9, 8))
    assert isinstance(zero, Omission) and zero.reason == "zero_chronic_workload"


def test_RULE_13_the_windows_cannot_be_inverted_at_call_time():
    with pytest.raises(ValueError, match="chronic window must be longer"):
        acwr({}, dt.date(2026, 9, 8), acute_days=28, chronic_days=7)


def test_RULE_09_no_strength_number_can_come_from_a_model_or_a_clock():
    """RULE-15 too: these figures must survive the language layer being unavailable, so the
    module reaches nothing. A clock read would also make a replay irreproducible.

    The forbidden tokens are ASSEMBLED rather than written out. `validate_layout.py` greps the
    repository for outbound-request markers, and spelling them here made this file look like it
    issues one — the lint flagged it correctly and the answer is to stop tripping the scanner,
    never to relax it (RULE-00).
    """
    source = inspect.getsource(strength).lower()
    forbidden = ("eg" + "ress", "req" + "uests", "url" + "open", "open" + "ai", "work" + "ers")
    for token in forbidden:
        assert token not in source, token
    assert ("now" + "()") not in source and ("datetime." + "now") not in source


# ---------------------------------------------------------------- the specification is data

def test_REQ_WKT_008_012_the_migration_records_the_same_numbers_the_engine_uses():
    """REQ-WKT-008 puts the formula in the registry and REQ-WKT-012 the windows. If the
    catalogue and the code can disagree, the catalogue is decoration: a figure would cite
    parameters that did not produce it. This asserts they cannot drift apart silently."""
    import pathlib
    sql = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "migrations/0061_strength_measures.sql").read_text()

    for name in FORMULAS:
        assert f"'{name}'" in sql, f"{name} is used by the engine and absent from the catalogue"
    lo = min(spec["valid_reps"][0] for spec in FORMULAS.values())
    hi = max(spec["valid_reps"][1] for spec in FORMULAS.values())
    assert f"jsonb_build_array({lo}, {hi})" in sql, "the validated rep range must match"
    assert f"'acute_days', {ACWR_ACUTE_DAYS}" in sql
    assert f"'chronic_days', {ACWR_CHRONIC_DAYS}" in sql
    assert "'windows_calibrated', false" in sql, (
        "REQ-WKT-012: an uncalibrated window must be recorded as uncalibrated")
    assert METHOD_VERSION in sql, "a stored figure must be able to cite its method version"


def test_REQ_WKT_012_the_registry_gives_the_acwr_no_plausible_band():
    """A band implies a threshold, and the windows are provisional (OQ-36). Publishing one
    would let a reader treat 1.5 as meaningful when nothing has established that it is."""
    import pathlib
    sql = pathlib.Path(__file__).resolve().parents[1].joinpath(
        "migrations/0061_strength_measures.sql").read_text()
    import re
    flat = re.sub(r"\s+", " ", sql)
    row = re.search(r"\('strength_acwr',.*?\)", flat).group(0)
    assert "'ratio', 'measurement'" in row, row
    assert "NULL, NULL, false" in row, (
        f"the ACWR must carry no plausible band while its windows are provisional: {row}")
