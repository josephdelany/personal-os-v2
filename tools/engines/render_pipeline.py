"""B20 §B — the render pipeline (REQ-NAR-024, 026, 030..039).

Pure: no database, no network, no model. The pipeline's whole job is to be the place where a
result becomes a screen, with the model as an OPTIONAL improvement rather than a dependency.

WHY EVERY SURFACE RENDERS WITH THE LANGUAGE LAYER DISABLED (REQ-NAR-030/031/032). Every number in
this system is computed deterministically. The model's contribution is the sentence around it. So
a surface that goes blank when the model is unavailable has made the model load-bearing for facts
it did not produce -- and it will go blank on exactly the day something is worth reading.

The pipeline therefore has NO error path for model unavailability. It has a template path, and
the template path is the default the model improves on rather than a fallback it replaces.

WHY THE CHART GOES BELOW THE VERDICT (REQ-NAR-034). A chart above the text is read first, and a
reader who has already formed a view from the shape will read the sentence as confirmation.
Below, the sentence sets the claim and the chart shows the evidence for it -- which is the order
in which they were actually produced.

WHY A CANDIDATE GETS NO CHART AT ALL (REQ-NAR-035). A chart is the most persuasive object this
system can render. On an unconfirmed candidate it converts "a generator flagged this" into
something that looks measured, and no label under it undoes that.

WHY THE FRONT END COMPUTES NOTHING (REQ-NAR-033). A percentage calculated in the browser has no
stored result to trace to, no code_version, and no way to appear in an export -- and it is
indistinguishable on screen from one that does.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

DECLINE_COOLDOWN_DAYS = 7            # REQ-NAR-026
EXPORT_TABLES = ("atoms", "links", "findings", "computations", "predictions", "tier_history")
TRUST_SECTION_FIELDS = ("coverage", "missingness_flags", "calibration_state")   # REQ-NAR-036
# REQ-TIER-048 / REQ-NAR-038, the disclosure set a recommendation must carry.
RECOMMENDATION_FIELDS = ("tier", "effect_size", "interval", "n", "coverage",
                         "what_would_change_this")


class RenderViolation(Exception):
    pass


def render(claim, *, template, model_text=None, language_layer_available=True):
    """REQ-NAR-030/031/032. There is no error path for the model being down.

    The template path is the DEFAULT that the model improves on, not a fallback it replaces. A
    surface that goes blank when the model is unavailable has made the model load-bearing for
    facts it did not produce — and it will go blank on exactly the day something is worth reading.
    """
    if not language_layer_available or model_text is None:
        return {"text": template, "path": "deterministic_template", "error": None,
                "degraded": False}
    return {"text": model_text, "path": "model", "error": None, "degraded": False}


def check_conditional_on_model(feature):
    """REQ-NAR-032. No function, brief, answer or alert may be conditional on the model."""
    if feature.get("requires_language_layer"):
        raise RenderViolation(
            f"REQ-NAR-032: {feature.get('name')!r} is conditional on the language layer; every "
            f"function, brief, answer and alert works without it")
    return True


def check_frontend_computation(displayed, *, stored_values):
    """REQ-NAR-033. Every displayed number is computed in the deterministic layer.

    A percentage calculated in the browser has no stored result to trace to, no code_version, and
    no way to appear in an export — and it is indistinguishable on screen from one that does.
    """
    stored = {str(v) for v in stored_values}
    invented = tuple(d for d in displayed if str(d) not in stored)
    if invented:
        raise RenderViolation(
            f"REQ-NAR-033: {list(invented)} are not stored values; the front end renders numbers "
            f"and computes none")
    return True


def layout(verdict_text, chart, *, tier):
    """REQ-NAR-034/035. Chart below the verdict, and no chart at all for a CANDIDATE.

    Above the text a chart is read first, and a reader who has already formed a view from the
    shape reads the sentence as confirmation. Below, the sentence sets the claim and the chart
    shows the evidence — the order in which they were actually produced.
    """
    if tier in ("CANDIDATE", "EXPLORATORY") and chart is not None:
        raise RenderViolation(
            "REQ-NAR-035: no chart for a CANDIDATE claim; a chart is the most persuasive object "
            "this system renders, and on an unconfirmed candidate it converts 'a generator "
            "flagged this' into something that looks measured")
    blocks = [{"kind": "verdict", "text": verdict_text}]
    if chart is not None:
        blocks.append({"kind": "chart", "chart": chart})
    return {"blocks": tuple(blocks), "chart_below_verdict": True}


def declined(suggestion_id, *, declined_days_ago, mentions_skipped_day=False):
    """REQ-NAR-026. Not re-proposed for 7 days, and a skipped day is never mentioned.

    The second half is the one that gets forgotten: "you did not log yesterday" is a reproach
    dressed as a status line, and it is the sentence most likely to end the logging altogether.
    """
    if mentions_skipped_day:
        raise RenderViolation(
            "REQ-NAR-026: a skipped day is never mentioned; 'you did not log yesterday' is a "
            "reproach dressed as a status line")
    if declined_days_ago is not None and declined_days_ago < DECLINE_COOLDOWN_DAYS:
        return {"propose": False, "reason": (f"declined {declined_days_ago} day(s) ago; not "
                                             f"re-proposed for {DECLINE_COOLDOWN_DAYS} days")}
    return {"propose": True}


def check_moralising(text, *, is_recommendation=False, tier=None, interval=None):
    """REQ-NAR-024 / RULE-25. No moralising judgment on a rating, total or behaviour.

    A decision-under-uncertainty recommendation is PERMITTED — with its tier and interval. The
    distinction is real and worth keeping: "you spent too much" is a verdict on Joe, while
    "consider moving caffeine earlier (DESCRIPTIVE, 22±18 min)" is an option with its evidence
    attached, and banning both would leave the system unable to suggest anything at all.
    """
    from tools.engines.narration import MORALISING
    hits = tuple(w for w in MORALISING
                 if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", (text or "").lower()))
    if not hits:
        return ()
    if is_recommendation and tier and interval:
        return ()
    return tuple(f"REQ-NAR-024: moralising judgment {w!r}" for w in hits)


def recommendation_template(rec, *, vocabulary):
    """REQ-NAR-038/039. The full REQ-TIER-048 disclosure set, and a vocabulary from the TABLE.

    `vocabulary` is the `recommendation` row of `tier_vocabulary`, passed in exactly as
    REQ-NAR-020 reads the per-tier rows — never a hardcoded list, because a hardcoded list is one
    that cannot be corrected without a deploy, and the wording of a recommendation is precisely
    the thing Joe is most likely to want corrected.
    """
    missing = [f for f in RECOMMENDATION_FIELDS if rec.get(f) is None]
    if missing:
        raise RenderViolation(
            f"REQ-NAR-038: a recommendation renders with {missing} too; the disclosure set is "
            f"what makes it a suggestion rather than an instruction")
    if not vocabulary:
        raise RenderViolation(
            "REQ-NAR-039: the recommendation vocabulary is read from tier_vocabulary, never "
            "hardcoded; a hardcoded list cannot be corrected without a deploy, and the wording "
            "is the thing most likely to need correcting")
    text = rec.get("text", "")
    permitted = tuple(v for v in vocabulary.get("permitted", ())
                      if v.lower() in text.lower())
    forbidden = tuple(v for v in vocabulary.get("forbidden", ())
                      if re.search(rf"(?<![a-z]){re.escape(v.lower())}(?![a-z])", text.lower()))
    if forbidden:
        raise RenderViolation(
            f"REQ-NAR-039: {list(forbidden)} assert a settled outcome; a recommendation carries "
            f"hedged decision verbs")
    if not permitted:
        raise RenderViolation(
            f"REQ-NAR-039: no permitted recommendation verb in {text!r}; the vocabulary row "
            f"lists {list(vocabulary.get('permitted', ()))}")
    return {"text": text, "tier": rec["tier"], "effect_size": rec["effect_size"],
            "interval": tuple(rec["interval"]), "n": rec["n"], "coverage": rec["coverage"],
            "what_would_change_this": rec["what_would_change_this"],
            "verbs_used": permitted}


# A sign only counts as part of a numeral when it is NOT preceded by a digit or a decimal point.
# Without that lookbehind, the interval "22 minutes (4-40)" parses as 4 and MINUS 40, and the
# checker flags a legitimate range as an invented number — the hyphen in a range is not a minus
# sign, and a range written with a hyphen is exactly how every interval on these surfaces is
# rendered. Found by this module's own test on its own example sentence.
NUMERAL = re.compile(r"(?<![\d.])[-+]?[0-9]+(?:\.[0-9]+)?")


def check_recommendation_numerals(rec):
    """REQ-NAR-038's second clause: no numeral absent from the recommendation's stored fields."""
    stored = set()
    for f in RECOMMENDATION_FIELDS:
        v = rec.get(f)
        for part in (v if isinstance(v, (list, tuple)) else [v]):
            if part is not None:
                stored.add(str(part))
                for m in NUMERAL.finditer(str(part)):
                    stored.add(m.group(0))
    bad = tuple(m.group(0) for m in NUMERAL.finditer(rec.get("text", ""))
                if m.group(0) not in stored)
    return bad


def weekly_summary(sections):
    """REQ-NAR-036. The TRUST section is in every weekly summary, not an option.

    Coverage, missingness and calibration are the three things that decide whether the rest of
    the summary means anything. A summary that reports findings without them is a summary that
    reads the same in a week when the Watch was off.
    """
    trust = sections.get("trust") or {}
    missing = [f for f in TRUST_SECTION_FIELDS if f not in trust]
    if missing:
        raise RenderViolation(
            f"REQ-NAR-036: the TRUST section carries {missing}; without them the summary reads "
            f"the same in a week when the Watch was off")
    return {**sections, "trust": trust, "trust_present": True}


def export(tables, *, price=0, synchronous=True, partial=False):
    """REQ-NAR-037. Complete, free, synchronous.

    All three words are load-bearing. An export that costs is a hostage; one that arrives by
    email later is one nobody checks; and one missing `tier_history` cannot answer "what did the
    system claim before it changed its mind", which is the question an export is FOR.
    """
    missing = [t for t in EXPORT_TABLES if t not in tables]
    if missing:
        raise RenderViolation(
            f"REQ-NAR-037: the export is complete and is missing {missing}; without tier_history "
            f"it cannot answer what the system claimed before it changed its mind")
    if price != 0 or not synchronous or partial:
        raise RenderViolation(
            "REQ-NAR-037: the export is complete, free and synchronous; a paid export is a "
            "hostage and a deferred one is never checked")
    return {"tables": tuple(EXPORT_TABLES), "price": 0, "synchronous": True, "complete": True}
