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

# REQ-FIN-051. Some descriptors are not merchants and must never be given a merchant name.
# An ATM withdrawal's destination is unknown by definition — the cash went somewhere the bank
# cannot see — and a transfer or a fee is a movement of Joe's own money, not a purchase.
# Calling any of them a merchant would put them in category rollups the requirement explicitly
# excludes them from, and "Non Chase Atm Withdraw Main" is not a shop.
# The order matters: `internal_transfer` is tested before the generic `transfer`, because
# "Online Transfer from CHK" matches both and only the first is true.
NON_MERCHANT = (
    ("atm",      re.compile(r"\bATM\b|\bWITHDRAW", re.I)),
    # MONEY MOVING BETWEEN JOE'S OWN ACCOUNTS IS NOT INCOME AND NOT SPENDING. Measured on the
    # real data: of the inbound total of inbound transactions, the great majority — 94% — is this. Counting it as
    # income overstates by seventeen times, and netting it against outflow makes total spend
    # look like $279 against a true the gross outflow. Both figures would be arithmetically perfect and
    # entirely false, which is why this needs its own kind rather than sharing `transfer`.
    ("internal_transfer",
     re.compile(r"\bONLINE TRANSFER (TO|FROM)\b|\bTRANSFER (TO|FROM) (CHK|SAV)\b"
                r"|\bAUTOMATIC PAYMENT\b|\bPAYMENT THANK YOU\b|\bE-?PAYMENT\b", re.I)),
    # A genuine person-to-person receipt or payment: someone else's money, or Joe's going to
    # someone else. REQ-FIN-049 nets THESE against a shared bill, never the internal ones.
    ("p2p",      re.compile(r"\bVENMO\b|\bCASH ?APP\b|\bPAYPAL\b|\bZELLE\b", re.I)),
    ("transfer", re.compile(r"\bONLINE TRANSFER\b|\bWIRE\b|\bTRANSFER (TO|FROM)\b", re.I)),
    ("fee",      re.compile(r"\bFEE\b|\bINTEREST CHARGE\b|\bSERVICE CHARGE\b", re.I)),
)


def classify_non_merchant(raw: str) -> str | None:
    """REQ-FIN-051. The kind of non-purchase this descriptor is, or None."""
    for kind, pattern in NON_MERCHANT:
        if pattern.search(raw or ""):
            return kind
    return None

# REQ-FIN-060. Ordered, and each carries an ID because REQ-FIN-062 requires the ordered list of
# rules that FIRED to be stored — "we normalised it somehow" is not provenance.
STRIP_RULES: tuple[tuple[str, str], ...] = (
    ("facilitator_sq",     r"^SQ\s*\*\s*"),
    ("facilitator_tst",    r"^TST\s*\*\s*"),
    ("facilitator_pypl",   r"^PYPL\s*\*\s*"),
    ("facilitator_sp",     r"^SP\s+"),
    ("facilitator_amzn",   r"^AMZN\s+MKTP\s*"),
    # Card descriptors embed the purchase DATE — "HANNAFORD #8229 WATERVILLE ME 10/14 Purc".
    # It must go before punctuation stripping, or "10/14" becomes "10 14" and sits between the
    # merchant and the state, blocking both the state and the city rule. That single omission
    # split one supermarket into three merchants.
    # A price in the descriptor is not part of the name. Without this "$1.50 FRESH PIZZA"
    # normalised to "1 50 FRESH PIZZA" — punctuation stripping turned the amount into two
    # tokens that then blocked nothing and matched nothing.
    ("currency_amount",    r"[$£€]\s?\d+(?:[.,]\d{2})?"),
    ("embedded_date",      r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b"),
    # ...and the truncated "Purchase" the same descriptors trail.
    ("purchase_suffix",    r"\s+PURC\w*\s*$"),
    ("phone_number",       r"\b\d{3}[-. ]?\d{3}[-. ]?\d{4}\b"),
    ("card_suffix",        r"\bX{2,}\d{2,}\b"),
    # A store code is not always digits: "HANNAFORD # EL" and "HANNAFORD # KE" are the same
    # chain under two store codes, and matching only digits left them as two merchants.
    ("store_number",       r"\s#\s*[A-Z0-9]+\b"),
    ("digit_run",          r"\b\d{3,}\b"),
    # A bare trailing number is a store or lane number too. Without this, "HANNAFORD
    # WATERVILLE ME 11" and "HANNAFORD WATERVILLE ME 19" became two different merchants.
    ("trailing_number",    r"\s+\d{1,2}\s*$"),
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
    merchant_source: str    # human | pattern_exact | pattern_regex | fuzzy | provisional | not_a_merchant
    confidence: float | None
    non_merchant_kind: str | None = None        # REQ-FIN-051: atm | transfer | fee
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
    # A FIXED POINT, not one pass. The rules interact: stripping a trailing store number can
    # expose the state code that was hiding behind it, and stripping that can expose the city.
    # One pass left "HANNAFORD WATERVILLE ME 11" and "HANNAFORD WATERVILLE ME 19" as two
    # different merchants because `trailing_state` is anchored to the end and the digits were
    # in the way. Iterating until nothing changes removes them in any order they appear.
    for _ in range(8):
        before = text
        for rule_id, pattern in STRIP_RULES:
            replacement = " " if rule_id in ("punctuation", "whitespace") else ""
            new = re.sub(pattern, replacement, text)
            if new != text:
                if rule_id not in fired:
                    fired.append(rule_id)
                text = new
        text = text.strip()
        if text == before.strip():
            break
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


def resolve(normalized: str, patterns, known_merchants, *, human_alias=None,
            raw: str | None = None) -> Resolution:
    """The cascade. `human_alias` is Joe's recorded correction for this exact descriptor.

    Every step returns immediately. There is no path that reaches a later step after an
    earlier one matched, which is the property that makes the stored `merchant_source`
    meaningful rather than decorative.
    """
    # RULE-10. A human correction is not a high-confidence guess; it is the answer, and it
    # outranks every rule permanently. Nothing below can revisit it.
    if human_alias:
        return Resolution(human_alias, "human", 1.0)

    # REQ-FIN-051, checked on the RAW descriptor before normalisation strips the evidence.
    # These need no review: their disposition is known and it is not "a merchant we could not
    # identify". Sending them to the queue would bury the descriptors that genuinely need Joe.
    kind = classify_non_merchant(raw if raw is not None else normalized)
    if kind:
        return Resolution(None, "not_a_merchant", None, non_merchant_kind=kind)

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
