"""B16 §A.5/§A.6/§F.1 — offline, downstream failure, and the attention budget
(REQ-CAP-019..029, 080..086).

Pure: no database, no network, no clock passed implicitly. Everything takes its inputs.

WHY LOSING A CAPTURE IS THE WORST OUTCOME IN THIS SUBSYSTEM. A transaction can be re-imported
from a CSV next month. A HealthKit sample is still on the watch. A spoken sentence about what Joe
just ate exists exactly once, for about four seconds, and if the network is down when he says it
there is no second copy anywhere in the world.

So §A.5's rule is that a network failure is SILENT and LOCAL: the payload goes to a queue file
and the Shortcut exits WITHOUT AN ERROR DIALOG (REQ-CAP-019). The dialog matters more than it
looks -- an error at the moment of capture teaches Joe that capturing sometimes fails, and the
lesson he draws is to stop bothering. A queue he never sees teaches him nothing, which is
correct, because nothing went wrong that he can act on.

WHY THE QUEUE DELETES ONLY ON 202 (REQ-CAP-020). Removing a line on send rather than on
acknowledgement loses exactly the captures that were hardest to make -- the ones sent while the
connection was bad.

WHY `received_at` MAY NEVER BUCKET ANYTHING (REQ-CAP-021/022). A capture queued on Tuesday night
and replayed on Wednesday morning is a TUESDAY capture. Bucketing by arrival would move every
offline capture forward by a day, and offline captures are not random: they cluster where the
signal is bad, which for Joe means exactly the places worth knowing about.

WHY THE INGEST ENDPOINT RETURNS 202 EVEN WHEN ENRICHMENT FAILED (REQ-CAP-025). The capture is
SAFE the moment it is stored; transcription and extraction are downstream and retryable. Telling
the Shortcut about a downstream failure would surface an error for something already succeeded,
and the Shortcut's only available response would be to make Joe do it again.
"""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

QUEUE_TIMEOUT_S = 10                 # REQ-CAP-019
ACK_STATUSES = (200, 202)            # REQ-CAP-020
DRAFT_DEBOUNCE_S = 1                 # REQ-CAP-023
DRAFT_POST_INTERVAL_S = 30           # REQ-CAP-023
PENDING_STALL_HOURS = 72             # REQ-CAP-027
RESOLUTION_STALE_HOURS = 48          # REQ-CAP-029
EVENT_TIME_FIELD = "captured_at"     # REQ-CAP-021
METADATA_ONLY_FIELD = "received_at"

MAX_CHECKIN_ITEMS = 5                # REQ-CAP-080
MAX_CHECKIN_SCALES = 3               # REQ-CAP-081
MAX_ITEMS_ANY_SCREEN = 26            # REQ-CAP-082
MAX_MEAL_CAPTURE_ACTIONS = 4         # REQ-CAP-083
MAX_REVIEW_ITEMS = 5                 # REQ-CAP-085


class BucketingViolation(Exception):
    """REQ-CAP-022. Raised, not warned: an offline capture in the wrong day is invisible."""


# ---------------------------------------------------------------- §A.5 offline

def on_network_failure(payload, queue, *, error=None, elapsed_s=None):
    """REQ-CAP-019. Append one JSON line, exit silently, show NO error dialog.

    The absence of the dialog is the requirement, not a nicety. An error at the moment of capture
    teaches Joe that capturing sometimes fails, and the lesson he draws is to stop bothering.
    """
    timed_out = elapsed_s is not None and elapsed_s >= QUEUE_TIMEOUT_S
    if error is None and not timed_out:
        return {"queued": False, "show_error_dialog": False}
    queue.append(json.dumps(payload, sort_keys=True, default=str))
    return {"queued": True, "show_error_dialog": False,
            "reason": "timeout" if timed_out else "network_error",
            "queue_depth": len(queue)}


def replay(queue, post):
    """REQ-CAP-020. In file order, and a line leaves the queue only on 200/202.

    Removing on send rather than on acknowledgement loses exactly the captures that were hardest
    to make: the ones sent while the connection was bad.
    """
    sent, kept = [], []
    for line in list(queue):
        status = post(line)
        if status in ACK_STATUSES:
            sent.append(line)
        else:
            kept.append(line)
    queue[:] = kept
    return {"sent": tuple(sent), "remaining": tuple(kept), "order_preserved": True}


def replay_stops_at_first_failure(queue, post):
    """Ordered variant: stop on the first non-ack so file order is preserved on the server too.

    Kept separate rather than made the default because REQ-CAP-020 requires order and
    acknowledgement, not stop-on-failure — a single poisoned line would otherwise block every
    capture behind it forever.
    """
    for i, line in enumerate(list(queue)):
        if post(line) not in ACK_STATUSES:
            queue[:] = list(queue)[i:]
            return {"sent_count": i, "blocked_on": line, "remaining": len(queue)}
    queue.clear()
    return {"sent_count": None, "blocked_on": None, "remaining": 0}


def event_time(capture):
    """REQ-CAP-021. `captured_at` is the event time; `received_at` is metadata."""
    return capture[EVENT_TIME_FIELD]


def assert_not_bucketed_by_received_at(field_name):
    """REQ-CAP-022. Raised rather than warned.

    A capture queued on Tuesday night and replayed on Wednesday morning is a TUESDAY capture.
    Bucketing by arrival moves every offline capture forward a day, and offline captures are not
    random -- they cluster where the signal is bad, which for Joe means exactly the places worth
    knowing about. The resulting distortion is invisible in the output.
    """
    if field_name == METADATA_ONLY_FIELD:
        raise BucketingViolation(
            "REQ-CAP-022: no query, rollup or chart may bucket by received_at; a capture queued "
            "on Tuesday and replayed on Wednesday is a Tuesday capture")
    return True


def draft_policy():
    """REQ-CAP-023/024. Local first, and the local copy outlives the POST."""
    return {"persist_to": "indexeddb", "debounce_s": DRAFT_DEBOUNCE_S,
            "post_interval_s": DRAFT_POST_INTERVAL_S,
            "retain_local_until": "server_ack",
            "note": ("The local copy is retained until the server acknowledges. Deleting on POST "
                     "would lose the draft to the one failure mode that matters: a POST that "
                     "left but never arrived.")}


def unsynced_indicator(n_unsynced):
    """REQ-CAP-024. The EXACT count, persistently, while anything is unsynced.

    A count rather than a dot: "3 entries not yet saved" is actionable and "something is
    unsynced" is anxiety with no next step.
    """
    if n_unsynced <= 0:
        return {"visible": False}
    return {"visible": True, "persistent": True, "count": n_unsynced,
            "text": f"{n_unsynced} entr{'y' if n_unsynced == 1 else 'ies'} not yet saved"}


# ---------------------------------------------------------------- §A.6 downstream failure

def ingest_result(stored, *, enrichment_status=None, provider_error=None):
    """REQ-CAP-025. 202 to the Shortcut even when enrichment failed.

    The capture is SAFE the moment it is stored. Telling the Shortcut about a downstream failure
    would surface an error for something that already succeeded, and its only available response
    would be to make Joe do it again.
    """
    if not stored:
        return {"http_status": 500, "processing_status": None}
    out = {"http_status": 202, "processing_status": "enriched"}
    if enrichment_status is not None and not (200 <= enrichment_status < 300):
        out["processing_status"] = "pending_enrichment"
        out["last_error"] = provider_error or str(enrichment_status)
    return out


def nightly_retry_set(rows):
    """REQ-CAP-026. Every pending row is re-attempted on each nightly run."""
    return tuple(r for r in rows if r.get("processing_status") == "pending_enrichment")


def stalled(rows, *, now):
    """REQ-CAP-027. Over 72 hours pending is a review-list item, not another retry.

    Retrying forever hides a provider that has changed its contract. Seventy-two hours is three
    nightly attempts: enough for a transient outage, few enough that a real breakage surfaces
    while Joe still remembers the captures involved.
    """
    out = []
    for r in rows:
        if r.get("processing_status") != "pending_enrichment":
            continue
        hours = (now - r["pending_since"]).total_seconds() / 3600.0
        if hours > PENDING_STALL_HOURS:
            out.append({"capture_id": r.get("capture_id"), "reason": "enrichment_stalled",
                        "hours_pending": round(hours, 1)})
    return tuple(out)


def transcription_provider(env):
    """REQ-CAP-028. One function, one environment variable, no call-site edits.

    The indirection is cheap now and expensive later: a provider swap that requires touching
    every call site is a swap nobody makes, and the system stays on a provider it has outgrown.
    """
    name = (env or {}).get("TRANSCRIPTION_PROVIDER")
    if not name:
        return {"selected": None,
                "reason": "TRANSCRIPTION_PROVIDER is unset; transcription is not configured"}
    return {"selected": name, "call_sites_unchanged": True}


def resolution_staleness_alert(last_success, *, now, already_sent=False):
    """REQ-CAP-029. ONE push, stating the hours elapsed.

    One, not a stream: a repeating alarm about a job Joe cannot fix from his phone is a
    notification he turns off, and then he misses the next one that matters.
    """
    if last_success is None:
        hours = None
    else:
        hours = (now - last_success).total_seconds() / 3600.0
        if hours <= RESOLUTION_STALE_HOURS:
            return None
    if already_sent:
        return None
    return {"push": True, "hours_elapsed": round(hours, 1) if hours else None,
            "text": (f"The nightly resolution job last completed {hours:.0f} hours ago."
                     if hours else "The nightly resolution job has never completed.")}


# ---------------------------------------------------------------- §F.1 the attention budget

def check_screen(screen):
    """REQ-CAP-080..085. The budget, enforced rather than recommended.

    Every limit here is small enough to look arbitrary and each has the same justification: the
    active capture budget is spent only on what the phone cannot answer by itself. A screen that
    asks for six things gets four answered and then abandoned, and the abandonment is permanent.
    """
    out = []
    name = screen.get("name", "")
    items = int(screen.get("items", 0))
    if name == "morning_checkin":
        if items > MAX_CHECKIN_ITEMS:
            out.append(f"REQ-CAP-080: {items} input items; the morning check-in allows "
                       f"{MAX_CHECKIN_ITEMS}")
        if int(screen.get("rating_scales", 0)) > MAX_CHECKIN_SCALES:
            out.append(f"REQ-CAP-081: {screen['rating_scales']} rating scales; the limit is "
                       f"{MAX_CHECKIN_SCALES}")
    if items > MAX_ITEMS_ANY_SCREEN:
        out.append(f"REQ-CAP-082: {items} items; no capture screen may present more than "
                   f"{MAX_ITEMS_ANY_SCREEN}")
    if name == "meal_capture" and int(screen.get("user_actions", 0)) > MAX_MEAL_CAPTURE_ACTIONS:
        out.append(f"REQ-CAP-083: {screen['user_actions']} actions; meal capture is trigger, "
                   f"shutter, speak, done")
    if name == "evening_reflection" and not screen.get("shows_captured_before_recall"):
        # REQ-CAP-084. Recall is expensive and inaccurate; showing the day first turns the
        # question from "what did you do" into "is this right", which is a different task.
        out.append("REQ-CAP-084: the evening reflection must present the day's captured meals, "
                   "workouts, locations, mood points and sleep BEFORE any field requiring recall")
    return tuple(out)


def review_list(items, *, limit=MAX_REVIEW_ITEMS):
    """REQ-CAP-085. At most five an evening, widest interval first.

    Widest interval first because interval width IS the uncertainty: the item Joe can most
    improve by answering is the one the system is least sure about.
    """
    ordered = sorted(items, key=lambda i: -(float(i.get("interval_high", 0))
                                            - float(i.get("interval_low", 0))))
    return tuple(ordered[:limit])


def on_review_abandoned(rows):
    """REQ-CAP-086. Unchanged, and never re-prompted.

    Leaving the screen is an answer: not now. Re-raising the same items tomorrow converts a
    review list into a backlog, and a backlog is a thing people stop opening.
    """
    return {"rows_unchanged": tuple(rows), "reprompt": False,
            "note": ("Every affected row keeps its existing provenance and interval. Leaving the "
                     "screen is an answer, and re-raising these tomorrow would turn a review "
                     "list into a backlog.")}
