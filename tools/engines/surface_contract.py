"""The remaining surface contracts: ask, act, sleep, reconstruction, tier attachment
(REQ-ASK-001/024/026/029, REQ-ACT-004/007/008/010, REQ-SLP-020..023, REQ-REC-013/015/016,
REQ-TIER-023/025).

Pure: no database, no clock, no model. Five small contracts, each closing out a prefix.

WHY THE PLAN AND THE ANSWER ARE TWO STEPS (REQ-ASK-001). A model that plans and answers in one
breath has already decided the answer before the numbers arrive, and the plan becomes a
justification written after the fact. Two steps means the query plan is a commitment the
deterministic layer then executes -- and if the numbers say something else, they win.

WHY INFORMATIVE MISSINGNESS CAPS AN ANSWER AT INSUFFICIENT (REQ-ASK-026). If a metric is missing
BECAUSE of the thing being asked about -- Joe does not log dinner on the nights he drinks -- then
the observed rows are a biased sample of exactly the question. No amount of data fixes that,
because the missing rows are the informative ones.

WHY ONE INSTRUCTION A DAY, PULLED (REQ-ACT-008). Two recommendations compete, and the one Joe
acts on is whichever is easier rather than whichever matters. Pulled rather than pushed because
a pushed instruction arrives when the system is ready, and the system is never the thing with
the context.

WHY FOUR RECOVERY MEASURES STAY SEPARATE (REQ-SLP-020). HRV, resting heart rate, respiratory rate
and wrist temperature have DIFFERENT capture rates and different failure modes -- the Watch
stopped recording some of them before others. A combined "recovery score" hides which one is
missing, so a score built from one live measure and three dead ones looks identical to a score
built from four.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

RECOVERY_MEASURES = ("hrv_sdnn_ms", "resting_hr", "respiratory_rate", "wrist_temperature")
MEDICAL_REFERRAL = ("I am not able to give medical advice. If this is a health concern, please "
                    "raise it with a clinician.")     # RULE-26, stored not generated
EVENT_FAMILIES_REQUIRED = ("multiple_event_families", "contradictory_evidence",
                           "duplicated_evidence", "unknown_presence", "historical_corrections",
                           "model_unavailable", "inferred_input_propagation")
CAUSAL_VOCAB = ("causes", "caused", "because", "leads to", "led to", "makes", "drives")


class SurfaceViolation(Exception):
    pass


# ---------------------------------------------------------------- ask

def plan_then_answer(question, *, planner, executor):
    """REQ-ASK-001. The language layer emits a PLAN. It does not answer in the same step.

    A model that plans and answers in one breath has already decided the answer before the
    numbers arrive, and the plan becomes a justification written after the fact.
    """
    plan = planner(question)
    if not isinstance(plan, dict) or "answer" in plan or "text" in plan:
        raise SurfaceViolation(
            "REQ-ASK-001: the language layer emits a structured query plan and no answer; a plan "
            "carrying an answer was written before the numbers arrived")
    return {"plan": plan, "result": executor(plan)}


def no_adjustment_set(question, *, dag_has_minimal_set):
    """REQ-ASK-024. No minimal sufficient adjustment set means the question is unanswerable
    from observation, and the answer says so.

    Not "here is a weaker version": the DAG says which confounders must be held fixed, and if
    they cannot be, the estimate is of something other than the effect asked about.
    """
    if dag_has_minimal_set:
        return None
    return {"tier": "INSUFFICIENT", "insufficiency_reason": "no_adjustment_set",
            "text": ("This cannot be answered from observation: there is no set of measures that "
                     "would hold the confounders fixed for this effect."),
            "what_would_answer_it": "a randomized trial on the exposure"}


def informative_missingness_cap(answer, *, flags):
    """REQ-ASK-026. Stated in the answer, and the tier capped at INSUFFICIENT.

    If a metric is missing BECAUSE of the thing being asked about — Joe does not log dinner on
    the nights he drinks — the observed rows are a biased sample of exactly the question. No
    amount of data fixes that, because the missing rows are the informative ones.
    """
    informative = tuple(sorted(m for m, v in (flags or {}).items() if v))
    if not informative:
        return answer
    return {**answer, "tier": "INSUFFICIENT",
            "insufficiency_reason": "informative_missingness",
            "informative_missingness": informative,
            "disclosure": (f"{', '.join(informative)} is missing in a way that depends on what "
                           f"this question is about, so the rows that remain are a biased sample "
                           f"of it. More of the same data would not fix this.")}


def in_scope(question_kind):
    """REQ-ASK-029. Performance and subjective state from logged behaviour are IN scope.

    Recorded explicitly because the medical boundary (RULE-26) is easy to over-apply: "why do I
    feel flat on Thursdays" is a question about logged behaviour, not a request for a diagnosis,
    and refusing it would make the system useless for the thing it is actually for.
    """
    return {"in_scope": question_kind in ("performance", "subjective_state", "behaviour"),
            "distinct_from": "medical_advice",
            "note": ("Answering from logged behaviour is in scope and is a different thing from "
                     "diagnosing.")}


# ---------------------------------------------------------------- act

def standing_order(rule, *, registered_rules, stored_numbers):
    """REQ-ACT-004. Only from a rule JOE registered, evaluated against STORED numbers.

    Both halves matter. A rule the system invented is advice wearing a standing order's clothes,
    and a condition evaluated against freshly computed numbers is a rule that can fire on
    arithmetic nobody stored.
    """
    if rule["id"] not in registered_rules:
        raise SurfaceViolation(
            f"REQ-ACT-004: {rule['id']!r} is not in config.standing_orders; a standing order is "
            f"a rule Joe registered, not one the system proposed")
    fired = [k for k in rule["condition_fields"] if k in stored_numbers]
    if len(fired) != len(rule["condition_fields"]):
        raise SurfaceViolation(
            "REQ-ACT-004: a standing order's condition is evaluated against stored numbers; "
            "computing them here would let it fire on arithmetic nobody stored")
    return {"kind": "standing_order", "tier": "DESCRIPTIVE",
            "numbers": {k: stored_numbers[k] for k in rule["condition_fields"]},
            "text": f"Your standing order: {rule['text']}",
            "phrase_present": "your standing order"}


def effect_statement(value, unit, *, counter_frame):
    """REQ-ACT-007 / REQ-TIER-024/028. Absolute units, named, with the counter-frame stated.

    The counter-frame is the same number read the other way — "22 minutes more sleep" and "22
    minutes less of the evening". Both are true, and a recommendation that states only the
    flattering one is an argument rather than a measurement.
    """
    if not unit:
        raise SurfaceViolation("REQ-ACT-007: the unit is named")
    if not counter_frame:
        raise SurfaceViolation(
            "REQ-ACT-007 / REQ-TIER-028: the counter-frame is stated; a recommendation that "
            "gives only the flattering reading of a number is an argument, not a measurement")
    return {"value": value, "unit": unit, "text": f"{value} {unit}",
            "counter_frame": counter_frame}


def daily_instruction(candidates, *, already_surfaced_today):
    """REQ-ACT-008. At most one a day, read-only, pulled and never pushed.

    Two recommendations compete, and the one Joe acts on is whichever is easier rather than
    whichever matters. Pulled because a pushed instruction arrives when the SYSTEM is ready, and
    the system is never the thing with the context.
    """
    if already_surfaced_today:
        return {"surface": None, "reason": "one instruction per subject day"}
    if not candidates:
        return {"surface": None, "reason": "nothing met the bar today"}
    top = max(candidates, key=lambda c: c.get("rank_score", 0))
    return {"surface": top, "read_only": True, "pushed": False, "pulled": True,
            "counts_against_prompt_limit": False,
            "note": ("A surface, not a prompt: it does not count against RULE-27's "
                     "one-prompt-per-subject-per-day limit.")}


def pattern_recommendation(rec, prediction):
    """REQ-ACT-010. Exactly one scored forward prediction, in the SAME transaction.

    Same as REQ-INF-301 for findings and REQ-INF-331 for recommendations: advice that commits to
    nothing can never be found wrong.
    """
    if not prediction:
        raise SurfaceViolation(
            "REQ-ACT-010: a pattern recommendation inserts exactly one scored forward prediction "
            "in the same transaction; advice that commits to nothing can never be found wrong")
    return {"recommendation": rec, "predictions": (prediction,), "atomic": True}


# ---------------------------------------------------------------- sleep and recovery

def recovery_coverage(coverage_by_measure):
    """REQ-SLP-020. Four separate measures with their own coverage; never one score.

    They have different capture rates and different failure modes — the Watch stopped recording
    some before others. A combined score hides which one is missing, so a score built from one
    live measure and three dead ones looks identical to a score built from four.
    """
    return {"measures": {m: coverage_by_measure.get(m) for m in RECOVERY_MEASURES},
            "combined_score": None,
            "note": ("These are four measures with four coverages. A single recovery score built "
                     "from one live measure and three lapsed ones would look identical to one "
                     "built from four.")}


def lapsed_measure(measure, *, last_observation, as_of):
    """REQ-SLP-021. Report the LAPSE with its date, not the last value as if current.

    Showing the last observation as the current one is the failure that made this requirement:
    an HRV from 2026-08-21 rendered without its date reads as today's HRV, and the reader has no
    way to know the Watch stopped.
    """
    if last_observation is None:
        return {"lapsed": True, "last_observation": None,
                "text": f"{measure} has no observations."}
    days = (as_of - last_observation).days
    return {"lapsed": days > 0, "last_observation": last_observation, "days_since": days,
            "value_shown_as_current": False,
            "text": (f"{measure} last recorded {last_observation.isoformat()}, {days} days ago." )}


def medical_guard(text, *, would_advise_on_condition):
    """REQ-SLP-022 / RULE-26. The STORED referral string, never a generated one.

    Stored because a generated refusal is a generated sentence about a medical topic, which is
    the thing being refused.
    """
    if would_advise_on_condition:
        return {"text": MEDICAL_REFERRAL, "generated": False, "original_withheld": True}
    return {"text": text, "generated": True}


def sleep_relation(statement, *, tier, coverage):
    """REQ-SLP-023. Tier and coverage attached; no causal vocabulary."""
    hits = tuple(v for v in CAUSAL_VOCAB
                 if re.search(rf"(?<![a-z]){re.escape(v)}(?![a-z])", statement.lower()))
    if hits:
        raise SurfaceViolation(
            f"REQ-SLP-023: causal vocabulary {list(hits)} in a statement relating sleep to "
            f"another measure")
    if tier is None or coverage is None:
        raise SurfaceViolation("REQ-SLP-023: the tier and coverage the reasoning layer assigned "
                               "travel with the statement")
    return {"text": statement, "tier": tier, "coverage": coverage}


# ---------------------------------------------------------------- reconstruction

def inferred_input(analysis, *, inputs):
    """REQ-REC-013. Uncertainty and lineage recorded; never treated as measured or independent.

    Not independent because inferred events derived from a shared source move together: three
    events reconstructed from the same receipt are one observation wearing three hats, and an
    analysis that counts them as three has tripled its own confidence for free.
    """
    for i in inputs:
        for f in ("uncertainty", "source_lineage"):
            if i.get(f) is None:
                raise SurfaceViolation(
                    f"REQ-REC-013: an inferred input carries {f}; without it the analysis cannot "
                    f"tell a reconstruction from a measurement")
    shared = {}
    for i in inputs:
        shared.setdefault(i["source_lineage"], []).append(i)
    return {**analysis, "inferred_inputs": tuple(inputs), "treated_as_measured": False,
            "independent": False,
            "shared_lineage_groups": tuple(sorted(k for k, v in shared.items() if len(v) > 1)),
            "note": ("Events reconstructed from one source move together; counting them as "
                     "independent observations multiplies confidence for free.")}


def distinguishing_evidence(alternatives, *, discriminators):
    """REQ-REC-015. Name what would tell the alternatives apart, or say that nothing would.

    "We are not sure" is not an answer. "We are not sure, and a receipt timestamp would settle
    it" is one Joe can act on; "we are not sure and nothing available would settle it" is one he
    can stop thinking about.
    """
    if len(alternatives) < 2:
        return None
    if discriminators:
        return {"alternatives": tuple(alternatives), "would_distinguish": tuple(discriminators),
                "text": (f"{len(alternatives)} interpretations fit. "
                         f"{', '.join(discriminators)} would tell them apart.")}
    return {"alternatives": tuple(alternatives), "would_distinguish": (),
            "text": (f"{len(alternatives)} interpretations fit and no discriminating evidence "
                     f"has been identified.")}


def acceptance_report(cases):
    """REQ-REC-016. Each family recorded as passed or EXPLICITLY OPEN — never one aggregate.

    A single pass/fail hides which family failed, and the families here fail for different
    reasons: contradictory evidence is a data problem, model unavailability is an ops problem,
    and inferred-input propagation is a correctness one.
    """
    missing = [f for f in EVENT_FAMILIES_REQUIRED if f not in cases]
    if missing:
        raise SurfaceViolation(
            f"REQ-REC-016: acceptance covers {missing} too; a single aggregate verdict hides "
            f"which family failed, and these fail for different reasons")
    return {"cases": {f: cases[f] for f in EVENT_FAMILIES_REQUIRED},
            "aggregate_verdict": None,
            "open": tuple(sorted(f for f, v in cases.items() if v != "passed")),
            "note": "Each family is passed or explicitly open. There is no single verdict."}


# ---------------------------------------------------------------- tier attachment

def confirmed_payload(claim, *, adjustment_set, e_value_point, negative_control_result):
    """REQ-TIER-023. All three travel in the SAME payload as the claim.

    Not reachable through a trace: in the payload. A CONFIRMED claim whose adjustment set is one
    click away is a CONFIRMED claim most readers will meet without it, and the adjustment set is
    what the word "confirmed" is resting on.
    """
    for name, v in (("adjustment_set", adjustment_set), ("e_value_point", e_value_point),
                    ("negative_control_result", negative_control_result)):
        if v is None:
            raise SurfaceViolation(
                f"REQ-TIER-023: a CONFIRMED_OBSERVATIONAL claim renders with {name} attached in "
                f"the same payload; it is what the word 'confirmed' rests on")
    return {**claim, "tier": "CONFIRMED_OBSERVATIONAL", "adjustment_set": tuple(adjustment_set),
            "e_value_point": e_value_point, "negative_control_result": negative_control_result}


def interval_statement(*, credible_interval=None, p_direction=None, confidence_interval=None):
    """REQ-TIER-025. Credible intervals and probability of direction; never a frequentist CI.

    A 95% confidence interval is not a 95% probability that the value is inside it, and every
    reader outside statistics reads it as one. Reporting the quantity people already think they
    are reading is more honest than reporting the other one correctly and being misread.
    """
    if confidence_interval is not None:
        raise SurfaceViolation(
            "REQ-TIER-025: a frequentist confidence interval is not rendered; it is not a 95% "
            "probability that the value is inside it, and every reader outside statistics reads "
            "it as one")
    if credible_interval is None or p_direction is None:
        raise SurfaceViolation("REQ-TIER-025: a credible interval and a probability of direction "
                               "are both reported")
    return {"credible_interval": tuple(credible_interval), "p_direction": p_direction,
            "text": (f"{credible_interval[0]}–{credible_interval[1]} "
                     f"({p_direction:.0%} probability the effect is in this direction)")}
