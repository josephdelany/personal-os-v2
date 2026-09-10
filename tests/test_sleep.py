"""B21.2 — sleep timing (REQ-SLP-001..013; RULE-06, RULE-07, RULE-08, RULE-12).

Pure arithmetic over explicit intervals, so it is exercised exhaustively rather than sampled.
Every test is about a distinction the measures must not collapse.
"""
import datetime as dt

import pytest

from tools.engines.sleep import (MIN_NIGHTS_FOR_REGULARITY, ET, Night, Omission,
                                 merge, midpoint_minutes, night, regularity, sessions)

U = dt.timezone.utc


def iv(h1, m1, h2, m2, day=14):
    return (dt.datetime(2026, 8, day, h1, m1, tzinfo=U),
            dt.datetime(2026, 8, day, h2, m2, tzinfo=U))


def test_REQ_SLP_002_overlapping_segments_are_counted_once():
    assert merge([iv(3, 0, 5, 0), iv(4, 0, 6, 0)]) == [iv(3, 0, 6, 0)]


def test_REQ_SLP_001_the_window_contains_the_awake_time_and_the_duration_does_not():
    """Three facts about one night that are not the same fact. A 6h duration inside a 9h window
    is a different night from 6h inside a 6h window, and one number would erase that."""
    n = night([iv(3, 0, 6, 0), iv(7, 0, 9, 0)])
    assert n.asleep_min == 300.0, "duration is the union of the asleep segments"
    assert n.window_min == 360.0, "the window runs onset to final wake"
    assert n.awake_in_window_min == 60.0
    assert n.efficiency == round(300 / 360, 3)


def test_REQ_SLP_004_a_nap_is_disclosed_not_folded_into_the_night():
    """Real data: 2026-07-14 held two blocks 352 minutes apart. Treating every segment in a
    subject day as one period made a 938-minute "window" holding 586 minutes of sleep, with a
    midpoint at 13:14 — an outlier that on its own pushed the regularity spread from plausible
    to 208 minutes. Splitting on the importer's own three-hour session gap took it to 87."""
    n = night([iv(3, 0, 9, 0), iv(15, 0, 17, 0)])
    assert n.asleep_min == 360.0, "the main session only"
    assert n.other_sessions == 1
    assert n.other_asleep_min == 120.0
    assert n.window_min == 360.0, "the nap must not stretch the night's window"


def test_REQ_SLP_003_the_session_gap_is_the_importers_own_constant():
    """One definition of where a night ends. If the engine and the importer could disagree
    about that, one night could be two facts."""
    from tools.importers.apple_health import SLEEP_SESSION_GAP
    import tools.engines.sleep as sleep_engine
    assert sleep_engine.SLEEP_SESSION_GAP is SLEEP_SESSION_GAP


def test_REQ_SLP_003_a_short_intra_night_wake_does_not_split_the_night():
    """Apple records wake periods as their own segments and they are minutes, not hours."""
    assert len(sessions([iv(3, 0, 5, 0), iv(5, 20, 9, 0)])) == 1


def test_REQ_SLP_007_the_midpoint_is_local_so_a_clock_change_cannot_move_it():
    """Computed in UTC, a March daylight-saving change would shift every midpoint by an hour
    and read as Joe's sleep shifting."""
    winter = night([(dt.datetime(2026, 1, 15, 4, 0, tzinfo=U),
                     dt.datetime(2026, 1, 15, 12, 0, tzinfo=U))])
    summer = night([(dt.datetime(2026, 7, 15, 3, 0, tzinfo=U),
                     dt.datetime(2026, 7, 15, 11, 0, tzinfo=U))])
    # 23:00 -> 07:00 local in both seasons, despite a one-hour offset difference.
    assert midpoint_minutes(winter, ET) == midpoint_minutes(summer, ET)


def test_REQ_SLP_007_midnight_does_not_split_the_midpoint_distribution():
    """23:50 and 00:10 are twenty minutes apart, not twenty-three hours. Anchoring on noon is
    what makes a spread over those two nights meaningful."""
    before = night([(dt.datetime(2026, 8, 14, 1, 50, tzinfo=U),   # 21:50 local
                     dt.datetime(2026, 8, 14, 5, 50, tzinfo=U))])  # 01:50 local
    after = night([(dt.datetime(2026, 8, 14, 2, 10, tzinfo=U),
                    dt.datetime(2026, 8, 14, 6, 10, tzinfo=U))])
    assert abs(midpoint_minutes(before) - midpoint_minutes(after)) == 20.0


def test_REQ_SLP_011_regularity_refuses_a_sample_too_thin_to_mean_anything():
    one = night([iv(3, 0, 9, 0)])
    r = regularity([one] * (MIN_NIGHTS_FOR_REGULARITY - 1))
    assert isinstance(r, Omission) and r.reason == "too_few_nights"
    ok = regularity([one] * MIN_NIGHTS_FOR_REGULARITY)
    assert ok["nights_used"] == MIN_NIGHTS_FOR_REGULARITY


def test_REQ_SLP_012_a_missing_night_is_absent_from_the_statistic_not_treated_as_usual():
    """An unlogged night is unknown. Counting it as the median would make an irregular sleeper
    look regular in exactly the weeks the data is worst."""
    nights = [night([iv(2 + i % 3, 0, 8 + i % 3, 0)]) for i in range(8)]
    r = regularity(nights)
    assert r["nights_used"] == 8, "only nights actually present may be counted"


def test_REQ_SLP_001_a_night_with_no_segments_is_an_omission_not_a_zero_length_sleep():
    assert isinstance(night([]), Omission)
    assert isinstance(night([(None, None)]), Omission)


def test_REQ_SLP_006_an_undefined_efficiency_is_none_rather_than_one():
    """A ratio with no denominator is not 100%."""
    n = Night(onset=dt.datetime(2026, 8, 14, tzinfo=U),
              final_wake=dt.datetime(2026, 8, 14, tzinfo=U), window_min=0.0, asleep_min=0.0)
    assert n.efficiency is None


def test_REQ_SLP_010_regularity_reports_a_spread_and_carries_no_target():
    r = regularity([night([iv(3, 0, 9, 0)])] * 8)
    assert "sd_minutes" in r and "carries no target" in r["note"]


def test_REQ_SLP_005_the_main_session_rule_is_duration_and_never_time_of_day():
    """Choosing "the night" from two comparable blocks means asserting when Joe sleeps, which
    is a measurement definition reserved to him. The rule is stated (longest by time asleep)
    and applied without regard to the clock, so a long daytime sleep wins on its own terms and
    the other session is disclosed rather than silently preferred."""
    daytime_longer = night([iv(3, 0, 6, 0), iv(15, 0, 21, 0)])
    assert daytime_longer.asleep_min == 360.0, "the longer block wins regardless of the hour"
    assert daytime_longer.other_sessions == 1 and daytime_longer.other_asleep_min == 180.0
    # ...and the reverse ordering gives the mirror answer, so nothing in the rule is nocturnal.
    night_longer = night([iv(1, 0, 9, 0), iv(15, 0, 17, 0)])
    assert night_longer.asleep_min == 480.0 and night_longer.other_asleep_min == 120.0


def test_REQ_SLP_013_coverage_is_reported_against_the_window_the_caller_asked_about():
    """An aggregate over 8 of 30 nights and one over 8 of 8 are different claims, and silence
    about the denominator reads as the second."""
    nights = [night([iv(2 + i % 3, 0, 8 + i % 3, 0)]) for i in range(8)]
    asked = regularity(nights, window_nights=30)
    assert asked["nights_used"] == 8 and asked["window_nights"] == 30
    assert asked["coverage"] == round(8 / 30, 3)

    unstated = regularity(nights)
    assert unstated["coverage"] is None, (
        "with no window the engine knows what it used and not what it missed; reporting "
        "complete coverage would be a claim it cannot support")
