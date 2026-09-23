"""B12 §D.4/§D.4a/§E.3/§G.1 — quantity, propagation and display
(REQ-NUT-018..027, 041..053, 062..065).

A calorie count is the most confidently wrong number a system like this can produce: assembled
from a food someone identified from a sentence, a portion nobody weighed, and a database entry
for something similar — then rendered as "1,847 kcal", which reads like a measurement.
"""
import pytest

from tools.engines.nutrition_display import (METHOD_WEIGHT, NutritionDisplayError, TIGHT_METHODS,
                                             UNRESOLVED, analysis_rows, check_framing,
                                             confidence_may_not_narrow, convert_quantity,
                                             correct_portion, daily_total, deficit_statement,
                                             extraction_may_not_emit_grams, render_value,
                                             resolve_count, resolve_quantifier,
                                             resolve_vernacular, round_interval,
                                             unresolved_is_not_an_error)

ITEMS = [{"kcal_low": 250, "kcal_high": 320}, {"kcal_low": 400, "kcal_high": 620}]


def test_REQ_NUT_019_a_stated_unit_converts_and_is_EXTRACTED():
    """A stated unit is something Joe said. It is not an inference and must not be marked one."""
    out = convert_quantity(2, "oz")
    assert out["provenance"] == "extracted" and out["grams"] == pytest.approx(56.69904625)


def test_REQ_NUT_019_volume_conversion_never_implicitly_supplies_density():
    out = convert_quantity(0.25, 'liters')
    assert out == {'volume_ml':250, 'provenance':'extracted', 'basis':'0.25 liters'}


def test_REQ_NUT_020_a_vernacular_phrase_resolves_as_DEFAULTED():
    """"A bowl" is not a quantity Joe stated — it is one the system looked up. REQ-CAP-062
    excludes `defaulted` from statistics, which is exactly right for a portion nobody
    measured."""
    aliases = {("cereal", "a bowl"): {"grams": 60, "n_corrections": 2}}
    out = resolve_vernacular("a bowl", "cereal", aliases)
    assert out["provenance"] == "defaulted" and out["grams"] == 60
    assert resolve_vernacular("a trough", "cereal", aliases) is None


def test_REQ_NUT_023_the_extraction_service_may_not_emit_grams_for_a_phrase():
    """A model asked how many grams are in "a bowl of oats" will answer, and the answer will look
    identical to one from Joe's own corrected portion table."""
    assert extraction_may_not_emit_grams({"quantity_unit": "g", "from_vernacular": False})
    with pytest.raises(NutritionDisplayError, match="REQ-NUT-023"):
        extraction_may_not_emit_grams({"quantity_unit": "grams", "from_vernacular": True})


def test_REQ_NUT_018_022_a_correction_updates_the_grams_and_counts_itself():
    """A phrase corrected four times is one where the default was wrong four times, and that is
    worth surfacing before it is wrong a fifth."""
    out = correct_portion({"grams": 60, "n_corrections": 3}, 85)
    assert out["grams"] == 85 and out["n_corrections"] == 4 and out["provenance"] == "joe"


def test_REQ_NUT_050_052_a_count_multiplies_the_branded_per_serving_weight():
    rec = {"serving_grams": 128}
    assert resolve_count(2, rec)["grams"] == 256
    assert resolve_count(0.5, rec)["grams"] == 64


def test_REQ_NUT_051_no_branded_serving_weight_means_the_count_stays_unconverted():
    """The count is kept verbatim. Without a per-serving gram weight there is nothing to multiply
    it by, and inventing one would carry a guess into the day's total."""
    out = resolve_quantifier("2 burritos", 2, None)
    assert out["nutrition_status"] == UNRESOLVED
    assert out["reason"] == "no_branded_serving_weight" and out["count"] == 2
    assert out["grams"] is None and out["review"] is True


def test_REQ_NUT_053_a_vague_quantifier_gets_no_fraction():
    """"Most of a burrito" is not 0.75 of one. Assigning a fraction would invent a number and
    carry it through a whole day's total — the figure Joe actually reads."""
    for phrase in ("most of the burrito", "a few bites of it", "picked at it"):
        out = resolve_quantifier(phrase, None, {"serving_grams": 300})
        assert out["nutrition_status"] == UNRESOLVED, phrase
        assert out["reason"] == "vague_quantifier" and out["grams"] is None


def test_REQ_NUT_052_an_EXPLICIT_fraction_does_resolve():
    """The rule is about vagueness, not about fractions: "half" is a stated quantity."""
    out = resolve_quantifier("half a burrito", None, {"serving_grams": 300})
    assert out["grams"] == 150 and out["provenance"] == "extracted"


def test_REQ_NUT_043_the_lows_sum_to_the_low_and_the_highs_to_the_high():
    """Summing the points and putting a band around them would understate the width: the errors
    are systematic — portion sizes drift the same direction all day — not independent."""
    t = daily_total(ITEMS)
    assert t["kcal_low"] == 650 and t["kcal_high"] == 940
    assert t["kcal_point"] == 795


def test_REQ_NUT_026_a_total_states_how_many_unresolved_items_it_excludes():
    t = daily_total(ITEMS + [{"nutrition_status": UNRESOLVED}])
    assert t["unresolved_items"] == 1
    assert "1 item(s)" in t["unresolved_note"]
    assert t["kcal_low"] == 650, "the unresolved item contributes nothing, not zero"


def test_REQ_NUT_049_rounding_never_narrows_an_interval():
    """Rounding 1,847.4–2,103.6 to 1,847–2,104 is fine. Rounding it to 1,850–2,100 removes 7 kcal
    of honest uncertainty for tidiness, and every such rounding removes a little more."""
    lo, hi = round_interval(1847.4, 2103.6)
    assert (lo, hi) == (1847, 2104)
    assert lo <= 1847.4 and hi >= 2103.6


def test_REQ_NUT_044_063_the_interval_is_the_value_everywhere():
    out = render_value(795, 650, 940, estimate_method="estimated")
    assert out["text"] == "~795 kcal (650–940)"
    with pytest.raises(NutritionDisplayError, match="REQ-NUT-063"):
        render_value(795, None, None, estimate_method="estimated")


def test_REQ_NUT_045_065_visual_weight_follows_the_METHOD_not_the_magnitude():
    """Weighting by magnitude makes a big number look more certain than a small one, when the
    opposite is usually true."""
    big_estimate = render_value(3000, 2000, 4000, estimate_method="estimated")
    small_weighed = render_value(80, 78, 82, estimate_method="weighed")
    assert big_estimate["weight"] == "light" and small_weighed["weight"] == "solid"
    assert METHOD_WEIGHT["labelled"] == "solid"


def test_REQ_NUT_062_an_unresolved_food_is_never_rendered_as_a_number():
    """Not zero, not a dash with a tooltip: the words."""
    out = render_value(None, None, None, estimate_method="estimated", status=UNRESOLVED)
    assert out["numeric"] is False and out["text"] == "not resolved"
    assert "not zero" in out["note"]


def test_REQ_NUT_046_analysis_either_restricts_to_tight_methods_or_weights_by_width():
    """What is not available is treating a voice-logged estimate and a weighed portion as equally
    informative, which is what an unweighted correlation does."""
    rows = [{"estimate_method": "weighed", "kcal_low": 78, "kcal_high": 82},
            {"estimate_method": "estimated", "kcal_low": 200, "kcal_high": 800}]
    assert [r["estimate_method"] for r in analysis_rows(rows)] == ["weighed"]
    weighted = analysis_rows(rows, mode="weight")
    assert weighted[0]["weight"] > weighted[1]["weight"], "the tight interval counts for more"
    assert set(TIGHT_METHODS) == {"weighed", "labelled", "portion_alias"}


def test_REQ_NUT_047_an_interval_wider_than_the_difference_says_so_in_plain_words():
    """A day logged by voice routinely has a 500 kcal width. Reporting a 300 kcal deficit against
    it is reporting a difference the data cannot see, and the number would be believed."""
    out = deficit_statement({"kcal_low": 1600, "kcal_high": 2400, "kcal_point": 2000}, 2300)
    assert out["resolvable"] is False
    assert "cannot resolve that difference" in out["text"]

    tight = deficit_statement({"kcal_low": 1980, "kcal_high": 2020, "kcal_point": 2000}, 2300)
    assert tight["resolvable"] is True and "300 kcal below" in tight["text"]


def test_REQ_NUT_048_no_red_green_over_under_or_pass_fail_framing():
    assert check_framing({"text": "2,000 kcal across 4 items."}) == ()
    assert check_framing({"text": "You went over budget today"})
    assert check_framing({"colour": "red", "text": "x"})
    assert any("REQ-NUT-048" in v for v in check_framing({"text": "off track"}))


def test_REQ_NUT_064_a_low_logged_intake_is_never_called_a_deficiency():
    """"Deficiency" is a clinical term with a clinical meaning, and a low LOGGED intake is a fact
    about the logging at least as often as about the eating."""
    v = check_framing({"text": "Your iron looks deficient"})
    assert any("REQ-NUT-064" in x for x in v)
    assert any("about the logging" in x for x in v)


def test_REQ_NUT_041_vision_confidence_never_narrows_a_quantity_interval():
    """Its confidence is about IDENTIFICATION — how sure it is that this is a bagel. The interval
    is about QUANTITY, and a confident identification says nothing about how big it was."""
    out = confidence_may_not_narrow((200, 800), vision_confidence=0.99)
    assert out["interval"] == (200, 800) and out["narrowed"] is False
    assert "not portion size" in out["note"]


def test_REQ_NUT_027_unresolved_is_a_normal_outcome_not_a_failure_state():
    """Shown as a failure it reads as something Joe did wrong; shown as a normal outcome it reads
    as a question he can answer, which is what it is."""
    out = unresolved_is_not_an_error({"name": "the thing from the deli"})
    assert out["is_error"] is False and out["severity"] == "normal"
    assert "tell me what this was" in out["text"]
