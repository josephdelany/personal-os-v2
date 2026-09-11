"""B17 §C.1 — necessity is a tier, not a fact (REQ-FIN-110..116).

Pure: no database, no clock, no model.

THE WHOLE SECTION IN ONE SENTENCE. Whether a purchase was worth making is not a fact this system
can observe, so it does not model one. What it can observe is whether the thing has been USED,
and even that has three states rather than two.

WHY THREE TIERS AND NOT A BOOLEAN (REQ-FIN-110). 'used' / 'unused' / 'unknown'. A boolean forces
every purchase into used-or-not, and the overwhelming majority of them are neither: there is
simply no evidence either way. Collapsing 'unknown' into 'unused' is what turns a system that
lacks data into a system that accuses.

The same argument rules out a score and a percentage. "68% used" is a number with no referent --
there is nothing it is 68% of -- and it would be read as a judgement with decimal places.

WHY THE DEFAULT IS 'unknown' AND MOVES ONLY ON EVIDENCE (REQ-FIN-111). A gym membership with no
`place_visit` rows is not an unused gym membership; it is a gym membership about which nothing is
recorded, and those two differ entirely in what they license the system to say.

WHY THE WORDS ARE BANNED OUTRIGHT (REQ-FIN-112). 'necessary', 'unnecessary', 'needed',
'wasteful', 'frivolous' -- written, stored, displayed OR exported. Not softened, not gated behind
a tier: banned. Each of them asserts a judgement about how Joe should live that no transaction
record can support, and a stored one leaks into an export or a prompt later.

WHY A BARE LABEL IS FORBIDDEN (REQ-FIN-113). "Unused" alone is an accusation. "Last gym
place_visit 71 days ago" is a fact Joe can immediately confirm, correct, or explain -- and the
difference between those two sentences is the difference between a system he argues with and one
he trusts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TIERS = ("used", "unused", "unknown")            # REQ-FIN-110, exactly three
DEFAULT_TIER = "unknown"                         # REQ-FIN-111

# REQ-FIN-112, verbatim from the requirement.
FORBIDDEN_WORDS = ("necessary", "unnecessary", "needed", "wasteful", "frivolous")


class ForbiddenJudgement(Exception):
    """REQ-FIN-112. Raised on write, not filtered on display: a stored word leaks later."""


@dataclass(frozen=True)
class UsageStatus:
    subject: str
    tier: str
    evidence: str                 # REQ-FIN-113, concrete, never a bare label
    provenance: str               # 'inferred' | 'joe'
    confidence: float
    supersedes: str | None = None

    def __post_init__(self):
        if self.tier not in TIERS:
            raise ValueError(f"REQ-FIN-110: {self.tier!r} is not one of {TIERS}; usage status is "
                             f"three tiers, never a boolean, a score or a percentage")
        if not self.evidence:
            raise ValueError("REQ-FIN-113: a usage status is never displayed as a bare label; "
                             "name the evidence that produced it")
        guard_words(self.evidence)
        guard_words(self.subject)
        if self.provenance == "joe":
            # RULE-10 / REQ-FIN-114. Joe's own statement is certain by definition.
            if self.confidence != 1.0:
                raise ValueError("REQ-FIN-114: a status Joe set carries confidence 1.0")
        elif self.provenance != "inferred":
            raise ValueError("REQ-FIN-114: provenance is 'inferred' unless Joe set it directly. "
                             "How the spine represents a direct human override is OQ-32 and is "
                             "deliberately not decided here.")
        elif not 0.0 <= self.confidence < 1.0:
            raise ValueError("REQ-FIN-114: an inferred status carries a confidence below 1.0; "
                             "certainty is reserved for Joe")


def guard_words(text):
    """REQ-FIN-112. Written, stored, displayed OR exported — all four are the same check."""
    low = (text or "").lower()
    for w in FORBIDDEN_WORDS:
        if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", low):
            raise ForbiddenJudgement(
                f"REQ-FIN-112: {w!r} may not be written, stored, displayed or exported in "
                f"reference to any transaction, merchant or category")
    return True


def initial_status(subject):
    """REQ-FIN-111. Everything starts unknown, and says why."""
    return UsageStatus(subject=subject, tier=DEFAULT_TIER,
                       evidence="No usage evidence has been recorded for this purchase.",
                       provenance="inferred", confidence=0.0)


def from_evidence(subject, rows, *, as_of, unused_after_days=60, source_last_seen=None):
    """REQ-FIN-111/113, REQ-REC-009. A tier, with the concrete evidence that produced it.

    An empty evidence list returns 'unknown', never 'unused'. A gym membership with no
    `place_visit` rows is not an unused gym membership; it is one about which nothing is
    recorded, and those two license entirely different sentences.

    **`source_last_seen` IS WHAT SEPARATES A QUIET GYM FROM A DEAD SENSOR** (INTENT_COVERAGE R4).
    It is the last subject day on which the evidence SOURCE produced anything at all -- not about
    this subject, about anything -- which is what `tools/check_freshness.py` already measures per
    metric.

    'unused' is a claim that Joe did not go somewhere, and it is supportable only if something
    was watching and saw nothing. Stale evidence has two entirely different causes:

        the source kept capturing and recorded no visit   -> 'unused' is supported
        the source stopped capturing                      -> 'unknown'; nothing was watching

    Before this they were read identically. That is not hypothetical here: the Watch stopped in
    five stages ending 2026-08-21 and the bank CSV export died 2026-05-13, so the largest
    silences in this system are its own instruments failing. Reading those as 'unused' would
    accuse Joe of not going to the gym on the strength of a broken logger.

    **`source_last_seen=None` MEANS THE CALLER HAS NOT ESTABLISHED CONTINUITY, AND YIELDS
    'unknown'.** The permissive default was the whole bug: a caller who never considered the
    question silently got the accusatory answer. An 'unused' now has to be asked for by a caller
    able to say what was watching, which is the only kind of caller entitled to one.
    """
    if not rows:
        return initial_status(subject)
    latest = max(rows, key=lambda r: r["day"])
    days = (as_of - latest["day"]).days
    # Confidence falls with the age of the evidence: a visit yesterday says more about today than
    # one eleven weeks ago, and reporting both at the same confidence would flatten that.
    confidence = round(max(0.05, min(0.95, 1.0 - days / 365.0)), 2)
    # REQ-FIN-113's own example, in its own shape.
    evidence = f"last {subject} {latest['kind']} {days} days ago ({latest['day'].isoformat()})"

    if days < unused_after_days:
        return UsageStatus(subject=subject, tier="used", evidence=evidence,
                           provenance="inferred", confidence=confidence)

    # The evidence is stale. Whether that means anything at all depends on whether anything was
    # still watching, so the tier is not decided until that is known.
    if source_last_seen is None:
        return UsageStatus(
            subject=subject, tier=DEFAULT_TIER,
            evidence=(f"{evidence}; no continuity was established for the source, so the "
                      f"silence since then cannot be read as absence of use"),
            provenance="inferred", confidence=0.0)
    if source_last_seen <= latest["day"]:
        # The source produced nothing after the last recorded use, so there has been no
        # observation window at all. REQ-REC-009: absence of a record is absence of capture.
        silent = (as_of - source_last_seen).days
        return UsageStatus(
            subject=subject, tier=DEFAULT_TIER,
            evidence=(f"{evidence}, and the source itself last recorded anything {silent} days "
                      f"ago ({source_last_seen.isoformat()}) -- the gap is the source's, not a "
                      f"record of absence"),
            provenance="inferred", confidence=0.0)

    # Something was watching after the last recorded use, and registered none.
    watched = (source_last_seen - latest["day"]).days
    return UsageStatus(
        subject=subject, tier="unused",
        evidence=(f"{evidence}; the source kept recording for {watched} days afterwards "
                  f"(to {source_last_seen.isoformat()}) and registered no further use"),
        provenance="inferred", confidence=confidence)


def override(existing, tier, *, note, subject=None):
    """REQ-FIN-115. Joe's override is permanent and no automated process may change it.

    The inferred row is SUPERSEDED rather than replaced, so "what did the system think before he
    told us" still has an answer.
    """
    guard_words(note)
    return UsageStatus(subject=subject or existing.subject, tier=tier,
                       evidence=note, provenance="joe", confidence=1.0,
                       supersedes=getattr(existing, "subject", None) and existing.evidence)


def automated_update(existing, proposed):
    """REQ-FIN-115. An automated process may not touch a status Joe set."""
    if existing.provenance == "joe":
        raise ValueError("REQ-FIN-115: Joe set this usage status; no automated process may "
                         "change it")
    return proposed


def as_interval(low, high, *, observed=False):
    """REQ-FIN-116. An inferred quantity is an interval, never a point.

    A point estimate of something nobody measured states a precision the method does not have,
    and a single number is what a reader remembers. An OBSERVED quantity is a point, because it
    was measured — the rule is about inference, not about formatting.
    """
    if observed:
        if low != high:
            raise ValueError("REQ-FIN-116: an observed quantity is a single measured value")
        return {"value": low, "kind": "observed"}
    if high < low:
        raise ValueError("REQ-FIN-116: an interval's upper bound is not below its lower")
    if low == high:
        raise ValueError("REQ-FIN-116: an inferred quantity may not be expressed as a point "
                         "estimate; a zero-width interval is a point with brackets on it")
    return {"low": low, "high": high, "kind": "inferred"}
