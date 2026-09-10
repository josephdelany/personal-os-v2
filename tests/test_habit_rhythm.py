"""B17 §D.3 — the habit-rhythm engine (REQ-FIN-199).

A periodogram always returns a peak, so most of these tests are about the gate in front of it.
"""
import datetime as dt

import pytest

from tools.engines.habit_rhythm import (FAP_THRESHOLD, MIN_CYCLES_FOR_PERIODOGRAM, NoRhythm,
                                        analyse, day_of_week_rhythm, hour_of_day_rhythm,
                                        lomb_scargle)


def fridays(n, start=dt.date(2026, 1, 2)):
    return [start + dt.timedelta(days=7 * i) for i in range(n)]


def test_REQ_FIN_199_the_default_method_is_a_chi_square_against_uniform():
    r = day_of_week_rhythm(fridays(30) + [dt.date(2026, 3, 3) + dt.timedelta(days=11 * i)
                                          for i in range(10)])
    assert r["method"] == "chi_square_vs_uniform"
    assert r["df"] == 6 and r["peak_weekday"] == 4
    assert r["uniform_rejected"] is True


def test_REQ_FIN_199_a_uniform_series_is_not_a_rhythm():
    every_day = [dt.date(2026, 1, 1) + dt.timedelta(days=i) for i in range(70)]
    r = day_of_week_rhythm(every_day)
    assert r["p_value"] == pytest.approx(1.0)
    assert r["uniform_rejected"] is False


def test_REQ_FIN_199_a_p_value_is_never_returned_without_an_effect_size():
    """A large n makes a trivial departure significant, and the p-value alone would then read as
    a finding."""
    r = day_of_week_rhythm(fridays(40))
    assert "cramers_v" in r and r["cramers_v"] > 0


def test_RULE_06_too_few_observations_returns_a_reason_not_a_p_value():
    r = day_of_week_rhythm(fridays(3))
    assert isinstance(r, NoRhythm)
    assert r.reason == "too_few_observations"
    assert "asymptotic" in r.detail


def test_REQ_FIN_163_199_a_date_only_row_is_refused_rather_than_scored_as_midnight():
    """Scoring it as midnight would put a spike at 00:00 in every histogram and the test would
    then find it significant."""
    timed = [dt.datetime(2026, 9, 1, 21, 0) for _ in range(30)]
    dateless = [dt.date(2026, 9, 2) for _ in range(10)]
    r = hour_of_day_rhythm(timed + dateless)
    assert r["date_only_refused"] == 10
    assert r["n"] == 30
    assert r["counts"][0] == 0, "no phantom midnight spike"
    assert r["peak_hour"] == 21


def test_REQ_FIN_199_the_hour_histogram_is_circular_over_24_bins():
    r = hour_of_day_rhythm([dt.datetime(2026, 9, 1, h % 24) for h in range(48)])
    assert r["bins"] == 24 and r["df"] == 23
    assert sum(r["counts"]) == 48
    assert r["uniform_rejected"] is False, "two full cycles is uniform"


def test_REQ_FIN_199_the_periodogram_refuses_a_series_with_too_few_cycles():
    """A periodogram will ALWAYS return a peak. On a short irregular series the highest peak is
    noise, and it arrives looking exactly like a discovery."""
    r = lomb_scargle([0, 1, 2, 3], [1.0, 2.0, 1.0, 2.0], span_days=4)
    assert isinstance(r, NoRhythm) and r.reason == "too_few_cycles"
    assert "noise wearing a period's clothes" in r.detail


def test_REQ_FIN_199_a_peak_that_does_not_clear_the_false_alarm_probability_is_not_reported():
    """Not reported at a lower tier. Not reported."""
    import random
    rng = random.Random(5)
    t = list(range(400))
    noise = [rng.gauss(0, 1) for _ in t]
    r = lomb_scargle(t, noise, span_days=400, min_period=2.0, max_period=40.0)
    assert isinstance(r, NoRhythm), r
    assert r.reason == "peak_does_not_clear_false_alarm_probability"
    assert "always returns a peak" in r.detail


def test_REQ_FIN_199_a_real_period_clears_the_gate():
    import math
    t = list(range(400))
    y = [math.sin(2 * math.pi * x / 14.0) for x in t]
    r = lomb_scargle(t, y, span_days=400, min_period=2.0, max_period=40.0)
    assert not isinstance(r, NoRhythm), r
    assert r["peak_period_days"] == pytest.approx(14.0, abs=0.6)
    assert r["false_alarm_probability"] <= FAP_THRESHOLD


def test_REQ_FIN_199_analyse_runs_the_default_first_and_the_periodogram_only_if_licensed():
    days = fridays(30)
    out = analyse(days, times=[dt.datetime.combine(d, dt.time(21)) for d in days])
    assert out["day_of_week"]["method"] == "chi_square_vs_uniform"
    assert "periodogram" not in out, "no values and no span: the periodogram is not licensed"
    assert MIN_CYCLES_FOR_PERIODOGRAM == 10
