"""B17 §C.3 — recurrence detection (REQ-FIN-130..140).

Pure: no database, no clock, no model. Deterministic — same charges in, same streams out.

WHY MEDIAN AND MAD, NEVER MEAN AND SD (REQ-FIN-133). A subscription billed on the 1st for eleven
months and skipped once has intervals [31, 31, 62, 31, ...]. The mean interval is dragged toward
35 and the standard deviation explodes, so the fit fails and a real subscription disappears from
the ledger. The median is 31 and the MAD is 0: one missed month is one outlier, and the whole
point of a robust statistic is that an outlier does not get a vote.

WHY MONTHLY IS DAY-OF-MONTH, NOT 30 DAYS (REQ-FIN-132). A charge on the 31st recurs on the 28th
in February and slides to Monday when the 1st is a Sunday. Measured as a fixed 30-day interval
those are misses; measured as "same day of month, plus or minus three", they are the same
subscription. A 30-day rule also drifts a full day every month by construction, so after a year
it is comparing against a date the merchant never used.

WHY AMOUNT STABILITY IS NOT REQUIRED (REQ-FIN-136). A phone bill and a utility bill are recurring
in every sense that matters and their amounts move every month. Requiring a stable amount to
call something recurring would detect Netflix and miss the electricity -- and the electricity is
the one worth knowing about, because it is where a step change hides.

WHY A CANCELLED STREAM IS NEVER DELETED (REQ-FIN-138). A resurrected subscription is itself
behavioural data: the thing Joe cancelled in March and restarted in September is a more
interesting fact than either event alone. Deleting the row would make the restart look like a
first-ever charge.
"""
from __future__ import annotations

import datetime as dt
import statistics
from dataclasses import dataclass, field

CANDIDATE_PERIODS = (7, 14, 15, 30, 91, 365)     # REQ-FIN-132
MONTHLY_DAY_TOLERANCE = 3                        # REQ-FIN-132
MATURE_OCCURRENCES = 3                           # REQ-FIN-130
EARLY_OCCURRENCES = 2                            # REQ-FIN-131
FIXED_CV = 0.02                                  # REQ-FIN-134
LAPSED_MULTIPLE = 1.5                            # REQ-FIN-137
CANCELLED_MULTIPLE = 2.5                         # REQ-FIN-137

# REQ-FIN-139. Same mathematics, different table, different surface. A weekly coffee IS periodic,
# and calling it a subscription would put "cancel this?" next to something nobody subscribes to.
HABIT_CATEGORIES = frozenset({"groceries", "fuel", "coffee", "bars", "dining"})


@dataclass(frozen=True)
class Stream:
    merchant: str
    account: str
    occurrences: int
    period_days: int | None
    period_label: str
    interval_mad: float
    amount_behaviour: str
    amounts: tuple
    first_day: dt.date
    last_day: dt.date
    maturity: str                 # 'mature' | 'early_detection'
    lifecycle: str                # 'active' | 'lapsed' | 'cancelled'
    changepoint: dict | None = None
    routed_to: str = "subscriptions"
    user_label: str | None = None


def _median_interval(days):
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps:
        return None, None
    med = statistics.median(gaps)
    # Median absolute deviation, not standard deviation: one missed month is one outlier and an
    # outlier must not get a vote.
    mad = statistics.median([abs(g - med) for g in gaps])
    return med, mad


def _monthly_fit(days, tolerance=MONTHLY_DAY_TOLERANCE):
    """REQ-FIN-132. Same day-of-month, plus or minus `tolerance`, month-end aware.

    A charge on the 31st lands on the 28th in February and on the 30th in April. Comparing raw
    day numbers would call those a 3-day and a 1-day miss; comparing against the last day of the
    shorter month calls them exact, which is what they are.
    """
    if len(days) < 2:
        return False, None
    anchor = days[0].day
    misses = []
    for d in days[1:]:
        last = _last_day_of_month(d.year, d.month)
        target = min(anchor, last)
        misses.append(abs(d.day - target))
    return all(m <= tolerance for m in misses), (max(misses) if misses else None)


def _last_day_of_month(year, month):
    if month == 12:
        return 31
    return (dt.date(year, month + 1, 1) - dt.timedelta(days=1)).day


def _best_period(days):
    """Which candidate period fits, if any. Monthly is tested by day-of-month, not by 30 days."""
    monthly_ok, worst = _monthly_fit(days)
    if monthly_ok:
        return 30, "monthly_day_of_month", 0.0
    med, mad = _median_interval(days)
    if med is None:
        return None, "unknown", None
    best, best_err = None, None
    for p in CANDIDATE_PERIODS:
        err = abs(med - p) / p
        if best_err is None or err < best_err:
            best, best_err = p, err
    # A period only counts as a fit if the median lands near it AND the spread is small relative
    # to the period. A MAD of 10 days around a 30-day period is not a monthly subscription.
    if best_err is not None and best_err <= 0.20 and (mad or 0) <= max(2.0, 0.2 * best):
        return best, f"{best}_day", float(mad or 0)
    return None, "irregular", float(mad or 0)


def detect_changepoint(amounts, *, min_segment=2, min_step_fraction=0.05):
    """REQ-FIN-134/135. A single step in the amount series, found by exhaustive split.

    Exhaustive rather than iterative because a stream has tens of points, not thousands, and an
    exhaustive search is deterministic and has no tuning parameters to get wrong. The step must
    clear 5% of the earlier level: a subscription that moves from $9.99 to $10.00 has not
    changed price, it has been rounded, and reporting that as a price rise would train Joe to
    ignore the ones that matter.
    """
    n = len(amounts)
    if n < 2 * min_segment:
        return None
    best = None
    for cut in range(min_segment, n - min_segment + 1):
        left, right = amounts[:cut], amounts[cut:]
        lm, rm = statistics.mean(left), statistics.mean(right)
        if lm == 0:
            continue
        if abs(rm - lm) / abs(lm) < min_step_fraction:
            continue
        # Within-segment variance: the split that best explains the series.
        cost = sum((x - lm) ** 2 for x in left) + sum((x - rm) ** 2 for x in right)
        if best is None or cost < best["cost"]:
            best = {"index": cut, "previous_amount": round(lm, 2), "new_amount": round(rm, 2),
                    "cost": cost}
    if best:
        best.pop("cost")
    return best


def classify_amounts(amounts):
    """REQ-FIN-134. 'fixed' below 2% CV, 'fixed_with_step' on a changepoint, else 'variable'."""
    vals = [float(a) for a in amounts]
    if len(vals) < 2:
        return "fixed", None
    mean = statistics.mean(vals)
    cv = (statistics.pstdev(vals) / abs(mean)) if mean else 0.0
    if cv < FIXED_CV:
        return "fixed", None
    cp = detect_changepoint(vals)
    if cp:
        # Fixed on each side of one step. Checked rather than assumed: a series that wanders AND
        # happens to have a best split is 'variable', and calling it 'fixed_with_step' would
        # promise a stable price that does not exist.
        left, right = vals[:cp["index"]], vals[cp["index"]:]
        for seg in (left, right):
            m = statistics.mean(seg)
            if m and (statistics.pstdev(seg) / abs(m)) >= FIXED_CV:
                return "variable", cp
        return "fixed_with_step", cp
    return "variable", None


def lifecycle(days_since_last, expected_period, *, tolerance_days=0):
    """REQ-FIN-137. active < 1.5x, lapsed 1.5x-2.5x, cancelled beyond."""
    if expected_period is None:
        return "active"
    limit = expected_period * LAPSED_MULTIPLE + tolerance_days
    dead = expected_period * CANCELLED_MULTIPLE + tolerance_days
    if days_since_last < limit:
        return "active"
    if days_since_last <= dead:
        return "lapsed"
    return "cancelled"


def changepoint_insight(stream):
    """REQ-FIN-135. The previous amount, the new amount, and the MONTH of the change.

    The month, not the index: "it went from $12.99 to $15.99 in March" is a fact Joe can check
    against his memory. "A changepoint at position 7" is not.
    """
    cp = stream.changepoint
    if not cp:
        return None
    return {
        "kind": "recurring_amount_change",
        "merchant": stream.merchant,
        "previous_amount": cp["previous_amount"],
        "new_amount": cp["new_amount"],
        "changed_month": cp.get("changed_month"),
        "text": (f"{stream.merchant} changed from {cp['previous_amount']:.2f} to "
                 f"{cp['new_amount']:.2f} in {cp.get('changed_month')}."),
    }


def build_stream(merchant, account, charges, *, as_of, category=None, user_labels=None,
                 tolerance_days=0):
    """One (merchant, account) group -> a Stream, or None if it is not periodic enough.

    `charges` is a sequence of (day, amount), any order. `user_labels` maps (merchant, account)
    to Joe's ruling, which is applied in EVERY subsequent run (REQ-FIN-140) -- a label he has to
    reapply is a label he stops giving.
    """
    charges = sorted(charges, key=lambda c: c[0])
    days = [c[0] for c in charges]
    amounts = tuple(float(c[1]) for c in charges)
    n = len(charges)
    if n < EARLY_OCCURRENCES:
        return None

    label = (user_labels or {}).get((merchant, account))
    if label == "not_a_subscription":
        return None                       # REQ-FIN-140, applied before any detection work

    period, period_label, mad = _best_period(days)
    if period is None and label != "is_a_subscription":
        return None
    if period is None:
        period, period_label = 30, "user_asserted"

    behaviour, cp = classify_amounts(amounts)
    if cp:
        cp = dict(cp)
        cp["changed_month"] = days[cp["index"]].strftime("%B %Y")

    # REQ-FIN-139. Same mathematics, different destination.
    routed = "habits" if (category or "").lower() in HABIT_CATEGORIES else "subscriptions"

    return Stream(
        merchant=merchant, account=account, occurrences=n,
        period_days=period, period_label=period_label, interval_mad=float(mad or 0.0),
        amount_behaviour=behaviour, amounts=amounts,
        first_day=days[0], last_day=days[-1],
        # REQ-FIN-130/131. Two occurrences is an early detection, marked as such, so a
        # newly-started subscription is visible before it has run three cycles.
        maturity="mature" if n >= MATURE_OCCURRENCES else "early_detection",
        lifecycle=lifecycle((as_of - days[-1]).days, period, tolerance_days=tolerance_days),
        changepoint=cp, routed_to=routed, user_label=label)


def detect(charges, *, as_of, categories=None, user_labels=None):
    """REQ-FIN-130. Group by (canonical_merchant, account) and build every stream.

    `charges` is a sequence of dicts with merchant, account, day, amount. Streams that lapse or
    cancel are RETURNED, never dropped (REQ-FIN-138): a resurrected subscription is itself
    behavioural data, and deleting the row would make a restart look like a first-ever charge.
    """
    groups: dict = {}
    for c in charges:
        groups.setdefault((c["merchant"], c["account"]), []).append((c["day"], c["amount"]))
    out = []
    for (merchant, account), rows in sorted(groups.items()):
        s = build_stream(merchant, account, rows, as_of=as_of,
                         category=(categories or {}).get(merchant),
                         user_labels=user_labels)
        if s is not None:
            out.append(s)
    return tuple(out)
