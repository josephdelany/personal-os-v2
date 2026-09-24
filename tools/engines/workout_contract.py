"""B18 §A/§B — the workout capture and render contract (REQ-WKT-001..022).

Pure: no database, no clock, no model. `strength.py` computes e1RM, volume and ACWR; this is what
may be captured, how a correction outranks a guess, and what a surface may say about the result.

WHY THE SET IS THE UNIT (REQ-WKT-001). A session total loses the thing strength training is
about: 5x5 at 225 and 1x25 at 135 are the same volume and completely different training. Once the
sets are collapsed the distinction cannot be recovered, and every derived measure downstream
inherits the loss.

WHY THE EXERCISE RESOLVES TO ONE ENTITY (REQ-WKT-006). "Bench", "bench press", "barbell bench",
"BB bench" are one movement, and left as free text they are four series with a quarter of the
data each. Nothing detects that: four sparse trends look exactly like four exercises Joe does
rarely.

WHY A REST DAY IS OBSERVED_ABSENT AND NOT A GAP (REQ-WKT-019). "I chose not to train" and "no
data" are different facts, and only the first is evidence about training. Collapsing them makes a
deliberate deload indistinguishable from a week the phone was off -- and the ACWR that reads them
as identical will call one of them detraining.

WHY THERE IS NO STREAK (REQ-WKT-014/016). Strength is a trend toward a stated objective, not an
attendance record. A streak makes a missed session a failure, and Joe's capture has stopped twice
this year through no act of his -- a streak would have scored both as lapses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CAPTURE_PATHS = ("ios_shortcut", "manual_logger", "v0_workout_text")          # REQ-WKT-002
FORBIDDEN_CAPTURE = ("pwa", "getusermedia", "browser_microphone")
SET_FIELDS = ("exercise", "load", "reps", "rpe")           # REQ-WKT-001
PRESENCE = ("observed", "observed_absent", "unknown")      # REQ-WKT-019
WORKOUT_TIER = "DESCRIPTIVE"                               # REQ-WKT-021
COVERAGE_WINDOW_DAYS = 7                                   # REQ-WKT-016

# REQ-WKT-014/016. Attendance vocabulary, refused on every workout surface.
# "broken" is attendance language. "broke" is deliberately NOT here: "you broke a personal
# record" is exactly what this surface exists to say, and banning the stem would refuse the
# sentence the objective function is about.
STREAK_TERMS = ("streak", "streaks", "compliance", "adherence score", "consecutive days",
                "days in a row", "broken", "perfect week", "missed day", "badge")

# REQ-WKT-021. Language reserved for tiers this measure can never reach.
CAUSAL_TERMS = ("caused", "causes", "because", "led to", "leads to", "proves", "guarantees")


class CaptureRefused(Exception):
    """REQ-WKT-002 / RULE-30. Unapproved workout capture or browser media is refused."""


class RenderViolation(Exception):
    """REQ-WKT-014/015/016/021."""


@dataclass(frozen=True)
class SetRecord:
    exercise: str                 # the CANONICAL entity, not free text
    load: float | None
    reps: int | None
    rpe: float | None
    raw_exercise: str = ""        # what Joe actually said, kept verbatim
    presence: str = "observed"
    superseded_by: str | None = None
    corrected_by: str | None = None

    def __post_init__(self):
        if self.presence not in PRESENCE:
            raise ValueError(f"REQ-WKT-019: presence is one of {PRESENCE}")


def check_capture_path(path):
    """REQ-WKT-002. Shortcuts, interim logger or approved V0 text; never browser media."""
    p = str(path).lower()
    if any(f in p for f in FORBIDDEN_CAPTURE):
        raise CaptureRefused(
            f"REQ-WKT-002 / RULE-30: {path!r} — workout capture is iOS Shortcuts or the interim "
            f"manual logger or named V0 text path; never generic PWA/media capture")
    if p not in CAPTURE_PATHS:
        raise CaptureRefused(f"REQ-WKT-002: {path!r} is not one of {list(CAPTURE_PATHS)}")
    return True


def record_set(**kw):
    """REQ-WKT-001. Set granularity, with the raw text kept beside the canonical entity.

    5x5 at 225 and 1x25 at 135 are the same volume and completely different training. Once the
    sets are collapsed that distinction cannot be recovered.
    """
    missing = [f for f in SET_FIELDS if f not in kw]
    if missing:
        raise ValueError(f"REQ-WKT-001: a set carries {missing}; a session total loses what "
                         f"strength training is about")
    return SetRecord(**kw)


def resolve_exercise(raw, aliases, *, human_confirmed=None):
    """REQ-WKT-006/020. One canonical entity per movement, and a human answer outranks the map.

    "Bench", "bench press", "barbell bench", "BB bench" are one movement. Left as free text they
    are four series with a quarter of the data each — and nothing detects that, because four
    sparse trends look exactly like four exercises Joe does rarely.
    """
    if human_confirmed:
        return {"exercise": human_confirmed, "raw_exercise": raw, "resolved_by": "human",
                "outranks_automated": True}
    key = re.sub(r"[^a-z0-9]+", " ", str(raw).lower()).strip()
    canonical = aliases.get(key)
    if canonical is None:
        return {"exercise": None, "raw_exercise": raw, "resolved_by": None,
                "needs_review": True,
                "note": ("Unmapped movement. Left unresolved rather than given its own series, "
                         "because a new series looks identical to an exercise done rarely.")}
    return {"exercise": canonical, "raw_exercise": raw, "resolved_by": "alias_map"}


def supersede(existing, **correction):
    """REQ-WKT-020 / RULE-10. A correction is a new row that outranks every automated value.

    Superseding rather than updating, so "what did the log say before Joe fixed it" still has an
    answer — which is the only way to tell a mis-transcription from a change of mind.
    """
    if existing.corrected_by == "joe" and correction.get("corrected_by") != "joe":
        raise ValueError("REQ-WKT-020: an automated value may not overwrite Joe's correction")
    fields = {**existing.__dict__, **correction, "corrected_by": correction.get("corrected_by",
                                                                                "joe")}
    fields.pop("superseded_by", None)
    return (SetRecord(**{**existing.__dict__, "superseded_by": "next"}), SetRecord(**fields))


def log_rest_day(day, *, deliberate=True):
    """REQ-WKT-019. A rest day is `observed_absent`, distinct from an unlogged day.

    "I chose not to train" and "no data" are different facts, and only the first is evidence
    about training. Collapsing them makes a deliberate deload indistinguishable from a week the
    phone was off — and an ACWR that reads them as identical will call one of them detraining.
    """
    return {"day": day, "presence": "observed_absent" if deliberate else "unknown",
            "is_evidence_about_training": deliberate,
            "note": ("A deliberate rest day is a fact about training. An unlogged day is not, and "
                     "an ACWR that treats them alike will call one of them detraining.")}


def point_in_time(sets, *, window_close, known_at):
    """REQ-WKT-013 / INV-4. No set recorded after the window closed enters the measure.

    Both clocks: a set ABOUT a day inside the window that was RECORDED after it closed is
    knowledge the measure did not have. Letting it in makes a historical figure change when
    somebody backfills, and then the number Joe saw last week is not the number he sees now.
    """
    return tuple(s for s in sets
                 if s["day"] <= window_close and s["recorded_at"] <= known_at)


def check_workout_copy(text):
    """REQ-WKT-014/016/021. No streak, no compliance score, no causal claim.

    Strength is a trend toward a stated objective, not an attendance record. A streak makes a
    missed session a failure — and Joe's capture has stopped twice this year through no act of
    his, so a streak would have scored both as lapses.
    """
    out, low = [], (text or "").lower()
    for t in STREAK_TERMS:
        if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low):
            out.append(f"REQ-WKT-014/016: attendance framing {t!r}")
    for t in CAUSAL_TERMS:
        if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", low):
            out.append(f"REQ-WKT-021: {t!r} — a workout derived measure is DESCRIPTIVE and "
                       f"asserts no causal or experimental strength claim")
    return tuple(out)


def coverage(days_trained, *, window=COVERAGE_WINDOW_DAYS):
    """REQ-WKT-016. A rolling figure, and nothing that can be broken."""
    return {"window_days": window, "days_trained": days_trained,
            "coverage_pct": round(100.0 * days_trained / window, 1),
            "streak": None, "breakable": False,
            "note": "A rolling 7-day figure. There is no streak to break."}


def render_numeral(value, *, stored_fields, unit):
    """REQ-WKT-015 / RULE-14 / INV-3. Every numeral traces to a stored computation.

    The render layer formats. It does not divide, average, convert or total — each of those is a
    computation, and a computation performed at render time has no stored result to trace to.
    """
    if value not in stored_fields.values():
        raise RenderViolation(
            f"REQ-WKT-015: {value!r} is not a stored value; the render layer formats and performs "
            f"no arithmetic beyond formatting")
    if not unit:
        raise RenderViolation("REQ-WKT-015: a workout numeral renders with its unit")
    return f"{value} {unit}"


def deterministic_render(measure, *, language_layer_available):
    """REQ-WKT-017 / RULE-15. The figures survive the narrator being down.

    A surface that goes blank when the model is unavailable has made the model load-bearing for
    facts that were computed without it.
    """
    return {"rendered": True, "path": ("model" if language_layer_available
                                       else "deterministic_template"),
            "measure": measure,
            "note": ("The trend and its figures come from stored computations, so they render "
                     "whether or not the language layer is up.")}


def measure_tier(measure):
    """REQ-WKT-021. DESCRIPTIVE, always, for an observational strength measure."""
    return {**measure, "tier": WORKOUT_TIER,
            "note": ("An observational strength measure describes what was lifted. It is not an "
                     "experiment and makes no causal claim.")}


def objective_function(strength_trend, body_composition):
    """REQ-WKT-022. Strength progression AND body composition, together, as the objective.

    Together because either alone is gameable in a direction Joe does not want: e1RM alone rises
    with bodyweight, and body composition alone improves by eating less and lifting less. The
    pair is the thing the analysis is FOR, and naming it here keeps it from drifting into
    whatever is easiest to measure.
    """
    return {"objective": ("strength_progression", "body_composition"),
            "strength": strength_trend, "body_composition": body_composition,
            "tier": WORKOUT_TIER,
            "note": ("Either alone is gameable: e1RM rises with bodyweight, and body composition "
                     "improves by eating less and lifting less. The pair is the objective.")}
