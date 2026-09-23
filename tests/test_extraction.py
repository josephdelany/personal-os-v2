"""B16 §C.1/C.2/C.3 — the extractive-only contract (REQ-CAP-050..066, 108, 109).

The contract in one line: the model may point at the transcript, and may not add to it. Every
test here is a way of catching it adding.
"""
import datetime as dt

import pytest

from tools.engines.extraction import (DEFAULT_DAY_BOUNDARY_HOUR, FOOD_FIELDS, Field,
                                      MAX_EXTRACTION_ATTEMPTS, NUTRITION_TERMS, PROFILES,
                                      PROVENANCE, SchemaViolation, extract_with_retry,
                                      render_treatment, resolve_field, resolve_time,
                                      span_matches, statistical_inclusion, strip_nutrition,
                                      subject_day, validate_profile, validate_schema)

TRANSCRIPT = "had a bagel and cream cheese around eight this morning"
CAPTURED = dt.datetime(2026, 9, 10, 20, 0)


def test_REQ_CAP_108_the_profile_set_is_closed_and_unknown_subjects_route_to_note():
    """An un-profiled extraction is the failure the requirement names. A capture about something
    nobody anticipated should still be KEPT, as a note."""
    assert PROFILES == ("food", "workout", "drink", "activity", "mood", "note")
    for p in PROFILES:
        assert validate_profile(p) == p
    assert validate_profile("dream") == "note"
    assert validate_profile(None) == "note"


def test_REQ_CAP_050_051_the_food_profile_has_exactly_seven_fields_under_a_json_schema():
    validate_schema("food", {"properties": {f: {} for f in FOOD_FIELDS}})
    with pytest.raises(SchemaViolation, match="REQ-CAP-051"):
        validate_schema("food", {"properties": {f: {} for f in FOOD_FIELDS + ("notes",)}})
    with pytest.raises(SchemaViolation, match="REQ-CAP-051"):
        validate_schema("food", {"properties": {f: {} for f in FOOD_FIELDS[:-1]}})


def test_REQ_CAP_052_no_field_name_may_refer_to_calories_or_a_macronutrient():
    """A model asked for a `calories` field will produce one, fluently and wrongly. Keeping the
    word out of the schema is cheaper and more reliable than discarding what comes back."""
    for term in ("calories", "kcal", "protein", "carbs", "fat", "fibre", "macros", "energy"):
        with pytest.raises(SchemaViolation, match="REQ-CAP-052"):
            validate_schema("note", {"properties": {term: {}}})


def test_REQ_CAP_052_a_field_DESCRIPTION_is_checked_too():
    """The invitation is in the description as much as in the name."""
    with pytest.raises(SchemaViolation, match="REQ-CAP-052"):
        validate_schema("note", {"properties": {"amount": {"description": "energy in kcal"}}})


def test_REQ_CAP_053_the_span_assertion_is_a_string_comparison_not_a_judgement():
    """A model that invents an item invents its evidence span too, and the invented span will not
    be at that offset. This converts "did the model make this up" into a comparison."""
    start = TRANSCRIPT.index("bagel")
    assert span_matches(TRANSCRIPT, "bagel", start) is True
    assert span_matches(TRANSCRIPT, "bagel", start + 1) is False
    assert span_matches(TRANSCRIPT, "smoked salmon", 6) is False, "an invented item"
    assert span_matches(TRANSCRIPT, "bagel", None) is False
    assert span_matches(TRANSCRIPT, "bagel", -1) is False


def test_REQ_CAP_054_058_a_matching_span_is_extracted_and_a_mismatch_discards_the_VALUE():
    """Not merely flagged. A span that does not match means the model pointed at text that is not
    there, and nothing it said about that field survives."""
    ok = resolve_field("name", "bagel", TRANSCRIPT, evidence="bagel",
                       evidence_start=TRANSCRIPT.index("bagel"))
    assert ok.provenance == "extracted" and ok.value == "bagel"

    bad = resolve_field("name", "smoked salmon", TRANSCRIPT, evidence="smoked salmon",
                        evidence_start=6)
    assert bad.provenance == "inferred"
    assert bad.value is None, "the value is discarded, not kept at lower confidence"
    assert bad.reason == "span_mismatch"


def test_REQ_CAP_059_060_a_null_span_is_inferred_and_a_default_table_is_defaulted():
    assert resolve_field("quantity", 1, TRANSCRIPT).provenance == "inferred"
    assert resolve_field("quantity_unit", "each", TRANSCRIPT,
                         from_default_table=True).provenance == "defaulted"


def test_REQ_CAP_057_provenance_is_exactly_one_of_three():
    assert PROVENANCE == ("extracted", "inferred", "defaulted")
    with pytest.raises(ValueError, match="REQ-CAP-057"):
        Field("x", 1, "guessed")


def test_REQ_CAP_056_a_calorie_number_is_stripped_at_the_adapter_boundary():
    """Before any row exists, and explicitly NOT at reduced confidence: a stored number with low
    confidence is still a stored number, and confidence decays out of a reader's memory faster
    than the digits do."""
    cleaned, discarded = strip_nutrition(
        {"items": [{"name": "bagel", "calories": 289, "protein_g": 11}]})
    assert cleaned == {"items": [{"name": "bagel"}]}
    assert set(discarded) == {"$.items[0].calories", "$.items[0].protein_g"}


def test_REQ_CAP_056_nested_and_listed_values_are_stripped_too():
    cleaned, discarded = strip_nutrition({"a": {"b": [{"kcal": 1}, {"name": "x"}]}})
    assert cleaned == {"a": {"b": [{}, {"name": "x"}]}}
    assert discarded == ("$.a.b[0].kcal",)


def test_REQ_CAP_056_an_ordinary_field_is_not_stripped():
    cleaned, discarded = strip_nutrition({"name": "fat-free yoghurt", "quantity": 1})
    assert discarded == (), "the term must be a field NAME, not text in a value"
    assert cleaned["name"] == "fat-free yoghurt"


def test_REQ_CAP_055_two_retries_then_quarantine_and_never_a_partial_write():
    """A response that failed validation three times is one nobody understands, and writing the
    half that parsed would put unvalidated values beside validated ones."""
    calls = []

    def always_bad(attempt):
        calls.append(attempt)
        return {"bad": True}

    def strict(_):
        raise ValueError("schema")

    out = extract_with_retry(always_bad, validate=strict)
    assert out["ok"] is False
    assert calls == [1, 2, 3] and MAX_EXTRACTION_ATTEMPTS == 3
    assert out["processing_status"] == "extraction_quarantined"
    assert out["review_list"] is True
    assert "response" not in out, "nothing partial is handed back"


def test_REQ_CAP_055_a_later_attempt_that_succeeds_is_returned():
    def flaky(attempt):
        return {"ok": attempt >= 2}

    def validate(r):
        if not r["ok"]:
            raise ValueError("schema")

    out = extract_with_retry(flaky, validate=validate)
    assert out["ok"] is True and out["attempts"] == 2


# ---------------------------------------------------------------- C.3 time

def test_REQ_CAP_064_a_temporal_span_resolves_against_the_capture_time_preferring_the_past():
    f = resolve_time("yesterday at 7pm", CAPTURED)
    assert f.provenance == "extracted"
    assert f.value == dt.datetime(2026, 9, 9, 19, 0)
    assert f.value < CAPTURED, "PREFER_DATES_FROM='past'"


def test_REQ_CAP_065_an_unresolvable_span_falls_back_to_captured_at_as_DEFAULTED():
    """`defaulted`, not `inferred`. REQ-CAP-062 filters `defaulted` out of statistics and does
    NOT filter `inferred`, so mislabelling this would let a substituted timestamp into a trend as
    though it had been measured. The requirement records a reviewer catching exactly that."""
    f = resolve_time("banana o'clock", CAPTURED)
    assert f.value == CAPTURED
    assert f.provenance == "defaulted", "inferred would not be filtered from statistics"
    assert f.time_precision == "unknown"
    assert f.reason == "dateparser_failed"


def test_REQ_CAP_065_the_fallback_is_a_common_path_not_an_exotic_one():
    """Measured 2026-09-10: dateparser returns None for both of these, and they are two of the
    most natural things to say into a capture."""
    for span in ("this morning", "last Tuesday"):
        assert resolve_time(span, CAPTURED).provenance == "defaulted", span


def test_REQ_CAP_063_no_temporal_expression_at_all_is_also_defaulted_and_says_why():
    f = resolve_time(None, CAPTURED)
    assert f.provenance == "defaulted" and f.reason == "no_temporal_expression"
    assert f.time_precision == "unknown"


def test_REQ_CAP_066_a_capture_before_the_day_boundary_belongs_to_the_preceding_day():
    """A 01:30 note about the evening is about the evening, not about the morning that follows."""
    assert DEFAULT_DAY_BOUNDARY_HOUR == 4
    assert subject_day(dt.datetime(2026, 9, 11, 1, 30)) == dt.date(2026, 9, 10)
    assert subject_day(dt.datetime(2026, 9, 11, 4, 0)) == dt.date(2026, 9, 11)
    assert subject_day(dt.datetime(2026, 9, 11, 23, 0)) == dt.date(2026, 9, 11)


# ---------------------------------------------------------------- C.2 provenance downstream

def test_REQ_CAP_061_inferred_and_defaulted_demand_a_distinct_visual_treatment():
    """Returned as data rather than left to a stylesheet, so a surface cannot render an inferred
    value identically to a measured one by omission."""
    assert render_treatment(Field("x", 1, "extracted"))["distinct_treatment_required"] is False
    for p in ("inferred", "defaulted"):
        t = render_treatment(Field("x", 1, p))
        assert t["distinct_treatment_required"] is True
        assert t["label"]


def test_REQ_CAP_062_defaulted_fields_are_excluded_or_counted_never_silently_included():
    fields = [Field("a", 1, "extracted"), Field("b", 2, "inferred"), Field("c", 3, "defaulted")]
    out = statistical_inclusion(fields)
    assert [f.name for f in out["included"]] == ["a", "b"]
    assert out["n_defaulted_excluded"] == 1
    assert "1 field(s)" in out["disclosure"]
    assert "1 field(s)" in out["if_included_disclosure"], "both branches the requirement offers"


def test_REQ_CAP_062_nothing_is_disclosed_when_nothing_was_defaulted():
    out = statistical_inclusion([Field("a", 1, "extracted")])
    assert out["n_defaulted_excluded"] == 0 and out["disclosure"] == ""


def test_REQ_CAP_109_the_extractive_only_contract_binds_EVERY_profile():
    """Not only the food profile. The span assertion and the discard-on-mismatch apply to
    workout, drink, activity, mood and note alike — a profile exempt from them is a profile where
    the model may add."""
    for profile in PROFILES:
        bad = resolve_field("x", "invented", TRANSCRIPT, evidence="not in the transcript",
                            evidence_start=0)
        assert bad.value is None and bad.reason == "span_mismatch", profile
        validate_schema(profile, {"properties": {f: {} for f in FOOD_FIELDS}}
                        if profile == "food" else {"properties": {"note": {}}})


@pytest.mark.parametrize("value,evidence", [("salmon", "bagel"), ("ham", "champagne"),
                                            ("", "bagel"), (None, "bagel")])
def test_REQ_CAP_053_054_058_real_evidence_cannot_launder_an_invented_name(value,evidence):
    field = resolve_field("name", value, evidence, evidence=evidence, evidence_start=0)
    assert field.value is None
    assert field.provenance == "inferred"
    assert field.reason == "value_not_in_span"


def test_REQ_CAP_053_058_verbatim_name_can_have_surrounding_words_and_case():
    field = resolve_field("name", "Big Mac", "a Big Mac", evidence="a Big Mac", evidence_start=0)
    assert field.value == "Big Mac" and field.provenance == "extracted"
    field = resolve_field("name", "BIG MAC", "a Big Mac", evidence="a Big Mac", evidence_start=0)
    assert field.value == "BIG MAC" and field.provenance == "extracted"


@pytest.mark.parametrize("evidence,offset", [("",0),("a",False),("a",True),(1,0),([],0),("a",0.0)])
def test_REQ_CAP_053_invalid_or_empty_evidence_never_proves_a_value(evidence,offset):
    assert span_matches("a", evidence, offset) is False
