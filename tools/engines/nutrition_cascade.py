"""B12 §D.2/D.3 — the source cascade (REQ-NUT-012..016, REQ-NUT-024, REQ-NUT-036).

Pure orchestration: no database, no clock, no network. Each SOURCE is a callable supplied by the
caller, so the ordering, the refusals and the brand rules are testable without an API key, a
socket, or Joe's USDA registration.

WHY A CASCADE AND NOT A SEARCH. The four sources are not interchangeable and they are not ranked
by convenience. They are ranked by HOW DIRECTLY EACH KNOWS THIS PARTICULAR FOOD:

  1. joe              — Joe measured or entered it. Nothing outranks the person who ate it.
  2. usda_branded     — the manufacturer's own label for this exact product.
  3. usda_foundation  — a laboratory analysis of the generic food.
  4. off_product      — a crowd-sourced label, correct far more often than not.

Each step down is a weaker claim about THIS item, and the interval widens accordingly. Running
them in parallel and taking "the best match" would silently prefer whichever source happened to
have the tidiest string.

THE RULE THAT MATTERS MOST (REQ-NUT-016). A named restaurant item NEVER falls back to a generic
food. "Chipotle chicken burrito" resolving to USDA's "burrito, chicken" is not a small error: a
restaurant portion is routinely double the generic, and the number would look entirely ordinary.
So a branded query may only be answered by a branded source, and when none has it the item stays
UNRESOLVED with its restaurant token intact (REQ-NUT-015). An unresolved item is a question Joe
can answer; a plausible wrong number is not.

WHY 429 STOPS THE WHOLE SOURCE FOR AN HOUR (REQ-NUT-012). A rate limit is the provider saying
stop. Retrying around it gets the key banned, and the failure mode of a banned key is every
future item unresolved -- so the polite failure is also the cheap one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# REQ-NUT-036: the order is the contract, not an implementation detail.
SOURCE_PRECEDENCE = ("joe", "usda_branded", "usda_foundation", "off_product")
BRANDED_SOURCES = frozenset({"joe", "usda_branded", "off_product"})
RATE_LIMIT_COOLDOWN_S = 60 * 60         # REQ-NUT-012


class SourceUnavailable(Exception):
    """The source could not answer at all — not configured, rate limited, or unreachable.

    Distinct from "this source does not know this food": a missing key means every item is
    unresolved for a reason that has nothing to do with the food, and reporting that as
    `no_source_match` would send Joe a review list of items nothing was ever going to resolve.
    """
    def __init__(self, source, reason, detail=""):
        super().__init__(f"{source}: {reason}")
        self.source, self.reason, self.detail = source, reason, detail


class NotConfigured(SourceUnavailable):
    def __init__(self, source, detail=""):
        super().__init__(source, "not_configured", detail)


class RateLimited(SourceUnavailable):
    def __init__(self, source, detail=""):
        super().__init__(source, "rate_limited", detail)


@dataclass
class Cooldowns:
    """REQ-NUT-012. Which sources are in their 60-minute penalty box, and until when."""
    until: dict = field(default_factory=dict)
    cooldown_s: int = RATE_LIMIT_COOLDOWN_S

    def trip(self, source, now=None):
        self.until[source] = (now if now is not None else time.time()) + self.cooldown_s

    def active(self, source, now=None):
        now = now if now is not None else time.time()
        return self.until.get(source, 0) > now

    def remaining(self, source, now=None):
        now = now if now is not None else time.time()
        return max(0.0, self.until.get(source, 0) - now)


@dataclass(frozen=True)
class Unresolved:
    """RULE-06. An item nothing could answer, with everything that was tried.

    `reason` is `no_source_match` only when every source was actually ASKED and none knew the
    food. If a source was skipped -- no key, in cooldown -- the reason says so instead, because
    "we could not find it" and "we could not look" are different facts and only one of them is
    about the food.
    """
    item_text: str
    reason: str
    tried: tuple
    brand: str | None = None
    status: str = "unresolved"
    review_reason: str | None = None


def resolve(item_text, sources, *, brand=None, cooldowns=None, now=None):
    """Walk the cascade. Returns the first source's answer, or `Unresolved`.

    `sources` maps a source name to a callable `(item_text, brand) -> result | None`. Returning
    None means "this source does not know this food"; raising `SourceUnavailable` means "this
    source could not be asked". A source absent from the mapping is simply not configured.
    """
    cooldowns = cooldowns if cooldowns is not None else Cooldowns()
    tried, asked, skipped = [], 0, []

    for name in SOURCE_PRECEDENCE:
        # REQ-NUT-016. A named restaurant or branded item may only be answered by a source that
        # knows BRANDS. Letting it reach usda_foundation would resolve "Chipotle chicken
        # burrito" to a generic burrito -- routinely half the calories, and indistinguishable
        # from a correct answer on the plate.
        if brand and name not in BRANDED_SOURCES:
            tried.append({"source": name, "outcome": "skipped_generic_source_for_branded_item"})
            continue
        fn = sources.get(name)
        if fn is None:
            tried.append({"source": name, "outcome": "not_configured"})
            skipped.append(name)
            continue
        if cooldowns.active(name, now):
            tried.append({"source": name, "outcome": "rate_limited",
                          "retry_in_s": round(cooldowns.remaining(name, now))})
            skipped.append(name)
            continue
        try:
            result = fn(item_text, brand)
        except RateLimited:
            # REQ-NUT-012. The provider said stop. Stop for this source, for an hour, and carry
            # on down the cascade -- the other sources have their own quotas and are unaffected.
            cooldowns.trip(name, now)
            tried.append({"source": name, "outcome": "rate_limited_now"})
            skipped.append(name)
            continue
        except SourceUnavailable as e:
            tried.append({"source": name, "outcome": e.reason, "detail": e.detail})
            skipped.append(name)
            continue
        asked += 1
        if result is None:
            tried.append({"source": name, "outcome": "no_match"})
            continue
        out = dict(result)
        out["source"] = name
        out.setdefault("nutrition_status", "resolved")
        # REQ-NUT-014. A manufacturer's label is a LABELLED estimate and must record whose label
        # it was. Without the brand owner, a labelled figure cannot be re-checked against the
        # product it came from, and `labelled` becomes a claim about precision with no referent.
        if name == "usda_branded":
            out["estimate_method"] = "labelled"
            if not out.get("brand_owner"):
                raise ValueError("REQ-NUT-014: a usda_branded match must record its brand owner")
        out["tried"] = tuple(tried + [{"source": name, "outcome": "match"}])
        return out

    # REQ-NUT-015 / REQ-NUT-024. Every source refused. WHY it refused decides what Joe is told.
    if asked == 0:
        reason = "no_source_available"
        review = None       # nothing to review: this is an operations problem, not a food one
    else:
        reason = "no_source_match"
        review = "no_source_match"
    return Unresolved(item_text=item_text, reason=reason, tried=tuple(tried), brand=brand,
                      review_reason=review)


def resolvable_sources(sources, cooldowns=None, now=None, brand=None):
    """Which sources could answer right now. Used to explain a refusal, never to reorder one."""
    cooldowns = cooldowns if cooldowns is not None else Cooldowns()
    return tuple(n for n in SOURCE_PRECEDENCE
                 if n in sources and not cooldowns.active(n, now)
                 and (not brand or n in BRANDED_SOURCES))
