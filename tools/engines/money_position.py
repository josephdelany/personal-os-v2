"""B17 Missing-C — income, balance, budget and forecast (REQ-FIN-001..004, 120..123, 214,
222/223, 259..266).

Pure: no database, no clock, no model.

WHY INCOME IS A DIRECTION AND NOT A CATEGORY (REQ-FIN-259/260). Money arriving is three different
things: a paycheck, a reimbursement for a tab Joe fronted, and a transfer between his own
accounts. Measured on this data, **94% of inbound money is internal transfer** -- so a system
that treats "inbound" as "income" overstates earnings roughly seventeen-fold, and every
savings-rate and net-spend figure built on it inherits that.

So direction is not enough on its own: a reimbursement already netted against a shared cost
(REQ-FIN-049) is explicitly NOT income, because counting it twice -- once as a reduction in spend
and once as an arrival of money -- is double-counting in the flattering direction.

WHY THE BALANCE IS AS-OF AND NEVER LIVE (REQ-FIN-262/263). §E's measured harm applies here in
full: a running position updated continuously is the "you have $312 left" counter with a
different label. So it is derived as-of a stated date, updated at most daily, and labelled with
its coverage limitation -- because a balance derived from imports that stopped on 2026-05-13 is
an approximate position, and an unlabelled approximate position is read as an exact one.

WHY A FORECAST IS A RANGE AT LEAST 20% WIDE (REQ-FIN-265). A projected end-of-month total is the
single most tempting number in a finance app and the one §E's evidence most directly implicates.
Detected recurrence gives a good basis for one -- which makes it more dangerous, not less.

WHY THE USAGE-INFERENCE CONFIDENCE IS CAPPED BY PURCHASE TYPE (REQ-FIN-120). A gym membership has
a strong usage signal (a place visit); a book has none. Letting the engine assign its own
confidence would let a plausible-looking chain of reasoning about a book reach the same number as
a door swipe.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

INCOME = "income"
SPEND = "spend"
REIMBURSEMENT = "reimbursement"
INTERNAL_TRANSFER = "internal_transfer"

# REQ-FIN-120. The cap is a property of the purchase TYPE, never of the reasoning.
USAGE_CONFIDENCE_CAP = {"strong": 0.90, "medium": 0.60, "weak": 0.30, "not_inferable": 0.00}
NOT_INFERABLE_TEXT = "no usage signal exists for this"      # REQ-FIN-121

FORECAST_MIN_WIDTH = 0.20          # REQ-FIN-265 / REQ-FIN-212
BALANCE_MAX_UPDATE_HOURS = 24      # REQ-FIN-262 / REQ-FIN-211


class MoneyViolation(Exception):
    pass


# ---------------------------------------------------------------- the spine contract

def transaction_atom(txn, *, n_observations):
    """REQ-FIN-001/002/003. A transaction is an atom, and every displayed number carries its n.

    The n is not decoration: "you spent $412 at Hannaford" over three charges and over ninety are
    different claims, and the figure alone is identical.
    """
    if n_observations is None:
        raise MoneyViolation(
            "REQ-FIN-002/003: a finance figure renders with the count of underlying observations; "
            "$412 over three charges and over ninety are different claims and the figure alone is "
            "identical")
    return {"kind": "transaction", **txn, "n_observations": n_observations}


def check_recurring_cost(dependencies):
    """REQ-FIN-004 / RULE-28. $0.00 recurring, and no code path may require a paid tier."""
    paid = tuple(sorted(d["name"] for d in dependencies if d.get("requires_paid_tier")))
    if paid:
        raise MoneyViolation(
            f"REQ-FIN-004: {list(paid)} require a paid tier; the finance subsystem incurs $0.00 "
            f"in recurring cost and no code path may require one")
    return True


# ---------------------------------------------------------------- income

def classify_inbound(txn, *, netted_against=None, own_accounts=()):
    """REQ-FIN-259/260. Inbound is not income. Measured here: 94% of it is internal transfer.

    A system that treats inbound as income overstates earnings roughly seventeen-fold, and every
    savings-rate and net-spend figure built on it inherits that. A reimbursement already netted
    against a shared cost is explicitly NOT income either — counting it once as a reduction in
    spend and again as an arrival of money is double-counting in the flattering direction.
    """
    if float(txn.get("amount", 0)) <= 0:
        return {"direction": SPEND, "is_income": False}
    if netted_against is not None:
        return {"direction": REIMBURSEMENT, "is_income": False,
                "netted_against": netted_against,
                "reason": ("REQ-FIN-260: already netted against a shared cost; counting it again "
                           "as income would double-count in the flattering direction")}
    counterparty = (txn.get("counterparty_account") or "")
    if counterparty and counterparty in set(own_accounts):
        return {"direction": INTERNAL_TRANSFER, "is_income": False,
                "reason": ("a transfer between Joe's own accounts is not money arriving; measured "
                           "on this data, 94% of inbound money is internal transfer")}
    return {"direction": INCOME, "is_income": True}


def income_streams(income_txns, *, detect):
    """REQ-FIN-261. Detected by the SAME recurrence engine, inheriting its maturity threshold.

    A separate threshold for income would be a second definition of "recurring" in one system, and
    the two would drift — a paycheck detected as a stream by one rule and not by the other is a
    difference nobody would look for.
    """
    charges = [{"merchant": t["counterparty"], "account": t["account"], "day": t["day"],
                "amount": t["amount"]} for t in income_txns]
    streams = detect(charges)
    return tuple({"counterparty": s.merchant, "cadence_days": s.period_days,
                  "cadence_label": s.period_label, "amount_behaviour": s.amount_behaviour,
                  "maturity": s.maturity, "engine": "recurrence.detect"} for s in streams)


# ---------------------------------------------------------------- balance and position

def balance(transactions, *, as_of, coverage_gaps=None, last_update=None, now=None):
    """REQ-FIN-262/263. As-of a stated date, at most daily, labelled with its coverage limits.

    §E's measured harm applies in full: a running position updated continuously is the "you have
    $312 left" counter with a different label. And a balance derived from imports that stopped on
    2026-05-13 is an approximate position — an unlabelled approximate position is read as an
    exact one.
    """
    if last_update is not None and now is not None:
        hours = (now - last_update).total_seconds() / 3600.0
        if hours < BALANCE_MAX_UPDATE_HOURS:
            return {"updated": False,
                    "reason": (f"REQ-FIN-262/211: last updated {hours:.1f}h ago; a position may "
                               f"not update more than once per {BALANCE_MAX_UPDATE_HOURS}h")}
    total = sum(float(t["amount"]) for t in transactions if t["day"] <= as_of)
    gaps = {a: d for a, d in (coverage_gaps or {}).items() if d and d > 0}
    return {"position": round(total, 2), "as_of": as_of, "live": False,
            "coverage_gaps": gaps,
            "label": (f"As of {as_of.isoformat()}." +
                      (f" Approximate: {', '.join(f'{a} has a {d}-day gap' for a, d in sorted(gaps.items()))}."
                       if gaps else "")),
            "is_exact": not gaps}


def reconcile(transactions, statement_balance, *, period, tolerance=0.01):
    """REQ-FIN-266. Reconciled on `posted_at`, and every non-reconciling period is FLAGGED.

    On posted_at because a balance is about money that has moved (REQ-FIN-041). And flagged rather
    than silently absorbed: a period that does not reconcile means transactions are missing, and
    the totals for that period are wrong by exactly the amount nobody can see.
    """
    posted = [t for t in transactions
              if t.get("posted_at") is not None and period[0] <= t["posted_at"].date() <= period[1]]
    derived = round(sum(float(t["amount"]) for t in posted), 2)
    delta = round(derived - float(statement_balance), 2)
    if abs(delta) <= tolerance:
        return {"reconciles": True, "period": period, "derived": derived, "delta": 0.0}
    return {"reconciles": False, "period": period, "derived": derived,
            "statement": float(statement_balance), "delta": delta, "flagged": True,
            "text": (f"{period[0].isoformat()}–{period[1].isoformat()} does not reconcile: "
                     f"{derived:.2f} ingested against {float(statement_balance):.2f} posted, a "
                     f"difference of {delta:.2f}. Transactions are missing and this period's "
                     f"totals are wrong by that amount.")}


# ---------------------------------------------------------------- budget and forecast

def budget_vs_actual(*, budget, actual, period_closed, as_range=None):
    """REQ-FIN-214/264. Retrospective or a range; never a live remaining-to-spend counter, and
    never a score, grade or judgment.

    Budgets are in scope (RULED-2/ADR-0031). What is not in scope is the counter ticking down,
    which is the exact intervention with measured evidence of harm.
    """
    if not period_closed and as_range is None:
        raise MoneyViolation(
            "REQ-FIN-264/214: budget-versus-actual is presented retrospectively for a closed "
            "period or as a range; a live remaining-to-spend counter is the one feature with "
            "measured evidence of causing overspending")
    out = {"budget": budget, "score": None, "grade": None, "judgment": None,
           "live_counter": False}
    if period_closed:
        return {**out, "actual": actual, "form": "retrospective"}
    return {**out, "actual_range": tuple(as_range), "form": "range"}


def forecast_outflows(streams, *, as_of, horizon_days=30):
    """REQ-FIN-265. Committed and expected outflows as a RANGE at least 20% of its midpoint wide.

    A projected end-of-month total is the single most tempting number in a finance app, and
    detected recurrence gives a good basis for one — which makes it more dangerous, not less.
    """
    committed = sum(float(s["monthly_amount"]) for s in streams
                    if s.get("amount_behaviour") == "fixed" and s.get("lifecycle") == "active")
    variable = sum(float(s["monthly_amount"]) for s in streams
                   if s.get("amount_behaviour") != "fixed" and s.get("lifecycle") == "active")
    mid = committed + variable
    if mid == 0:
        return {"low": 0.0, "high": 0.0, "midpoint": 0.0, "point_estimate": None}
    half = max(mid * FORECAST_MIN_WIDTH / 2.0, variable / 2.0)
    lo, hi = round(mid - half, 2), round(mid + half, 2)
    width = (hi - lo) / abs(mid)
    if width < FORECAST_MIN_WIDTH:
        raise MoneyViolation(
            f"REQ-FIN-265/212: a forecast range {width:.0%} of its midpoint is below the "
            f"{FORECAST_MIN_WIDTH:.0%} floor; a range that tight is a projected total with a "
            f"hyphen in it")
    return {"low": lo, "high": hi, "midpoint": round(mid, 2), "point_estimate": None,
            "committed": round(committed, 2), "horizon_days": horizon_days, "as_of": as_of}


def pattern_beside_goals(pattern, goals, *, tier, uncertainty, what_would_raise_it, gap=None):
    """REQ-FIN-222 / RULE-25. The pattern beside Joe's own goals; the gap may be NAMED, not
    asserted."""
    out = {"pattern": pattern, "goals": tuple(goals), "tier": tier,
           "uncertainty": uncertainty, "what_would_raise_it": what_would_raise_it,
           "asserted_as_established": False}
    if gap:
        out["gap"] = gap
        out["gap_qualifier"] = f"At {tier}, {uncertainty}. {what_would_raise_it}"
    return out


def changes_made(cancellations, *, period):
    """REQ-FIN-223 / REQ-FIN-156. The running record of what Joe changed and what it did.

    The only place this system keeps score, and it scores the SYSTEM: a review that reports
    spending without reporting what the last review changed is a review that never closes a loop.
    """
    total = round(sum(float(c["monthly_amount"]) for c in cancellations), 2)
    return {"period": period, "changes": tuple(cancellations),
            "running_total_monthly": total,
            "text": (f"{len(cancellations)} change(s) since this record began, "
                     f"{total:.2f}/month." if cancellations else
                     "No changes recorded yet.")}


# ---------------------------------------------------------------- usage inference

def usage_confidence(purchase_class, proposed_confidence):
    """REQ-FIN-120. Capped by the purchase TYPE, never by the reasoning.

    A gym membership has a strong usage signal (a place visit); a book has none. Letting the
    engine assign its own confidence would let a plausible chain of reasoning about a book reach
    the same number as a door swipe.
    """
    if purchase_class not in USAGE_CONFIDENCE_CAP:
        raise MoneyViolation(f"REQ-FIN-120: {purchase_class!r} is not a purchase class")
    cap = USAGE_CONFIDENCE_CAP[purchase_class]
    return {"confidence": min(float(proposed_confidence), cap), "cap": cap,
            "capped": float(proposed_confidence) > cap, "purchase_class": purchase_class}


def not_inferable(purchase):
    """REQ-FIN-121. 'unknown', the stored sentence, and NO inference attempted.

    Not "we tried and could not tell" — no attempt at all. An attempted inference on something
    with no signal produces a number derived from nothing, and a 0.0-confidence number still
    renders.
    """
    return {"status": "unknown", "text": NOT_INFERABLE_TEXT,
            "inference_attempted": False, "confidence": 0.0}


def consumption_gap(acquired_kcal, required_kcal, *, uncertainty):
    """REQ-FIN-122. A RANGE with its uncertainty stated, never a point.

    The published method infers waste as the gap between food energy acquired and metabolic
    energy required — a difference of two estimates, each with its own error, so the gap's
    uncertainty is larger than either. A point estimate of it would be the most precise-looking
    and least supported number in the subsystem.
    """
    if not uncertainty:
        raise MoneyViolation(
            "REQ-FIN-122: the grocery-versus-consumption gap is a range with a stated "
            "uncertainty; it is the difference of two estimates and its error is larger than "
            "either")
    gap = float(acquired_kcal) - float(required_kcal)
    half = abs(float(uncertainty))
    return {"low": round(gap - half, 1), "high": round(gap + half, 1), "point_estimate": None,
            "uncertainty": half,
            "note": ("The gap between energy acquired and energy required is the difference of "
                     "two estimates, so its uncertainty is larger than either.")}


def transaction_as_visit(txn, *, merchant_has_location):
    """REQ-FIN-123. A transaction at a known physical location IS a location fix.

    Cheap and reliable: a card present at a gym is stronger evidence of being at the gym than
    most things this system could infer, and it costs no capture at all.
    """
    if not merchant_has_location:
        return None
    return {"kind": "usage_evidence", "type": "transaction_as_visit",
            "merchant": txn.get("merchant"), "day": txn.get("day"),
            "note": ("A card present at a merchant with a known physical location is a location "
                     "fix, and it costs no capture.")}
