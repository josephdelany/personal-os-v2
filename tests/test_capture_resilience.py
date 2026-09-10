"""B16 §A.5/§A.6/§F.1 — offline, downstream failure, the attention budget
(REQ-CAP-019..029, 080..086).

A spoken sentence about what Joe just ate exists exactly once, for about four seconds. A
transaction can be re-imported next month; this cannot. Most of these tests are about not losing
it, and the rest are about not exhausting the person producing it.
"""
import datetime as dt

import pytest

from tools.engines.capture_resilience import (ACK_STATUSES, BucketingViolation,
                                              MAX_CHECKIN_ITEMS, MAX_ITEMS_ANY_SCREEN,
                                              MAX_REVIEW_ITEMS, PENDING_STALL_HOURS,
                                              QUEUE_TIMEOUT_S, RESOLUTION_STALE_HOURS,
                                              assert_not_bucketed_by_received_at, check_screen,
                                              draft_policy, event_time, ingest_result,
                                              nightly_retry_set, on_network_failure,
                                              on_review_abandoned, replay,
                                              replay_stops_at_first_failure,
                                              resolution_staleness_alert, review_list, stalled,
                                              transcription_provider, unsynced_indicator)

NOW = dt.datetime(2026, 9, 10, 8, 0)


# ---------------------------------------------------------------- §A.5 offline

def test_REQ_CAP_019_a_network_failure_queues_locally_and_shows_NO_error_dialog():
    """The absence of the dialog is the requirement. An error at the moment of capture teaches
    Joe that capturing sometimes fails, and the lesson he draws is to stop bothering."""
    q = []
    out = on_network_failure({"text": "had a bagel"}, q, error="ENOTCONN")
    assert out["queued"] is True
    assert out["show_error_dialog"] is False
    assert len(q) == 1 and "bagel" in q[0]


def test_REQ_CAP_019_a_ten_second_timeout_queues_as_well_as_an_error():
    q = []
    assert on_network_failure({"t": 1}, q, elapsed_s=QUEUE_TIMEOUT_S)["queued"] is True
    assert on_network_failure({"t": 2}, q, elapsed_s=QUEUE_TIMEOUT_S - 1)["queued"] is False
    assert len(q) == 1


def test_REQ_CAP_020_a_line_leaves_the_queue_only_on_an_acknowledgement():
    """Removing on send rather than on acknowledgement loses exactly the captures that were
    hardest to make: the ones sent while the connection was bad."""
    assert ACK_STATUSES == (200, 202)
    q = ["a", "b", "c"]
    out = replay(q, post=lambda line: 202 if line != "b" else 500)
    assert out["sent"] == ("a", "c")
    assert q == ["b"], "the unacknowledged line stays"


def test_REQ_CAP_020_the_queue_is_posted_in_file_order():
    seen = []
    q = ["1", "2", "3"]
    replay(q, post=lambda l: seen.append(l) or 202)
    assert seen == ["1", "2", "3"]


def test_REQ_CAP_020_a_poisoned_line_does_not_block_every_capture_behind_it():
    """Stop-on-failure is available but is NOT the default: a single bad line would otherwise
    block every capture behind it forever."""
    q = ["bad", "good"]
    replay(q, post=lambda l: 500 if l == "bad" else 202)
    assert q == ["bad"], "the good line still went"

    q2 = ["bad", "good"]
    out = replay_stops_at_first_failure(q2, post=lambda l: 500 if l == "bad" else 202)
    assert out["sent_count"] == 0 and q2 == ["bad", "good"]


def test_REQ_CAP_021_022_captured_at_is_the_event_time_and_received_at_may_bucket_nothing():
    """A capture queued Tuesday night and replayed Wednesday morning is a TUESDAY capture.
    Offline captures are not random — they cluster where the signal is bad, which for Joe means
    exactly the places worth knowing about."""
    tuesday = dt.datetime(2026, 9, 8, 22, 30)
    wednesday = dt.datetime(2026, 9, 9, 7, 10)
    assert event_time({"captured_at": tuesday, "received_at": wednesday}) == tuesday
    assert assert_not_bucketed_by_received_at("captured_at")
    with pytest.raises(BucketingViolation, match="REQ-CAP-022"):
        assert_not_bucketed_by_received_at("received_at")


def test_REQ_CAP_023_the_local_draft_outlives_the_post():
    """Deleting on POST would lose the draft to the one failure mode that matters: a POST that
    left but never arrived."""
    p = draft_policy()
    assert p["debounce_s"] == 1 and p["post_interval_s"] == 30
    assert p["retain_local_until"] == "server_ack"


def test_REQ_CAP_024_the_unsynced_indicator_states_an_exact_count():
    """"3 entries not yet saved" is actionable; "something is unsynced" is anxiety with no next
    step."""
    assert unsynced_indicator(0)["visible"] is False
    one = unsynced_indicator(1)
    assert one["count"] == 1 and one["text"] == "1 entry not yet saved"
    assert one["persistent"] is True
    assert unsynced_indicator(3)["text"] == "3 entries not yet saved"


# ---------------------------------------------------------------- §A.6 downstream failure

def test_REQ_CAP_025_a_downstream_failure_still_returns_202_to_the_shortcut():
    """The capture is SAFE the moment it is stored. Surfacing a downstream error would report a
    failure for something that already succeeded, and the Shortcut's only response would be to
    make Joe do it again."""
    out = ingest_result(stored=True, enrichment_status=503, provider_error="upstream_unavailable")
    assert out["http_status"] == 202
    assert out["processing_status"] == "pending_enrichment"
    assert out["last_error"] == "upstream_unavailable"


def test_REQ_CAP_025_a_successful_enrichment_is_not_marked_pending():
    out = ingest_result(stored=True, enrichment_status=200)
    assert out["http_status"] == 202 and out["processing_status"] == "enriched"
    assert "last_error" not in out


def test_REQ_CAP_025_a_failure_to_STORE_is_a_real_error():
    """The 202 is about downstream enrichment, not about losing the capture."""
    assert ingest_result(stored=False)["http_status"] == 500


def test_REQ_CAP_026_every_pending_row_is_retried_nightly():
    rows = [{"capture_id": 1, "processing_status": "pending_enrichment"},
            {"capture_id": 2, "processing_status": "enriched"}]
    assert [r["capture_id"] for r in nightly_retry_set(rows)] == [1]


def test_REQ_CAP_027_over_seventy_two_hours_pending_becomes_a_review_item_not_another_retry():
    """Retrying forever hides a provider that has changed its contract. 72 hours is three nightly
    attempts: enough for a transient outage, few enough that a real breakage surfaces while Joe
    still remembers the captures involved."""
    rows = [{"capture_id": 1, "processing_status": "pending_enrichment",
             "pending_since": NOW - dt.timedelta(hours=PENDING_STALL_HOURS + 1)},
            {"capture_id": 2, "processing_status": "pending_enrichment",
             "pending_since": NOW - dt.timedelta(hours=PENDING_STALL_HOURS - 1)}]
    out = stalled(rows, now=NOW)
    assert [r["capture_id"] for r in out] == [1]
    assert out[0]["reason"] == "enrichment_stalled"


def test_REQ_CAP_028_transcription_is_selected_by_one_environment_variable():
    """A provider swap that requires touching every call site is a swap nobody makes, and the
    system stays on a provider it has outgrown."""
    assert transcription_provider({"TRANSCRIPTION_PROVIDER": "workers_ai"})["selected"] == \
        "workers_ai"
    unset = transcription_provider({})
    assert unset["selected"] is None and "not configured" in unset["reason"]


def test_REQ_CAP_029_one_push_after_forty_eight_hours_stating_the_hours():
    """One, not a stream: a repeating alarm about a job Joe cannot fix from his phone is a
    notification he turns off, and then he misses the next one that matters."""
    stale = resolution_staleness_alert(NOW - dt.timedelta(hours=RESOLUTION_STALE_HOURS + 2),
                                       now=NOW)
    assert stale["push"] is True and stale["hours_elapsed"] == 50.0
    assert "50 hours ago" in stale["text"]
    assert resolution_staleness_alert(NOW - dt.timedelta(hours=RESOLUTION_STALE_HOURS - 1),
                                      now=NOW) is None
    assert resolution_staleness_alert(NOW - dt.timedelta(hours=100), now=NOW,
                                      already_sent=True) is None


def test_REQ_CAP_029_a_job_that_has_never_run_is_also_reported():
    a = resolution_staleness_alert(None, now=NOW)
    assert a["push"] is True and "never completed" in a["text"]


# ---------------------------------------------------------------- §F.1 the attention budget

def test_REQ_CAP_080_081_the_morning_check_in_is_five_items_and_three_scales():
    """A screen that asks for six things gets four answered and then abandoned, and the
    abandonment is permanent."""
    assert check_screen({"name": "morning_checkin", "items": MAX_CHECKIN_ITEMS,
                         "rating_scales": 3}) == ()
    v = check_screen({"name": "morning_checkin", "items": 6, "rating_scales": 4})
    assert any("REQ-CAP-080" in x for x in v) and any("REQ-CAP-081" in x for x in v)


def test_REQ_CAP_082_no_capture_screen_exceeds_twenty_six_items():
    assert check_screen({"name": "anything", "items": MAX_ITEMS_ANY_SCREEN}) == ()
    assert any("REQ-CAP-082" in x
               for x in check_screen({"name": "anything", "items": 27}))


def test_REQ_CAP_083_meal_capture_is_four_actions_trigger_shutter_speak_done():
    assert check_screen({"name": "meal_capture", "items": 1, "user_actions": 4}) == ()
    assert any("REQ-CAP-083" in x
               for x in check_screen({"name": "meal_capture", "items": 1, "user_actions": 5}))


def test_REQ_CAP_084_the_evening_screen_shows_the_day_before_asking_for_recall():
    """Recall is expensive and inaccurate. Showing the day first turns "what did you do" into
    "is this right", which is a different and much cheaper task."""
    v = check_screen({"name": "evening_reflection", "items": 3,
                      "shows_captured_before_recall": False})
    assert any("REQ-CAP-084" in x for x in v)
    assert check_screen({"name": "evening_reflection", "items": 3,
                         "shows_captured_before_recall": True}) == ()


def test_REQ_CAP_085_five_review_items_an_evening_widest_interval_first():
    """Interval width IS the uncertainty: the item Joe can most improve by answering is the one
    the system is least sure about."""
    items = [{"id": i, "interval_low": 0, "interval_high": i} for i in range(10)]
    page = review_list(items)
    assert len(page) == MAX_REVIEW_ITEMS == 5
    assert [i["id"] for i in page] == [9, 8, 7, 6, 5]


def test_REQ_CAP_086_leaving_the_review_screen_changes_nothing_and_never_re_prompts():
    """Leaving is an answer: not now. Re-raising the same items tomorrow converts a review list
    into a backlog, and a backlog is a thing people stop opening."""
    rows = [{"id": 1, "provenance": "inferred"}, {"id": 2, "provenance": "defaulted"}]
    out = on_review_abandoned(rows)
    assert out["reprompt"] is False
    assert out["rows_unchanged"] == tuple(rows)
