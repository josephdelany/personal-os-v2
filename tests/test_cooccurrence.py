"""B17 §D.1/D.2 — the link object and its evidence tiers (REQ-FIN-160..180).

Spend can be correlated against sleep, mood, workouts, location, substances and productivity —
hundreds of implicit tests, and REQ-FIN-176 states the consequence plainly: something will always
look significant. Almost every test here is about the system declining to look.
"""
import datetime as dt

import pytest

from tools.engines.cooccurrence import (ALCOHOL_WINDOW_HOURS, Cooccurrence, T1_MIN_N,
                                        T2_MIN_SMALLER_ARM, TIERS, UnregisteredHypothesis,
                                        alcohol_context, assign_tier, compute, link_transaction,
                                        missingness, prompt_once, render)

DAY = dt.date(2026, 9, 4)                      # a Friday
EVENING = dt.datetime(2026, 9, 4, 21, 0)


def co(**kw):
    base = dict(hypothesis_id="H-1", atom_ids=("a1",), subject_day=DAY, tier="T1_DESCRIPTIVE",
                n=12)
    base.update(kw)
    return Cooccurrence(**base)


# ---------------------------------------------------------------- D.2 the tier ladder

def test_REQ_FIN_170_the_tier_set_is_closed():
    assert TIERS == ("T0_OBSERVED", "T1_DESCRIPTIVE", "T2_COOCCURRENT", "T3_CAUSAL")
    with pytest.raises(ValueError, match="REQ-FIN-170"):
        co(tier="T4_PROVEN")


def test_REQ_FIN_174_T3_is_permanently_unreachable():
    """It exists in the vocabulary so the ladder is honest about having a rung above T2, and it
    is welded shut because observational spend data cannot support a causal claim at any n."""
    with pytest.raises(ValueError, match="REQ-FIN-174"):
        co(tier="T3_CAUSAL")
    for n in (1, 10, 100, 10_000):
        tier, _, _ = assign_tier(n=n, smaller_arm_n=n // 2, day_of_week_controlled=True)
        assert tier != "T3_CAUSAL"


def test_REQ_FIN_170_171_a_single_fact_is_T0_and_carries_no_interpretation():
    """One evening is an anecdote. An interpretation on top of n=1 is the whole of the harm this
    ladder exists to prevent."""
    r = render(co(n=1, tier="T0_OBSERVED"), "a bar charge and 6.1 hours of sleep")
    assert r["display"] and r["tier"] == "T0_OBSERVED"
    assert r["interpretation"] is None
    assert r["text"].startswith("On 2026-09-04:")


def test_REQ_FIN_172_a_T1_below_ten_is_not_displayed():
    r = render(co(n=T1_MIN_N - 1), "bar visits on Fridays")
    assert r["display"] is False and "REQ-FIN-172" in r["reason"]
    assert render(co(n=T1_MIN_N), "bar visits on Fridays")["display"] is True


def test_REQ_FIN_173_a_T2_whose_smaller_arm_is_under_twenty_is_not_displayed():
    r = render(co(n=100, smaller_arm_n=T2_MIN_SMALLER_ARM - 1, day_of_week_controlled=True), "x")
    assert r["display"] is False and "REQ-FIN-173" in r["reason"]
    ok = render(co(n=100, smaller_arm_n=T2_MIN_SMALLER_ARM, day_of_week_controlled=True), "x")
    assert ok["display"] is True and ok["tier"] == "T2_COOCCURRENT"


def test_REQ_FIN_177_a_T2_without_day_of_week_controlled_is_refused():
    """Friday is both the high-work day and the social day. Almost every apparent finding in this
    domain is day-of-week wearing a costume."""
    r = render(co(n=200, smaller_arm_n=90, day_of_week_controlled=False), "x")
    assert r["display"] is False
    assert "REQ-FIN-177" in r["reason"] and "Friday" in r["reason"]


def test_REQ_FIN_170_a_failing_T2_is_not_silently_demoted_to_T1():
    """T1 and T2 answer different questions; presenting an underpowered rate difference as a
    count would answer a question nobody asked."""
    tier, ok, _ = assign_tier(n=200, smaller_arm_n=5, day_of_week_controlled=True)
    assert tier == "T2_COOCCURRENT" and ok is False


def test_REQ_FIN_178_the_n_is_in_the_same_sentence_as_the_claim():
    """A claim whose n sits in a tooltip is a claim most readers will meet without its n."""
    r = render(co(n=41), "bar visits fell after 22:00")
    assert "(n=41)" in r["text"]
    assert r["text"].index("n=41") > r["text"].index("bar visits")


def test_REQ_FIN_179_excluded_cash_is_stated_not_merely_done():
    """An excluded denominator nobody is told about is a rate that cannot be checked."""
    r = render(co(n=40, excluded_cash_n=7), "bar visits")
    assert "Excludes 7 cash or ATM transaction(s)" in r["text"]
    assert "not random missingness" in r["text"]


def test_REQ_FIN_163_a_date_only_link_says_so_in_the_rendered_text():
    assert "no within-day claim" in render(co(n=20, date_only=True), "x")["text"]


# ---------------------------------------------------------------- D.2 registration

def test_REQ_FIN_175_a_cooccurrence_cannot_exist_without_a_hypothesis_key():
    with pytest.raises(UnregisteredHypothesis, match="REQ-FIN-175"):
        co(hypothesis_id="")


def test_REQ_FIN_176_an_unregistered_pairing_aborts_and_is_logged():
    """The abort is deliberate rather than a skip. A pairing silently not computed leaves no
    trace, so a job quietly fishing across every lens looks identical to a job doing nothing."""
    log = []
    with pytest.raises(UnregisteredHypothesis, match="REQ-FIN-176"):
        compute(hypothesis_id="H-9", registered_hypotheses=["H-1"], atom_ids=("a",),
                subject_day=DAY, n=50, attempted_pairing="spend~sleep", log=log)
    assert log and log[0]["event"] == "unregistered_pairing_aborted"
    assert log[0]["pairing"] == "spend~sleep"
    assert "something will always look significant" in log[0]["reason"]


def test_REQ_FIN_175_a_registered_hypothesis_computes_normally():
    c = compute(hypothesis_id="H-1", registered_hypotheses=["H-1"], atom_ids=("a", "b"),
                subject_day=DAY, n=30)
    assert c.tier == "T1_DESCRIPTIVE" and c.hypothesis_id == "H-1"


# ---------------------------------------------------------------- D.1 building the links

def test_REQ_FIN_162_the_join_is_on_occurred_at_never_on_posted_at():
    """Settlement is commonly the following day. Joining on it would attribute a Thursday night
    to Friday — silently moving every late-week evening into the weekend and manufacturing the
    weekend pattern the analysis was looking for."""
    txn = {"category": "bar", "occurred_at": EVENING, "subject_day": DAY,
           "posted_at": dt.datetime(2026, 9, 5, 9, 0)}
    drink = {"occurred_at": dt.datetime(2026, 9, 4, 21, 30), "props": {"class": "alcohol"}}
    link = link_transaction(txn, consume_atoms=[drink])
    assert link["alcohol_atoms"] == (drink,)
    assert link["subject_day"] == DAY, "the Thursday-into-Friday slide must not happen"


def test_REQ_FIN_161_the_alcohol_window_is_three_hours_either_side():
    txn = {"category": "bar", "occurred_at": EVENING, "subject_day": DAY}
    inside = {"occurred_at": EVENING - dt.timedelta(hours=ALCOHOL_WINDOW_HOURS),
              "props": {"class": "alcohol"}}
    outside = {"occurred_at": EVENING + dt.timedelta(hours=ALCOHOL_WINDOW_HOURS, minutes=1),
               "props": {"class": "alcohol"}}
    link = link_transaction(txn, consume_atoms=[inside, outside])
    assert link["alcohol_atoms"] == (inside,)


def test_REQ_FIN_161_a_non_alcohol_consume_atom_does_not_count():
    txn = {"category": "bar", "occurred_at": EVENING, "subject_day": DAY}
    food = {"occurred_at": EVENING, "props": {"class": "food"}}
    assert link_transaction(txn, consume_atoms=[food])["alcohol_atoms"] == ()


def test_REQ_FIN_161_mood_is_matched_on_the_subject_day_and_place_on_the_interval():
    txn = {"category": "restaurant", "occurred_at": EVENING, "subject_day": DAY}
    mood = {"subject_day": DAY, "value": 6}
    other = {"subject_day": dt.date(2026, 9, 3), "value": 3}
    place = {"starts_at": EVENING - dt.timedelta(hours=1),
             "ends_at": EVENING + dt.timedelta(hours=1)}
    link = link_transaction(txn, mood_atoms=[mood, other], place_atoms=[place])
    assert link["mood_atoms"] == (mood,)
    assert link["place_atoms"] == (place,)


def test_REQ_FIN_163_a_date_only_import_is_barred_from_within_day_analysis():
    """The charge did happen, so the link is kept as a same-day fact rather than dropped — but a
    CSV row with no clock cannot support a plus-or-minus-three-hour window."""
    txn = {"category": "bar", "occurred_at": DAY, "subject_day": DAY, "date_only": True}
    drink = {"occurred_at": EVENING, "props": {"class": "alcohol"}}
    link = link_transaction(txn, consume_atoms=[drink])
    assert link["date_only"] is True
    assert link["eligible_for_within_day"] is False
    assert link["alcohol_atoms"] == ()
    assert link["implied_unlogged"] is False, "absence of a window is not evidence of absence"


def test_REQ_FIN_160_only_bar_and_restaurant_transactions_are_linked():
    for category in ("groceries", "fuel", "utilities"):
        assert link_transaction({"category": category, "occurred_at": EVENING}) is None


def test_REQ_FIN_164_the_prompt_is_offered_once_and_never_repeated():
    txn = {"category": "bar", "occurred_at": EVENING, "subject_day": DAY}
    link = link_transaction(txn)
    p = prompt_once(link, already_prompted_days=[])
    assert p and p["dismissible"] is True and p["repeat"] is False
    assert prompt_once(link, already_prompted_days=[DAY]) is None


def test_REQ_FIN_165_missingness_is_counted_whether_or_not_joe_ever_answers():
    """If the count only existed when he replied, the days he ignored the prompt — the busiest
    ones, the ones most likely to involve a bar — would look like days with no drinking."""
    drink = {"occurred_at": EVENING, "props": {"class": "alcohol"}}
    logged = link_transaction({"category": "bar", "occurred_at": EVENING, "subject_day": DAY},
                              consume_atoms=[drink])
    unlogged = link_transaction({"category": "bar", "occurred_at": EVENING,
                                 "subject_day": dt.date(2026, 9, 11)})
    m = missingness([logged, unlogged])
    assert m["occasions"] == 2 and m["implied_unlogged"] == 1 and m["logged"] == 1
    assert m["unlogged_fraction"] == 0.5
    assert "ignored the prompt" in m["note"]


def test_REQ_FIN_166_180_occasions_are_primary_and_the_amount_is_netted():
    """A $120 tab three people split is one occasion and $40 of Joe's money. Reporting the $120
    as the alcohol metric would make a normal evening look like a heavy one."""
    link = link_transaction({"category": "bar", "occurred_at": EVENING, "subject_day": DAY})
    out = alcohol_context([link], amounts=[120.0], inbound_transfers=[40.0, 40.0])
    assert out["primary_metric"] == "occasions"
    assert out["occasions"] == 1
    assert out["secondary_amount_net"] == 40.0
    assert out["netted_inbound"] == 80.0
    assert "robust to price variance" in out["note"]
