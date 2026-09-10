"""B16 §C.4/§F.2 — vision extraction and prompt scheduling
(REQ-CAP-032, 067..072, 087..092, 110, 111).
"""
import pytest

from tools.engines.vision_and_prompts import (CONSISTENCY_TEMPERATURE, DELIVERY_CHANNEL,
                                              FORBIDDEN_CHANNELS, MAX_SCHEDULED_PROMPTS_PER_DAY,
                                              PROMPT_LEAD_MINUTES, PromptViolation,
                                              SCHEDULE_MIN_DAYS, TIME_BUCKETS, VISION_FIELDS,
                                              VisionViolation, check_channel, check_pinned_models,
                                              check_prompt_timing, compute_schedule,
                                              consistency_flags, location_capture,
                                              observed_absent, prompt_times, reconcile,
                                              structure_via_text_model, time_bucket,
                                              vision_request)


def test_REQ_CAP_068_the_vision_model_is_asked_for_four_things_and_no_more():
    """NOT grams, not calories, not a serving size. A vision model asked "how many grams" will
    answer, and the answer is a guess about a photograph's scale dressed as a measurement."""
    assert VISION_FIELDS == ("name", "confidence", "portion_cue", "count")
    assert vision_request(VISION_FIELDS)["portion_cue_is_a_string"] is True
    for extra in ("grams", "calories", "serving_size", "kcal"):
        with pytest.raises(VisionViolation, match="REQ-CAP-068"):
            vision_request(VISION_FIELDS + (extra,))


def test_REQ_CAP_069_dictation_wins_and_the_discarded_vision_value_is_KEPT():
    """The photo shows what was on the plate; the sentence says what Joe ate. Those differ
    predictably — a shared dish, a plate he did not finish, something eaten before the photo."""
    out = reconcile({"name": "half a bagel", "count": 1},
                    {"name": "bagel", "count": 2})
    assert out["resolved"]["name"] == "half a bagel" and out["resolved"]["count"] == 1
    fields = {c["field"] for c in out["conflicts"]}
    assert fields == {"name", "count"}
    assert all(c["table"] == "extraction_conflicts" for c in out["conflicts"])
    assert out["conflicts"][0]["kept_source"] == "dictation"


def test_REQ_CAP_069_agreement_records_no_conflict():
    assert reconcile({"name": "bagel", "count": 1}, {"name": "bagel", "count": 1})["conflicts"] \
        == ()


def test_REQ_CAP_070_a_vision_model_without_response_format_gets_a_two_step_path():
    """Prose from the vision model, structure from a text model under a JSON Schema — not
    free-text parsed by regex, because the schema is what makes the span assertion possible at
    all, and a path that skips it is a path where the model may add."""
    out = structure_via_text_model(False, prose="a bagel and cream cheese",
                                   text_model=lambda p: {"items": [{"name": "bagel"}]})
    assert out["path"] == "prose_then_text_model" and out["schema_enforced"] is True
    assert structure_via_text_model(True, prose=None,
                                    text_model=None)["path"] == "direct"


def test_REQ_CAP_071_a_model_id_missing_from_the_catalog_fails_the_run():
    """Non-zero exit rather than a fallback: a model that has left the catalogue is a silent
    change in what the system extracts, and falling back would make it invisible exactly when it
    starts mattering."""
    assert check_pinned_models(["@cf/a"], ["@cf/a", "@cf/b"])["exit_code"] == 0
    with pytest.raises(VisionViolation, match="REQ-CAP-071"):
        check_pinned_models(["@cf/a", "@cf/gone"], ["@cf/a"])


def test_REQ_CAP_072_a_field_that_differs_between_two_runs_is_flagged():
    """A field that differs between two runs is one the model was not sure about — information
    its own confidence score does not reliably carry."""
    out = consistency_flags({"name": "bagel", "count": 1}, {"name": "bagel", "count": 2})
    assert out["name"]["consistency_flag"] is True
    assert out["count"]["consistency_flag"] is False
    assert CONSISTENCY_TEMPERATURE == 0.7


def test_REQ_CAP_072_a_field_present_in_only_one_run_is_inconsistent():
    out = consistency_flags({"name": "bagel"}, {"name": "bagel", "portion_cue": "half"})
    assert out["portion_cue"]["consistency_flag"] is False


def test_REQ_CAP_067_an_evening_reflection_item_gets_a_BUCKET_never_a_clock_time():
    """Joe writing at 21:00 about lunch does not know when lunch was, and a recalled clock time
    is an invention with a plausible shape."""
    out = time_bucket("midday", source="pwa_text", field="evening_reflection")
    assert out["time_bucket"] == "midday" and out["clock_time_emitted"] is False
    assert TIME_BUCKETS == ("morning", "midday", "afternoon", "evening", "night")
    with pytest.raises(VisionViolation, match="REQ-CAP-067"):
        time_bucket("13:40", source="pwa_text", field="evening_reflection")
    assert time_bucket("midday", source="ios_shortcut", field="x") is None


def test_REQ_CAP_111_a_stated_non_occurrence_is_observed_absent_not_unknown():
    """RULE-07 in one line: a day Joe SAYS he did not drink is evidence about drinking, and a day
    with no entry is not. Collapsing them makes his statement worth as much as his silence."""
    out = observed_absent("I did not drink today", subject="alcohol")
    assert out["presence"] == "observed_absent" and out["is_evidence"] is True
    assert out["presence"] != "unknown"


def test_REQ_CAP_110_a_location_capture_is_stored_raw_and_ROUTED_to_the_restricted_path():
    """Routed rather than handled inline, because the restricted path is where the home-coordinate
    and egress-precision rules live — a coordinate taking the ordinary path is one they never
    saw."""
    out = location_capture({"fixes": 3}, source="location")
    assert out["route_to"] == "restricted_coordinate_path"
    assert out["handled_inline"] is False
    assert out["raw_captures"]["source"] == "location"
    assert location_capture({}, source="ios_shortcut") is None


# ---------------------------------------------------------------- §F.2

def test_REQ_CAP_089_the_schedule_needs_fourteen_days_and_uses_the_MEDIAN():
    """The median rather than the mean: one 02:00 kebab should not move the dinner prompt by half
    an hour, and it would."""
    caps = [{"occasion": "dinner", "minutes_from_midnight": m}
            for m in (1140, 1150, 1130, 120)]      # three ~19:00 and one 02:00
    out = compute_schedule(caps, occasions=["dinner"], days_of_data=SCHEDULE_MIN_DAYS)
    assert out["schedule"][0]["median_minutes"] == 1135
    assert out["schedule"][0]["median_minutes"] > 1000, "the 02:00 outlier must not drag it"
    assert compute_schedule(caps, occasions=["dinner"],
                            days_of_data=SCHEDULE_MIN_DAYS - 1)["schedule"] == ()


def test_REQ_CAP_090_a_prompt_is_sent_fifteen_minutes_before_the_median_eating_time():
    """It arrives while Joe is deciding what to eat, which is the difference between a
    notification he acts on and one he turns off."""
    out = prompt_times([{"occasion": "dinner", "median_minutes": 1140, "n": 20}])
    assert out[0]["send_at_minutes"] == 1140 - PROMPT_LEAD_MINUTES == 1125
    assert out[0]["derived_from"] == "median_eating_time" and out[0]["random"] is False


def test_REQ_CAP_087_a_randomly_timed_prompt_is_refused():
    assert check_prompt_timing({"send_at_minutes": 1125})
    for bad in ({"random": True}, {"jitter_minutes": 20}):
        with pytest.raises(PromptViolation, match="REQ-CAP-087"):
            check_prompt_timing(bad)


def test_REQ_CAP_088_no_more_than_three_scheduled_prompts_a_day():
    three = [{"occasion": o, "median_minutes": 600 + 200 * i, "n": 20}
             for i, o in enumerate(("breakfast", "lunch", "dinner"))]
    assert len(prompt_times(three)) == MAX_SCHEDULED_PROMPTS_PER_DAY == 3
    with pytest.raises(PromptViolation, match="REQ-CAP-088"):
        prompt_times(three + [{"occasion": "snack", "median_minutes": 900, "n": 5}])


def test_REQ_CAP_091_the_schedule_recomputes_monthly_from_trailing_data():
    out = compute_schedule([{"occasion": "dinner", "minutes_from_midnight": 1140}],
                           occasions=["dinner"], days_of_data=30)
    assert out["recompute"] == "monthly"


def test_REQ_CAP_092_prompts_are_web_push_and_never_sms_or_email():
    """SMS and email are channels Joe reads for other reasons, and a capture prompt arriving among
    them competes with things that matter more and loses."""
    assert check_channel(DELIVERY_CHANNEL)
    for bad in FORBIDDEN_CHANNELS:
        with pytest.raises(PromptViolation, match="REQ-CAP-092"):
            check_channel(bad)


def test_REQ_CAP_032_vad_filter_is_sent_on_every_transcription_request():
    """Named here as well as in the parameter block: without voice-activity detection, Whisper
    transcribes silence into plausible words, and a hallucinated sentence in a capture is
    indistinguishable from something Joe said."""
    from tools.engines.capture_budget import TRANSCRIPTION_PARAMS, transcription_request
    assert TRANSCRIPTION_PARAMS["vad_filter"] is True
    assert transcription_request(b"audio")["vad_filter"] is True
    with pytest.raises(ValueError, match="REQ-CAP-031..033"):
        transcription_request(b"audio", params={"vad_filter": False})
