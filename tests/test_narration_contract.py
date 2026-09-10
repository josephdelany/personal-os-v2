"""B20 §A — the language layer's contract and the render pipeline (REQ-NAR-001..006, 010..015).

Every number in this system is computed by SQL or a pure engine, and the model's entire job is to
put those numbers in a sentence. These tests are what make that enforceable rather than asserted.
"""
import pytest

from tools.engines.narration_contract import (NarrationLog, NarrationRefused, ROUNDING_RULES,
                                              Slot, Template, accept, check_input,
                                              permitted_numerals, render_template,
                                              verify_entities, verify_numerals, verify_relations)

RESULT = {"metric": "sleep_minutes", "value": 444.0, "hours": 7.4213, "days": 30,
          "unit": "minutes", "note": "Coverage was 30 of 30 days."}
TPL = Template("Your {metric} averaged {hours} over {days}.",
               slots=(Slot("metric", "metric"),
                      Slot("hours", "hours", unit="hours", rounding="one_dp"),
                      Slot("days", "days", unit="days")))


def test_REQ_NAR_001_raw_rows_photos_and_coordinates_may_not_reach_the_language_layer():
    """A model that receives raw rows will summarise them, and its summary is a computation
    nobody registered. Refused BEFORE the call, because a bad input cannot be repaired after the
    sentence is written."""
    assert check_input({"metric": "steps", "value": 9000})
    for bad in ({"atoms": [{"id": 1}]}, {"context": {"lat": 44.5}},
                {"photo_ref": "abc"}, {"a": {"b": [{"coordinates": [1, 2]}]}}):
        with pytest.raises(NarrationRefused, match="REQ-NAR-001"):
            check_input(bad)


def test_REQ_NAR_002_the_narration_log_is_append_only():
    """A narration is evidence of what the system SAID, and a system that can revise its own
    account of what it said cannot be audited on it."""
    log = NarrationLog()
    log.append({"text": "x"})
    assert log.writable_tables() == ("narration_log",)
    with pytest.raises(TypeError, match="REQ-NAR-002"):
        log[0] = {"text": "y"}


def test_REQ_NAR_003_the_model_does_not_get_a_vote_on_the_tier():
    out = accept("Your sleep_minutes averaged 7.4 hours over 30 days.", template=TPL,
                 result=RESULT, tier="DESCRIPTIVE", model_tier="CONFIRMED_OBSERVATIONAL")
    assert out["used"] == "deterministic_template"
    assert out["tier"] == "DESCRIPTIVE"
    assert out["rows"][0]["rule"] == "REQ-NAR-003"


def test_REQ_NAR_012_a_numeral_that_is_not_in_the_result_is_refused():
    assert verify_numerals("7.4 hours over 30 days", RESULT) == ()
    assert verify_numerals("about 8 hours", RESULT) == ("8",)


def test_REQ_NAR_012_a_registered_rounding_of_a_stored_value_is_permitted():
    """"a registered rounding of one" is the requirement's own phrase, and it is what lets a
    template show 7.4 for a stored 7.4213 without opening the door to any convenient number."""
    allowed = permitted_numerals(RESULT)
    assert "7.4" in allowed and "7.4213" in allowed and "7" in allowed
    assert "7.5" not in allowed


def test_REQ_NAR_012_a_prose_field_does_not_license_its_own_numerals():
    """A clause stored in the result and compared against itself is self-certifying — the same
    defect 0059's SQL verifier had to fix."""
    result = {"value": 5, "note": "across 9,999 days"}
    assert verify_numerals("9999 days", result) == ("9999",)


def test_REQ_NAR_004_an_entity_the_result_does_not_name_is_refused():
    """A model that adds a plausible entity is inventing a claim, and plausibility is exactly
    what makes it dangerous."""
    result = {"merchant": "Hannaford", "amount": 41.0}
    assert verify_entities("Hannaford was 41.", result) == ()
    assert verify_entities("Whole Foods was 41.", result) == ("Whole Foods",)


def test_REQ_NAR_005_a_causal_relation_needs_an_edge_in_the_input():
    """The model may say two things happened. It may not say one happened because of the other
    unless the input already carries that edge — the edge is the thing that was computed, tiered
    and registered; the sentence is not."""
    plain = {"a": 1, "b": 2}
    assert verify_relations("Sleep was 1 and spend was 2.", plain) == ()
    assert verify_relations("Spend was 2 because sleep was 1.", plain)
    with_edge = {"a": 1, "b": 2, "edges": [{"from": "a", "to": "b"}]}
    assert verify_relations("Spend was 2 because sleep was 1.", with_edge) == ()


def test_REQ_NAR_010_every_slot_is_declared_and_bound_to_a_result_field():
    with pytest.raises(ValueError, match="REQ-NAR-010"):
        Template("Your {metric} was {mystery}.", slots=(Slot("metric", "metric"),))


def test_REQ_NAR_010_012_a_literal_numeral_in_template_prose_is_refused():
    """It did not come from the result object and no slot binds it, so nothing can trace it."""
    with pytest.raises(ValueError, match="REQ-NAR-010/012"):
        Template("Your {metric} was above 8 hours.", slots=(Slot("metric", "metric"),))


def test_REQ_NAR_011_slot_values_come_from_the_result_object_only():
    assert render_template(TPL, RESULT) == \
        "Your sleep_minutes averaged 7.4 hours over 30 days."
    with pytest.raises(ValueError, match="REQ-NAR-011"):
        render_template(TPL, {"metric": "x", "days": 1})


def test_REQ_NAR_014_a_numeral_is_never_rendered_without_its_unit():
    """"Your sleep was 7.4" is not a shorter way of saying "7.4 hours" — it is a sentence the
    reader completes, and half of them complete it wrongly."""
    bare = Template("Your sleep was {hours}.",
                    slots=(Slot("hours", "hours", rounding="one_dp"),))
    with pytest.raises(ValueError, match="REQ-NAR-014"):
        render_template(bare, RESULT)


def test_REQ_NAR_015_only_registered_rounding_rules_may_be_used():
    """Ad-hoc rounding is a computation: 7.44 as "7" is a different claim from 7.44 as "7.4",
    and neither is traceable unless the rule itself is stored."""
    assert set(ROUNDING_RULES) >= {"integer", "one_dp", "two_dp", "thousands"}
    bad = Template("Your sleep was {hours}.",
                   slots=(Slot("hours", "hours", unit="hours", rounding="three_dp_ish"),))
    with pytest.raises(ValueError, match="REQ-NAR-015"):
        render_template(bad, RESULT)


def test_REQ_NAR_013_a_refused_sentence_falls_back_to_the_TEMPLATE_not_to_an_error():
    """The number behind it is perfectly good. Showing an error would hide a real answer because
    the prose around it was wrong; showing the template shows the answer in plainer words."""
    out = accept("Your sleep averaged about 8 hours over 30 days.", template=TPL, result=RESULT,
                 tier="DESCRIPTIVE", finding_id="F-1")
    assert out["used"] == "deterministic_template"
    assert out["text"] == render_template(TPL, RESULT)
    assert "8 hours" not in out["text"]


def test_REQ_NAR_013_the_violation_row_carries_the_numeral_and_the_field_set():
    out = accept("It was 8 hours.", template=TPL, result=RESULT, tier="DESCRIPTIVE",
                 finding_id="F-9")
    row = out["rows"][0]
    assert row["rule"] == "REQ-NAR-012" and "8" in row["detail"]
    assert row["finding_id"] == "F-9"
    assert "hours" in row["result_fields"] and "days" in row["result_fields"]


def test_REQ_NAR_006_a_clean_model_sentence_is_accepted_unchanged():
    """The contract is not a refusal machine: a sentence that adds nothing survives intact."""
    text = "Your sleep_minutes averaged 7.4 hours over 30 days."
    out = accept(text, template=TPL, result=RESULT, tier="DESCRIPTIVE", model_tier="DESCRIPTIVE")
    assert out["used"] == "model" and out["text"] == text and out["rows"] == ()


def test_REQ_NAR_006_the_model_may_not_compute_a_number_the_engine_did_not():
    """444 minutes and 30 days are both in the result. 14.8 per day is not — it is a division
    the model performed, and a division is a computation."""
    out = accept("That is 14.8 minutes per day.", template=TPL, result=RESULT,
                 tier="DESCRIPTIVE")
    assert out["used"] == "deterministic_template"
    assert any(r["rule"] == "REQ-NAR-012" for r in out["rows"])
