"""B14R step 4: the deterministic reconstruction evaluator (REQ-REC-006..015).

The engine concludes; the model never does. Every function here is total, deterministic and
takes no model output as an argument. A model may propose a CANDIDATE — "these three records
might be one meal" — but the decision about whether that candidate is supported, at what
tier, and with what uncertainty is made here, from evidence, by rules that were registered
before the question was asked (RULE-11, RULE-13).

Three refusals are enforced by signature rather than by discipline:

  * `evaluate()` has NO probability parameter. It is not possible to pass a confidence in.
    A probability may only be attached later, by `calibrate()`, which demands the stored
    calibration that earned it (REQ-REC-010).
  * There is no `did_not_occur` return path from missing evidence. Absence of a record is
    absence of capture (REQ-REC-009); only positive contradicting evidence can produce it.
  * `evaluate()` takes an `as_of` and drops evidence recorded after it, so a reconstruction
    cannot use knowledge it did not have (RULE-04, REQ-REC-012).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# RULE-16 vocabulary. A reconstruction does not get a private confidence language, and it
# cannot reach the causal tiers at all — those require the confirmation pipeline (RULE-19).
TIERS = ("INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY")


# The three tiers a reconstruction can occupy, weakest first. The causal tiers are deliberately
# absent: a reconstruction cannot reach them at all (RULE-19).
TIER_ORDER = ("INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY")


def weaker(a: str, b: str) -> str:
    """The weaker of two tiers. A chain is as strong as its weakest link, never its longest."""
    return a if TIER_ORDER.index(a) <= TIER_ORDER.index(b) else b


@dataclass(frozen=True)
class Evidence:
    """One citation. `origin_group` is what makes independence countable: two copies of one
    receipt share it, so they cannot be counted as two corroborations (REQ-REC-008)."""
    ref: str
    kind: str
    stance: str            # 'supports' | 'contradicts'
    origin_group: str
    recorded_at: dt.datetime
    # INV-5, REQ-REC-016 (inferred-input propagation). A citation is either something that was
    # MEASURED or something this system previously CONCLUDED. The distinction has to travel with
    # the citation, because by the time a reconstruction is stored, both look like rows.
    provenance: str = "measured"        # 'measured' | 'inferred'
    input_tier: str | None = None       # the tier of an inferred input; None when measured

    def __post_init__(self):
        if self.stance not in ("supports", "contradicts"):
            raise ValueError(f"stance must be supports or contradicts, not {self.stance!r}")
        if self.provenance not in ("measured", "inferred"):
            raise ValueError(f"provenance must be measured or inferred, not {self.provenance!r}")
        if self.provenance == "inferred" and self.input_tier not in TIER_ORDER:
            raise ValueError(
                "INV-5: an inferred citation must carry the tier it was concluded at; without it "
                "a conclusion built on a guess cannot be held below the guess")
        if self.provenance == "measured" and self.input_tier is not None:
            raise ValueError("a measured citation has no tier; only a conclusion has one")


@dataclass(frozen=True)
class Method:
    key: str
    version: int
    event_family: str
    required_evidence: tuple[str, ...]
    permissible_outputs: tuple[str, ...]
    temporal_specification: str


@dataclass
class Reconstruction:
    presence: str
    tier: str
    reason: str
    rule_score: float | None = None
    probability: float | None = None          # only ever set by calibrate()
    calibration_ref: str | None = None
    alternatives: list[dict] = field(default_factory=list)
    no_alternative_generator: bool = False
    unresolved_ambiguity: str | None = None
    missing_evidence: tuple[str, ...] = ()
    discriminating_evidence: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    # Which of the supporting citations were themselves conclusions. Stored, not derived at
    # render time: the reader of a stored row must be able to see that it rests on an inference
    # without re-walking the evidence graph.
    inferred_inputs: tuple[str, ...] = ()

    @property
    def independent_support(self) -> int:
        return independent_origins(self.evidence, "supports")

    @property
    def independent_contradiction(self) -> int:
        return independent_origins(self.evidence, "contradicts")


def independent_origins(evidence, stance) -> int:
    """Distinct origins, never row count. REQ-REC-008 / INTENT_COVERAGE R5."""
    return len({e.origin_group for e in evidence if e.stance == stance})


def known_at(evidence, as_of: dt.datetime):
    """REQ-REC-012. Evidence recorded after the cutoff did not exist for this question."""
    return tuple(e for e in evidence if e.recorded_at <= as_of)


def evaluate(method: Method, evidence, as_of: dt.datetime,
             alternatives=None, discriminating=()) -> Reconstruction:
    """Decide what the evidence supports. Never returns a probability."""
    visible = known_at(tuple(evidence), as_of)
    alternatives = list(alternatives or [])

    have = {e.kind for e in visible if e.stance == "supports"}
    missing = tuple(k for k in method.required_evidence if k not in have)
    if missing:
        # REQ-REC-009. The required evidence is absent, which says nothing whatever about
        # whether the event happened — only that this method cannot speak to it. Returning
        # 'did_not_occur' here is the single most tempting error in the feature and there is
        # deliberately no code path to it.
        return Reconstruction(
            presence="unknown", tier="INSUFFICIENT", reason="required_evidence_missing",
            missing_evidence=missing, evidence=visible,
            alternatives=alternatives, no_alternative_generator=not alternatives,
            discriminating_evidence=tuple(discriminating))

    support = independent_origins(visible, "supports")
    against = independent_origins(visible, "contradicts")

    if against >= support:
        # REQ-REC-007. Contradicting evidence is not outweighed by counting harder. When the
        # independent origins are level or against, the honest state is unresolved — and the
        # question of what would settle it is part of the answer (REQ-REC-015).
        return Reconstruction(
            presence="unknown", tier="INSUFFICIENT", reason="contradicted",
            unresolved_ambiguity=(f"{against} independent source(s) contradict and "
                                  f"{support} support; no rule resolves the conflict"),
            evidence=visible, alternatives=alternatives,
            no_alternative_generator=not alternatives,
            discriminating_evidence=tuple(discriminating))

    # An UNCALIBRATED ranking (REQ-REC-010). It orders reconstructions against each other and
    # it is not a chance of anything. It is deliberately a small integer ratio rather than
    # something that looks like a percentage.
    score = float(support - against) / float(support + against) if (support + against) else 0.0
    tier = "EXPLORATORY" if support >= 2 else "DESCRIPTIVE"

    # REQ-REC-016, inferred-input propagation. A reconstruction resting on an earlier
    # reconstruction cannot be more certain than the thing it rests on. Two inferred
    # corroborations are not the same as two observations, and without this cap they would
    # promote each other: infer A at DESCRIPTIVE, infer B from A and A' at EXPLORATORY, and the
    # system now believes something more strongly than any measurement ever supported. The cap
    # is the WEAKEST inferred input, not an average — averaging would let a strong input launder
    # a weak one.
    inferred = tuple(e for e in visible if e.stance == "supports" and e.provenance == "inferred")
    for e in inferred:
        tier = weaker(tier, e.input_tier)

    return Reconstruction(
        presence="occurred", tier=tier, reason="supported", rule_score=score,
        inferred_inputs=tuple(e.ref for e in inferred),
        evidence=visible, alternatives=alternatives,
        no_alternative_generator=not alternatives,
        unresolved_ambiguity=(None if not alternatives else
                              "alternatives remain open; no discriminating evidence observed"
                              if not discriminating else None),
        discriminating_evidence=tuple(discriminating))


def calibrate(r: Reconstruction, probability: float, calibration_ref: str) -> Reconstruction:
    """REQ-REC-010. The only door a probability comes through, and it is locked to a stored
    calibration. Nothing in this module calls it: no calibration exists yet, so every
    reconstruction this system currently produces reports uncertainty as unquantified."""
    if not calibration_ref:
        raise ValueError("REQ-REC-010: a probability requires the calibration that earned it")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("a probability lies in [0, 1]")
    if r.presence == "unknown":
        raise ValueError("REQ-REC-009: an unknown event cannot carry a probability")
    r.probability, r.calibration_ref = probability, calibration_ref
    return r


def to_row(r: Reconstruction, method: Method, event_time_from, event_time_to,
           subject_day, knowledge_time, author="engine") -> dict:
    """The insert shape for core.inferred_events. The table's CHECK constraints are the
    second line of defence; this is the first, and neither is sufficient alone."""
    if r.presence not in ("occurred", "did_not_occur", "unknown"):
        raise ValueError(f"presence {r.presence!r} is not three-valued (RULE-07)")
    if r.presence != "unknown" and r.presence not in method.permissible_outputs:
        raise ValueError(f"REQ-REC-006: {method.key} may not output {r.presence!r}")
    if r.probability is not None and not r.calibration_ref:
        raise ValueError("REQ-REC-010: a probability requires its calibration")
    return dict(
        event_family=method.event_family, method_key=method.key,
        method_version=method.version, event_time_from=event_time_from,
        event_time_to=event_time_to, subject_day=subject_day,
        knowledge_time=knowledge_time, tier=r.tier, presence=r.presence,
        rule_score=r.rule_score, probability=r.probability,
        calibration_ref=r.calibration_ref,
        alternatives=r.alternatives, no_alternative_generator=r.no_alternative_generator,
        unresolved_ambiguity=r.unresolved_ambiguity, author=author,
        # Carried into the row so the fact that this rests on a conclusion survives storage.
        inferred_inputs=list(r.inferred_inputs))
