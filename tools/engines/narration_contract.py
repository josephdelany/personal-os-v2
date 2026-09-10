"""B20 §A — the language layer's contract and the render pipeline (REQ-NAR-001..006, 010..015).

Pure: no database, no network, no model call. The model's OUTPUT is passed in; what comes back is
what may be shown.

THE ARRANGEMENT. Every number in this system is computed by SQL or by a pure Python engine, and
the model's entire job is to put those numbers into a sentence. RULE-09 and RULE-11 say so, and
this module is what makes the saying enforceable, in two directions:

  * WHAT GOES IN (REQ-NAR-001). A structured result object, and nothing else. No atom rows, no
    photo references, no coordinates. A model that receives raw rows will summarise them, and its
    summary will be a computation nobody registered.
  * WHAT COMES BACK (REQ-NAR-004/005/006/012). Every numeral must already exist in the result
    object; every entity must already be named there; every causal link must already be an edge
    there. Anything else is discarded and the deterministic template is shown instead.

WHY THE FALLBACK IS A TEMPLATE AND NOT AN ERROR (REQ-NAR-013). A refused sentence still has a
number behind it that is perfectly good. Showing an error would hide a real answer because the
prose around it was wrong; showing the template shows the answer in plainer words. The violation
is logged either way, so a model that keeps failing is visible without the user paying for it.

WHY A NUMERAL WITHOUT ITS UNIT IS A DEFECT (REQ-NAR-014). "Your sleep was 7.4" is not a shorter
way of saying "7.4 hours" -- it is a sentence a reader completes themselves, and half of them
will complete it wrongly. The unit travels with the slot, not with the template's prose.

WHY ROUNDING MUST BE REGISTERED (REQ-NAR-015). Ad-hoc rounding in a template is a computation:
7.44 rendered as "7" is a different claim from 7.44 rendered as "7.4", and neither is traceable
to a stored value unless the rounding rule itself is stored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# REQ-NAR-001. What may never enter the language layer's input.
FORBIDDEN_INPUT_KEYS = ("atoms", "atom_rows", "raw_captures", "rows", "photo", "photo_ref",
                        "photos", "image", "lat", "lon", "latitude", "longitude", "coordinate",
                        "coordinates", "geo")

# REQ-NAR-005. A relation must be an EDGE in the input, not a word in the output.
CAUSAL_CONNECTIVES = (r"\bbecause\b", r"\bcauses?\b", r"\bcaused\b", r"\bled to\b",
                      r"\bleads to\b", r"\bdue to\b", r"\bmakes? you\b", r"\bdrives?\b",
                      r"\bresult(?:s|ed) in\b", r"\btriggers?\b", r"\bso\b")

NUMERAL = re.compile(r"[-+]?[0-9][0-9,]*(?:\.[0-9]+)?")


class NarrationRefused(Exception):
    """REQ-NAR-001. Raised before the call, because a bad input cannot be repaired after it."""


@dataclass(frozen=True)
class Slot:
    """REQ-NAR-010. A numeric slot, bound by NAME to a field of the result object."""
    name: str
    field: str
    unit: str | None = None
    rounding: str | None = None      # a registered rule name, never an inline format


@dataclass(frozen=True)
class Template:
    text: str
    slots: tuple = ()

    def __post_init__(self):
        declared = {s.name for s in self.slots}
        used = set(re.findall(r"\{(\w+)\}", self.text))
        missing = used - declared
        if missing:
            raise ValueError(f"REQ-NAR-010: {sorted(missing)} appear in the template with no "
                             f"declared slot bound to a result field")
        # A numeral written directly into template prose is a number nobody can trace: it did not
        # come from the result object and no slot binds it.
        prose = re.sub(r"\{\w+\}", "", self.text)
        if NUMERAL.search(prose):
            raise ValueError("REQ-NAR-010/012: a literal numeral in template prose has no slot "
                             "binding it to a stored value")


# REQ-NAR-015. Rounding rules are registered per metric, by name.
ROUNDING_RULES = {
    "integer": lambda v: f"{round(float(v)):d}",
    "one_dp": lambda v: f"{float(v):.1f}",
    "two_dp": lambda v: f"{float(v):.2f}",
    "thousands": lambda v: f"{round(float(v)):,d}",
}


def check_input(payload):
    """REQ-NAR-001. A structured result object, and nothing else.

    A model that receives raw rows will summarise them, and its summary is a computation nobody
    registered. Refused before the call because a bad input cannot be repaired afterwards -- the
    sentence is already written by then.
    """
    def walk(node, path="$"):
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in FORBIDDEN_INPUT_KEYS:
                    raise NarrationRefused(
                        f"REQ-NAR-001: {path}.{k} may not reach the language layer; it receives "
                        f"a structured result object, never raw rows, photos or coordinates")
                walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(payload)
    return True


def scalar_values(result):
    """Every scalar in the result object, as strings, for numeral matching.

    PROSE fields are excluded for the same reason 0059's SQL verifier excludes them: a clause
    stored in the result and compared against itself is self-certifying, and the check that
    claimed to prove it introduced no untraced numeral would be proving nothing.
    """
    prose = {"note", "caveat", "summary", "text", "narration", "clause", "disclosure",
             "what_would_raise_it", "rolling_28_clause"}
    out = []
    for k, v in (result or {}).items():
        if k in prose or isinstance(v, (dict, list, tuple)):
            continue
        if v is not None and not isinstance(v, bool):
            out.append(str(v))
    return tuple(out)


def permitted_numerals(result, *, rounding_rules=None):
    """REQ-NAR-012. Every value in the result object, plus its REGISTERED roundings.

    "a registered rounding of one" is the requirement's own phrase, and it is what lets a
    template show 7.4 for a stored 7.4213 without opening the door to any convenient number.
    """
    rules = rounding_rules or ROUNDING_RULES
    out = set()
    for s in scalar_values(result):
        out.add(s.replace(",", ""))
        for m in NUMERAL.finditer(s):
            out.add(m.group(0).replace(",", ""))
        try:
            f = float(s.replace(",", ""))
        except (TypeError, ValueError):
            continue
        for fn in rules.values():
            try:
                out.add(fn(f).replace(",", ""))
            except (TypeError, ValueError):
                continue
    return out


def verify_numerals(text, result, *, rounding_rules=None):
    """REQ-NAR-012. Every numeral in the string traces to a stored value or a registered rounding."""
    allowed = permitted_numerals(result, rounding_rules=rounding_rules)
    bad = [m.group(0) for m in NUMERAL.finditer(text or "")
           if m.group(0).replace(",", "") not in allowed]
    return tuple(bad)


def verify_entities(text, result):
    """REQ-NAR-004. No entity the result object does not name.

    Checked over the result's own string values rather than a global list, because the question
    is not "is this a real merchant" but "did the input mention it". A model that adds a plausible
    entity is inventing a claim, and plausibility is exactly what makes it dangerous.
    """
    named = " ".join(scalar_values(result)).lower()
    # Capitalised multi-word runs are the shape an invented entity takes in generated prose.
    candidates = re.findall(r"\b(?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)+\b", text or "")
    return tuple(c for c in candidates if c.lower() not in named)


def verify_relations(text, result):
    """REQ-NAR-005. A causal or contributory relation must be an EDGE in the input.

    The model may say two things happened. It may not say one happened because of the other
    unless the result object already carries that edge -- because the edge is the thing that was
    computed, tiered and registered, and the sentence is not.
    """
    if result.get("edges") or result.get("relation") or result.get("hypothesis_id"):
        return ()
    low = (text or "").lower()
    return tuple(c for c in CAUSAL_CONNECTIVES if re.search(c, low))


def render_template(template, result, *, rounding_rules=None):
    """REQ-NAR-010/011/014/015. Slots injected from the result object; nothing else.

    The deterministic rendering. This is what is shown when the model's sentence is refused, and
    it is also the thing the model's sentence is checked against.
    """
    rules = rounding_rules or ROUNDING_RULES
    values = {}
    for slot in template.slots:
        if slot.field not in result:
            raise ValueError(f"REQ-NAR-011: slot {slot.name!r} is bound to {slot.field!r}, which "
                             f"the result object does not contain")
        raw = result[slot.field]
        if slot.rounding is not None:
            if slot.rounding not in rules:
                # REQ-NAR-015. Ad-hoc rounding is a computation: 7.44 as "7" is a different claim
                # from 7.44 as "7.4", and neither is traceable unless the rule itself is stored.
                raise ValueError(f"REQ-NAR-015: rounding rule {slot.rounding!r} is not registered")
            shown = rules[slot.rounding](raw)
        else:
            shown = str(raw)
        if slot.unit:
            # REQ-NAR-014. "Your sleep was 7.4" is not a shorter way of saying "7.4 hours" -- it
            # is a sentence the reader completes, and half of them complete it wrongly.
            shown = f"{shown} {slot.unit}"
        elif NUMERAL.fullmatch(str(shown)):
            raise ValueError(f"REQ-NAR-014: slot {slot.name!r} renders a bare numeral with no "
                             f"unit attached")
        values[slot.name] = shown
    return template.text.format(**values)


def accept(model_text, *, template, result, tier, model_tier=None, rounding_rules=None,
           finding_id=None):
    """The whole contract, applied to one generated sentence.

    Returns what may be shown, plus any `render_violations` rows. REQ-NAR-013: a refused sentence
    falls back to the deterministic template rather than to an error, because the number behind it
    is perfectly good and showing an error would hide a real answer for a prose fault.
    """
    deterministic = render_template(template, result, rounding_rules=rounding_rules)
    violations = []

    # REQ-NAR-003. The model does not get a vote on the tier.
    if model_tier is not None and model_tier != tier:
        violations.append({"rule": "REQ-NAR-003", "detail": f"{model_tier!r} != {tier!r}"})
    for n in verify_numerals(model_text, result, rounding_rules=rounding_rules):
        violations.append({"rule": "REQ-NAR-012", "detail": f"untraceable numeral {n!r}"})
    for e in verify_entities(model_text, result):
        violations.append({"rule": "REQ-NAR-004", "detail": f"entity not in the result: {e!r}"})
    for r in verify_relations(model_text, result):
        violations.append({"rule": "REQ-NAR-005",
                           "detail": f"causal relation {r!r} with no edge in the input"})

    if violations:
        return {"text": deterministic, "used": "deterministic_template",
                "tier": tier,
                "rows": tuple({**v, "finding_id": finding_id,
                               "offending_text": model_text,
                               "result_fields": tuple(sorted(result))} for v in violations)}
    return {"text": model_text, "used": "model", "tier": tier, "rows": ()}


@dataclass
class NarrationLog:
    """REQ-NAR-002. The language layer's only writable table, and it is append-only.

    Append-only because a narration is evidence of what the system SAID, and a system that can
    revise its own account of what it said cannot be audited on it.
    """
    entries: list = field(default_factory=list)

    def append(self, entry):
        self.entries.append(dict(entry))
        return len(self.entries)

    def __setitem__(self, *_):
        raise TypeError("REQ-NAR-002: narration_log is append-only")

    def writable_tables(self):
        return ("narration_log",)
