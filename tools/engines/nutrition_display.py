"""B12 §D.4/§D.4a/§E.3/§G.1 — quantity, propagation and display (REQ-NUT-018..027, 041..053,
062..065).

Pure: no database, no network, no model.

WHY EVERY NUTRIENT FIGURE IS AN INTERVAL, EVERYWHERE. A calorie count is the most confidently
wrong number a system like this can produce. It is assembled from a food someone identified from
a sentence, a portion nobody weighed, and a database entry for something similar -- and then it
is rendered as "1,847 kcal", which reads like a measurement.

So the interval is the value, and a POINT is never shown alone (REQ-NUT-044/063). This is not
hedging: the honest width of the estimate is the most informative thing about it, and a day
logged by voice has a width that makes a 300 kcal deficit unresolvable (REQ-NUT-047). Saying so
in plain words is more useful than a number that pretends otherwise.

WHY BOUNDS SUM SEPARATELY (REQ-NUT-043). The day's low is the sum of the lows and the day's high
is the sum of the highs. Summing the points and putting a band around them would understate the
width -- the errors here are systematic (portion sizes drift the same direction all day), not
independent, so they do not cancel.

WHY ROUNDING MAY NEVER NARROW (REQ-NUT-049). Rounding 1,847.4-2,103.6 to 1,847-2,104 is fine.
Rounding it to 1,850-2,100 removes 7 kcal of honest uncertainty for tidiness, and every such
rounding along the chain removes a little more.

WHY VISION CONFIDENCE MAY NEVER NARROW AN INTERVAL (REQ-NUT-041). A model's reported per-item
confidence is a statement about IDENTIFICATION -- how sure it is that this is a bagel. The
interval is about QUANTITY. A confident identification of a bagel says nothing about how big the
bagel was, and letting it narrow the interval would convert one kind of certainty into another
it has no bearing on.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from lib.quantity_literals import VAGUE_QUANTIFIERS, EXPLICIT_FRACTIONS

# REQ-NUT-046. Methods whose intervals are tight enough for a trend analysis to restrict to.
TIGHT_METHODS = ("weighed", "labelled", "portion_alias")
# REQ-NUT-045. Visual weight by method, never by magnitude.
METHOD_WEIGHT = {"weighed": "solid", "labelled": "solid", "portion_alias": "medium",
                 "estimated": "light", "inferred": "light"}

# REQ-NUT-053. Quantifiers that map to no explicit fraction.

UNRESOLVED = "unresolved"


class NutritionDisplayError(Exception):
    """Raised where a display rule would otherwise be silently broken."""


# ---------------------------------------------------------------- §D.4 quantity

def convert_quantity(value, unit):
    """REQ-NUT-019. A mass or volume unit converts, and the provenance is `extracted`.

    A stated unit is something Joe said. It is not an inference and must not be marked as one.
    """
    from lib.mass_units import convert_quantity as convert
    quantity = convert(value, unit)
    key = 'grams' if quantity['unit'] == 'g' else 'volume_ml'
    return {key: quantity['value'], "provenance": "extracted", "basis": f"{value} {unit}"}


def resolve_vernacular(phrase, food_class, portion_aliases):
    """REQ-NUT-020/023. A vernacular phrase resolves from the table, provenance `defaulted`.

    `defaulted` and not `extracted`, because "a bowl" is not a quantity Joe stated — it is one
    the system looked up. REQ-CAP-062 excludes `defaulted` from statistics, which is exactly
    right for a portion nobody measured.
    """
    row = portion_aliases.get((food_class, phrase.lower()))
    if row is None:
        return None
    return {"grams": row["grams"], "provenance": "defaulted",
            "basis": f"portion_aliases[{food_class}, {phrase}]",
            "n_corrections": row.get("n_corrections", 0)}


def extraction_may_not_emit_grams(extracted_field):
    """REQ-NUT-023. The extraction service emits the PHRASE, never a gram value.

    A model asked how many grams are in "a bowl of oats" will answer, and the answer will look
    identical to one that came from Joe's own corrected portion table.
    """
    if extracted_field.get("quantity_unit") in ("g", "gram", "grams") and \
            extracted_field.get("from_vernacular"):
        raise NutritionDisplayError(
            "REQ-NUT-023: the extraction service may not emit a gram value for a vernacular "
            "portion phrase; it emits the phrase and the resolver looks it up")
    return True


def correct_portion(alias_row, grams):
    """REQ-NUT-022. Joe's correction updates the grams and increments the counter.

    `n_corrections` is the useful number: a phrase corrected four times is one where the default
    was wrong four times, and that is worth surfacing before it is wrong a fifth.
    """
    return {**alias_row, "grams": grams,
            "n_corrections": alias_row.get("n_corrections", 0) + 1,
            "provenance": "joe"}


# ---------------------------------------------------------------- §D.4a counts of branded items

def resolve_count(count, branded_record):
    """REQ-NUT-050/052. count x the Branded per-serving gram weight, fractions included."""
    if branded_record is None or branded_record.get("serving_grams") is None:
        return None
    return {"grams": round(float(count) * float(branded_record["serving_grams"]), 2),
            "provenance": "extracted", "basis": f"{count} x {branded_record['serving_grams']}g"}


def resolve_quantifier(text, count_or_none, branded_record):
    """REQ-NUT-051/053. A vague quantifier gets no fraction, and a missing record gets no guess.

    "Most of a burrito" is not 0.75 of one. Assigning a fraction to it would invent a number and
    then carry it through a whole day's total, and the day's total is the figure Joe actually
    reads.
    """
    low = (text or "").lower()
    for q in VAGUE_QUANTIFIERS:
        if q in low:
            return {"nutrition_status": UNRESOLVED, "reason": "vague_quantifier",
                    "quantifier": q, "grams": None, "review": True,
                    "note": (f"{q!r} maps to no explicit fraction. Assigning one would invent a "
                             f"number and carry it into the day's total.")}
    for phrase, frac in EXPLICIT_FRACTIONS.items():
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", low):
            r = resolve_count(frac, branded_record)
            if r is None:
                break
            return r
    if count_or_none is None:
        return {"nutrition_status": UNRESOLVED, "reason": "no_count", "grams": None,
                "review": True}
    r = resolve_count(count_or_none, branded_record)
    if r is None:
        # REQ-NUT-051. Left unconverted rather than converted with a guessed serving weight.
        return {"nutrition_status": UNRESOLVED, "reason": "no_branded_serving_weight",
                "count": count_or_none, "grams": None, "review": True,
                "note": ("The count is kept verbatim. Without a per-serving gram weight from the "
                         "Branded record there is nothing to multiply it by.")}
    return r


# ---------------------------------------------------------------- §E.3 propagation and display

def daily_total(items):
    """REQ-NUT-043. Lows sum to the low; highs sum to the high.

    Summing the points and putting a band around them would understate the width: the errors here
    are systematic — portion sizes drift the same direction all day — not independent, so they do
    not cancel.
    """
    resolved = [i for i in items if i.get("nutrition_status") != UNRESOLVED]
    unresolved = len(items) - len(resolved)
    low = sum(float(i["kcal_low"]) for i in resolved)
    high = sum(float(i["kcal_high"]) for i in resolved)
    return {"kcal_low": round(low, 1) if resolved else None, "kcal_high": round(high, 1) if resolved else None,
            "kcal_point": round((low + high) / 2.0, 1) if resolved else None,
            "n_items": len(resolved),
            # REQ-NUT-026. Every total that includes an unresolved item's meal says how many.
            "unresolved_items": unresolved,
            "unresolved_note": (f"{unresolved} item(s) in this day could not be resolved and are "
                                f"not in these figures." if unresolved else "")}


def round_interval(low, high, *, places=0):
    """REQ-NUT-049. Never in a direction that narrows.

    Rounding 1,847.4–2,103.6 to 1,847–2,104 is fine. Rounding it to 1,850–2,100 removes 7 kcal of
    honest uncertainty for tidiness, and every such rounding along the chain removes a little
    more. So the low floors and the high ceils.
    """
    f = 10 ** places
    return (math.floor(float(low) * f) / f, math.ceil(float(high) * f) / f)


def render_value(point, low, high, *, estimate_method, status=None):
    """REQ-NUT-044/045/062/063/065. The interval is the value.

    An unresolved food is never a number (REQ-NUT-062) — not zero, not a dash with a tooltip: the
    words. And the visual weight follows the METHOD, never the magnitude (REQ-NUT-045), because
    weighting by magnitude makes a big number look more certain than a small one when the
    opposite is usually true.
    """
    if status == UNRESOLVED:
        return {"text": "not resolved", "numeric": False, "weight": "light",
                "note": "This item has no nutrient figures. It is not zero."}
    if low is None or high is None:
        raise NutritionDisplayError(
            "REQ-NUT-063: a nutrient interval may not be presented as a point estimate anywhere, "
            "including summaries, notifications and exports")
    lo, hi = round_interval(low, high)
    return {"text": f"~{round(point):g} kcal ({lo:g}–{hi:g})", "numeric": True,
            # REQ-NUT-065 / REQ-CAP-061: an inferred item never renders identically to a
            # confirmed one, and the difference is carried as data rather than left to CSS.
            "weight": METHOD_WEIGHT.get(estimate_method, "light"),
            "estimate_method": estimate_method}


def analysis_rows(rows, *, mode="restrict"):
    """REQ-NUT-046. Either weight by inverse interval width, or restrict to the tight methods.

    Both are offered because the requirement offers both. What is not available is treating a
    voice-logged estimate and a weighed portion as equally informative, which is what an
    unweighted correlation does.
    """
    if mode == "restrict":
        return tuple(r for r in rows if r.get("estimate_method") in TIGHT_METHODS)
    out = []
    for r in rows:
        width = float(r["kcal_high"]) - float(r["kcal_low"])
        out.append({**r, "weight": (1.0 / width) if width > 0 else 1.0})
    return tuple(out)


def deficit_statement(total, target):
    """REQ-NUT-047. When the interval is wider than the difference, say so in plain words.

    A day logged by voice routinely has a 500 kcal width. Reporting a 300 kcal deficit against it
    is reporting a difference the data cannot see, and the number would be believed.
    """
    if any(total.get(k) is None for k in ('kcal_low','kcal_point','kcal_high')):
        return {'resolvable':False,'text':"This day's logging has no usable nutrient total to compare."}
    width = float(total["kcal_high"]) - float(total["kcal_low"])
    diff = float(total["kcal_point"]) - float(target)
    if abs(diff) < width:
        return {"resolvable": False,
                "text": (f"Today's logging spans {width:.0f} kcal, which is wider than the "
                         f"{abs(diff):.0f} kcal difference from {target:.0f}. This day's logging "
                         f"cannot resolve that difference.")}
    return {"resolvable": True, "difference": round(diff, 1),
            "text": f"{abs(diff):.0f} kcal {'above' if diff > 0 else 'below'} {target:.0f}."}


def check_framing(payload):
    """REQ-NUT-048/064. No red/green, no over/under, no pass/fail, no "deficiency".

    "Deficiency" is a clinical term with a clinical meaning, and a low LOGGED intake is a fact
    about the logging at least as often as about the eating.
    """
    out = []
    blob = " ".join(str(v) for v in payload.values()).lower()
    for token in ("over budget", "under budget", "exceeded", "pass", "fail", "failed",
                  "on track", "off track"):
        if re.search(rf"(?<![a-z]){re.escape(token)}(?![a-z])", blob):
            out.append(f"REQ-NUT-048: judgment framing {token!r}")
    if payload.get("colour") in ("red", "green") or payload.get("color") in ("red", "green"):
        out.append("REQ-NUT-048: red/green judgment framing")
    for token in ("deficiency", "deficient"):
        if token in blob:
            out.append(f"REQ-NUT-064: {token!r} — a low LOGGED intake is a fact about the "
                       f"logging at least as often as about the eating")
    return tuple(out)


def confidence_may_not_narrow(interval, *, vision_confidence):
    """REQ-NUT-041. A model's per-item confidence never narrows a quantity interval.

    Its confidence is about IDENTIFICATION — how sure it is that this is a bagel. The interval is
    about QUANTITY. A confident identification says nothing about how big the bagel was, and
    letting it narrow the interval converts one kind of certainty into another it has no bearing
    on.
    """
    return {"interval": tuple(interval), "narrowed": False,
            "vision_confidence": vision_confidence,
            "note": ("Vision confidence describes identification, not portion size, so it does "
                     "not change this interval.")}


def unresolved_is_not_an_error(item):
    """REQ-NUT-027. A normal outcome, never a failure state.

    Shown as a failure it reads as something Joe did wrong; shown as a normal outcome it reads as
    a question he can answer, which is what it is.
    """
    if item.get('reason') in ('defaulted_event_time_excluded','defaulted_quantity_excluded'):
        field='event time' if item['reason']=='defaulted_event_time_excluded' else 'quantity'
        return {'status':UNRESOLVED,'is_error':False,'severity':'normal','item':item.get('name'),
                'label':'excluded: defaulted '+field,
                'text':'Excluded from this total because its '+field+' was supplied by a system default.'}
    return {"status": UNRESOLVED, "is_error": False, "severity": "normal",
            "text": "Not resolved yet — tell me what this was and it will be.",
            "item": item.get("name")}
