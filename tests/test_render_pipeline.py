"""B20 §B — the render pipeline (REQ-NAR-024, 026, 030..039).

The pipeline's whole job is to be the place where a result becomes a screen, with the model as an
OPTIONAL improvement rather than a dependency.
"""
import pytest

from tools.engines.render_pipeline import (DECLINE_COOLDOWN_DAYS, EXPORT_TABLES,
                                           RECOMMENDATION_FIELDS, RenderViolation,
                                           TRUST_SECTION_FIELDS, check_conditional_on_model,
                                           check_frontend_computation, check_moralising,
                                           check_recommendation_numerals, declined, export,
                                           layout, recommendation_template, render,
                                           weekly_summary)

VOCAB = {"permitted": ["consider", "you could", "the evidence leans toward"],
         "forbidden": ["you must", "you should", "this will", "guaranteed"]}
REC = {"tier": "DESCRIPTIVE", "effect_size": 22, "interval": [4, 40], "n": 30, "coverage": 0.9,
       "what_would_change_this": "40 more paired days would move this",
       "text": "Consider moving caffeine earlier: 22 minutes (4-40), n=30, coverage 0.9."}


def test_REQ_NAR_030_031_every_surface_renders_with_the_language_layer_disabled():
    """A surface that goes blank when the model is unavailable has made the model load-bearing
    for facts it did not produce — and it will go blank on exactly the day something is worth
    reading."""
    out = render({}, template="Sleep averaged 7.4 hours.", model_text="You slept about 7.4 hours.",
                 language_layer_available=False)
    assert out["text"] == "Sleep averaged 7.4 hours."
    assert out["path"] == "deterministic_template"
    assert out["error"] is None, "there is no error path for the model being down"


def test_REQ_NAR_031_the_template_is_the_default_the_model_improves_on():
    assert render({}, template="t", model_text=None)["path"] == "deterministic_template"
    assert render({}, template="t", model_text="m")["path"] == "model"


def test_REQ_NAR_032_nothing_may_be_conditional_on_the_language_layer():
    assert check_conditional_on_model({"name": "weekly_brief"})
    with pytest.raises(RenderViolation, match="REQ-NAR-032"):
        check_conditional_on_model({"name": "alert", "requires_language_layer": True})


def test_REQ_NAR_033_the_front_end_computes_no_displayed_number():
    """A percentage calculated in the browser has no stored result to trace to, no code_version,
    and no way to appear in an export — and it is indistinguishable on screen from one that
    does."""
    assert check_frontend_computation([444, 30], stored_values=[444, 30, 0.9])
    with pytest.raises(RenderViolation, match="REQ-NAR-033"):
        check_frontend_computation([444, 14.8], stored_values=[444, 30])


def test_REQ_NAR_034_the_chart_renders_below_the_verdict():
    """Above the text a chart is read first, and a reader who has already formed a view from the
    shape reads the sentence as confirmation."""
    out = layout("Sleep averaged 7.4 hours.", {"kind": "line"}, tier="DESCRIPTIVE")
    assert [b["kind"] for b in out["blocks"]] == ["verdict", "chart"]
    assert out["chart_below_verdict"] is True


def test_REQ_NAR_035_a_candidate_claim_gets_no_chart_at_all():
    """A chart is the most persuasive object this system renders. On an unconfirmed candidate it
    converts "a generator flagged this" into something that looks measured, and no label under it
    undoes that."""
    for tier in ("CANDIDATE", "EXPLORATORY"):
        with pytest.raises(RenderViolation, match="REQ-NAR-035"):
            layout("A generator flagged this.", {"kind": "scatter"}, tier=tier)
    assert layout("A generator flagged this.", None, tier="CANDIDATE")["blocks"]


def test_REQ_NAR_026_a_declined_suggestion_waits_seven_days():
    assert declined("s1", declined_days_ago=3)["propose"] is False
    assert declined("s1", declined_days_ago=DECLINE_COOLDOWN_DAYS)["propose"] is True
    assert declined("s1", declined_days_ago=None)["propose"] is True


def test_REQ_NAR_026_a_skipped_day_is_never_mentioned():
    """The half that gets forgotten: "you did not log yesterday" is a reproach dressed as a status
    line, and it is the sentence most likely to end the logging altogether."""
    with pytest.raises(RenderViolation, match="REQ-NAR-026"):
        declined("s1", declined_days_ago=None, mentions_skipped_day=True)


def test_REQ_NAR_024_a_moralising_judgment_on_a_total_is_refused():
    assert check_moralising("Dining was $412 across 19 charges.") == ()
    assert check_moralising("That was excessive.")


def test_REQ_NAR_024_a_recommendation_with_its_tier_and_interval_is_PERMITTED():
    """The distinction is real and worth keeping: "you spent too much" is a verdict on Joe, while
    a hedged option with its evidence attached is an option — and banning both would leave the
    system unable to suggest anything at all."""
    text = "Consider whether that was necessary for you."
    assert check_moralising(text) != (), "bare, it is moralising"
    assert check_moralising(text, is_recommendation=True, tier="DESCRIPTIVE",
                            interval=[4, 40]) == ()


def test_REQ_NAR_038_a_recommendation_renders_the_full_disclosure_set():
    """The disclosure set is what makes it a suggestion rather than an instruction."""
    out = recommendation_template(REC, vocabulary=VOCAB)
    assert out["tier"] == "DESCRIPTIVE" and out["n"] == 30
    assert out["what_would_change_this"]
    for f in RECOMMENDATION_FIELDS:
        bad = {**REC, f: None}
        with pytest.raises(RenderViolation, match="REQ-NAR-038"):
            recommendation_template(bad, vocabulary=VOCAB)


def test_REQ_NAR_039_the_vocabulary_comes_from_the_TABLE_not_a_hardcoded_list():
    """A hardcoded list cannot be corrected without a deploy, and the wording of a recommendation
    is precisely the thing Joe is most likely to want corrected."""
    with pytest.raises(RenderViolation, match="REQ-NAR-039"):
        recommendation_template(REC, vocabulary=None)


def test_REQ_NAR_039_a_verb_asserting_a_settled_outcome_is_refused():
    hard = {**REC, "text": "You must move caffeine earlier: this will add 22 minutes."}
    with pytest.raises(RenderViolation, match="REQ-NAR-039"):
        recommendation_template(hard, vocabulary=VOCAB)


def test_REQ_NAR_039_a_recommendation_with_no_hedged_verb_at_all_is_refused():
    flat = {**REC, "text": "Move caffeine earlier: 22 minutes (4-40), n=30, coverage 0.9."}
    with pytest.raises(RenderViolation, match="REQ-NAR-039"):
        recommendation_template(flat, vocabulary=VOCAB)


def test_REQ_NAR_038_a_hyphenated_range_is_not_read_as_a_negative_number():
    """Found by this test on its own example sentence: "22 minutes (4-40)" parsed as 4 and MINUS
    40, so the checker flagged a legitimate interval as an invented number. The hyphen in a range
    is not a minus sign, and a hyphenated range is exactly how every interval here is rendered."""
    assert check_recommendation_numerals(REC) == (), REC["text"]
    assert check_recommendation_numerals(
        {**REC, "effect_size": -22, "text": "Consider it: -22 minutes."}) == ()


def test_REQ_NAR_038_no_numeral_absent_from_the_stored_fields():
    assert check_recommendation_numerals(REC) == ()
    invented = {**REC, "text": "Consider moving caffeine earlier: about 45 minutes."}
    assert "45" in check_recommendation_numerals(invented)


def test_REQ_NAR_036_the_TRUST_section_is_in_every_weekly_summary():
    """Coverage, missingness and calibration decide whether the rest of the summary means
    anything. A summary that reports findings without them reads the same in a week when the
    Watch was off."""
    ok = weekly_summary({"findings": [], "trust": {"coverage": 0.9, "missingness_flags": [],
                                                   "calibration_state": "DESCRIPTIVE"}})
    assert ok["trust_present"] is True
    assert TRUST_SECTION_FIELDS == ("coverage", "missingness_flags", "calibration_state")
    with pytest.raises(RenderViolation, match="REQ-NAR-036"):
        weekly_summary({"findings": [], "trust": {"coverage": 0.9}})


def test_REQ_NAR_037_the_export_is_complete_free_and_synchronous():
    """All three words are load-bearing: a paid export is a hostage, a deferred one is never
    checked, and one missing tier_history cannot answer what the system claimed before it changed
    its mind — which is the question an export is FOR."""
    assert export(list(EXPORT_TABLES))["complete"] is True
    with pytest.raises(RenderViolation, match="REQ-NAR-037"):
        export([t for t in EXPORT_TABLES if t != "tier_history"])
    for kw in ({"price": 1}, {"synchronous": False}, {"partial": True}):
        with pytest.raises(RenderViolation, match="REQ-NAR-037"):
            export(list(EXPORT_TABLES), **kw)
