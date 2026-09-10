"""The remaining surface contracts: ask, act, sleep, reconstruction, tier attachment.

Five small contracts, each closing out a prefix.
"""
import datetime as dt

import pytest

from tools.engines.surface_contract import (CAUSAL_VOCAB, EVENT_FAMILIES_REQUIRED,
                                            MEDICAL_REFERRAL, RECOVERY_MEASURES,
                                            SurfaceViolation, acceptance_report,
                                            confirmed_payload, daily_instruction,
                                            distinguishing_evidence, effect_statement,
                                            in_scope, informative_missingness_cap,
                                            inferred_input, interval_statement, lapsed_measure,
                                            medical_guard, no_adjustment_set,
                                            pattern_recommendation, plan_then_answer,
                                            recovery_coverage, sleep_relation, standing_order)

AS_OF = dt.date(2026, 9, 10)


# ---------------------------------------------------------------- ask

def test_REQ_ASK_001_the_language_layer_plans_and_does_not_answer_in_the_same_step():
    """A model that plans and answers in one breath has already decided the answer before the
    numbers arrive, and the plan becomes a justification written after the fact."""
    out = plan_then_answer("how is my sleep",
                           planner=lambda q: {"op": "describe", "metric": "sleep_minutes"},
                           executor=lambda p: {"value": 444})
    assert out["plan"]["op"] == "describe" and out["result"]["value"] == 444
    with pytest.raises(SurfaceViolation, match="REQ-ASK-001"):
        plan_then_answer("q", planner=lambda q: {"op": "describe", "answer": "7.4 hours"},
                         executor=lambda p: {})


def test_REQ_ASK_024_no_adjustment_set_means_unanswerable_from_observation():
    """The DAG says which confounders must be held fixed. If they cannot be, the estimate is of
    something other than the effect asked about."""
    out = no_adjustment_set("does caffeine cause poor sleep", dag_has_minimal_set=False)
    assert out["insufficiency_reason"] == "no_adjustment_set"
    assert "cannot be answered from observation" in out["text"]
    assert "randomized trial" in out["what_would_answer_it"]
    assert no_adjustment_set("q", dag_has_minimal_set=True) is None


def test_REQ_ASK_026_informative_missingness_caps_the_answer_at_INSUFFICIENT():
    """If a metric is missing BECAUSE of the thing being asked about — Joe does not log dinner on
    the nights he drinks — the observed rows are a biased sample of exactly the question."""
    out = informative_missingness_cap({"tier": "PROMOTED", "value": 4},
                                      flags={"dinner_kcal": True, "steps": False})
    assert out["tier"] == "INSUFFICIENT"
    assert out["informative_missingness"] == ("dinner_kcal",)
    assert "would not fix this" in out["disclosure"]
    assert informative_missingness_cap({"tier": "PROMOTED"}, flags={"steps": False})["tier"] == \
        "PROMOTED"


def test_REQ_ASK_029_performance_and_subjective_state_are_IN_scope():
    """The medical boundary is easy to over-apply: "why do I feel flat on Thursdays" is a
    question about logged behaviour, and refusing it would make the system useless for the thing
    it is actually for."""
    for kind in ("performance", "subjective_state", "behaviour"):
        assert in_scope(kind)["in_scope"] is True
    assert in_scope("diagnosis")["in_scope"] is False


# ---------------------------------------------------------------- act

def test_REQ_ACT_004_a_standing_order_comes_only_from_a_rule_JOE_registered():
    """A rule the system invented is advice wearing a standing order's clothes."""
    rule = {"id": "so-1", "condition_fields": ["sleep_minutes"], "text": "protect Sunday"}
    out = standing_order(rule, registered_rules={"so-1"}, stored_numbers={"sleep_minutes": 400})
    assert out["tier"] == "DESCRIPTIVE" and out["phrase_present"] == "your standing order"
    assert out["numbers"] == {"sleep_minutes": 400}
    with pytest.raises(SurfaceViolation, match="REQ-ACT-004"):
        standing_order(rule, registered_rules=set(), stored_numbers={"sleep_minutes": 400})


def test_REQ_ACT_004_the_condition_is_evaluated_against_STORED_numbers():
    """A condition evaluated against freshly computed numbers is a rule that can fire on
    arithmetic nobody stored."""
    rule = {"id": "so-1", "condition_fields": ["sleep_minutes"], "text": "x"}
    with pytest.raises(SurfaceViolation, match="REQ-ACT-004"):
        standing_order(rule, registered_rules={"so-1"}, stored_numbers={})


def test_REQ_ACT_007_an_effect_names_its_unit_and_states_the_counter_frame():
    """"22 minutes more sleep" and "22 minutes less of the evening" are the same number. A
    recommendation that gives only the flattering reading is an argument, not a measurement."""
    out = effect_statement(22, "minutes", counter_frame="22 minutes less of the evening")
    assert out["text"] == "22 minutes" and out["counter_frame"]
    with pytest.raises(SurfaceViolation, match="REQ-ACT-007"):
        effect_statement(22, "minutes", counter_frame=None)
    with pytest.raises(SurfaceViolation, match="REQ-ACT-007"):
        effect_statement(22, None, counter_frame="x")


def test_REQ_ACT_008_at_most_one_instruction_a_day_pulled_and_never_pushed():
    """Two recommendations compete, and the one Joe acts on is whichever is easier rather than
    whichever matters. Pulled because a pushed instruction arrives when the SYSTEM is ready."""
    cands = [{"id": "a", "rank_score": 0.2}, {"id": "b", "rank_score": 0.9}]
    out = daily_instruction(cands, already_surfaced_today=False)
    assert out["surface"]["id"] == "b"
    assert out["pushed"] is False and out["pulled"] is True and out["read_only"] is True
    assert out["counts_against_prompt_limit"] is False
    assert daily_instruction(cands, already_surfaced_today=True)["surface"] is None


def test_REQ_ACT_010_a_pattern_recommendation_carries_exactly_one_prediction_atomically():
    out = pattern_recommendation({"text": "x"}, {"prediction_id": "P-1"})
    assert out["atomic"] is True and len(out["predictions"]) == 1
    with pytest.raises(SurfaceViolation, match="REQ-ACT-010"):
        pattern_recommendation({"text": "x"}, None)


# ---------------------------------------------------------------- sleep and recovery

def test_REQ_SLP_020_four_recovery_measures_stay_separate_with_their_own_coverage():
    """They have different capture rates and different failure modes — the Watch stopped
    recording some before others. A score built from one live measure and three dead ones looks
    identical to one built from four."""
    out = recovery_coverage({"hrv_sdnn_ms": 0.1, "resting_hr": 0.9})
    assert set(out["measures"]) == set(RECOVERY_MEASURES)
    assert out["combined_score"] is None
    assert out["measures"]["respiratory_rate"] is None


def test_REQ_SLP_021_a_lapsed_measure_reports_the_lapse_not_the_last_value_as_current():
    """An HRV from 2026-08-21 rendered without its date reads as today's HRV, and the reader has
    no way to know the Watch stopped."""
    out = lapsed_measure("hrv_sdnn_ms", last_observation=dt.date(2026, 8, 21), as_of=AS_OF)
    assert out["lapsed"] is True and out["days_since"] == 20
    assert out["value_shown_as_current"] is False
    assert "2026-08-21" in out["text"]


def test_REQ_SLP_022_a_medical_question_returns_the_STORED_referral_string():
    """Stored because a generated refusal is a generated sentence about a medical topic, which is
    the thing being refused."""
    out = medical_guard("Your low HRV suggests you should see a cardiologist",
                        would_advise_on_condition=True)
    assert out["text"] == MEDICAL_REFERRAL and out["generated"] is False
    assert out["original_withheld"] is True
    assert medical_guard("Your HRV averaged 41 ms.",
                         would_advise_on_condition=False)["generated"] is True


def test_REQ_SLP_023_a_sleep_relation_carries_tier_and_coverage_and_no_causal_vocabulary():
    ok = sleep_relation("On short nights, steps were lower.", tier="DESCRIPTIVE", coverage=0.9)
    assert ok["tier"] == "DESCRIPTIVE" and ok["coverage"] == 0.9
    with pytest.raises(SurfaceViolation, match="REQ-SLP-023"):
        sleep_relation("Short sleep causes fewer steps.", tier="DESCRIPTIVE", coverage=0.9)
    with pytest.raises(SurfaceViolation, match="REQ-SLP-023"):
        sleep_relation("On short nights, steps were lower.", tier=None, coverage=0.9)
    assert "because" in CAUSAL_VOCAB


# ---------------------------------------------------------------- reconstruction

def test_REQ_REC_013_inferred_inputs_carry_uncertainty_and_lineage_and_are_not_independent():
    """Three events reconstructed from the same receipt are one observation wearing three hats,
    and an analysis that counts them as three has tripled its own confidence for free."""
    inputs = [{"id": 1, "uncertainty": 0.3, "source_lineage": "receipt:99"},
              {"id": 2, "uncertainty": 0.3, "source_lineage": "receipt:99"},
              {"id": 3, "uncertainty": 0.2, "source_lineage": "receipt:12"}]
    out = inferred_input({"name": "a"}, inputs=inputs)
    assert out["treated_as_measured"] is False and out["independent"] is False
    assert out["shared_lineage_groups"] == ("receipt:99",)
    with pytest.raises(SurfaceViolation, match="REQ-REC-013"):
        inferred_input({}, inputs=[{"id": 1, "uncertainty": 0.3}])


def test_REQ_REC_015_name_what_would_distinguish_the_alternatives_or_say_nothing_would():
    """"We are not sure" is not an answer. "We are not sure, and a receipt timestamp would settle
    it" is one Joe can act on; "nothing available would settle it" is one he can stop thinking
    about."""
    out = distinguishing_evidence(["lunch", "dinner"], discriminators=["a receipt timestamp"])
    assert out["would_distinguish"] == ("a receipt timestamp",)
    none = distinguishing_evidence(["lunch", "dinner"], discriminators=[])
    assert none["would_distinguish"] == ()
    assert "no discriminating evidence has been identified" in none["text"]
    assert distinguishing_evidence(["lunch"], discriminators=[]) is None


def test_REQ_REC_016_each_family_is_passed_or_explicitly_open_never_one_verdict():
    """A single pass/fail hides which family failed, and these fail for different reasons:
    contradictory evidence is a data problem, model unavailability is an ops problem, and
    inferred-input propagation is a correctness one."""
    cases = {f: "passed" for f in EVENT_FAMILIES_REQUIRED}
    cases["model_unavailable"] = "open"
    out = acceptance_report(cases)
    assert out["aggregate_verdict"] is None
    assert out["open"] == ("model_unavailable",)
    with pytest.raises(SurfaceViolation, match="REQ-REC-016"):
        acceptance_report({"multiple_event_families": "passed"})


# ---------------------------------------------------------------- tier attachment

def test_REQ_TIER_023_a_confirmed_claim_carries_all_three_in_the_SAME_payload():
    """Not reachable through a trace: in the payload. A CONFIRMED claim whose adjustment set is
    one click away is one most readers will meet without it — and the adjustment set is what the
    word "confirmed" is resting on."""
    out = confirmed_payload({"text": "x"}, adjustment_set=["dow", "steps"], e_value_point=2.4,
                            negative_control_result="passed")
    assert out["adjustment_set"] == ("dow", "steps") and out["e_value_point"] == 2.4
    for missing in ("adjustment_set", "e_value_point", "negative_control_result"):
        kw = {"adjustment_set": ["dow"], "e_value_point": 2.4,
              "negative_control_result": "passed"}
        kw[missing] = None
        with pytest.raises(SurfaceViolation, match="REQ-TIER-023"):
            confirmed_payload({"text": "x"}, **kw)


def test_REQ_TIER_025_a_frequentist_confidence_interval_is_never_rendered():
    """A 95% CI is not a 95% probability that the value is inside it, and every reader outside
    statistics reads it as one. Reporting the quantity people already think they are reading is
    more honest than reporting the other one correctly and being misread."""
    out = interval_statement(credible_interval=[-40, -4], p_direction=0.97)
    assert "97% probability" in out["text"]
    with pytest.raises(SurfaceViolation, match="REQ-TIER-025"):
        interval_statement(confidence_interval=[-40, -4])
    with pytest.raises(SurfaceViolation, match="REQ-TIER-025"):
        interval_statement(credible_interval=[-40, -4])
