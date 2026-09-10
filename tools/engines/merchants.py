"""B14.1 — descriptor normalisation and the merchant resolution cascade.

REQ-FIN-060..062 (normalisation), REQ-FIN-070..074 (resolution), RULE-10 (a human correction
outranks every automated match, permanently), RULE-09 (this assigns an identity, never a
number), INV-2 (aliases are appended, never edited).

Pure functions with no database and no network, so the cascade can be exercised exhaustively
and cheaply. The caller supplies the patterns and known merchants; this module decides.

WHY THE CASCADE ORDER IS NOT NEGOTIABLE. Each step is strictly more speculative than the one
before it, and a later step must never run once an earlier one has answered — otherwise a
fuzzy guess can overrule an exact rule and nothing in the stored result would show it. The
order is: human correction, exact pattern, regex pattern, fuzzy ≥ 0.80, provisional.

WHY 0.80 AND NOT A TRIGRAM THRESHOLD. REQ-FIN-072 names `difflib.SequenceMatcher` and 0.80
explicitly. The B14 brief proposed trigram similarity ≥ 0.6; the requirement wins, and the
difference is not cosmetic — trigram similarity on short descriptors scores substrings near
1.0 (this is the same artefact that sent "sleep" to "Asleep"), which is exactly the wrong
behaviour for merchant names where one is often a prefix of another.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

FUZZY_FLOOR = 0.80          # REQ-FIN-072/073, verbatim from the requirement.

# REQ-FIN-060. Ordered, and each carries an ID because REQ-FIN-062 requires the ordered list of
# rules that FIRED to be stored — "we normalised it somehow" is not provenance.
STRIP_RULES: tuple[tuple[str, str], ...] = (
    ("facilitator_sq",     r"^SQ\s*\*\s*"),
    ("facilitator_tst",    r"^TST\s*\*\s*"),
    ("facilitator_pypl",   r"^PYPL\s*\*\s*"),
    ("facilitator_sp",     r"^SP\s+"),
    ("facilitator_amzn",   r"^AMZN\s+MKTP\s*"),
    ("phone_number",       r"\b\d{3}[-. ]?\d{3}[-. ]?\d{4}\b"),
    ("card_suffix",        r"\bX{2,}\d{2,}\b"),
    ("store_number",       r"\s#\s*\d+\b"),
    ("digit_run",          r"\b\d{3,}\b"),
    ("trailing_state",     r"\s+[A-Z]{2}\s*$"),
    # NOTE: the trailing CITY is not here. It cannot be a fixed regex — "OAKLAND" and
    # "NEW YORK" are one and two tokens — and a gazetteer is a dependency this project will
    # not take for one field. It is stripped by `normalize(..., location_tokens=...)` using
    # tokens DISCOVERED from Joe's own descriptors; see `discover_location_tokens`.
    ("punctuation",        r"[^A-Z0-9&' ]+"),
    ("whitespace",         r"\s{2,}"),
)


@dataclass(frozen=True)
class Normalized:
    raw: str                                    # REQ-FIN-061: never overwritten
    normalized: str
    rules_fired: tuple[str, ...]                # REQ-FIN-062: ordered, by rule ID


@dataclass(frozen=True)
class Pattern:
    pattern: str
    canonical: str
    is_regex: bool = False
    specificity: int = 0                        # REQ-FIN-071: descending order


@dataclass
class Resolution:
    canonical: str | None
    merchant_source: str                        # human | pattern_exact | pattern_regex | fuzzy | provisional
    confidence: float | None
    needs_review: bool = False
    unconfirmed: bool = False
    considered: tuple[tuple[str, float], ...] = field(default_factory=tuple)


def normalize(descriptor: str, location_tokens: frozenset[str] = frozenset()) -> Normalized:
    """REQ-FIN-060/061/062. Upper-case the remainder; keep the original untouched.

    `location_tokens` is the discovered city vocabulary (see `discover_location_tokens`). A
    trailing run of tokens that are ALL known locations is stripped; a run that is not, is
    kept. That is why the vocabulary is discovered rather than guessed: "SHELL OIL HOUSTON"
    loses HOUSTON because HOUSTON follows dozens of unrelated merchants in Joe's data, while
    a merchant genuinely called "... GARAGE" keeps GARAGE because GARAGE does not.
    """
    raw = descriptor or ""
    text, fired = raw.upper(), []
    for rule_id, pattern in STRIP_RULES:
        replacement = " " if rule_id in ("punctuation", "whitespace") else ""
        new = re.sub(pattern, replacement, text)
        if new != text:
            fired.append(rule_id)
            text = new
    text = text.strip()
    if location_tokens:
        tokens = text.split()
        # Never strip everything: a descriptor that is ONLY a city name is a gap, not a
        # merchant called "" (RULE-06), and the caller must see it as unresolvable.
        cut = len(tokens)
        while cut > 1 and tokens[cut - 1] in location_tokens:
            cut -= 1
        if cut < len(tokens):
            fired.append("trailing_city")
            tokens = tokens[:cut]
        text = " ".join(tokens)
    return Normalized(raw=raw, normalized=text.strip(), rules_fired=tuple(fired))


def discover_location_tokens(descriptors, *, min_distinct_prefixes: int = 4) -> frozenset[str]:
    """Learn the city vocabulary from Joe's own descriptors, deterministically.

    A token is a location when it appears as the last word of the pre-state remainder after
    MANY DIFFERENT merchant prefixes. "HOUSTON" follows Shell, a supermarket and a pharmacy;
    "GARAGE" follows only Joe's Garage. The threshold is a count of distinct prefixes, not a
    similarity or a model judgement, so the result is reproducible and inspectable.

    Returns an empty set on thin input rather than a confident-looking guess: with four
    descriptors nothing is learnable, and a wrong strip silently merges two merchants.
    """
    from collections import defaultdict
    prefixes = defaultdict(set)
    for d in descriptors:
        text = normalize(d).normalized
        tokens = text.split()
        if len(tokens) < 2:
            continue
        prefixes[tokens[-1]].add(" ".join(tokens[:-1]))
    return frozenset(tok for tok, seen in prefixes.items()
                     if len(seen) >= min_distinct_prefixes)


def resolve(normalized: str, patterns, known_merchants, *, human_alias=None) -> Resolution:
    """The cascade. `human_alias` is Joe's recorded correction for this exact descriptor.

    Every step returns immediately. There is no path that reaches a later step after an
    earlier one matched, which is the property that makes the stored `merchant_source`
    meaningful rather than decorative.
    """
    # RULE-10. A human correction is not a high-confidence guess; it is the answer, and it
    # outranks every rule permanently. Nothing below can revisit it.
    if human_alias:
        return Resolution(human_alias, "human", 1.0)

    key = (normalized or "").strip().upper()
    if not key:
        # An empty descriptor is not a merchant called "". It is a gap (RULE-06).
        return Resolution(None, "provisional", None, needs_review=True, unconfirmed=True)

    # REQ-FIN-070: exact, confidence 1.0, no later step runs.
    for p in patterns:
        if not p.is_regex and p.pattern.strip().upper() == key:
            return Resolution(p.canonical, "pattern_exact", 1.0)

    # REQ-FIN-071: regex, in DESCENDING specificity, first match wins.
    for p in sorted((p for p in patterns if p.is_regex),
                    key=lambda p: (-p.specificity, p.pattern)):
        if re.search(p.pattern, key, re.I):
            return Resolution(p.canonical, "pattern_regex", 1.0)

    # REQ-FIN-072: difflib against every known merchant; the ratio IS the confidence.
    scored = sorted(((m, difflib.SequenceMatcher(None, key, m.upper()).ratio())
                     for m in known_merchants), key=lambda t: (-t[1], t[0]))
    considered = tuple(scored[:3])
    if scored and scored[0][1] >= FUZZY_FLOOR:
        return Resolution(scored[0][0], "fuzzy", round(scored[0][1], 4), considered=considered)

    # REQ-FIN-073: below the floor, a PROVISIONAL merchant and a review row — and explicitly
    # NOT a row in merchant_patterns. Writing the guess into the pattern table would make the
    # next identical descriptor resolve as `pattern_exact` at confidence 1.0, laundering a
    # guess into a fact with no record that it ever was one.
    return Resolution(key, "provisional", None, needs_review=True, unconfirmed=True,
                      considered=considered)


def confirm(normalized: str, canonical: str) -> Pattern:
    """REQ-FIN-074. Joe's confirmation is what promotes a provisional merchant into a pattern."""
    if not normalized or not canonical:
        raise ValueError("REQ-FIN-074: a confirmation needs both the descriptor and the merchant")
    return Pattern(pattern=normalized.strip().upper(), canonical=canonical, is_regex=False)
