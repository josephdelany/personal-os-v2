"""B16 §A.1..A.4 — the ingest endpoint contract (REQ-CAP-003..018).

Order is the contract: authenticate, validate identity, insert, THEN enrich.
"""
import pytest

from tools.engines.ingest_endpoint import (FROZEN_COLUMNS, IDENTITY_FIELDS, IMAGE_LONGEST_EDGE,
                                           IngestViolation, PWA_IMAGE_MECHANISM,
                                           PWA_WRITABLE_FIELDS, check_append_only,
                                           check_byte_origin, check_capture_id_origin,
                                           correct_derived, extraction_row, handle,
                                           pwa_image_mechanism, pwa_writable,
                                           recomputable_view, resize_image)

TOKEN = "tok"
GOOD = {"bearer_token": TOKEN,
        "body": {"capture_id": "c-1", "captured_at": "2026-09-10T20:00:00Z",
                 "transcript": "had a bagel"}}


def test_REQ_CAP_008_a_bad_token_returns_401_and_the_body_is_NEVER_read():
    """Parsing an unauthenticated body is doing work on behalf of whoever sent it, and the body
    of a capture request is audio."""
    out = handle({**GOOD, "bearer_token": "wrong"}, expected_token=TOKEN)
    assert out["status"] == 401 and out["body_read"] is False
    assert handle({"body": GOOD["body"]}, expected_token=TOKEN)["status"] == 401


@pytest.mark.parametrize("expected,supplied", [
    (None, None), ("", ""), ("   ", "   "), (False, False), (7, 7),
    ({"token": "value"}, {"token": "value"}), (b"tok", b"tok"),
    (TOKEN, None), (TOKEN, ""), (TOKEN, "wrong"), (TOKEN, TOKEN + " "),
    (TOKEN, "\ud800"),
])
def test_REQ_CAP_008_invalid_credentials_never_read_body_or_invoke_callbacks(expected, supplied):
    class UnreadableBody(dict):
        def get(self, key, default=None):
            assert key != "body", "unauthenticated request body was accessed"
            return super().get(key, default)

    def forbidden_callback(_):
        pytest.fail("unauthenticated request invoked storage or enrichment")

    out = handle(UnreadableBody(bearer_token=supplied), expected_token=expected,
                 insert=forbidden_callback, enqueue=forbidden_callback)
    assert out == {"status": 401, "body": {"error": "unauthorized"},
                   "body_read": False, "rows": ()}


def test_REQ_CAP_008_valid_token_reaches_identity_validation_without_normalisation():
    # Opaque strings compare exactly; non-ASCII input must not make compare_digest crash.
    assert handle({"bearer_token": "valid-\u00e9", "body": {}},
                  expected_token="valid-\u00e9")["status"] == 400
    assert handle({"bearer_token": "valid-e\u0301", "body": {}},
                  expected_token="valid-\u00e9")["status"] == 401


def test_REQ_CAP_007_missing_identity_fields_return_400_and_keep_the_RAW_BODY():
    """A rejected capture is still the only copy of whatever it was, and a rejection with no body
    cannot be replayed after the fix."""
    assert IDENTITY_FIELDS == ("capture_id", "captured_at")
    for missing in IDENTITY_FIELDS:
        body = {k: v for k, v in GOOD["body"].items() if k != missing}
        out = handle({"bearer_token": TOKEN, "body": body}, expected_token=TOKEN)
        assert out["status"] == 400
        row = out["rows"][0]
        assert row["table"] == "ingest_rejections"
        assert row["reason"] == "missing_identity_fields"
        assert row["raw_body"] == body, "the raw body is kept"


def test_REQ_CAP_011_the_row_is_inserted_BEFORE_any_model_call():
    """Everything downstream is a recomputable view over the raw capture. The capture is not. A
    capture lost while waiting for a model is lost permanently, and the model is the least
    reliable thing in the path."""
    order = []
    out = handle(GOOD, expected_token=TOKEN,
                 insert=lambda r: order.append("insert"),
                 enqueue=lambda cid: order.append("enqueue"))
    assert order == ["insert", "enqueue"]
    assert out["status"] == 202 and out["body"]["capture_id"] == "c-1"
    assert out["insert_preceded_model_call"] is True


def test_REQ_CAP_016_017_a_duplicate_returns_200_and_enqueues_NO_second_job():
    """The Shortcut learns the capture is safe, removes the line from its queue, and no second
    enrichment job is enqueued for work already done."""
    calls = []
    out = handle(GOOD, expected_token=TOKEN, existing_capture_ids={"c-1"},
                 insert=lambda r: calls.append("insert"),
                 enqueue=lambda cid: calls.append("enqueue"))
    assert out["status"] == 200
    assert out["body"] == {"status": "duplicate", "capture_id": "c-1"}
    assert out["enrichment_enqueued"] is False
    assert calls == [], "nothing was inserted and nothing was enqueued"


def test_REQ_CAP_016_the_insert_uses_on_conflict_do_nothing():
    row = handle(GOOD, expected_token=TOKEN)["rows"][0]
    assert row["on_conflict"] == "do_nothing"


def test_REQ_CAP_018_the_capture_id_comes_from_the_client_never_the_server():
    """The Shortcut generates it before the first attempt, so the same id survives a timeout, a
    queue and an hourly replay. A server-generated id gives every retry a new identity — and the
    offline queue retries by design."""
    assert check_capture_id_origin({"capture_id": "c-1"}) == "c-1"
    with pytest.raises(IngestViolation, match="REQ-CAP-018"):
        check_capture_id_origin({"capture_id": "c-1"}, server_generated=True)
    with pytest.raises(IngestViolation, match="REQ-CAP-018"):
        check_capture_id_origin({})


def test_REQ_CAP_003_every_audio_and_image_byte_originates_in_the_shortcut():
    """The Shortcut is the only path with no browser permission prompt in it, which is what makes
    capture a two-second act rather than a negotiation."""
    assert check_byte_origin("ios_shortcut")
    for bad in ("pwa", "web_upload", "email"):
        with pytest.raises(IngestViolation, match="REQ-CAP-003"):
            check_byte_origin(bad)


def test_REQ_CAP_004_a_pwa_image_uses_a_file_input_and_no_other_mechanism():
    """`<input type="file" capture>` hands the OS camera the job and gives the PWA the result. It
    never holds a stream, and cannot be left recording — which getUserMedia can."""
    assert pwa_image_mechanism(PWA_IMAGE_MECHANISM)
    with pytest.raises(IngestViolation, match="RULE-30"):
        pwa_image_mechanism("navigator.mediaDevices.getUserMedia")


def test_REQ_CAP_005_the_pwa_writes_two_fields_and_renders_everything_else():
    """The constraint keeps the PWA a surface rather than a second capture path — and a second
    capture path is a second set of rules to keep in step with the first."""
    assert PWA_WRITABLE_FIELDS == ("morning_checkin", "evening_reflection")
    for f in PWA_WRITABLE_FIELDS:
        assert pwa_writable(f)["writable"] is True
    assert pwa_writable("meal_log")["read_only"] is True


def test_REQ_CAP_010_images_resize_to_1024_BEFORE_upload():
    """Bytes that never leave the phone cost nothing on the bad connection where a capture is
    most likely to time out into the offline queue."""
    assert resize_image(IMAGE_LONGEST_EDGE)["resized_before_upload"] is True
    with pytest.raises(IngestViolation, match="REQ-CAP-010"):
        resize_image(4032)


def test_REQ_CAP_012_the_ingest_role_may_not_update_or_delete_the_frozen_columns():
    assert FROZEN_COLUMNS == ("payload", "captured_at", "source", "capture_id")
    assert check_append_only({"ingest": {"INSERT": ["payload"], "SELECT": ["payload"]}})
    with pytest.raises(IngestViolation, match="REQ-CAP-012"):
        check_append_only({"ingest": {"UPDATE": ["payload"]}})
    with pytest.raises(IngestViolation, match="REQ-CAP-012"):
        check_append_only({"ingest": {"DELETE": ["capture_id"]}})


def test_REQ_CAP_013_every_derived_row_traces_to_the_capture_it_is_a_view_over():
    assert recomputable_view({"food": "bagel"}, raw_capture_id="c-1")["recomputable"] is True
    with pytest.raises(IngestViolation, match="REQ-CAP-013"):
        recomputable_view({"food": "bagel"}, raw_capture_id=None)


def test_REQ_CAP_014_a_correction_supersedes_the_derived_row_and_never_touches_the_capture():
    """The transcript is the evidence. Leaving it untouched means "what did Joe actually say"
    survives every later opinion about what he meant."""
    out = correct_derived({"id": "d1", "food": "bagel"}, {"food": "everything bagel"},
                          raw_capture_id="c-1")
    assert out["raw_capture_modified"] is False
    assert out["superseded"]["food"] == "bagel" and out["superseded"]["is_current"] is False
    assert out["new"]["food"] == "everything bagel" and out["new"]["supersedes"] == "d1"


def test_REQ_CAP_015_every_extraction_row_records_the_model_and_the_prompt_version():
    """Without both, a change in output cannot be attributed: a different model and a reworded
    prompt produce the same kind of drift, and only these two fields tell them apart."""
    out = extraction_row({"food": "bagel"}, model_id="@cf/m", prompt_version="p3")
    assert out["model_id"] == "@cf/m" and out["prompt_version"] == "p3"
    for missing in ("model_id", "prompt_version"):
        kw = {"model_id": "@cf/m", "prompt_version": "p3"}
        kw[missing] = None
        with pytest.raises(IngestViolation, match="REQ-CAP-015"):
            extraction_row({}, **kw)
