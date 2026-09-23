"""B16 §C.1/C.2/C.3 — the extractive-only contract (REQ-CAP-050..066, 108, 109).

Pure: no database, no network, no model call. The model's RESPONSE is passed in; what comes back
is what may be written.

THE CONTRACT IN ONE LINE. The model may point at the transcript. It may not add to it.

WHY THAT NEEDS ENFORCING RATHER THAN PROMPTING. A language model asked for the calories in "a
bagel and cream cheese" will answer, fluently and plausibly, and the answer will be wrong in a
way nobody can see. Every guard here exists because asking nicely does not work:

  * REQ-CAP-052 keeps the words out of the SCHEMA, so the model is never invited to produce them.
  * REQ-CAP-053 asserts `transcript[start:start+len(evidence)] == evidence`. A model that invents
    an item invents its evidence span too, and the span will not match. This is the load-bearing
    check: it converts "did the model make this up" from a judgement into a string comparison.
  * REQ-CAP-056 strips any calorie or macronutrient number at the ADAPTER BOUNDARY, before a row
    exists -- and explicitly NOT at reduced confidence. A stored number with low confidence is
    still a stored number, and confidence decays out of a reader's memory faster than the digits
    do.

WHY THE FALLBACK IS `defaulted` AND NOT `inferred` (REQ-CAP-065). When `dateparser` cannot
resolve a temporal span the event time falls back to `captured_at`. That is a SYSTEM DEFAULT, and
`defaulted` is the value REQ-CAP-062 excludes from statistics. `inferred` is not filtered, so
labelling the fallback `inferred` would let a substituted timestamp into a trend as though it had
been measured. The requirement records a reviewer catching exactly that mistake in an earlier
draft; the same trap is easy to fall into here and the label is chosen deliberately.

That fallback is COMMON, not exotic: measured on 2026-09-10, `dateparser` returns None for both
"this morning" and "last Tuesday" -- two of the most natural things to say into a capture.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

# REQ-CAP-108. A closed set. "The profile set extends only by a requirement edit, never
# silently -- new subjects are a spec change."
PROFILES = ("food", "workout", "drink", "activity", "mood", "note")
FALLBACK_PROFILE = "note"

# REQ-CAP-051. Exactly these fields, per food item. Not "at least".
FOOD_FIELDS = ("name", "evidence", "evidence_start", "quantity", "quantity_unit",
               "quantity_evidence", "quantity_evidence_start")

# REQ-CAP-052. Neither a field NAME nor a field DESCRIPTION may refer to these.
NUTRITION_TERMS = ("calorie", "calories", "kcal", "kilocalorie", "kilocalories", "energy",
                   "protein", "carbohydrate", "carbohydrates", "carbs", "fat", "fats",
                   "fibre", "fiber", "macronutrient", "macro", "macros")

PROVENANCE = ("extracted", "inferred", "defaulted")     # REQ-CAP-057
MAX_EXTRACTION_ATTEMPTS = 3                              # REQ-CAP-055: the call plus two retries
DEFAULT_DAY_BOUNDARY_HOUR = 4                            # REQ-CAP-066 / ADR-0019


class SchemaViolation(Exception):
    """REQ-CAP-051/052. Refused before a call is made, not after a response arrives."""


@dataclass(frozen=True)
class Field:
    name: str
    value: object
    provenance: str
    reason: str = ""
    time_precision: str | None = None

    def __post_init__(self):
        if self.provenance not in PROVENANCE:
            raise ValueError(f"REQ-CAP-057: provenance is exactly one of {PROVENANCE}")


def validate_profile(subject):
    """REQ-CAP-108. One profile from the closed set; anything unrecognised routes to `note`.

    Routing rather than raising, because an un-profiled extraction is the failure the requirement
    names: a capture about something nobody anticipated should still be KEPT, as a note, rather
    than dropped or handed to a schema that does not fit it.
    """
    return subject if subject in PROFILES else FALLBACK_PROFILE


def validate_schema(profile, schema):
    """REQ-CAP-051/052/109. Checked before the call, because a schema is what invites an answer.

    A model asked for a `calories` field will produce one. Keeping the word out of the schema is
    cheaper and more reliable than discarding what comes back — though REQ-CAP-056 discards it
    too, because the two guards fail differently.
    """
    names = list(schema.get("properties", schema) or {})
    if profile == "food" and tuple(names) != FOOD_FIELDS:
        raise SchemaViolation(
            f"REQ-CAP-051: the food profile's fields are exactly {FOOD_FIELDS}; got {tuple(names)}")
    blob = " ".join(names).lower()
    for prop in (schema.get("properties") or {}).values():
        if isinstance(prop, dict):
            blob += " " + str(prop.get("description", "")).lower()
    for term in NUTRITION_TERMS:
        if re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", blob):
            raise SchemaViolation(
                f"REQ-CAP-052: no field name or description may refer to {term!r}; a model asked "
                f"for it will answer, fluently and wrongly")
    return True


def span_matches(transcript, evidence, evidence_start):
    """REQ-CAP-053. The load-bearing check, and it is a string comparison.

    A model that invents an item invents its evidence span too, and the invented span will not be
    at that offset in the transcript. This converts "did the model make this up" from a judgement
    into `transcript[start:start+len(evidence)] == evidence`.
    """
    if not isinstance(transcript, str) or not isinstance(evidence, str) or not evidence:
        return False
    if type(evidence_start) is not int or evidence_start < 0:
        return False
    return transcript[evidence_start:evidence_start + len(evidence)] == evidence


def resolve_field(name, value, transcript, *, evidence=None, evidence_start=None,
                  from_default_table=False):
    """REQ-CAP-053/054/058/059/060. The value that may be written, and its provenance."""
    if from_default_table:
        # REQ-CAP-060. A system default, and REQ-CAP-062 will exclude it from statistics.
        return Field(name, value, "defaulted", "supplied by a system default table")
    if evidence is None and evidence_start is None:
        # REQ-CAP-059. The model produced it with no span to point at. Kept, marked, not trusted.
        return Field(name, value, "inferred", "model value with no evidence span")
    if span_matches(transcript, evidence, evidence_start):
        # A genuine span alone does not support an arbitrary model label. Keep
        # the verbatim food/name contract: "salmon" cannot cite "bagel", and
        # "ham" cannot cite the middle of "champagne". Case is not meaning.
        if name == "name" and (not isinstance(value, str) or not value.strip()
                or re.search(r"(?<!\w)" + re.escape(value.casefold()) + r"(?!\w)",
                             evidence.casefold()) is None):
            return Field(name, None, "inferred", "value_not_in_span")
        return Field(name, value, "extracted")          # REQ-CAP-058
    # REQ-CAP-054. The VALUE is discarded, not merely flagged: a span that does not match means
    # the model pointed at text that is not there, and nothing it said about that field survives.
    return Field(name, None, "inferred", "span_mismatch")


def strip_nutrition(response):
    """REQ-CAP-056. At the adapter boundary, before any row exists, and NOT at reduced confidence.

    A stored number with low confidence is still a stored number, and confidence decays out of a
    reader's memory faster than the digits do. Returns (cleaned, discarded_keys).
    """
    discarded = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if any(re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", str(k).lower())
                       for t in NUTRITION_TERMS):
                    discarded.append(f"{path}.{k}")
                    continue
                out[k] = walk(v, f"{path}.{k}")
            return out
        if isinstance(node, list):
            return [walk(v, f"{path}[{i}]") for i, v in enumerate(node)]
        return node

    return walk(response), tuple(discarded)


def extract_with_retry(call, *, validate, max_attempts=MAX_EXTRACTION_ATTEMPTS):
    """REQ-CAP-055. At most two retries, then quarantine — never a partial write.

    Quarantine rather than a best-effort parse: a response that failed schema validation three
    times is a response nobody understands, and writing the half of it that parsed would put
    unvalidated values in the same table as validated ones with nothing to tell them apart.
    """
    errors = []
    for attempt in range(1, max_attempts + 1):
        try:
            response = call(attempt)
            validate(response)
            return {"ok": True, "response": response, "attempts": attempt}
        except Exception as e:                    # noqa: BLE001 — any validation failure retries
            errors.append(f"attempt {attempt}: {e}")
    return {"ok": False, "processing_status": "extraction_quarantined",
            "review_list": True, "attempts": max_attempts, "errors": tuple(errors)}


def resolve_time(span, captured_at):
    """REQ-CAP-063/064/065. The model emits the SPAN; this resolves it.

    The model never emits a timestamp (REQ-CAP-063) because a resolved time cannot be checked
    against the transcript — a span can. `dateparser` does the resolution with the capture as its
    relative base and a preference for the past, since a capture describes something that has
    already happened.
    """
    if span:
        import dateparser
        parsed = dateparser.parse(str(span), settings={"RELATIVE_BASE": captured_at,
                                                       "PREFER_DATES_FROM": "past"})
        if parsed is not None:
            return Field("event_time", parsed, "extracted", time_precision="resolved")
    # REQ-CAP-065. `defaulted`, NOT `inferred`: REQ-CAP-062 filters `defaulted` out of statistics
    # and does not filter `inferred`, so mislabelling this would let a substituted timestamp into
    # a trend as though it had been measured. The requirement records a reviewer catching exactly
    # that in an earlier draft.
    return Field("event_time", captured_at, "defaulted",
                 reason="dateparser_failed" if span else "no_temporal_expression",
                 time_precision="unknown")


def subject_day(event_time, *, boundary_hour=DEFAULT_DAY_BOUNDARY_HOUR):
    """REQ-CAP-066. A capture before the personal day boundary belongs to the preceding day.

    A 01:30 note about the evening is about the evening, not about the morning that follows it.
    """
    day = event_time.date()
    return day - dt.timedelta(days=1) if event_time.hour < boundary_hour else day


def render_treatment(field):
    """REQ-CAP-061. `inferred` and `defaulted` render distinctly from `extracted`.

    Returned as data rather than left to a stylesheet, so a surface cannot render an inferred
    value identically to a measured one by omission.
    """
    return {"provenance": field.provenance,
            "distinct_treatment_required": field.provenance != "extracted",
            "label": {"extracted": "from what you said",
                      "inferred": "the model's addition, not in your words",
                      "defaulted": "a system default, not evidence"}[field.provenance]}


def statistical_inclusion(fields):
    """REQ-CAP-062. Exclude `defaulted`, or state the count alongside the claim.

    Both branches are offered because the requirement offers both, and the choice belongs to the
    caller. What is not available is including them silently.
    """
    kept = tuple(f for f in fields if f.provenance != "defaulted")
    n_defaulted = len(fields) - len(kept)
    return {"included": kept, "n_defaulted_excluded": n_defaulted,
            "disclosure": (f"{n_defaulted} field(s) carrying system defaults are excluded."
                           if n_defaulted else ""),
            "if_included_disclosure": (f"Includes {n_defaulted} field(s) supplied by a system "
                                       f"default rather than observed." if n_defaulted else "")}
