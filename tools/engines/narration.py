"""B20 — the tier vocabulary linter (REQ-NAR-020..023, REQ-TIER-020; RULE-19, RULE-23).

A tier is a claim about how much is known. Vocabulary is how a tier leaks: "steps were
typically 2,206" and "steps increase HRV" can sit on the same evidence, and only the second
asserts something the evidence cannot carry. The tiers are enforced in the data all the way
down and then one verb undoes it.

WHAT A VIOLATION IS. Not "an unrecognised word" — most words belong to no tier. A violation is
a term reserved for a tier ABOVE the one this claim was assigned. `tier_vocabulary` is a set of
per-tier allow-lists, so the linter ranks the tiers and asks whether any term from a higher
rank appears.

WHY THE MONTH OF MAY NEARLY BROKE IT. "may" is EXPLORATORY vocabulary. A DESCRIPTIVE answer
reading "over 1 May to 30 May" contains it twice, and a case-insensitive match would discard a
correct answer and write a violation row about it — a linter that silences true statements is
worse than no linter, because the failure is invisible and looks like reticence. Terms that are
also ordinary proper nouns are matched CASE-SENSITIVELY in lower case only.

This module is pure. The vocabulary is passed in from `config.tier_vocabulary`, never hardcoded
(REQ-TIER-020 says the linter reads the table).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The ladder, lowest first. `_ask_tier_rank` in 0049 orders the same way; this is the render
# side of the same ordering and a test pins them together.
#
# CANDIDATE AND EXPLORATORY ARE ONE RUNG UNDER TWO NAMES, and the system genuinely uses both.
# `core.findings.tier` (0007) permits 'CANDIDATE'; `config.tier_vocabulary` (0049) names the
# same rung 'EXPLORATORY', because REQ-NAR-013 defines the EXPLORATORY SURFACE as where a
# CANDIDATE finding may appear. A linter that knew only one of them would RAISE on a real
# findings row rather than lint it — and REQ-NAR-020 requires every generated claim to be
# linted, so raising is not a safe failure. Both rank identically here; which name is canonical
# is a decision, recorded as OQ-66.
TIER_ORDER = ("INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY", "PROMOTED",
              "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")
TIER_ALIASES = {"CANDIDATE": "EXPLORATORY"}

# Terms that are also ordinary English proper nouns or nouns. Matched in lower case only, so a
# date or a name cannot trip the linter. Anything not listed here is matched case-insensitively.
CASE_SENSITIVE_TERMS = frozenset({"may", "march", "will"})

# REQ-NAR-021 reserves "a VERB OR QUALIFIER not permitted at its tier". Some rows in
# `tier_vocabulary` are neither: they are the scaffolding a phrase needs — "highest ON Tuesday"
# — and they carry no claim on their own. Treating them as reservations makes the linter fail a
# correct template: the live INSUFFICIENT copy, "There is not enough data ON {display}", was
# flagged for a preposition. A linter that discards true statements is worse than none, because
# the failure is invisible and reads as reticence.
#
# This list is deliberately tiny and only prepositions. Anything that could carry a claim —
# "per", as in a rate — stays a reservation.
STRUCTURAL_TERMS = frozenset({"on", "in", "at", "of", "to", "over"})

# REQ-NAR-023, verbatim from the requirement, plus RULE-23's standalone `necessary`.
MORALISING = ("excessive", "wasteful", "necessary", "unnecessary", "too much", "splurge",
              "guilty")


# REQ-NAR-025 / RULE-24. Four surfaces this system may never show, banned as CONCEPTS rather
# than as words, because each is a way of converting a measurement into a verdict:
#
#   a streak       — makes a missing day a failure. Joe's capture has stopped twice this year
#                    through no act of his; a streak would have scored both as lapses.
#   a compliance   — measures obedience to a plan rather than what happened.
#     score
#   a composite    — averages incomparable measures into one number whose movement cannot be
#     wellness       attributed to anything, and whose inputs have wildly different coverage.
#     score
#   a celebration  — attaches an emotional reward to a number, which is what makes a metric
#                    worth gaming.
FORBIDDEN_SURFACES = (
    ("streak", re.compile(r"\bstreaks?\b|\bdays? in a row\b|\bconsecutive days?\b", re.I)),
    ("compliance_score", re.compile(r"\bcompliance\b|\badherence score\b", re.I)),
    ("composite_score", re.compile(r"\bwellness score\b|\bhealth score\b|\breadiness score\b"
                                   r"|\boverall score\b", re.I)),
    ("celebration", re.compile(r"\bcongratulations?\b|\bwell done\b|\bkeep it up\b"
                               r"|\bnice work\b|🎉|🔥", re.I)),
)


def forbidden_surface(text: str):
    """REQ-NAR-025 / RULE-24. Which banned surface a string would render, if any."""
    return tuple(kind for kind, pattern in FORBIDDEN_SURFACES
                 if pattern.search(text or ""))


@dataclass(frozen=True)
class Violation:
    term: str
    term_tier: str
    claim_tier: str
    rule: str = "vocabulary_above_tier"


def rank(tier: str) -> int:
    tier = TIER_ALIASES.get(tier, tier)
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        # An unknown tier is not treated as the lowest — that would make every term permitted.
        raise ValueError(f"unknown tier {tier!r}; expected one of {TIER_ORDER}")


def _appears(term: str, text: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
    if term.lower() in CASE_SENSITIVE_TERMS:
        return re.search(pattern, text) is not None          # lower case only
    return re.search(pattern, text, re.I) is not None


def lint(claim: str, tier: str, vocabulary) -> tuple[Violation, ...]:
    """REQ-NAR-020/021. Terms in `claim` reserved for a tier above `tier`.

    `vocabulary` maps a tier to its permitted terms, exactly as `config.tier_vocabulary` stores
    it. A term permitted at THIS tier or below is fine; a term permitted only above it is the
    violation, and the caller discards the string and renders the deterministic template.
    """
    claim_rank = rank(tier)
    found = []
    for term_tier, terms in vocabulary.items():
        if rank(term_tier) <= claim_rank:
            continue
        for term in terms:
            if term.lower() in STRUCTURAL_TERMS:
                continue
            if _appears(term, claim or ""):
                found.append(Violation(term=term, term_tier=term_tier, claim_tier=tier))
    return tuple(sorted(found, key=lambda v: (rank(v.term_tier), v.term)))


def moralising(text: str) -> tuple[str, ...]:
    """REQ-NAR-023 / RULE-23. A spending or screen-time figure is not a character judgement."""
    return tuple(term for term in MORALISING
                 if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", text or "", re.I))


def check_templates(templates, vocabulary):
    """REQ-NAR-022. A template declared for a tier may not contain a term above it.

    Templates are checked at build time rather than at render time because a template is a
    promise about every answer it will ever produce, and finding the breach on the day it is
    read is finding it too late.
    """
    breaches = []
    for tier, template in templates:
        breaches.extend((tier, template, v) for v in lint(template, tier, vocabulary))
    return tuple(breaches)
