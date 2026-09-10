"""B16 §F.3 — compliance instrumentation without gamification (REQ-CAP-093..099).

Pure, so exercised exhaustively. Almost every test here asserts that the system DOES NOT do the
obvious thing: no streak, no 100% bar, no imputed meal, no extra prompts when capture falls.
"""
import datetime as dt

import pytest

from tools.engines.compliance import (Alert, DECLINE_CONSECUTIVE_WEEKS, DECLINE_PP_PER_WEEK,
                                      DESIGN_ALERT_REASON, EATING_OCCASIONS_BAR, GAMIFIED,
                                      WINDOW_DAYS, check_surfaces, coverage, day_is_covered,
                                      lint_surface, prompt_plan, weekly_decline)

AS_OF = dt.date(2026, 9, 10)


def days(**per_day):
    """`per_day` maps an offset-back-from-AS_OF to (checkin, eating_occasions)."""
    out = []
    for offset, (checkin, meals) in per_day.items():
        out.append({"day": AS_OF - dt.timedelta(days=int(offset)),
                    "morning_checkin": checkin, "eating_occasions": meals})
    return out


def test_REQ_CAP_096_the_adherence_bar_is_two_eating_occasions_not_every_meal():
    """A 100% bar guarantees daily failure, which is the mechanism the whole section exists to
    avoid."""
    assert EATING_OCCASIONS_BAR == 2
    ok, detail = day_is_covered({"morning_checkin": True, "eating_occasions": 2})
    assert ok is True
    assert detail["eating_occasions"]["bar"] == 2
    assert day_is_covered({"morning_checkin": True, "eating_occasions": 4})[0] is True
    assert day_is_covered({"morning_checkin": True, "eating_occasions": 1})[0] is False


def test_REQ_CAP_094_coverage_is_a_rolling_percentage_over_a_fixed_denominator():
    """The denominator is the window, not the days that happen to have a record. Dividing by
    "days we heard from" would report 100% for a week containing one entry — the arithmetic
    version of imputing the rest."""
    one_good_day = days(**{"0": (True, 3)})
    r = coverage(one_good_day, AS_OF)
    assert r["window_days"] == WINDOW_DAYS == 7
    assert r["days_covered"] == 1
    assert r["coverage_pct"] == pytest.approx(14.3, abs=0.1), "1/7, not 1/1"


def test_REQ_CAP_099_a_missing_meal_is_never_imputed():
    """Two logged meals out of four is 50%, not "two logged and two estimated". The estimate
    would make the record look complete while making it false."""
    r = coverage(days(**{str(i): (True, 2) for i in range(7)}), AS_OF)
    assert r["imputed"] is False
    assert r["coverage_pct"] == 100.0, "the bar is two occasions, and two were logged"
    partial = coverage(days(**{str(i): (True, 1) for i in range(7)}), AS_OF)
    assert partial["coverage_pct"] == 0.0, "one occasion misses the bar and is not topped up"


def test_RULE_06_a_day_with_no_record_is_absent_not_zero():
    """"Missing" and "logged nothing" are different facts, and only one of them is about Joe."""
    r = coverage(days(**{"0": (True, 2)}), AS_OF)
    absent = [d for d in r["per_day"] if d["detail"].get("no_record")]
    assert len(absent) == 6
    assert all(d["covered"] is False for d in absent)


def test_REQ_CAP_095_the_module_cannot_compute_a_streak_at_all():
    """A rolling percentage and a streak come from the same data and say opposite things after
    one missed day: 100% -> 86%, and 40 -> 0. The second is a cliff, and the cliff is what makes
    a person stop. So there is no run-length function in this module — unlike regimes.py, where
    one is required."""
    import tools.engines.compliance as m
    assert not hasattr(m, "run_lengths")
    assert not hasattr(m, "streak")
    r = coverage(days(**{str(i): (True, 2) for i in range(7)}), AS_OF)
    assert "streak" not in r and "consecutive" not in r
    assert lint_surface(r["note"]) == (), r["note"]


def test_REQ_CAP_095_gamified_language_is_caught_before_it_reaches_a_screen():
    for bad in ("You're on a 12 day streak!", "Badge unlocked", "Keep it up!",
                "You broke your chain", "3 consecutive days", "back on track",
                "Perfect week", "You have 400 points"):
        assert lint_surface(bad), f"not caught: {bad!r}"


def test_REQ_CAP_095_the_linter_prefers_a_miss_to_a_false_positive():
    """A false positive gets a linter switched off, and a switched-off linter catches nothing.
    Whole-word matching means an ordinary technical sentence passes."""
    for fine in ("The chained migration applies cleanly",
                 "A badger crossed the road",
                 "Coverage declined by 2 percentage points per week",
                 "Coverage was 86% over the last 7 days",
                 "Your sleep averaged 7.4 hours"):
        assert lint_surface(fine) == (), f"false positive on {fine!r}"


def test_REQ_CAP_095_many_surfaces_are_checked_at_once_and_only_failures_returned():
    out = check_surfaces({"ok": "Coverage was 86%.", "bad": "You broke your streak."})
    assert set(out) == {"bad"}
    assert "streak" in out["bad"]


def test_REQ_CAP_097_an_alert_fires_only_on_a_sustained_decline():
    """An alert that fires on ordinary variation trains its reader to ignore it, and this is the
    only signal that the ASKING has stopped working."""
    a = weekly_decline([90.0, 87.0, 84.0, 80.0])
    assert isinstance(a, Alert)
    assert a.reason == DESIGN_ALERT_REASON
    assert a.total_decline_pp == pytest.approx(10.0)
    assert len(a.weeks) == DECLINE_CONSECUTIVE_WEEKS + 1


def test_REQ_CAP_097_one_bad_week_is_not_an_alert():
    assert weekly_decline([90.0, 89.5, 89.0, 80.0]) is None
    assert weekly_decline([90.0, 85.0, 85.5, 86.0]) is None


def test_REQ_CAP_097_a_decline_at_exactly_the_threshold_does_not_fire():
    """"More than 2 percentage points" is strict. A boundary that fires at exactly the threshold
    would make the requirement's number mean something different from what it says."""
    assert weekly_decline([90.0, 88.0, 86.0, 84.0]) is None
    assert weekly_decline([90.0, 87.9, 85.8, 83.7]) is not None
    assert DECLINE_PP_PER_WEEK == 2.0


def test_REQ_CAP_097_too_short_a_history_is_not_an_alert():
    assert weekly_decline([90.0, 80.0, 70.0]) is None


def test_REQ_CAP_097_the_alert_is_addressed_to_the_design_log_not_to_joe():
    """A declining check-in rate is evidence that the asking is wrong, not that Joe is failing.
    Sending it to him would be the nag REQ-CAP-098 forbids, arriving under another name."""
    a = weekly_decline([90.0, 87.0, 84.0, 80.0])
    assert a.audience == "design_log"


def test_REQ_CAP_093_a_prompt_whose_capture_already_arrived_is_suppressed():
    """Asking for something already given is the fastest way to teach someone to ignore the
    asking."""
    plan = prompt_plan(("morning_checkin", "dinner"), captured_today=("morning_checkin",))
    assert plan["send"] == ("dinner",)
    assert plan["suppressed_already_captured"] == ("morning_checkin",)


def test_REQ_CAP_098_falling_coverage_never_adds_prompts():
    """The instinct is exactly backwards: when compliance drops the correct response is to
    shorten the task, not to add reminders — the one intervention participants uniformly found
    aversive."""
    scheduled = ("morning_checkin", "dinner")
    for pct in (95.0, 50.0, 10.0, 0.0):
        plan = prompt_plan(scheduled, coverage_pct=pct)
        assert len(plan["send"]) <= len(scheduled), pct
        assert plan["frequency_change"] == "none"
    assert lint_surface(prompt_plan(scheduled, coverage_pct=0.0)["note"]) == ()


def test_REQ_CAP_098_the_plan_can_only_ever_shrink():
    plan = prompt_plan(("a", "b", "c"), captured_today=("a", "b", "c"), coverage_pct=5.0)
    assert plan["send"] == ()


def test_REQ_CAP_094_F_Q1_the_coverage_components_are_a_parameter_not_a_baked_in_constant():
    """F-Q1 in the spec is open: exactly what counts toward rolling 7-day coverage. Baking it in
    where a later ruling could not reach it would settle Joe's open question by accident."""
    recs = days(**{str(i): (False, 2) for i in range(7)})   # meals logged, no check-ins
    both = coverage(recs, AS_OF)
    meals_only = coverage(recs, AS_OF, components=("eating_occasions",))
    assert both["coverage_pct"] == 0.0
    assert meals_only["coverage_pct"] == 100.0


def test_REQ_CAP_095_the_forbidden_vocabulary_is_declared_not_inferred():
    for term in ("streak", "badge", "chain", "leaderboard", "points"):
        assert term in GAMIFIED


def test_REQ_CAP_095_the_linter_checks_envelopes_not_source_code():
    """REQ-CAP-095 says SHALL NOT *display*, and a comment is not a display. Run over .py and
    .sql this vocabulary produces ~200 false positives — `chain` (a migration chain), `rank` (a
    window function), `points` ("the number points at"), `broke` (a commit message). A linter
    with 200 false positives is a linter somebody deletes."""
    from tools.engines.compliance import lint_envelope
    assert lint_envelope({"coverage_pct": 86.0, "note": "Two of seven days met the bar."}) == []
    # A migration comment mentioning a supersession chain is not a display.
    assert lint_surface("read the chain, not one file") != ()   # the raw vocabulary matches...
    assert lint_envelope({"sql_comment": None}) == []           # ...but no envelope carries it


def test_REQ_CAP_095_a_key_is_a_display_even_when_no_sentence_mentions_it():
    """A key named `streaks` becomes a heading, and a heading is a display."""
    from tools.engines.compliance import lint_envelope
    hits = lint_envelope({"state": {"streaks": [{"metric": "rhr", "run_days": 3}]}})
    assert hits, "a gamified KEY must be caught"
    assert hits[0]["where"] == "key" and hits[0]["path"] == "$.state.streaks"


def test_REQ_CAP_095_gamified_text_nested_in_an_envelope_is_found_with_its_path():
    from tools.engines.compliance import lint_envelope
    hits = lint_envelope({"cards": [{"title": "OK"}, {"title": "Keep it up!"}]})
    assert [h["path"] for h in hits] == ["$.cards[1].title"]
