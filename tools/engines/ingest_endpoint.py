"""B16 §A.1..A.4 — the ingest endpoint contract (REQ-CAP-003..018).

Pure: no database, no network, no clock. The request comes in as a dict; what comes back is the
status, the body and the rows to write.

WHY THE ROW IS INSERTED BEFORE ANY MODEL CALL (REQ-CAP-011). Everything downstream — the
transcript, the extraction, the resolution — is a recomputable view over the raw capture. The
capture is not. So it is stored first, and the 202 is returned once THAT insert commits, not once
the enrichment succeeds. A capture lost while waiting for a model is lost permanently, and the
model is the least reliable thing in the path.

WHY THE `capture_id` COMES FROM THE CLIENT (REQ-CAP-016/017/018). The Shortcut generates it
before the first attempt, so the SAME id survives a timeout, a queue, and an hourly replay.
Generating it server-side would give every retry a new identity, and the offline queue — which
retries by design — would duplicate every capture it ever held.

`ON CONFLICT DO NOTHING` plus a 200 with `{"status":"duplicate"}` closes the loop: the Shortcut
learns the capture is safe, removes the line from its queue, and no second enrichment job is
enqueued for work already done.

WHY A BAD TOKEN MEANS THE BODY IS NEVER READ (REQ-CAP-008). Parsing an unauthenticated body is
doing work on behalf of whoever sent it, and the body of a capture request is audio.

WHY THE RAW ROW IS NEVER MODIFIED BY A CORRECTION (REQ-CAP-013/014). The transcript is the
evidence. A correction supersedes the DERIVED row and leaves the capture untouched, so "what did
Joe actually say" survives every later opinion about what he meant.
"""
from __future__ import annotations

from dataclasses import dataclass

IMAGE_LONGEST_EDGE = 1024                     # REQ-CAP-010
PWA_IMAGE_MECHANISM = '<input type="file" accept="image/*" capture="environment">'  # REQ-CAP-004
PWA_WRITABLE_FIELDS = ("morning_checkin", "evening_reflection")                     # REQ-CAP-005
# REQ-CAP-012. Columns the ingest role may never UPDATE or DELETE.
FROZEN_COLUMNS = ("payload", "captured_at", "source", "capture_id")
IDENTITY_FIELDS = ("capture_id", "captured_at")                                     # REQ-CAP-007


class IngestViolation(Exception):
    pass


def check_byte_origin(source):
    """REQ-CAP-003. Every audio and image byte originates in the capture Shortcut.

    The Shortcut is the only path with no browser permission prompt in it, which is what makes
    capture a two-second act rather than a negotiation.
    """
    if source != "ios_shortcut":
        raise IngestViolation(
            f"REQ-CAP-003: audio and image bytes originate in the capture Shortcut, not {source!r}")
    return True


def pwa_image_mechanism(mechanism):
    """REQ-CAP-004 / RULE-30. A file input with `capture`, and nothing else.

    `<input type="file" capture>` hands the OS camera the job and gives the PWA the result. It
    never asks for a permission, never holds a stream, and cannot be left recording — which
    `getUserMedia` can, and does, when a page is backgrounded badly.
    """
    if mechanism != PWA_IMAGE_MECHANISM:
        raise IngestViolation(
            f"REQ-CAP-004 / RULE-30: a still image is acquired with {PWA_IMAGE_MECHANISM} and by "
            f"no other mechanism; getUserMedia holds a stream that can be left recording")
    return True


def pwa_writable(field):
    """REQ-CAP-005. Two writable fields; everything else is a read-only rendering.

    The constraint is what keeps the PWA a surface rather than a second capture path — and a
    second capture path is a second set of rules to keep in step with the first.
    """
    return {"writable": field in PWA_WRITABLE_FIELDS,
            "read_only": field not in PWA_WRITABLE_FIELDS,
            "note": ("The PWA renders what was captured elsewhere. Two fields are the exception, "
                     "and everything else is a view.")}


def resize_image(longest_edge):
    """REQ-CAP-010. 1024 px longest edge, before upload.

    Before upload rather than server-side: the bytes that never leave the phone cost no
    bandwidth on a bad connection, and a capture on a bad connection is the one most likely to
    time out into the offline queue.
    """
    if longest_edge > IMAGE_LONGEST_EDGE:
        raise IngestViolation(
            f"REQ-CAP-010: images resize to a {IMAGE_LONGEST_EDGE}px longest edge before upload; "
            f"bytes that never leave the phone cost nothing on the bad connection where a "
            f"capture is most likely to time out")
    return {"longest_edge": longest_edge, "resized_before_upload": True}


def handle(request, *, expected_token, existing_capture_ids=(), insert=None, enqueue=None):
    """The endpoint. Returns (status, body, rows).

    Order is the contract: authenticate, validate identity, insert, THEN enrich.
    """
    rejections = []

    # REQ-CAP-008. The body is not read. Parsing an unauthenticated body is doing work on behalf
    # of whoever sent it, and the body of a capture request is audio.
    if request.get("bearer_token") != expected_token:
        return {"status": 401, "body": {"error": "unauthorized"}, "body_read": False,
                "rows": ()}

    payload = request.get("body") or {}
    missing = [f for f in IDENTITY_FIELDS if not payload.get(f)]
    if missing:
        # REQ-CAP-007. 400, and the raw body is kept: a rejected capture is still the only copy
        # of whatever it was, and a rejection with no body cannot be replayed after the fix.
        rejections.append({"table": "ingest_rejections", "raw_body": payload,
                           "reason": "missing_identity_fields", "missing": tuple(missing)})
        return {"status": 400, "body": {"error": "missing_identity_fields"},
                "body_read": True, "rows": tuple(rejections)}

    capture_id = payload["capture_id"]
    if capture_id in set(existing_capture_ids):
        # REQ-CAP-016/017. ON CONFLICT DO NOTHING, a 200, and NO second enrichment job.
        return {"status": 200, "body": {"status": "duplicate", "capture_id": capture_id},
                "inserted": False, "enrichment_enqueued": False, "rows": ()}

    # REQ-CAP-011. The row lands BEFORE any model call, and the 202 follows that insert.
    row = {"table": "raw_captures", "capture_id": capture_id,
           "captured_at": payload["captured_at"], "payload": payload,
           "source": payload.get("source", "ios_shortcut"),
           "on_conflict": "do_nothing"}
    if insert is not None:
        insert(row)
    enqueued = False
    if enqueue is not None:
        enqueue(capture_id)          # after the insert, never before
        enqueued = True
    return {"status": 202, "body": {"capture_id": capture_id}, "inserted": True,
            "insert_preceded_model_call": True, "enrichment_enqueued": enqueued,
            "rows": (row,)}


def check_capture_id_origin(payload, *, server_generated=False):
    """REQ-CAP-018. Derived from the client payload only.

    The Shortcut generates it before the first attempt, so the same id survives a timeout, a
    queue and an hourly replay. Generating it server-side would give every retry a new identity,
    and the offline queue — which retries by design — would duplicate every capture it held.
    """
    if server_generated:
        raise IngestViolation(
            "REQ-CAP-018: capture_id comes from the client payload; a server-generated id gives "
            "every retry a new identity, and the offline queue retries by design")
    if not payload.get("capture_id"):
        raise IngestViolation("REQ-CAP-018: the client payload carries the capture_id")
    return payload["capture_id"]


def check_append_only(grants):
    """REQ-CAP-012. UPDATE and DELETE denied on the four frozen columns, for every ingest role."""
    bad = []
    for role, perms in (grants or {}).items():
        for col in FROZEN_COLUMNS:
            for verb in ("UPDATE", "DELETE"):
                if col in (perms.get(verb) or ()):
                    bad.append(f"{role} may {verb} raw_captures.{col}")
    if bad:
        raise IngestViolation(f"REQ-CAP-012: raw_captures is append-only; {bad}")
    return True


def recomputable_view(derived_row, *, raw_capture_id):
    """REQ-CAP-013. Everything derived is a view over a transcript retained indefinitely."""
    if not raw_capture_id:
        raise IngestViolation(
            "REQ-CAP-013: every extracted, resolved and derived row traces to the raw capture it "
            "is a view over")
    return {**derived_row, "raw_capture_id": raw_capture_id, "recomputable": True}


def correct_derived(existing, corrected, *, raw_capture_id):
    """REQ-CAP-014. Supersede the derived row; never touch the capture.

    The transcript is the evidence. Leaving it untouched means "what did Joe actually say"
    survives every later opinion about what he meant.
    """
    return {"superseded": {**existing, "is_current": False},
            "new": {**existing, **corrected, "is_current": True,
                    "supersedes": existing.get("id"), "raw_capture_id": raw_capture_id},
            "raw_capture_modified": False}


def extraction_row(row, *, model_id, prompt_version):
    """REQ-CAP-015. `model_id` and `prompt_version` on every extracted row.

    Without both, a change in output cannot be attributed: a different model and a reworded
    prompt produce the same kind of drift, and only these two fields tell them apart.
    """
    for name, v in (("model_id", model_id), ("prompt_version", prompt_version)):
        if not v:
            raise IngestViolation(
                f"REQ-CAP-015: every extraction row records {name}; without both, a change in "
                f"output cannot be attributed to the model or to the prompt")
    return {**row, "model_id": model_id, "prompt_version": prompt_version}
