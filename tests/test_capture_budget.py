"""B16 §B.1/§B.2/§B.3/§G.2 — the neuron budget and refusal (REQ-CAP-030..046, 100..107).

RULE-28 forbids billing on overage, and REQ-CAP-042 makes the 10,000-neuron hard fail the
ENFORCEMENT MECHANISM for that rather than a nuisance to route around.
"""
import datetime as dt

import pytest

from tools.engines.capture_budget import (CAPTURE_NEVER, DEFERRED, EMPTY_TRANSCRIPT_MIN_SECONDS,
                                          FORBIDDEN_MODEL, HARD_CAP, NEURONS_PER_AUDIO_MINUTE,
                                          PENDING, PaidUsageForbidden, SOFT_CEILING,
                                          TRANSCRIPTION_MODEL, TRANSCRIPTION_PARAMS,
                                          assert_no_paid_usage, capture_with_everything_down,
                                          check_capture_path, deferred_indicator, deferred_queue,
                                          estimated_neurons, ios_dictation, may_call,
                                          on_allowance_exhausted, on_transcript,
                                          store_transcription, transcription_request)

DAY = dt.date(2026, 9, 10)


def test_REQ_CAP_030_the_tiny_model_is_refused_by_name():
    with pytest.raises(ValueError, match="REQ-CAP-030"):
        transcription_request(b"a", model=FORBIDDEN_MODEL)
    assert transcription_request(b"a")["model"] == TRANSCRIPTION_MODEL


def test_REQ_CAP_031_033_the_three_parameters_are_asserted_not_assumed():
    """`condition_on_previous_text=False` matters more than it looks: with it on, Whisper carries
    context between segments and will continue a sentence it hallucinated, so one bad segment
    contaminates the rest of the transcript."""
    r = transcription_request(b"a")
    for k, v in TRANSCRIPTION_PARAMS.items():
        assert r[k] == v
    for k, bad in (("language", "fr"), ("vad_filter", False),
                   ("condition_on_previous_text", True)):
        with pytest.raises(ValueError, match="REQ-CAP-031..033"):
            transcription_request(b"a", params={k: bad})


def test_REQ_CAP_034_both_the_text_and_the_segment_timings_are_stored():
    """The timings are what make a later correction possible: without them a re-read of the audio
    has no way to locate the part that was wrong."""
    out = store_transcription({"capture_id": 1},
                              {"text": "had a bagel", "segments": [{"start": 0.0, "end": 1.2}]})
    assert out["transcript"] == "had a bagel"
    assert out["segments"] == ({"start": 0.0, "end": 1.2},)


def test_REQ_CAP_036_the_cost_formula_is_duration_over_sixty_times_46_63():
    assert NEURONS_PER_AUDIO_MINUTE == 46.63
    assert estimated_neurons(60) == pytest.approx(46.63)
    assert estimated_neurons(30) == pytest.approx(23.315)
    assert estimated_neurons(0) == 0.0


def test_REQ_CAP_036_the_estimate_is_not_rounded_to_a_whole_neuron():
    """The daily sum is compared against a ceiling, and rounding each call to an integer would
    drift the total by more than the margin the reservation depends on."""
    assert estimated_neurons(7) != round(estimated_neurons(7))


def test_REQ_CAP_037_a_new_capture_must_fit_under_the_soft_ceiling():
    assert may_call(spent_today=8_000, pending_cost=500)["allowed"] is True
    assert may_call(spent_today=SOFT_CEILING, pending_cost=1)["allowed"] is False
    assert may_call(spent_today=8_999, pending_cost=1)["allowed"] is True, "exactly 9,000 fits"


def test_REQ_CAP_038_039_the_margin_is_reserved_exclusively_for_deferred_retries():
    """Without the reservation a busy day starves yesterday's backlog permanently: the deferred
    captures are older, their audio is sitting on a phone, and they lose every race."""
    new = may_call(spent_today=9_500, pending_cost=100)
    retry = may_call(spent_today=9_500, pending_cost=100, is_deferred_retry=True)
    assert new["allowed"] is False and new["ceiling"] == SOFT_CEILING
    assert retry["allowed"] is True and retry["ceiling"] == HARD_CAP


def test_REQ_CAP_038_a_refused_new_capture_is_deferred_not_dropped():
    out = may_call(spent_today=9_500, pending_cost=100)
    assert out["refusal"].processing_status == DEFERRED
    assert out["refusal"].audio_retained is True
    assert out["refusal"].last_error == "neuron_cap"


def test_REQ_CAP_039_even_a_deferred_retry_stops_at_the_hard_cap():
    assert may_call(spent_today=HARD_CAP, pending_cost=1, is_deferred_retry=True)["allowed"] \
        is False


def test_REQ_CAP_042_paid_usage_and_a_payment_method_are_both_refused():
    """A soft check in application code fails open the day somebody edits it. An account with no
    payment method fails closed forever."""
    assert assert_no_paid_usage({"payment_method_attached": False})
    for bad in ({"payment_method_attached": True}, {"paid_usage_enabled": True}):
        with pytest.raises(PaidUsageForbidden, match="REQ-CAP-042"):
            assert_no_paid_usage(bad)


def test_REQ_CAP_041_043_an_exhausted_allowance_never_truncates_the_audio():
    """A capture lost to a budget ceiling would be lost to an accounting decision, which is the
    least defensible reason to lose anything."""
    out = on_allowance_exhausted({"capture_id": 1, "audio": b"...", "transcript": None})
    assert out["processing_status"] == DEFERRED and out["last_error"] == "neuron_cap"
    assert out["audio"] == b"..." and out["audio_retained"] is True
    assert out["processing_status"] != "enriched"


def test_REQ_CAP_040_deferred_captures_run_first_oldest_first():
    """A deferred capture's audio is sitting on a phone and the person who recorded it has moved
    on; the oldest is the one closest to being forgotten."""
    caps = [
        {"capture_id": "new", "captured_at": dt.datetime(2026, 9, 10, 9)},
        {"capture_id": "old_deferred", "captured_at": dt.datetime(2026, 9, 8, 20),
         "processing_status": DEFERRED},
        {"capture_id": "newer_deferred", "captured_at": dt.datetime(2026, 9, 9, 20),
         "processing_status": DEFERRED},
    ]
    order = [c["capture_id"] for c in deferred_queue(caps, now_utc_day=DAY)]
    assert order == ["old_deferred", "newer_deferred", "new"]


def test_REQ_CAP_044_the_deferred_indicator_states_the_count_and_the_reason():
    caps = [{"processing_status": DEFERRED}, {"processing_status": DEFERRED},
            {"processing_status": "enriched"}]
    ind = deferred_indicator(caps)
    assert ind["count"] == 2
    assert ind["reason"] == "waiting for tomorrow's AI budget"
    assert ind["text"] == "2 captures waiting for tomorrow's AI budget"
    assert deferred_indicator([{"processing_status": "enriched"}])["visible"] is False


def test_REQ_CAP_045_empty_is_not_the_same_as_failed_and_neither_is_complete():
    """A transcript of "" for two seconds is plausibly silence. The same for eleven seconds is a
    transcription that did not work, and treating it as a successful empty capture would file
    real speech as nothing."""
    silent = on_transcript({"capture_id": 1}, "", duration_seconds=EMPTY_TRANSCRIPT_MIN_SECONDS)
    assert silent["processing_status"] == "enriched", "short silence is a real empty capture"

    lost = on_transcript({"capture_id": 2}, "", duration_seconds=11)
    assert lost["processing_status"] == PENDING
    assert lost["last_error"] == "empty_transcript" and lost["review_list"] is True


def test_REQ_CAP_043_a_failed_transcription_is_never_marked_complete():
    out = on_transcript({"capture_id": 1}, None, duration_seconds=8)
    assert out["processing_status"] == PENDING
    assert out["processing_status"] != "enriched"
    assert out["review_list"] is True


def test_REQ_CAP_046_ios_dictation_costs_nothing_and_is_not_re_transcribed():
    """Re-transcribing would spend neurons to reproduce text the phone already produced, against
    the budget that is the binding constraint on the whole subsystem."""
    out = ios_dictation({"capture_id": 1}, "had a bagel")
    assert out["transcript_source"] == "ios_dictation"
    assert out["workers_ai_call"] is False and out["estimated_neurons"] == 0.0


# ---------------------------------------------------------------- §G.2

def test_REQ_CAP_100_107_the_eight_things_capture_may_never_do():
    clean = {"event_time_field": "captured_at", "pwa_permissions": [],
             "missing_log_framing": "coverage"}
    assert check_capture_path(clean) == ()
    for key, code in (("blocks_on_network", "REQ-CAP-100"),
                      ("has_required_field", "REQ-CAP-100"),
                      ("asks_confirmation", "REQ-CAP-102"),
                      ("drops_on_enrichment_failure", "REQ-CAP-103"),
                      ("mutates_raw_captures", "REQ-CAP-105")):
        v = check_capture_path({**clean, key: True})
        assert any(x.startswith(code) for x in v), key


def test_REQ_CAP_104_the_receive_time_is_never_the_event_time():
    v = check_capture_path({"event_time_field": "received_at"})
    assert any(x.startswith("REQ-CAP-104") for x in v)


def test_REQ_CAP_106_the_pwa_requests_no_camera_microphone_or_geolocation():
    for perm in ("camera", "microphone", "geolocation"):
        v = check_capture_path({"event_time_field": "captured_at", "pwa_permissions": [perm]})
        assert any(x.startswith("REQ-CAP-106") for x in v), perm


def test_REQ_CAP_107_a_missing_log_is_coverage_not_guilt():
    v = check_capture_path({"event_time_field": "captured_at", "missing_log_framing": "streak"})
    assert any(x.startswith("REQ-CAP-107") for x in v)
    assert len(CAPTURE_NEVER) == 7


def test_REQ_CAP_101_with_every_service_down_the_capture_still_completes():
    """The property the whole subsystem is arranged around, so it is a function rather than a
    comment: nothing in this path touches a network, a database or a model."""
    q = []
    out = capture_with_everything_down({"text": "had a bagel"}, q)
    assert out["completed"] is True and out["queued"] is True
    assert out["services_contacted"] == ()
    assert len(q) == 1
