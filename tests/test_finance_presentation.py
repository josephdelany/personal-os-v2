"""B17 §E — presentation restraint (REQ-FIN-210..228).

Pure, so exercised exhaustively. This section encodes measured harm: precise, frequent budget
feedback caused ~$40 (n=283, p=.002) and $32 (n=363) of overspending, and a range attenuated it
(n=198). Almost every test asserts the system refuses a feature that looks like good product
design.
"""
import datetime as dt

import pytest

from tools.engines.narration import MORALISING
from tools.engines.finance_presentation import (BANNED_WORDS, FINANCE_ONLY,
                                                MAX_NOTIFICATIONS_PER_MONTH,
                                                MIN_RANGE_WIDTH_FRACTION, STALE_IMPORT_DAYS,
                                                Violation, banned_words, check_alcohol_surface,
                                                check_cadence, check_copy,
                                                check_forward_amount, check_surface,
                                                copy_violation_rows, quantity_adjectives)


def codes(violations):
    return sorted({v.requirement for v in violations})


def test_REQ_FIN_218_the_banlist_extends_the_reasoning_layer_rather_than_copying_it():
    """Two copies of a banned-word list drift, and the drift is invisible until a word ships on
    one surface and not the other — which is exactly what the requirement's own 2026-08-24 note
    records happening with 'necessary'."""
    assert set(MORALISING) < set(BANNED_WORDS), "the finance list is a superset"
    assert set(FINANCE_ONLY) == {"overspent", "bad", "should have"}
    for w in ("excessive", "wasteful", "necessary", "unnecessary", "too much", "splurge",
              "guilty", "overspent", "bad", "should have"):
        assert w in BANNED_WORDS, w


def test_REQ_FIN_218_moralising_copy_is_caught():
    assert banned_words("You overspent on dining") == ("overspent",)
    # Compared as a set: the order follows the banlist, not the alphabet, and which order is
    # not part of the contract.
    assert set(banned_words("That was an unnecessary splurge")) == {"splurge", "unnecessary"}
    # "necessary" sits inside "unnecessary"; whole-word matching must report one token, not two.
    assert banned_words("unnecessary") == ("unnecessary",)


def test_REQ_FIN_218_whole_word_matching_so_ordinary_copy_survives():
    """A false positive gets a check switched off, and a switched-off check catches nothing."""
    for fine in ("Badly lit photo", "A badge appeared", "Necessarily approximate",
                 "Guiltless is not a word this system uses either"):
        assert banned_words(fine) == (), fine


def test_REQ_FIN_219_publication_is_blocked_and_a_row_cites_the_token():
    """Blocking rather than redacting is deliberate: silently deleting the word ships a sentence
    nobody wrote, and the sentence is still built on the judgement the word expressed."""
    r = copy_violation_rows("You overspent again", surface="review.body", question_id="q1")
    assert r["publish"] is False
    assert len(r["rows"]) == 1
    assert "overspent" in r["rows"][0]["token"]
    assert r["rows"][0]["rule"] == "REQ-FIN-218"
    assert r["rows"][0]["surface"] == "review.body"
    assert copy_violation_rows("Dining: $412 across 19 charges.")["publish"] is True


def test_REQ_FIN_220_a_quantity_adjective_is_a_verdict_wearing_a_measurement_s_clothes():
    """"A lot" is not a quantity; it is an opinion about one."""
    assert quantity_adjectives("You spent a lot at restaurants") == ("a lot",)
    assert "REQ-FIN-220" in codes(check_copy("A significant amount went to bars"))
    assert check_copy("$412 across 19 charges at 6 merchants") == ()


def test_REQ_FIN_210_a_running_remaining_counter_is_refused():
    """The single identified feature in this system with measured evidence of causing harm.
    Certainty removes the safety margin: told exactly how much room is left, people spend into
    it."""
    v = check_surface({"name": "dash", "remaining_in_period": 312.0})
    assert "REQ-FIN-210" in codes(v)
    assert "measured evidence" in str(v[0])
    assert "REQ-FIN-210" in codes(check_surface({"name": "d", "running_total": True}))


def test_REQ_FIN_211_nothing_may_update_more_than_once_a_day():
    """Frequency is half the mechanism; a figure refreshing hourly is a live counter whatever it
    is called."""
    assert "REQ-FIN-211" in codes(check_surface({"name": "d", "update_interval_hours": 1}))
    assert "REQ-FIN-211" not in codes(check_surface({"name": "d", "update_interval_hours": 24}))


def test_REQ_FIN_212_a_forward_point_estimate_is_refused():
    """The most tempting single number in the system, and the one the evidence most directly
    implicates."""
    assert check_forward_amount(312)[0].requirement == "REQ-FIN-212"
    assert check_forward_amount([250, 350]) == ()


def test_REQ_FIN_212_a_range_too_tight_is_a_point_estimate_with_a_hyphen_in_it():
    """The width floor exists so a range cannot be made technically compliant and practically
    precise."""
    assert check_forward_amount([311, 313])[0].requirement == "REQ-FIN-212"
    assert "point estimate with a hyphen" in check_forward_amount([311, 313])[0].detail
    assert MIN_RANGE_WIDTH_FRACTION == 0.20
    assert check_forward_amount([270, 330]) == (), "exactly 20% of a 300 midpoint clears it"


def test_REQ_FIN_212_an_inverted_range_is_refused_rather_than_silently_sorted():
    assert check_forward_amount([350, 250])[0].requirement == "REQ-FIN-212"


def test_REQ_FIN_212_forward_amounts_are_checked_wherever_they_appear_on_a_surface():
    v = check_surface({"name": "review", "forward_amounts": {"next_month": 900}})
    assert "REQ-FIN-212" in codes(v)
    assert "next_month" in str(v[0])


def test_REQ_FIN_215_216_a_pie_chart_is_a_share_of_total_and_both_are_refused():
    """Banning the words and allowing the shape would be theatre."""
    for chart in ("pie", "donut", "doughnut", "treemap", "sunburst", "stacked_percent"):
        assert "REQ-FIN-215" in codes(check_surface({"name": "s", "chart": chart})), chart
    assert "REQ-FIN-216" in codes(
        check_surface({"name": "s", "concentration_as_share_of_total": True}))
    assert check_surface({"name": "s", "chart": "ranked_bar"}) == ()


def test_REQ_FIN_217_a_retrospective_figure_needs_the_preceding_period_beside_it():
    """A figure with nothing to compare it to invites the reader to supply the comparison, and
    the one they supply is usually a judgement."""
    assert "REQ-FIN-217" in codes(check_surface({"name": "s", "retrospective_amount": 412.0}))
    assert check_surface({"name": "s", "retrospective_amount": 412.0,
                          "preceding_period_amount": 388.0}) == ()


def test_REQ_FIN_221_an_insight_without_a_not_useful_control_is_refused():
    """Without it, an unwanted insight can only be endured."""
    assert "REQ-FIN-221" in codes(check_surface({"name": "s", "is_insight": True}))
    assert check_surface({"name": "s", "is_insight": True, "not_useful_control": True}) == ()


def test_REQ_FIN_225_a_dead_account_must_be_named_and_no_total_called_complete():
    """Directly relevant: the bank CSV export died 2026-05-13 and a successor began 38 days
    later carrying a seventh of the value. A total spanning that is arithmetically correct and
    materially incomplete."""
    v = check_surface({"name": "s", "account_import_age_days": {"bank_csv": 120}})
    assert "REQ-FIN-225" in codes(v)
    assert "bank_csv" in str(v[0]) and "120 days" in str(v[0])
    assert check_surface({"name": "s", "account_import_age_days": {"bank_csv": 120},
                          "coverage_warning": "bank_csv has not imported since 2026-05-13"}) == ()
    assert STALE_IMPORT_DAYS == 35
    assert check_surface({"name": "s", "account_import_age_days": {"bank_csv": 35}}) == ()


def test_REQ_FIN_224_cash_and_split_tabs_must_be_labelled_in_the_same_view():
    for flag in ("has_atm_withdrawals", "has_split_tabs"):
        assert "REQ-FIN-224" in codes(check_surface({"name": "s", flag: True})), flag
    assert check_surface({"name": "s", "has_atm_withdrawals": True,
                          "limitation_labels": ["destination unknown"]}) == ()


def test_REQ_FIN_213_two_reviews_inside_seven_days_are_refused():
    """The cheap architecture is the behaviourally correct one; these limits stop a future
    surface undoing that by accident."""
    d = dt.date(2026, 9, 1)
    v = check_cadence([d, d + dt.timedelta(days=3)], [])
    assert "REQ-FIN-213" in codes(v) and "3 days apart" in str(v[0])
    assert check_cadence([d, d + dt.timedelta(days=7)], []) == ()


def test_REQ_FIN_226_at_most_four_notifications_a_month():
    d = dt.date(2026, 9, 1)
    five = [d + dt.timedelta(days=i * 5) for i in range(5)]
    assert "REQ-FIN-226" in codes(check_cadence([], five))
    assert check_cadence([], five[:4]) == ()
    assert MAX_NOTIFICATIONS_PER_MONTH == 4


def test_REQ_FIN_227_an_alcohol_surface_speaks_in_occasions_not_volume_or_cost():
    for field in ("total_volume_ml", "total_units", "total_spend"):
        v = check_alcohol_surface({"name": "alc", field: 1400})
        assert "REQ-FIN-227" in codes(v), field
    assert check_alcohol_surface({"name": "alc", "occasions": 6}) == ()


def test_REQ_FIN_228_coping_behaviour_is_not_described_as_a_malfunction():
    """Contradicted by the published finding, not merely unkind: making purchase decisions
    restores a sense of personal control and measurably reduces residual sadness."""
    v = check_alcohol_surface({"name": "alc", "body": "This looks like a bad habit"})
    assert "REQ-FIN-228" in codes(v)
    assert "restore" in str([x for x in v if x.requirement == "REQ-FIN-228"][0]).lower()
    assert check_alcohol_surface(
        {"name": "alc", "body": "Six occasions, five of them on Fridays."}) == ()


def test_a_compliant_review_surface_produces_no_violations_at_all():
    """The rules must leave a real surface buildable. A policy nothing can satisfy gets
    disabled, and this one has to survive contact with an actual review page."""
    assert check_surface({
        "name": "monthly_review",
        "title": "September, compared with August",
        "body": "Dining: $412 across 19 charges at 6 merchants. August: $388 across 17.",
        "chart": "ranked_bar",
        "retrospective_amount": 412.0,
        "preceding_period_amount": 388.0,
        "update_interval_hours": 720,
        "forward_amounts": {"october_range": [330, 470]},
        "is_insight": True, "not_useful_control": True,
        "account_import_age_days": {"chase_email": 3},
        "has_atm_withdrawals": True,
        "limitation_labels": ["ATM withdrawals: destination unknown"],
    }) == ()
