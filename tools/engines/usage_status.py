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


def from_evidence(subject, rows, *, as_of, unused_after_days=60):
    """REQ-FIN-111/113. A tier, with the concrete evidence that produced it.

    An empty evidence list returns 'unknown', never 'unused'. A gym membership with no
    `place_visit` rows is not an unused gym membership; it is one about which nothing is
    recorded, and those two license entirely different sentences.
    """
    if not rows:
        return initial_status(subject)
    latest = max(rows, key=lambda r: r["day"])
    days = (as_of - latest["day"]).days
    tier = "used" if days < unused_after_days else "unused"
    # REQ-FIN-113's own example, in its own shape.
    evidence = f"last {subject} {latest['kind']} {days} days ago ({latest['day'].isoformat()})"
    # Confidence falls with the age of the evidence: a visit yesterday says more about today than
    # one eleven weeks ago, and reporting both at the same confidence would flatten that.
    confidence = round(max(0.05, min(0.95, 1.0 - days / 365.0)), 2)
    return UsageStatus(subject=subject, tier=tier, evidence=evidence,
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
