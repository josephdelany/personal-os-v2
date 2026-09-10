"""B17 §C.3 — recurrence detection (REQ-FIN-130..140).

Pure and deterministic, exercised against series whose right answer is known by construction.
The spec calls this "the substrate for the whole section": everything in §C.4 and §D is built on
whether a stream was detected at all.
"""
import datetime as dt
import statistics

import pytest

from tools.engines.recurrence import (CANDIDATE_PERIODS, EARLY_OCCURRENCES, HABIT_CATEGORIES,
                                      MATURE_OCCURRENCES, Stream, build_stream,
                                      changepoint_insight, classify_amounts, detect,
                                      detect_changepoint, lifecycle)


def monthly(start, n, day=15, amount=12.99):
    out, y, m = [], start.year, start.month
    for _ in range(n):
        last = (dt.date(y + (m == 12), (m % 12) + 1, 1) - dt.timedelta(days=1)).day
        out.append((dt.date(y, m, min(day, last)), amount))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def test_REQ_FIN_130_three_occurrences_make_a_stream_mature():
    s = build_stream("Netflix", "visa", monthly(dt.date(2026, 1, 15), 3),
                     as_of=dt.date(2026, 4, 1))
    assert s.occurrences == 3 and s.maturity == "mature"
    assert MATURE_OCCURRENCES == 3


def test_REQ_FIN_131_two_occurrences_are_an_early_detection_marked_as_such():
    """So a newly-started subscription is visible before it has run three cycles."""
    s = build_stream("Netflix", "visa", monthly(dt.date(2026, 1, 15), 2),
                     as_of=dt.date(2026, 3, 1))
    assert s.maturity == "early_detection"
    assert EARLY_OCCURRENCES == 2


def test_REQ_FIN_130_one_occurrence_is_not_a_stream():
    assert build_stream("X", "visa", monthly(dt.date(2026, 1, 15), 1),
                        as_of=dt.date(2026, 2, 1)) is None


def test_REQ_FIN_132_a_charge_on_the_31st_still_fits_through_february():
    """Measured as a fixed 30-day interval these are misses. Measured as same-day-of-month plus
    or minus three, they are the same subscription."""
    days = [dt.date(2026, 1, 31), dt.date(2026, 2, 28), dt.date(2026, 3, 31),
            dt.date(2026, 4, 30), dt.date(2026, 5, 31)]
    s = build_stream("Netflix", "visa", [(d, 15.99) for d in days], as_of=dt.date(2026, 6, 5))
    assert s.period_label == "monthly_day_of_month"
    assert s.period_days == 30


def test_REQ_FIN_132_a_weekend_shift_of_up_to_three_days_does_not_break_the_fit():
    days = [dt.date(2026, 1, 1), dt.date(2026, 2, 2), dt.date(2026, 3, 3), dt.date(2026, 4, 1)]
    s = build_stream("Gym", "visa", [(d, 40.0) for d in days], as_of=dt.date(2026, 4, 10))
    assert s.period_label == "monthly_day_of_month"


def test_REQ_FIN_132_a_shift_beyond_the_tolerance_is_not_a_monthly_fit():
    days = [dt.date(2026, 1, 1), dt.date(2026, 2, 9), dt.date(2026, 3, 18)]
    s = build_stream("X", "visa", [(d, 40.0) for d in days], as_of=dt.date(2026, 3, 20))
    assert s is None or s.period_label != "monthly_day_of_month"


def test_REQ_FIN_132_the_candidate_periods_are_the_six_the_spec_names():
    assert CANDIDATE_PERIODS == (7, 14, 15, 30, 91, 365)


def test_REQ_FIN_132_a_weekly_stream_is_detected():
    days = [dt.date(2026, 1, 5) + dt.timedelta(days=7 * i) for i in range(6)]
    s = build_stream("Weekly", "visa", [(d, 9.0) for d in days], as_of=dt.date(2026, 2, 15))
    assert s.period_days == 7


def test_REQ_FIN_133_one_missed_month_does_not_destroy_the_fit():
    """The claim, checked against the alternative rather than asserted. Intervals [31, 59, 30]:
    the mean is dragged to 40 and the SD is 16, so a mean/SD rule rejects a real subscription.
    The median is 31 and the MAD is 1."""
    days = [dt.date(2026, 1, 1), dt.date(2026, 2, 1), dt.date(2026, 4, 1), dt.date(2026, 5, 1)]
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    assert statistics.mean(gaps) > 39 and statistics.pstdev(gaps) > 12, gaps
    assert statistics.median(gaps) == 31

    s = build_stream("Spotify", "visa", [(d, 11.99) for d in days], as_of=dt.date(2026, 5, 20))
    assert s is not None, "a mean/SD rule would have lost this subscription"
    assert s.period_days == 30


def test_REQ_FIN_134_a_stable_amount_is_fixed():
    assert classify_amounts([12.99] * 6)[0] == "fixed"
    assert classify_amounts([12.99, 13.00, 12.98])[0] == "fixed", "under 2% CV"


def test_REQ_FIN_134_135_a_price_rise_is_fixed_with_step_and_names_the_month():
    """"It went from $12.99 to $15.99 in March" is a fact Joe can check against his memory. "A
    changepoint at position 7" is not."""
    charges = [(dt.date(2026, m, 15), a)
               for m, a in zip(range(1, 7), [12.99, 12.99, 12.99, 15.99, 15.99, 15.99])]
    s = build_stream("Utility", "visa", charges, as_of=dt.date(2026, 6, 20))
    assert s.amount_behaviour == "fixed_with_step"
    insight = changepoint_insight(s)
    assert insight["previous_amount"] == 12.99 and insight["new_amount"] == 15.99
    assert insight["changed_month"] == "April 2026"
    assert "12.99 to 15.99 in April 2026" in insight["text"]


def test_REQ_FIN_134_a_rounding_change_is_not_a_price_rise():
    """$9.99 to $10.00 has not changed price, it has been rounded. Reporting that would train
    Joe to ignore the ones that matter."""
    assert detect_changepoint([9.99] * 4 + [10.00] * 4) is None


def test_REQ_FIN_134_a_wandering_series_is_variable_not_fixed_with_step():
    """A series that wanders AND happens to have a best split is variable; calling it
    fixed_with_step would promise a stable price that does not exist."""
    behaviour, _ = classify_amounts([40.0, 92.0, 51.0, 130.0, 61.0, 155.0])
    assert behaviour == "variable"


def test_REQ_FIN_136_amount_stability_is_not_required_to_be_recurring():
    """A phone bill and a utility bill are recurring in every sense that matters and their
    amounts move every month. Requiring stability would detect Netflix and miss the electricity
    — and the electricity is where a step change hides."""
    charges = [(dt.date(2026, m, 12), a)
               for m, a in zip(range(1, 7), [88.0, 141.0, 96.0, 73.0, 119.0, 90.0])]
    s = build_stream("Electric Co", "visa", charges, as_of=dt.date(2026, 6, 20))
    assert s is not None and s.period_label == "monthly_day_of_month"
    assert s.amount_behaviour == "variable"


def test_REQ_FIN_137_the_three_lifecycle_states_have_the_boundaries_the_spec_gives():
    assert lifecycle(29, 30) == "active"
    assert lifecycle(44, 30) == "active", "just under 1.5x"
    assert lifecycle(45, 30) == "lapsed", "1.5x"
    assert lifecycle(75, 30) == "lapsed", "2.5x is still lapsed"
    assert lifecycle(76, 30) == "cancelled"


def test_REQ_FIN_138_a_cancelled_stream_is_returned_not_dropped():
    """A resurrected subscription is itself behavioural data: the thing cancelled in March and
    restarted in September is a more interesting fact than either event alone. Deleting the row
    would make the restart look like a first-ever charge."""
    charges = [{"merchant": "Gone", "account": "visa", "day": d, "amount": 9.99}
               for d, _ in monthly(dt.date(2026, 1, 10), 4)]
    streams = detect(charges, as_of=dt.date(2026, 12, 1))
    assert len(streams) == 1
    assert streams[0].lifecycle == "cancelled"


def test_REQ_FIN_139_groceries_fuel_coffee_and_bars_route_to_habits_not_subscriptions():
    """Same mathematics, different table, different surface. A weekly coffee IS periodic, and
    calling it a subscription would put "cancel this?" next to something nobody subscribes to."""
    for category in ("groceries", "fuel", "coffee", "bars"):
        assert category in HABIT_CATEGORIES
        s = build_stream("M", "visa", monthly(dt.date(2026, 1, 5), 4), as_of=dt.date(2026, 5, 1),
                         category=category)
        assert s.routed_to == "habits", category
    s = build_stream("Netflix", "visa", monthly(dt.date(2026, 1, 5), 4),
                     as_of=dt.date(2026, 5, 1), category="entertainment")
    assert s.routed_to == "subscriptions"


def test_REQ_FIN_140_a_not_a_subscription_label_persists_into_every_later_run():
    """A label Joe has to reapply is a label he stops giving."""
    charges = monthly(dt.date(2026, 1, 5), 5)
    assert build_stream("M", "visa", charges, as_of=dt.date(2026, 6, 1)) is not None
    assert build_stream("M", "visa", charges, as_of=dt.date(2026, 6, 1),
                        user_labels={("M", "visa"): "not_a_subscription"}) is None


def test_REQ_FIN_140_a_missed_stream_joe_reports_is_kept_even_without_a_clean_period():
    charges = [(dt.date(2026, 1, 3), 20.0), (dt.date(2026, 2, 19), 20.0),
               (dt.date(2026, 4, 28), 20.0)]
    assert build_stream("Odd", "visa", charges, as_of=dt.date(2026, 5, 1)) is None
    s = build_stream("Odd", "visa", charges, as_of=dt.date(2026, 5, 1),
                     user_labels={("Odd", "visa"): "is_a_subscription"})
    assert s is not None and s.period_label == "user_asserted"


def test_REQ_FIN_130_streams_are_grouped_by_merchant_AND_account():
    """The same subscription on two cards is two streams: one may lapse while the other runs."""
    charges = []
    for acct in ("visa", "amex"):
        charges += [{"merchant": "Netflix", "account": acct, "day": d, "amount": a}
                    for d, a in monthly(dt.date(2026, 1, 9), 4)]
    streams = detect(charges, as_of=dt.date(2026, 5, 1))
    assert {s.account for s in streams} == {"visa", "amex"}
    assert len(streams) == 2


def test_RULE_11_detection_is_deterministic():
    charges = [{"merchant": "N", "account": "v", "day": d, "amount": a}
               for d, a in monthly(dt.date(2026, 1, 9), 6)]
    a = detect(charges, as_of=dt.date(2026, 7, 1))
    b = detect(list(reversed(charges)), as_of=dt.date(2026, 7, 1))
    assert a == b
