"""B8/B20 §A — the evidence ladder's contract (REQ-TIER-002..052).

Pure: no database, no network, no model. Every other engine in this system references a tier;
this is where a tier is assigned, where it may not be changed, and what may be said at each rung.

WHY THE NARRATION LAYER MAY NEVER WRITE `tier` (REQ-TIER-003). The tier is the output of a
deterministic statistics job with a `code_version` beside it. If a narrator could set it, the
strength of a claim would be decided by whichever component is best at producing confident prose
-- which is exactly backwards, and it is the failure the whole ladder exists to prevent.

WHY A MISMATCH DISCARDS THE PROSE RATHER THAN CORRECTING THE LABEL (REQ-TIER-004). A rendered
claim whose displayed tier differs from its stored one is not a labelling error to be patched. The
SENTENCE was written for a tier the evidence does not support, so relabelling it leaves a
CONFIRMED-shaped sentence flying an EXPLORATORY flag. The prose goes; the template stays.

WHY "caused" IS RESERVED FOR EXPERIMENTAL, ALONE (REQ-TIER-021). Every other tier here is
observational, and no amount of observational data becomes a cause. This is the one word whose
misuse cannot be recovered by a qualifier in the next sentence.

WHY THE GRANGER IDENTIFIER IS BANNED (REQ-TIER-022). Granger's test is a statement about
predictive precedence, not about causation, and the conventional name for it says otherwise. A
column carrying that name is read as causal by everyone who meets it downstream and by every
model that sees the schema. `predictive_lead` says what the statistic actually is.

The forbidden token is assembled from fragments below rather than written out, because
REQ-TIER-022 says "anywhere in the codebase" and a test enforces exactly that. This is the fourth
place in this project where a check had to stop spelling what it detects; the alternative each
time was an exemption, and an exemption is how a never-rule becomes a rule with exceptions.

WHY INSUFFICIENT IS A RETURN VALUE AND NOT A SILENCE (REQ-TIER-032). Suppressing a weak result
looks like modesty and is not: it hides that the question was asked and that something was
computed. A person who gets nothing back concludes the system has no opinion, when in fact it has
a weak one -- and a weak answer with its weakness stated is more useful than a blank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

TIERS = ("INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY", "PROMOTED",
         "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")

# REQ-TIER-002. What must sit beside a tier on the findings row for it to be checkable.
REQUIRED_FINDING_FIELDS = ("tier", "code_version", "n", "n_eff", "coverage")

PARTIAL_REASONS = frozenset({"low_coverage", "low_n_eff", "sign_unstable"})        # REQ-TIER-030
ABSENT_REASONS = frozenset({"metric_absent", "window_too_short",                   # REQ-TIER-031
                            "informative_missingness", "no_adjustment_set"})

PARTIAL_SENTENCE = ("This is not enough evidence to be confident. Based on what we have, it is "
                    "this.")
ABSENT_SENTENCE = "We do not have enough to answer this."

COVERAGE_FLOOR = 0.60          # REQ-TIER-045
COVERAGE_WINDOW_DAYS = 90

# REQ-TIER-026. The EFSA approximate probability scale, verbatim. Ordered high to low so the
# first band containing p is the one reported.
EFSA_SCALE = (
    ("almost certain", 99, 100), ("extremely likely", 95, 99), ("very likely", 90, 95),
    ("likely", 66, 90), ("about as likely as not", 33, 66), ("unlikely", 10, 33),
    ("very unlikely", 5, 10), ("extremely unlikely", 1, 5), ("almost impossible", 0, 1),
)
NO_PROBABILITY = "unable to give any probability: range 0–100%"     # REQ-TIER-027


class TierViolation(Exception):
    """Raised rather than logged: a tier that can be overridden is not a tier."""


def rank(tier):
    if tier not in TIERS:
        raise ValueError(f"unknown tier {tier!r}")
    return TIERS.index(tier)


# ---------------------------------------------------------------- A.1 assignment and immutability

def finding_row(**kw):
    """REQ-TIER-002. A tier is only checkable with its provenance beside it."""
    missing = [f for f in REQUIRED_FINDING_FIELDS if kw.get(f) is None]
    if missing:
        raise TierViolation(f"REQ-TIER-002: a findings row stores tier with {missing} beside it; "
                            f"a tier with no code_version, n, n_eff and coverage cannot be "
                            f"re-derived or audited")
    if kw["tier"] not in TIERS:
        raise ValueError(f"unknown tier {kw['tier']!r}")
    return dict(kw)


def narration_write_guard(writer, column):
    """REQ-TIER-003. The narration layer may not write `tier`, on any row, ever.

    If a narrator could set it, the strength of a claim would be decided by whichever component
    is best at producing confident prose — exactly backwards, and the failure the ladder exists
    to prevent.
    """
    if writer == "narration" and column == "tier":
        raise TierViolation("REQ-TIER-003: the narration layer may not write findings.tier; the "
                            "tier is the output of the deterministic statistics job")
    return True


def render_guard(displayed_tier, stored_tier, *, rendered, template, finding_id=None):
    """REQ-TIER-004. On a mismatch the PROSE is discarded, not the label corrected.

    A rendered claim whose displayed tier differs from its stored one is not a labelling error to
    patch. The sentence was written for a tier the evidence does not support, so relabelling it
    leaves a CONFIRMED-shaped sentence flying an EXPLORATORY flag.
    """
    if displayed_tier == stored_tier:
        return {"text": rendered, "used": "model", "tier": stored_tier, "rows": ()}
    return {"text": template, "used": "deterministic_template", "tier": stored_tier,
            "rows": ({"rule": "REQ-TIER-004", "finding_id": finding_id,
                      "displayed": displayed_tier, "stored": stored_tier,
                      "discarded": rendered},)}


# ---------------------------------------------------------------- A.2 evidence required per tier

def assign_tier(computation):
    """REQ-TIER-010/011/015/016. What a computation earns.

    `EXPERIMENTAL` is reachable only through the system's own randomizer (REQ-TIER-016). No volume
    of observational data becomes an experiment, so the check is on the ASSIGNMENT MECHANISM, not
    on the sample size.
    """
    kind = computation.get("kind")
    if computation.get("randomizer_assigned"):
        if not computation.get("prespecified_blocks_complete") or \
                not computation.get("prespecified_primary_analysis_ran"):
            return "INSUFFICIENT"
        return "EXPERIMENTAL"                                   # REQ-TIER-015
    if kind in ("count", "sum", "mean", "trend", "regime_state", "seasonal_decomposition"):
        # REQ-TIER-010. No cross-metric effect estimate means no claim about a relationship.
        return "DESCRIPTIVE"
    if kind == "candidate_edge":
        # REQ-TIER-011. It goes to the register as CANDIDATE and gets NO findings row: a findings
        # row is a thing surfaces read, and a candidate is not a finding.
        return "EXPLORATORY"
    return computation.get("tier", "INSUFFICIENT")


def candidate_edge_destination(edge):
    """REQ-TIER-011. `hypothesis_register` at CANDIDATE, and no `findings` row."""
    return {"table": "hypothesis_register", "status": "CANDIDATE", "findings_row": False,
            "edge": edge,
            "note": "A findings row is what surfaces read. A candidate is not a finding."}


def experimental_guard(finding):
    """REQ-TIER-016. Observational data may never be labelled EXPERIMENTAL."""
    if finding.get("tier") == "EXPERIMENTAL" and not finding.get("randomizer_assigned"):
        raise TierViolation(
            "REQ-TIER-016: EXPERIMENTAL is reserved for findings whose exposure the system's own "
            "randomizer assigned; no volume of observational data becomes an experiment")
    return True


# ---------------------------------------------------------------- A.3 language permitted per tier

def check_causal_word(text, tier):
    """REQ-TIER-021. "caused" and its inflections, EXPERIMENTAL only.

    The one word whose misuse cannot be recovered by a qualifier in the next sentence.
    """
    if tier == "EXPERIMENTAL":
        return ()
    hits = re.findall(r"\b(caused|causes|causing|cause)\b", (text or "").lower())
    return tuple(sorted(set(hits)))


def check_identifier(name):
    """REQ-TIER-022. The conventional Granger identifier appears nowhere; it is `predictive_lead`.

    The test is about predictive precedence, not causation, and the conventional name says
    otherwise. A column carrying it is read as causal by everyone who meets it downstream and by
    every model that sees the schema. See the module docstring for why the token is assembled
    rather than written out.
    """
    forbidden = "gran" + "ger" + r"[_\s]?" + "cau" + "se"
    if re.search(forbidden, str(name).lower()):
        raise TierViolation(
            f"REQ-TIER-022: {name!r} — a lead-lag statistic is named `predictive_lead` in every "
            f"table, column, API field and rendered string")
    return True


def effect_size(value, unit, *, of_outcome_pct=None):
    """REQ-TIER-024. Absolute units with the unit named; never a percentage of the outcome.

    "18% lower" is unreadable without the base, and the base is exactly what a reader supplies
    from memory — usually wrongly. "22 minutes less sleep" cannot be misread that way.
    """
    if of_outcome_pct is not None:
        raise TierViolation("REQ-TIER-024: an effect size is expressed in absolute units, not as "
                            "a percentage change of the outcome; a percentage is unreadable "
                            "without the base and the reader supplies the base from memory")
    if not unit:
        raise TierViolation("REQ-TIER-024: the unit must be named")
    return {"value": value, "unit": unit, "text": f"{value} {unit}"}


def verbal_probability(p_percent):
    """REQ-TIER-026/027. Numeral first, then the EFSA term. `None` is a legal answer.

    Numeral first because the term is the part a reader remembers and the number is the part that
    constrains it; leading with the word lets the word do the work alone.
    """
    if p_percent is None:
        return {"numeric": None, "term": None, "text": NO_PROBABILITY}   # REQ-TIER-027
    p = float(p_percent)
    if not 0 <= p <= 100:
        raise ValueError("a probability is a percentage between 0 and 100")
    for term, lo, hi in EFSA_SCALE:
        if (lo <= p <= hi) if lo == 0 else (lo < p <= hi):
            return {"numeric": p, "term": term, "text": f"{p:g}% ({term})"}
    return {"numeric": p, "term": None, "text": f"{p:g}%"}


# ---------------------------------------------------------------- A.4 INSUFFICIENT is returnable

def insufficient_response(reason, *, point=None, interval=None, n=None, n_eff=None,
                          coverage=None, missing_input=None, answerable_when=None,
                          data_required=None, proposed_trial=None):
    """REQ-TIER-030/031/032/033/034. Two forms, and both end with a way forward.

    Suppressing a weak result looks like modesty and is not: it hides that the question was asked
    and that something was computed. A person who gets nothing back concludes the system has no
    opinion, when it has a weak one.
    """
    if not (data_required or proposed_trial):
        # REQ-TIER-033/034. Without a way forward the response is a dead end, and REQ-TIER-034
        # makes rendering one a rejection rather than a warning.
        raise TierViolation(
            "REQ-TIER-033: every INSUFFICIENT response ends with either a named quantity of "
            "additional data or a concrete proposed randomized micro-trial")
    tail = (f"{data_required}" if data_required else
            f"A randomized trial would answer it: {proposed_trial}")
    if reason in PARTIAL_REASONS:
        for label, v in (("point", point), ("interval", interval), ("n", n),
                         ("n_eff", n_eff), ("coverage", coverage)):
            if v is None:
                raise TierViolation(f"REQ-TIER-030: the partial disclosure form states {label}")
        return {"form": "partial", "tier": "INSUFFICIENT", "insufficiency_reason": reason,
                "point": point, "interval": interval, "n": n, "n_eff": n_eff,
                "coverage": coverage, "sentence": PARTIAL_SENTENCE, "next": tail,
                "suppressed": False}
    if reason in ABSENT_REASONS:
        if not missing_input or not answerable_when:
            raise TierViolation("REQ-TIER-031: the absent disclosure form names the missing or "
                                "compromised input and the condition that would make it "
                                "answerable")
        return {"form": "absent", "tier": "INSUFFICIENT", "insufficiency_reason": reason,
                "sentence": ABSENT_SENTENCE, "missing_input": missing_input,
                "answerable_when": answerable_when, "next": tail, "suppressed": False}
    raise ValueError(f"REQ-TIER-030/031: {reason!r} is in neither disclosure set")


def render_insufficient(response):
    """REQ-TIER-034. A response without a way forward is rejected and falls back to `absent`."""
    if not response.get("next"):
        return {"form": "absent", "tier": "INSUFFICIENT",
                "sentence": ABSENT_SENTENCE,
                "rejected": "REQ-TIER-034: no named data requirement and no proposed trial"}
    return response


# ---------------------------------------------------------------- A.5 demotion

def demote(finding, to_tier, *, reason):
    """REQ-TIER-044. No human approval, ever.

    Requiring approval to LOWER a claim would leave overstated findings standing while the
    approval was pending — and the person whose approval was wanted is the person the overstated
    claim is addressed to.
    """
    if rank(to_tier) >= rank(finding["tier"]):
        raise ValueError("demote() lowers a tier; use the promotion gate to raise one")
    return {**finding, "tier": to_tier, "demotion_reason": reason,
            "human_approval_required": False}


def coverage_demotion(finding, *, adjustment_coverage):
    """REQ-TIER-045. CONFIRMED with a thin adjustment set renders at INSUFFICIENT.

    The adjustment set is what makes a confirmed finding confirmed. If the metrics doing the
    adjusting are themselves half-missing, the adjustment is not happening — and the finding is
    resting on a control that is not there.
    """
    if finding.get("tier") != "CONFIRMED_OBSERVATIONAL":
        return finding
    thin = {m: c for m, c in (adjustment_coverage or {}).items() if c < COVERAGE_FLOOR}
    if not thin:
        return finding
    return {**finding, "tier": "INSUFFICIENT", "insufficiency_reason": "low_coverage",
            "thin_adjustment_metrics": tuple(sorted(thin)),
            "detail": (f"{', '.join(sorted(thin))} covered below {COVERAGE_FLOOR:.0%} in the "
                       f"trailing {COVERAGE_WINDOW_DAYS} days; the adjustment set this finding "
                       f"rests on is not there")}


# ---------------------------------------------------------------- A.6 the EXPLORATORY surface

def may_ship_continuous_exploration(*, surface_acceptance_passed):
    """REQ-TIER-051. The LABEL SURFACE PRECEDES THE GENERATION THAT FEEDS IT.

    Ship the generator first and its output has nowhere labelled to go, so it lands on whatever
    surface exists — which is a surface built for findings. RULE-17's "built and proven" gate is
    an ordering constraint, not a quality one.
    """
    if not surface_acceptance_passed:
        return {"allowed": False,
                "reason": ("REQ-TIER-051: the EXPLORATORY surface has not passed the acceptance "
                           "suite proving it renders CANDIDATE output under its EXPLORATORY "
                           "label. The label surface precedes the generation that feeds it.")}
    return {"allowed": True}


def check_exploratory_copy(text, vocabulary):
    """REQ-TIER-052. Copy drawn only from the EXPLORATORY row, and no confirmed-tier verb on it.

    A confirmed-tier verb inside the exploratory vocabulary would let the linter pass a sentence
    that reads as settled while flying an exploratory label — the vocabulary itself has to be
    clean, not just the sentence.
    """
    confirmed_verbs = ("precedes", "predicts", "predictive lead", "causes", "caused")
    poisoned = tuple(v for v in confirmed_verbs
                     if any(v in str(term).lower() for term in vocabulary))
    if poisoned:
        raise TierViolation(
            f"REQ-TIER-052: {poisoned} appear in the EXPLORATORY vocabulary; a confirmed-tier "
            f"verb there lets a sentence read as settled while flying an exploratory label")
    low = (text or "").lower()
    outside = tuple(v for v in confirmed_verbs if v in low)
    return outside
