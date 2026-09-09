"""B14R step 4: the deterministic evaluator (REQ-REC-006..015).

The acceptance cases are INTENT_COVERAGE R1-R12. These cover the reconstruction-local ones
that need no entity resolution; R9/R11 belong to M5 and are not claimed here.
"""
import datetime as dt

import pytest

from tools.engines.reconstruct import (Evidence, Method, calibrate, evaluate,
                                       independent_origins, known_at, to_row)

NOW = dt.datetime(2026, 7, 2, tzinfo=dt.timezone.utc)
MEAL = Method("meal_from_charge", 1, "meal", ("transaction",), ("occurred",), "interval")


def ev(ref, kind="transaction", stance="supports", origin=None, at=None):
    return Evidence(ref, kind, stance, origin or ref,
                    at or dt.datetime(2026, 7, 1, 18, tzinfo=dt.timezone.utc))


def test_REQ_REC_009_missing_evidence_never_becomes_did_not_occur():
    """The single most tempting error in the feature. Absence of a record is absence of
    capture, not absence of the event, and there is deliberately no code path to the
    opposite conclusion."""
    r = evaluate(MEAL, [], NOW)
    assert r.presence == "unknown" and r.tier == "INSUFFICIENT"
    assert r.reason == "required_evidence_missing"
    assert r.missing_evidence == ("transaction",)
    assert r.rule_score is None


def test_REQ_REC_008_two_copies_of_one_receipt_are_not_two_corroborations():
    """INTENT_COVERAGE R5. Independence is counted by origin, never by row."""
    e = [ev("gmail:receipt-1", origin="receipt-1"),
         ev("drive:receipt-1-copy", origin="receipt-1"),
         ev("bank:txn-99", origin="bank-txn-99")]
    assert independent_origins(e, "supports") == 2, "duplicate copies counted as independent"
    r = evaluate(MEAL, e, NOW)
    assert r.independent_support == 2 and len(r.evidence) == 3


def test_REQ_REC_007_contradiction_is_not_outweighed_by_counting_harder():
    """INTENT_COVERAGE R3. One source contradicts attendance. Level or against is unresolved,
    and what would settle it is part of the answer."""
    e = [ev("bank:txn-99", origin="bank"),
         ev("calendar:declined", kind="calendar", stance="contradicts", origin="calendar")]
    r = evaluate(MEAL, e, NOW, discriminating=("a receipt naming the covers",))
    assert r.presence == "unknown" and r.reason == "contradicted"
    assert "contradict" in r.unresolved_ambiguity
    assert r.discriminating_evidence == ("a receipt naming the covers",)


def test_REQ_REC_007_an_empty_alternative_set_is_stated_not_left_blank():
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    assert r.no_alternative_generator is True and r.alternatives == []
    r2 = evaluate(MEAL, [ev("bank:txn-99")], NOW,
                  alternatives=[{"explanation": "someone else used the card"}])
    assert r2.no_alternative_generator is False


def test_REQ_REC_010_evaluate_cannot_be_handed_a_probability():
    """Enforced by signature, not by discipline. There is no parameter to pass one in."""
    import inspect
    params = set(inspect.signature(evaluate).parameters)
    assert "probability" not in params and "confidence" not in params
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    assert r.probability is None and r.calibration_ref is None
    assert r.rule_score is not None, "an uncalibrated ranking is still permitted"


def test_REQ_REC_010_a_probability_requires_the_calibration_that_earned_it():
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    with pytest.raises(ValueError, match="REQ-REC-010"):
        calibrate(r, 0.8, "")
    calibrate(r, 0.8, "cal-2026-09")
    assert (r.probability, r.calibration_ref) == (0.8, "cal-2026-09")


def test_REQ_REC_009_an_unknown_event_cannot_be_calibrated():
    r = evaluate(MEAL, [], NOW)
    with pytest.raises(ValueError, match="REQ-REC-009"):
        calibrate(r, 0.8, "cal-2026-09")


def test_REQ_REC_012_evidence_recorded_after_the_cutoff_is_not_used():
    """RULE-04. A reconstruction may not use knowledge it did not have. INTENT_COVERAGE R6:
    a later receipt revises the CURRENT reading without rewriting the historical one."""
    late = ev("gmail:receipt-later", origin="receipt",
              at=dt.datetime(2026, 8, 1, tzinfo=dt.timezone.utc))
    early = ev("bank:txn-99", origin="bank")
    assert known_at([early, late], NOW) == (early,)
    asked_then = evaluate(MEAL, [early, late], NOW)
    asked_now = evaluate(MEAL, [early, late], dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc))
    assert asked_then.independent_support == 1
    assert asked_now.independent_support == 2, "the later receipt is visible now"
    assert asked_then.tier == "DESCRIPTIVE" and asked_now.tier == "EXPLORATORY"


def test_REQ_REC_006_a_method_may_not_output_what_it_did_not_declare():
    """R2: a watch strength-session record with no set log reconstructs the SESSION. A method
    declaring only 'occurred' cannot be used to assert absence."""
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    r.presence = "did_not_occur"
    with pytest.raises(ValueError, match="REQ-REC-006"):
        to_row(r, MEAL, NOW, NOW, dt.date(2026, 7, 1), NOW)


def test_REQ_REC_005_the_row_carries_both_clocks_and_no_measured_value():
    """INV-5. Event time and knowledge time are different clocks; conflating them is how a
    replayed answer silently improves."""
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    row = to_row(r, MEAL, NOW, NOW, dt.date(2026, 7, 1), NOW)
    assert {"event_time_from", "event_time_to", "knowledge_time"} <= set(row)
    assert not (set(row) & {"value_point", "value_low", "value_high", "unit",
                            "estimate_method"})


def test_REQ_REC_014_the_engine_needs_no_model_to_return_an_answer():
    """RULE-15. INTENT_COVERAGE R10: with the language model unavailable, the registered
    method still executes and returns a traced deterministic answer."""
    import inspect
    for fn in (evaluate, calibrate, to_row, known_at, independent_origins):
        source = inspect.getsource(fn)
        assert "egress" not in source and "call(" not in source, f"{fn.__name__} reaches out"
    r = evaluate(MEAL, [ev("bank:txn-99")], NOW)
    assert r.presence == "occurred" and r.evidence, "no traceable evidence attached"


def test_REQ_REC_012_the_same_question_and_cutoff_replays_identically():
    e = [ev("bank:txn-99", origin="bank"), ev("gmail:receipt", origin="receipt")]
    first = evaluate(MEAL, e, NOW)
    second = evaluate(MEAL, list(reversed(e)), NOW)
    assert (first.presence, first.tier, first.rule_score) == \
           (second.presence, second.tier, second.rule_score), "order changed the answer"
