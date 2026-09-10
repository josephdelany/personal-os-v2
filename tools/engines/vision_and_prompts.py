"""B16 §C.4/§F.2 — vision extraction and prompt scheduling
(REQ-CAP-032, 067..072, 087..092, 110, 111).

Pure: no database, no network, no model. Model responses come in as dicts.

WHY DICTATION BEATS VISION ON DISAGREEMENT (REQ-CAP-069). The photo shows what was on the plate;
the sentence says what Joe ate. Those differ constantly and predictably -- a shared dish, a
plate he did not finish, something already eaten before the photo. The dictated value is a
statement by the person who ate it, and the vision value is a guess about a picture of it. The
discarded value is kept, because a systematic disagreement between the two is worth knowing about
and only survives if it is recorded.

WHY THE VISION MODEL IS ASKED FOR SO LITTLE (REQ-CAP-068). Names, a per-item confidence, a
`portion_cue` string, a count. NOT grams, not calories, not a serving size. A vision model asked
"how many grams" will answer, and the answer is a guess about a photograph's scale dressed as a
measurement -- and REQ-NUT-041 already forbids that confidence narrowing anything.

WHY EXTRACTION RUNS TWICE (REQ-CAP-072). At temperature 0.7 a field that differs between two runs
is a field the model was not sure about, and that is information the model's own confidence
score does not reliably carry. `consistency_flag = false` is cheap to compute and honest in a way
a self-reported confidence is not.

WHY A PROMPT IS NEVER SENT AT A RANDOM TIME (REQ-CAP-087). A prompt at a random time interrupts
whatever is happening. A prompt fifteen minutes before Joe's own median eating time arrives while
he is deciding what to eat -- and the difference between those two is the difference between a
notification he acts on and one he turns off.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

TIME_BUCKETS = ("morning", "midday", "afternoon", "evening", "night")   # REQ-CAP-067
VISION_FIELDS = ("name", "confidence", "portion_cue", "count")          # REQ-CAP-068
MAX_SCHEDULED_PROMPTS_PER_DAY = 3                                       # REQ-CAP-088
PROMPT_LEAD_MINUTES = 15                                                # REQ-CAP-090
SCHEDULE_MIN_DAYS = 14                                                  # REQ-CAP-089
DELIVERY_CHANNEL = "web_push"                                           # REQ-CAP-092
FORBIDDEN_CHANNELS = ("sms", "email", "phone_call")
CONSISTENCY_RUNS = 2                                                    # REQ-CAP-072
CONSISTENCY_TEMPERATURE = 0.7


class VisionViolation(Exception):
    pass


class PromptViolation(Exception):
    pass


# ---------------------------------------------------------------- §C.4 vision

def vision_request(schema_fields):
    """REQ-CAP-068. Names, confidence, a portion cue, a count — and nothing else.

    NOT grams, not calories, not a serving size. A vision model asked "how many grams" will
    answer, and the answer is a guess about a photograph's scale dressed as a measurement.
    """
    extra = tuple(f for f in schema_fields if f not in VISION_FIELDS)
    if extra:
        raise VisionViolation(
            f"REQ-CAP-068: the vision model is asked for {list(VISION_FIELDS)} only; {list(extra)} "
            f"would be a guess about a photograph's scale dressed as a measurement")
    return {"fields": VISION_FIELDS, "portion_cue_is_a_string": True}


def reconcile(dictated, vision):
    """REQ-CAP-069. Dictation wins, and the discarded vision value is KEPT.

    The photo shows what was on the plate; the sentence says what Joe ate. Those differ constantly
    and predictably — a shared dish, a plate he did not finish, something eaten before the photo.
    The dictated value is a statement by the person who ate it; the vision value is a guess about
    a picture of it.

    The discarded value is recorded because a systematic disagreement between the two is worth
    knowing about, and it only survives if it is written down.
    """
    conflicts = []
    out = dict(dictated)
    for field in ("name", "count"):
        d, v = dictated.get(field), (vision or {}).get(field)
        if v is not None and d is not None and d != v:
            conflicts.append({"table": "extraction_conflicts", "field": field,
                              "kept": d, "discarded": v, "kept_source": "dictation"})
    return {"resolved": out, "conflicts": tuple(conflicts),
            "note": ("The sentence says what Joe ate; the photo shows what was on the plate. "
                     "They differ predictably and the dictated value is the statement.")}


def structure_via_text_model(vision_accepts_response_format, *, prose, text_model):
    """REQ-CAP-070. A vision model with no `response_format` gets a two-step path.

    Prose from the vision model, structure from a text model under a JSON Schema. Not free-text
    parsed by regex: the schema is what makes REQ-CAP-053's span assertion possible at all, and a
    path that skips it is a path where the model may add.
    """
    if vision_accepts_response_format:
        return {"path": "direct", "schema_enforced": True}
    structured = text_model(prose)
    return {"path": "prose_then_text_model", "schema_enforced": True,
            "prose": prose, "structured": structured}


def check_pinned_models(configured, catalog):
    """REQ-CAP-071. Every model ID pinned, and a missing one FAILS the nightly run.

    Non-zero exit rather than a fallback: a model that has left the catalogue is a silent change
    in what the system extracts, and falling back to whatever is available would make the change
    invisible at exactly the moment it starts mattering.
    """
    missing = tuple(sorted(m for m in configured if m not in set(catalog)))
    if missing:
        raise VisionViolation(
            f"REQ-CAP-071: configured model ID(s) {list(missing)} are no longer in the catalog; "
            f"the nightly run exits non-zero rather than falling back, because a silent change "
            f"in what the system extracts is invisible exactly when it starts mattering")
    return {"pinned": tuple(configured), "exit_code": 0}


def consistency_flags(run_a, run_b):
    """REQ-CAP-072. Two runs at 0.7; any field that differs is flagged.

    A field that differs between two runs is a field the model was not sure about — information
    its own confidence score does not reliably carry. Cheap to compute, and honest in a way a
    self-reported confidence is not.
    """
    fields = set(run_a) | set(run_b)
    return {f: {"value": run_a.get(f),
                "consistency_flag": run_a.get(f) == run_b.get(f)}
            for f in sorted(fields)}


def time_bucket(bucket, *, source, field):
    """REQ-CAP-067. An evening-reflection item gets a BUCKET, never a clock time.

    Joe writing at 21:00 about lunch does not know when lunch was, and a recalled clock time is
    an invention with a plausible shape. A bucket is what he actually knows.
    """
    if source != "pwa_text" or field != "evening_reflection":
        return None
    if bucket not in TIME_BUCKETS:
        raise VisionViolation(
            f"REQ-CAP-067: the bucket is one of {list(TIME_BUCKETS)}; a recalled clock time is an "
            f"invention with a plausible shape")
    return {"time_bucket": bucket, "clock_time_emitted": False}


def observed_absent(statement, *, subject):
    """REQ-CAP-111 / RULE-07. "I did not drink today" is `observed_absent`, not `unknown`.

    The distinction is the whole of RULE-07: a day Joe SAYS he did not drink is evidence about
    drinking, and a day with no entry is not. Collapsing them makes his statement worth exactly
    as much as his silence.
    """
    return {"subject": subject, "presence": "observed_absent", "statement": statement,
            "is_evidence": True,
            "note": ("A day Joe says he did not drink is evidence about drinking; a day with no "
                     "entry is not. Collapsing them makes his statement worth as much as his "
                     "silence.")}


def location_capture(payload, *, source):
    """REQ-CAP-110. A `location` capture is stored raw and ROUTED to the restricted path.

    Routed rather than handled inline, because the restricted path is where the home-coordinate
    and egress-precision rules live (REQ-LOC-003) — and a coordinate that took the ordinary path
    would be one those rules never saw.
    """
    if source != "location":
        return None
    return {"raw_captures": {"source": "location", "payload": payload},
            "route_to": "restricted_coordinate_path",
            "handled_inline": False,
            "note": ("The restricted path is where the home-coordinate and egress-precision "
                     "rules live; a coordinate taking the ordinary path is one they never saw.")}


# ---------------------------------------------------------------- §F.2 prompting

def compute_schedule(captures, *, occasions, days_of_data):
    """REQ-CAP-089/091. Median captured_at per eating occasion, from at least 14 days.

    The median rather than the mean: one 02:00 kebab should not move the dinner prompt by half an
    hour, and it would.
    """
    if days_of_data < SCHEDULE_MIN_DAYS:
        return {"schedule": (), "reason": (f"{days_of_data} days of meal captures; the schedule "
                                           f"needs {SCHEDULE_MIN_DAYS}")}
    rows = []
    for occasion in occasions:
        mins = [c["minutes_from_midnight"] for c in captures if c.get("occasion") == occasion]
        if not mins:
            continue
        rows.append({"occasion": occasion,
                     "median_minutes": round(statistics.median(mins)),
                     "n": len(mins)})
    return {"schedule": tuple(rows), "recompute": "monthly",
            "note": "Median, not mean: one 02:00 kebab must not move the dinner prompt."}


def prompt_times(schedule):
    """REQ-CAP-087/088/090. Fifteen minutes before each median, at most three, never random.

    A prompt at a random time interrupts whatever is happening. A prompt fifteen minutes before
    Joe's own median eating time arrives while he is deciding what to eat — and that difference
    is the difference between a notification he acts on and one he turns off.
    """
    if len(schedule) > MAX_SCHEDULED_PROMPTS_PER_DAY:
        raise PromptViolation(
            f"REQ-CAP-088: {len(schedule)} scheduled prompts; the limit is "
            f"{MAX_SCHEDULED_PROMPTS_PER_DAY} per day")
    return tuple({"occasion": r["occasion"],
                  "send_at_minutes": r["median_minutes"] - PROMPT_LEAD_MINUTES,
                  "derived_from": "median_eating_time", "random": False}
                 for r in schedule)


def check_prompt_timing(prompt):
    """REQ-CAP-087. A randomly chosen time is refused outright."""
    if prompt.get("random") or prompt.get("jitter_minutes"):
        raise PromptViolation(
            "REQ-CAP-087: a prompt is never sent at a randomly chosen time; a random prompt "
            "interrupts whatever is happening, and one before Joe's own median eating time "
            "arrives while he is deciding what to eat")
    return True


def check_channel(channel):
    """REQ-CAP-092. Web Push, and never SMS or email.

    Not a preference: SMS and email are both channels Joe reads for other reasons, and a capture
    prompt arriving among them competes with things that matter more and loses.
    """
    if channel in FORBIDDEN_CHANNELS:
        raise PromptViolation(
            f"REQ-CAP-092: prompts are delivered by Web Push, never by {channel}; SMS and email "
            f"are channels Joe reads for other reasons, and a capture prompt there competes with "
            f"things that matter more and loses")
    if channel != DELIVERY_CHANNEL:
        raise PromptViolation(f"REQ-CAP-092: the delivery channel is {DELIVERY_CHANNEL}")
    return True
