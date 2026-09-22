"""B16 §B.1/§B.2/§B.3/§G.2 — the neuron budget and refusal (REQ-CAP-030..046, 100..107).

Pure: no database, no network, no clock. Everything takes its inputs.

WHY A BUDGET AT ALL. Workers AI's free allowance is 10,000 neurons a day and RULE-28 forbids
billing on overage. REQ-CAP-042 makes the hard fail at 10,000 the ENFORCEMENT MECHANISM for the
$0 constraint rather than a nuisance to route around: no payment method is attached, so the
account cannot spend money even if this code is wrong.

That is the right shape for a cost control. A soft check in application code fails open the day
somebody edits it; an account with no payment method fails closed forever.

THE 9,000/10,000 SPLIT (REQ-CAP-037/038/039). The soft ceiling is 9,000 and the thousand above it
is reserved EXCLUSIVELY for re-processing captures already deferred. Without the reservation, a
busy day starves yesterday's backlog permanently: every new capture competes with it on equal
terms, and the deferred ones -- which are older, and whose audio is sitting on a phone -- lose
every time. The margin is the only thing that guarantees the backlog eventually drains.

WHY A REFUSAL IS NEVER A DELETION (REQ-CAP-041/043). When the allowance is exhausted the audio is
kept, the status becomes `deferred_budget`, and the capture is retried tomorrow. Nothing is
truncated, overwritten or marked complete. A capture lost to a budget ceiling would be lost to an
accounting decision, which is the least defensible reason to lose anything.

WHY EMPTY IS NOT THE SAME AS FAILED (REQ-CAP-045). A transcript of "" for two seconds of audio is
plausibly silence. The same for eleven seconds is a transcription that did not work, and treating
it as a successful empty capture would file real speech as nothing.
"""
from __future__ import annotations

import datetime as dt
import copy
import math
from dataclasses import dataclass
from lib.model_contract import audio_neurons, AUDIO_NEURONS_PER_MINUTE

# REQ-CAP-030..033. The model and its parameters, fixed.
TRANSCRIPTION_MODEL = "@cf/openai/whisper-large-v3-turbo"
FORBIDDEN_MODEL = "@cf/openai/whisper-tiny-en"
TRANSCRIPTION_PARAMS = {"language": "en", "vad_filter": True,
                        "condition_on_previous_text": False}

NEURONS_PER_AUDIO_MINUTE = AUDIO_NEURONS_PER_MINUTE
SOFT_CEILING = 9_000                 # REQ-CAP-037/038
HARD_CAP = 10_000                    # REQ-CAP-042
EMPTY_TRANSCRIPT_MIN_SECONDS = 2     # REQ-CAP-045

DEFERRED = "deferred_budget"
PENDING = "pending_enrichment"


class PaidUsageForbidden(Exception):
    """REQ-CAP-042. The hard fail IS the $0 enforcement, not an obstacle to it."""


@dataclass(frozen=True)
class Refusal:
    """RULE-06. A call not made, with the reason and what survives."""
    reason: str
    processing_status: str
    last_error: str
    audio_retained: bool = True
    detail: str = ""


def transcription_request(audio, *, model=TRANSCRIPTION_MODEL, params=None):
    """REQ-CAP-030..033. The request, with its parameters asserted rather than assumed.

    `condition_on_previous_text=False` matters more than it looks: with it on, Whisper carries
    context between segments and will happily continue a sentence it hallucinated, so one bad
    segment contaminates the rest of the transcript.
    """
    if model == FORBIDDEN_MODEL:
        raise ValueError(f"REQ-CAP-030: {FORBIDDEN_MODEL} is forbidden; use {TRANSCRIPTION_MODEL}")
    if model != TRANSCRIPTION_MODEL:
        raise ValueError(f"REQ-CAP-030: the transcription model is {TRANSCRIPTION_MODEL}")
    merged = dict(TRANSCRIPTION_PARAMS)
    merged.update(params or {})
    for k, v in TRANSCRIPTION_PARAMS.items():
        if merged[k] != v:
            raise ValueError(f"REQ-CAP-031..033: {k} must be {v!r} on every request")
    return {"model": model, "audio": audio, **merged}


def validate_transcription(response):
    """Validate returned evidence before an append-only result can be persisted.

    Preserve segment metadata; never coerce malformed timings or invent missing
    text. This is validation only, not proof of provider receipt or DB persistence.
    """
    if not isinstance(response, dict) or not isinstance(response.get("text"), str):
        raise ValueError("invalid_transcript_text")
    segments = response.get("segments")
    if not isinstance(segments, list):
        raise ValueError("invalid_transcript_segments")
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("invalid_transcript_segment")
        start, end = segment.get("start"), segment.get("end")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in (start, end)):
            raise ValueError("invalid_transcript_timing")
        if start < 0 or end < start:
            raise ValueError("invalid_transcript_timing")
    return {"transcript": response["text"], "segments": copy.deepcopy(segments),
            "transcript_source": "workers_ai"}


def store_transcription(row, response):
    """Legacy pure projection; never authorizes updating an immutable raw row.

    Durable REQ-CAP-034 storage belongs to the append-only result consumer under
    ADR0148. This helper only validates/copies a response for existing pure callers.
    """
    result = validate_transcription(response)
    return {**row, **result, "segments": tuple(result["segments"])}


def estimated_neurons(duration_seconds):
    """REQ-CAP-036: use the shared audio-cost owner without per-call rounding."""
    return audio_neurons(duration_seconds)


def may_call(*, spent_today, pending_cost, is_deferred_retry=False):
    """REQ-CAP-037/038/039. The gate, before any call is issued.

    A NEW capture must fit under 9,000. A DEFERRED retry may use the reserved margin up to
    10,000. Without that reservation a busy day starves yesterday's backlog permanently: the
    deferred captures are older, their audio is sitting on a phone, and they lose every race.
    """
    ceiling = HARD_CAP if is_deferred_retry else SOFT_CEILING
    projected = float(spent_today) + float(pending_cost)
    if projected <= ceiling:
        return {"allowed": True, "projected": round(projected, 4), "ceiling": ceiling}
    return {"allowed": False, "projected": round(projected, 4), "ceiling": ceiling,
            "refusal": Refusal(
                reason="neuron_cap" if is_deferred_retry else "soft_ceiling",
                processing_status=DEFERRED, last_error="neuron_cap",
                detail=(f"{projected:.1f} projected neurons exceeds the "
                        f"{'hard cap' if is_deferred_retry else 'soft ceiling'} of {ceiling}. "
                        f"The audio is retained and the capture is retried tomorrow."))}


def assert_no_paid_usage(account):
    """REQ-CAP-042. No payment method, so the account cannot spend money if this code is wrong.

    A soft check in application code fails open the day somebody edits it. An account with no
    payment method fails closed forever, which is why the requirement calls the hard fail the
    enforcement mechanism rather than a limitation.
    """
    if account.get("payment_method_attached") or account.get("paid_usage_enabled"):
        raise PaidUsageForbidden(
            "REQ-CAP-042: paid Workers AI usage may not be enabled and no payment method may be "
            "attached; the 10,000-neuron hard fail is the $0-recurring enforcement mechanism")
    return True


def on_allowance_exhausted(capture):
    """REQ-CAP-041/043. Deferred, retained, never truncated or marked complete.

    A capture lost to a budget ceiling would be lost to an accounting decision, which is the
    least defensible reason to lose anything.
    """
    return {**capture, "processing_status": DEFERRED, "last_error": "neuron_cap",
            "audio_retained": True, "transcript": capture.get("transcript"),
            "note": "The audio is untouched. This is retried when the allowance resets."}


def deferred_queue(captures, *, now_utc_day):
    """REQ-CAP-040. Deferred captures first, oldest first, before anything received today.

    Oldest-first rather than newest-first because a deferred capture's audio is sitting on a
    phone and the person who recorded it has already moved on; the oldest is the one closest to
    being forgotten.
    """
    deferred = sorted((c for c in captures if c.get("processing_status") == DEFERRED),
                      key=lambda c: c["captured_at"])
    todays = [c for c in captures
              if c.get("processing_status") != DEFERRED
              and c["captured_at"].date() == now_utc_day]
    return tuple(deferred) + tuple(sorted(todays, key=lambda c: c["captured_at"]))


def deferred_indicator(captures):
    """REQ-CAP-044. The exact count and the reason, in Joe's words rather than the system's."""
    n = sum(1 for c in captures if c.get("processing_status") == DEFERRED)
    if not n:
        return {"visible": False}
    return {"visible": True, "count": n,
            "reason": "waiting for tomorrow's AI budget",
            "text": f"{n} capture{'' if n == 1 else 's'} waiting for tomorrow's AI budget"}


def on_transcript(capture, transcript, *, duration_seconds):
    """REQ-CAP-043/045. Empty is not the same as failed, and neither is complete.

    A transcript of "" for two seconds of audio is plausibly silence. The same for eleven seconds
    is a transcription that did not work, and treating it as a successful empty capture would
    file real speech as nothing.
    """
    if transcript is None:
        # REQ-CAP-043. Never dropped, never marked complete.
        return {**capture, "processing_status": PENDING, "last_error": "transcription_failed",
                "review_list": True}
    if not transcript.strip() and float(duration_seconds) > EMPTY_TRANSCRIPT_MIN_SECONDS:
        return {**capture, "processing_status": PENDING, "last_error": "empty_transcript",
                "review_list": True,
                "note": (f"{duration_seconds:.0f}s of audio returned no text. Short silence is "
                         f"plausible; this is not.")}
    return {**capture, "processing_status": "enriched", "transcript": transcript}


def ios_dictation(capture, text):
    """REQ-CAP-046. Dictated text costs nothing and must not be re-transcribed.

    Re-transcribing would spend neurons to reproduce text the phone already produced, against a
    budget that is the binding constraint on the whole subsystem.
    """
    return {**capture, "transcript": text, "transcript_source": "ios_dictation",
            "workers_ai_call": False, "estimated_neurons": 0.0}


# ---------------------------------------------------------------- §G.2 the capture never-rules

CAPTURE_NEVER = {
    "REQ-CAP-100": "capture blocks on a network call, database lookup, search or required field",
    "REQ-CAP-102": "capture asks Joe to confirm something",
    "REQ-CAP-103": "an input is lost to a failed enrichment",
    "REQ-CAP-104": "the server's receive time is used as the event time",
    "REQ-CAP-105": "a raw_captures row is modified or deleted",
    "REQ-CAP-106": "the PWA requests camera, microphone or geolocation permission",
    "REQ-CAP-107": "a missing log is surfaced as guilt rather than as coverage",
}


def check_capture_path(path):
    """REQ-CAP-100..107. The eight things capture may never do.

    REQ-CAP-101 is the positive form of the same idea and is tested by simulation rather than by
    inspection: with everything down, the Shortcut still completes and still queues.
    """
    out = []
    if any(path.get(k) for k in ("blocks_on_network", "blocks_on_db", "blocks_on_search",
                                 "has_required_field")):
        out.append("REQ-CAP-100")
    if path.get("asks_confirmation"):
        out.append("REQ-CAP-102")
    if path.get("drops_on_enrichment_failure"):
        out.append("REQ-CAP-103")
    if path.get("event_time_field") == "received_at":
        out.append("REQ-CAP-104")
    if path.get("mutates_raw_captures"):
        out.append("REQ-CAP-105")
    if set(path.get("pwa_permissions") or ()) & {"camera", "microphone", "geolocation"}:
        out.append("REQ-CAP-106")
    if path.get("missing_log_framing") not in (None, "coverage"):
        out.append("REQ-CAP-107")
    return tuple(f"{c}: {CAPTURE_NEVER[c]}" for c in out)


def capture_with_everything_down(payload, queue):
    """REQ-CAP-101. Every service unavailable, and the capture still completes.

    This is the property the whole subsystem is arranged around, so it is a function rather than
    a comment: nothing here touches a network, a database or a model.
    """
    queue.append(payload)
    return {"completed": True, "queued": True, "queue_depth": len(queue),
            "services_contacted": ()}
