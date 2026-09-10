"""B17 Missing-C — income, balance, budget and forecast (REQ-FIN-001..004, 120..123, 214,
222/223, 259..266).

Measured on Joe's own data: 94% of inbound money is internal transfer. A system that treats
inbound as income overstates earnings roughly seventeen-fold.
"""
import datetime as dt

import pytest

from tools.engines.money_position import (FORECAST_MIN_WIDTH, INCOME, INTERNAL_TRANSFER,
                                          MoneyViolation, NOT_INFERABLE_TEXT, REIMBURSEMENT,
                                          USAGE_CONFIDENCE_CAP, balance, budget_vs_actual,
                                          changes_made, check_recurring_cost, classify_inbound,
                                          consumption_gap, forecast_outflows, income_streams,
                                          not_inferable, pattern_beside_goals, reconcile,
                                          transaction_as_visit, transaction_atom,
                                          usage_confidence)

AS_OF = dt.date(2026, 9, 10)


def test_REQ_FIN_002_003_a_finance_figure_renders_with_its_n():
    """"$412 at Hannaford" over three charges and over ninety are different claims, and the
    figure alone is identical."""
    assert transaction_atom({"amount": 41.0}, n_observations=19)["n_observations"] == 19
    with pytest.raises(MoneyViolation, match="REQ-FIN-002/003"):
        transaction_atom({"amount": 41.0}, n_observations=None)


def test_REQ_FIN_004_no_code_path_may_require_a_paid_tier():
    assert check_recurring_cost([{"name": "pg8000"}, {"name": "scipy"}])
    with pytest.raises(MoneyViolation, match="REQ-FIN-004"):
        check_recurring_cost([{"name": "plaid", "requires_paid_tier": True}])


def test_REQ_FIN_259_inbound_money_is_not_automatically_income():
    """94% of inbound money here is internal transfer. Treating inbound as income overstates
    earnings roughly seventeen-fold, and every savings-rate figure inherits that."""
    own = {"acct_savings"}
    paycheck = classify_inbound({"amount": 2400, "counterparty_account": "employer"},
                                own_accounts=own)
    assert paycheck["direction"] == INCOME and paycheck["is_income"] is True

    internal = classify_inbound({"amount": 500, "counterparty_account": "acct_savings"},
                                own_accounts=own)
    assert internal["direction"] == INTERNAL_TRANSFER and internal["is_income"] is False
    assert "94%" in internal["reason"]


def test_REQ_FIN_260_a_netted_reimbursement_is_never_income():
    """Counting it once as a reduction in spend and again as an arrival of money is
    double-counting in the flattering direction."""
    out = classify_inbound({"amount": 40}, netted_against="t1")
    assert out["direction"] == REIMBURSEMENT and out["is_income"] is False
    assert "double-count" in out["reason"]


def test_REQ_FIN_261_income_streams_use_the_SAME_recurrence_engine():
    """A separate threshold for income would be a second definition of "recurring" in one system,
    and a paycheck detected by one rule and not the other is a difference nobody would look
    for."""
    from tools.engines.recurrence import detect
    txns = [{"counterparty": "Employer", "account": "chk",
             "day": dt.date(2026, m, 15), "amount": 2400.0} for m in range(1, 7)]
    out = income_streams(txns, detect=lambda c: detect(c, as_of=AS_OF))
    assert out and out[0]["engine"] == "recurrence.detect"
    assert out[0]["cadence_label"] == "monthly_day_of_month"
    assert out[0]["maturity"] == "mature"


def test_REQ_FIN_262_263_a_balance_is_as_of_a_date_and_never_live():
    """A running position updated continuously is the "$312 left" counter with a different
    label."""
    txns = [{"amount": 1000, "day": dt.date(2026, 9, 1)},
            {"amount": -300, "day": dt.date(2026, 9, 5)},
            {"amount": -50, "day": dt.date(2026, 9, 20)}]
    out = balance(txns, as_of=AS_OF)
    assert out["position"] == 700 and out["live"] is False
    assert out["as_of"] == AS_OF and "As of 2026-09-10" in out["label"]


def test_REQ_FIN_262_a_position_may_not_update_more_than_once_a_day():
    out = balance([], as_of=AS_OF, last_update=dt.datetime(2026, 9, 10, 8),
                  now=dt.datetime(2026, 9, 10, 12))
    assert out["updated"] is False and "REQ-FIN-262/211" in out["reason"]


def test_REQ_FIN_263_a_coverage_gap_makes_the_balance_APPROXIMATE_and_says_so():
    """A balance derived from imports that stopped on 2026-05-13 is an approximate position, and
    an unlabelled approximate position is read as an exact one."""
    out = balance([{"amount": 100, "day": AS_OF}], as_of=AS_OF,
                  coverage_gaps={"bank_csv": 38})
    assert out["is_exact"] is False
    assert "38-day gap" in out["label"]
    assert balance([], as_of=AS_OF)["is_exact"] is True


def test_REQ_FIN_266_a_period_that_does_not_reconcile_is_FLAGGED_not_absorbed():
    """A period that does not reconcile means transactions are missing, and the totals for that
    period are wrong by exactly the amount nobody can see."""
    period = (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    txns = [{"amount": -100, "posted_at": dt.datetime(2026, 9, 5)}]
    ok = reconcile(txns, -100, period=period)
    assert ok["reconciles"] is True
    bad = reconcile(txns, -250, period=period)
    assert bad["reconciles"] is False and bad["flagged"] is True
    assert bad["delta"] == 150.0
    assert "Transactions are missing" in bad["text"]


def test_REQ_FIN_266_reconciliation_reads_posted_at_not_occurred_at():
    """A balance is about money that has actually moved."""
    period = (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    txns = [{"amount": -100, "posted_at": dt.datetime(2026, 10, 2),
             "occurred_at": dt.datetime(2026, 9, 30)}]
    assert reconcile(txns, 0, period=period)["reconciles"] is True


def test_REQ_FIN_214_264_budget_versus_actual_is_retrospective_or_a_range_never_a_counter():
    """Budgets are in scope. What is not in scope is the counter ticking down."""
    closed = budget_vs_actual(budget=400, actual=412, period_closed=True)
    assert closed["form"] == "retrospective" and closed["live_counter"] is False
    assert closed["score"] is None and closed["grade"] is None and closed["judgment"] is None
    ranged = budget_vs_actual(budget=400, actual=None, period_closed=False, as_range=[330, 470])
    assert ranged["form"] == "range"
    with pytest.raises(MoneyViolation, match="REQ-FIN-264/214"):
        budget_vs_actual(budget=400, actual=250, period_closed=False)


def test_REQ_FIN_265_a_forecast_is_a_range_at_least_twenty_percent_wide():
    """A projected end-of-month total is the most tempting number in a finance app, and detected
    recurrence gives a good basis for one — which makes it more dangerous, not less."""
    streams = [{"monthly_amount": 100, "amount_behaviour": "fixed", "lifecycle": "active"},
               {"monthly_amount": 100, "amount_behaviour": "variable", "lifecycle": "active"}]
    out = forecast_outflows(streams, as_of=AS_OF)
    assert out["point_estimate"] is None
    width = (out["high"] - out["low"]) / out["midpoint"]
    assert width >= FORECAST_MIN_WIDTH
    assert out["committed"] == 100.0


def test_REQ_FIN_265_a_cancelled_stream_is_not_forecast():
    streams = [{"monthly_amount": 100, "amount_behaviour": "fixed", "lifecycle": "cancelled"}]
    assert forecast_outflows(streams, as_of=AS_OF)["midpoint"] == 0.0


def test_REQ_FIN_222_the_gap_may_be_NAMED_but_never_asserted_as_established():
    out = pattern_beside_goals("bar visits cluster on Fridays", ["train Saturday mornings"],
                               tier="T1_DESCRIPTIVE", uncertainty="n=19",
                               what_would_raise_it="20 more in the smaller arm",
                               gap="Friday visits sit before your Saturday sessions")
    assert out["asserted_as_established"] is False
    assert "T1_DESCRIPTIVE" in out["gap_qualifier"] and "n=19" in out["gap_qualifier"]


def test_REQ_FIN_223_the_review_carries_the_running_record_of_changes_and_their_effect():
    """The only place this system keeps score, and it scores the SYSTEM: a review that reports
    spending without reporting what the last review changed never closes a loop."""
    out = changes_made([{"stream": "Adobe", "monthly_amount": 22.99}], period="2026-Q3")
    assert out["running_total_monthly"] == 22.99 and "1 change(s)" in out["text"]
    assert changes_made([], period="2026-Q3")["text"] == "No changes recorded yet."


def test_REQ_FIN_120_confidence_is_capped_by_the_purchase_TYPE_not_by_the_reasoning():
    """A gym membership has a strong usage signal; a book has none. Letting the engine assign its
    own confidence would let a plausible chain of reasoning about a book reach the same number as
    a door swipe."""
    assert USAGE_CONFIDENCE_CAP == {"strong": 0.90, "medium": 0.60, "weak": 0.30,
                                    "not_inferable": 0.00}
    out = usage_confidence("weak", 0.95)
    assert out["confidence"] == 0.30 and out["capped"] is True
    assert usage_confidence("strong", 0.5)["confidence"] == 0.5
    with pytest.raises(MoneyViolation, match="REQ-FIN-120"):
        usage_confidence("very_strong", 0.9)


def test_REQ_FIN_121_a_not_inferable_purchase_attempts_NO_inference():
    """Not "we tried and could not tell" — no attempt at all. An attempted inference on something
    with no signal produces a number derived from nothing, and a 0.0-confidence number still
    renders."""
    out = not_inferable({"merchant": "a bookshop"})
    assert out["status"] == "unknown" and out["text"] == NOT_INFERABLE_TEXT
    assert out["inference_attempted"] is False


def test_REQ_FIN_122_the_consumption_gap_is_a_range_and_never_a_point():
    """It is the difference of two estimates, each with its own error, so the gap's uncertainty
    is larger than either — a point estimate of it would be the most precise-looking and least
    supported number in the subsystem."""
    out = consumption_gap(2400, 2100, uncertainty=400)
    assert out["point_estimate"] is None
    assert out["low"] == -100.0 and out["high"] == 700.0
    with pytest.raises(MoneyViolation, match="REQ-FIN-122"):
        consumption_gap(2400, 2100, uncertainty=None)


def test_REQ_FIN_123_a_transaction_at_a_known_location_IS_a_location_fix():
    """A card present at a gym is stronger evidence of being at the gym than most things this
    system could infer, and it costs no capture at all."""
    out = transaction_as_visit({"merchant": "Planet Fitness", "day": AS_OF},
                               merchant_has_location=True)
    assert out["type"] == "transaction_as_visit" and out["kind"] == "usage_evidence"
    assert transaction_as_visit({"merchant": "Amazon"}, merchant_has_location=False) is None
