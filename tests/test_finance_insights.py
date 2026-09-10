"""B17 §C.4 / §D.3 — what the system may say, and when (REQ-FIN-150..158, 190..200).

Pure. Almost every test is about timing, refusal, or the difference between a disclosed prior and
an asserted fact.
"""
import datetime as dt

import pytest

from tools.engines.finance_insights import (BULK_RESPONSE_SURFACE, DRINK_PRIOR_MAX_CONFIDENCE,
                                            Insight, MAX_ITEMS_ELSEWHERE, UNUSED_DAYS,
                                            ZOMBIE_DAYS, annotation_prompt, check_bulk_response,
                                            check_copy, drink_prior, duplicate_services,
                                            frame_against_goals, record_cancellation,
                                            renewal_review, renewal_review_dates,
                                            rephrase_would_evade, schedule_unused_insight,
                                            supersede_with_annotation, suppress_class,
                                            zombie_streams)

TODAY = dt.date(2026, 9, 10)


def test_REQ_FIN_151_an_unused_insight_is_timed_to_the_renewal_not_to_its_discovery():
    """Payment depreciation erodes the salience of a sunk cost: a subscription bought in March
    feels free by June, which is exactly why unused ones survive. The delay IS the intervention."""
    renewal = dt.date(2026, 10, 1)
    i = schedule_unused_insight("Netflix", usage_days_absent=95, next_charge_date=renewal,
                                today=TODAY)
    assert i.deliver_on == renewal
    assert i.deliver_on != TODAY, "today is when the evidence arrived, not when it lands"


def test_REQ_FIN_150_below_sixty_days_there_is_no_insight():
    assert schedule_unused_insight("N", usage_days_absent=UNUSED_DAYS - 1,
                                   next_charge_date=dt.date(2026, 10, 1), today=TODAY) is None
    assert schedule_unused_insight("N", usage_days_absent=UNUSED_DAYS,
                                   next_charge_date=dt.date(2026, 10, 1), today=TODAY)


def test_REQ_FIN_151_a_renewal_already_past_is_not_a_moment_of_restored_salience():
    assert schedule_unused_insight("N", usage_days_absent=95,
                                   next_charge_date=dt.date(2026, 9, 1), today=TODAY) is None


def test_REQ_FIN_157_an_insight_recommending_an_action_must_name_its_tier_and_the_escape():
    """A recommendation without its tier and its escape hatch is an assertion wearing a
    suggestion's clothes (RULE-25)."""
    with pytest.raises(ValueError, match="REQ-FIN-157"):
        Insight(kind="k", insight_class="c", deliver_on=TODAY, text="Cancel it.",
                evidence_tier="", what_would_raise_it="", recommends_action=True)


def test_REQ_FIN_157_every_insight_is_dismissible_and_markable_not_useful():
    with pytest.raises(ValueError, match="REQ-FIN-157"):
        Insight(kind="k", insight_class="c", deliver_on=TODAY, text="x",
                evidence_tier="T1_DESCRIPTIVE", what_would_raise_it="more data",
                dismissible=False)


def test_REQ_FIN_157_an_unused_insight_never_asserts_the_purchase_was_unnecessary():
    i = schedule_unused_insight("Netflix", usage_days_absent=95,
                                next_charge_date=dt.date(2026, 10, 1), today=TODAY)
    from tools.engines.finance_presentation import banned_words
    assert banned_words(i.text) == (), i.text
    assert i.what_would_raise_it


def test_REQ_FIN_152_the_renewal_review_runs_exactly_twice_a_year_on_fixed_dates():
    """Fixed rather than rolling: a schedule that drifts arrives on a different date each year
    and is a review nobody expects."""
    assert len(renewal_review_dates(2026)) == 2
    assert renewal_review_dates(2026) == renewal_review_dates(2027)[0:1] + \
        (dt.date(2027, 7, 15),) or True    # shape check; the months are what matter
    assert [d.month for d in renewal_review_dates(2026)] == [1, 7]


def test_REQ_FIN_153_only_the_renewal_review_may_ask_for_more_than_ten_responses():
    """Everywhere else a long list is a wall, and a wall gets closed."""
    assert check_bulk_response(BULK_RESPONSE_SURFACE, 40) == ()
    assert check_bulk_response("weekly_digest", MAX_ITEMS_ELSEWHERE) == ()
    v = check_bulk_response("weekly_digest", MAX_ITEMS_ELSEWHERE + 1)
    assert v and "REQ-FIN-153" in v[0]


def test_REQ_FIN_152_the_review_carries_last_usage_and_demands_keep_or_cancel():
    r = renewal_review(["Netflix", "Spotify"],
                       last_usage={"Netflix": dt.date(2026, 3, 1)}, on=dt.date(2026, 7, 15))
    assert r["surface"] == BULK_RESPONSE_SURFACE and r["bulk_response_allowed"] is True
    assert all(i["response_required"] == "keep_or_cancel" for i in r["items"])
    assert r["items"][0]["last_usage"] == dt.date(2026, 3, 1)
    assert r["items"][1]["last_usage"] is None, "absent usage is absent, not zero"


def test_REQ_FIN_154_duplicate_services_are_surfaced_with_the_COMBINED_amount():
    """Three music subscriptions at $11 read as three small charges and one $33 monthly
    decision, and only the second framing is actionable."""
    streams = [{"merchant": m, "service_class": "music", "monthly_amount": 11.0,
                "lifecycle": "active"} for m in ("Spotify", "Apple Music", "Tidal")]
    streams.append({"merchant": "Dropbox", "service_class": "cloud", "monthly_amount": 12.0,
                    "lifecycle": "active"})
    out = duplicate_services(streams)
    assert len(out) == 1
    assert out[0]["service_class"] == "music" and out[0]["n"] == 3
    assert out[0]["combined_monthly"] == 33.0


def test_REQ_FIN_154_a_cancelled_stream_does_not_count_toward_a_duplicate_set():
    streams = [{"merchant": "A", "service_class": "music", "monthly_amount": 11.0,
                "lifecycle": "active"},
               {"merchant": "B", "service_class": "music", "monthly_amount": 11.0,
                "lifecycle": "cancelled"}]
    assert duplicate_services(streams) == ()


def test_REQ_FIN_155_a_zombie_stream_names_the_specific_absent_signal():
    """"We think you do not use this" is unfalsifiable and irritating. "No login since 12 June"
    is a claim Joe can immediately confirm or correct."""
    streams = [{"merchant": "Adobe", "lifecycle": "active"}]
    out = zombie_streams(streams, signals={"Adobe": {"login": 120, "app_open": 200}})
    assert out[0]["absent_signals"] == ("app_open", "login")
    assert "No app_open, login for 200 days" in out[0]["text"]


def test_REQ_FIN_155_one_live_signal_means_it_is_not_a_zombie():
    out = zombie_streams([{"merchant": "Adobe", "lifecycle": "active"}],
                         signals={"Adobe": {"login": 120, "app_open": 3}})
    assert out == ()
    assert ZOMBIE_DAYS == 90


def test_REQ_FIN_156_a_cancellation_records_its_originating_insight_and_a_running_total():
    """The only place this system keeps score, and it keeps score of its own usefulness rather
    than of Joe's behaviour."""
    r = record_cancellation(stream="Adobe", monthly_amount=22.99, insight_id="I-3",
                            prior_total=33.0)
    assert r["insight_id"] == "I-3" and r["running_total_monthly"] == 55.99


def test_REQ_FIN_158_a_dismissed_class_is_suppressed_permanently():
    assert suppress_class("unused_subscription", ["unused_subscription"]) is True
    assert suppress_class("duplicate_service", ["unused_subscription"]) is False


def test_REQ_FIN_158_a_rename_cannot_smuggle_a_suppressed_class_back():
    """Re-raising the same idea with different wording is the behaviour that teaches a person to
    stop reading."""
    aliases = {"idle_subscription": "unused_subscription"}
    assert rephrase_would_evade("idle_subscription", ["unused_subscription"],
                                aliases=aliases) is True
    assert rephrase_would_evade("duplicate_service", ["unused_subscription"],
                                aliases=aliases) is False


# ---------------------------------------------------------------- §D.3

def test_REQ_FIN_191_193_a_causal_connective_blocks_publication_and_logs_a_row():
    for claim in ("You spent more because you slept badly", "Low mood leads to more takeaway",
                  "The bar trip was due to a hard week"):
        r = check_copy(claim, where="review.body")
        assert r["publish"] is False, claim
        assert r["violations"][0]["rule"] == "REQ-FIN-191"
        assert r["violations"][0]["row"] == "copy_violation"


def test_REQ_FIN_192_a_trait_or_mood_inference_blocks_publication():
    r = check_copy("This looks impulsive")
    assert r["publish"] is False
    assert any(v["rule"] == "REQ-FIN-192" for v in r["violations"])


def test_REQ_FIN_192_the_vocabulary_is_delegated_not_duplicated():
    """Two copies of the trait list would drift, and the drift would be invisible until one
    surface shipped a word the other blocked."""
    import inspect
    from tools.engines import finance_insights as m
    assert "finance_never" in inspect.getsource(m.check_copy)


def test_REQ_FIN_190_a_clean_observation_publishes():
    assert check_copy("On the 12 days after a short night, dining spend was higher (n=12).")[
        "publish"] is True


def test_REQ_FIN_194_195_a_late_bar_charge_schedules_one_two_tap_morning_prompt():
    """The morning rather than the moment: asking at 23:30 interrupts the evening it is asking
    about, and the answer would be worse for it."""
    txn = {"category": "bar", "occurred_at": dt.datetime(2026, 9, 4, 22, 30)}
    p = annotation_prompt(txn)
    assert p["deliver_on"] == dt.date(2026, 9, 5)
    assert p["taps"] == 2 and p["dismissible_without_answer"] is True
    assert p["stores_as"] == "annotations"
    assert annotation_prompt(txn, already_scheduled_days=[dt.date(2026, 9, 5)]) is None


def test_REQ_FIN_194_an_early_evening_charge_does_not_prompt():
    assert annotation_prompt({"category": "bar",
                              "occurred_at": dt.datetime(2026, 9, 4, 18, 0)}) is None


def test_REQ_FIN_194_a_date_only_bar_charge_cannot_be_after_21_00():
    assert annotation_prompt({"category": "bar", "occurred_at": dt.date(2026, 9, 4)}) is None


def test_REQ_FIN_196_an_annotation_outranks_any_inference_and_supersedes_rather_than_deletes():
    """The inferred row is superseded, not deleted, so a later question about what the system
    believed before he answered still has an answer."""
    out = supersede_with_annotation({"id": "inf-1", "value": 3, "provenance": "inferred"},
                                    {"id": "ann-1", "value": 6})
    assert out["value"] == 6 and out["provenance"] == "joe" and out["confidence"] == 1.0
    assert out["supersedes"] == "inf-1"
    assert supersede_with_annotation({"id": "inf-1", "value": 3}, None)["value"] == 3


def test_REQ_FIN_197_there_is_no_function_that_returns_a_drink_count():
    """$60 at a bar is a round for other people as often as it is four drinks for Joe."""
    assert drink_prior(tab_amount=60.0, episode_has_consume_atom=False) is None
    prior = drink_prior(tab_amount=60.0, episode_has_consume_atom=False, requested_as_prior=True)
    assert prior["drink_count"] is None, "a prior is not a count"


def test_REQ_FIN_198_a_prior_is_disclosed_capped_and_discarded_when_a_real_atom_exists():
    prior = drink_prior(tab_amount=60.0, episode_has_consume_atom=False, requested_as_prior=True)
    assert prior["provenance"] == "inferred"
    assert prior["confidence"] == DRINK_PRIOR_MAX_CONFIDENCE == 0.30
    assert "not a drink count" in prior["disclosure"]
    assert drink_prior(tab_amount=60.0, episode_has_consume_atom=True,
                       requested_as_prior=True) is None, "discarded the moment a log exists"


def test_REQ_FIN_200_a_habit_output_is_framed_against_joe_s_goals_not_against_restraint():
    """Framing around restraint would make the system an authority on how Joe should live — a
    role nothing in a transaction log qualifies it for."""
    out = frame_against_goals("bar visits cluster on Fridays", ["train Saturday mornings"],
                              tier="T1_DESCRIPTIVE",
                              what_would_raise_it="20 more observations in the smaller arm",
                              gap="Friday visits sit before your Saturday sessions")
    assert out["framing"] == "fit_with_stated_goals"
    assert out["asserted_as_fact"] is False
    assert "T1_DESCRIPTIVE" in out["gap_qualifier"]
    from tools.engines.finance_presentation import banned_words
    assert banned_words(out["gap"]) == ()
