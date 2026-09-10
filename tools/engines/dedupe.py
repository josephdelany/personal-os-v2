"""B17 §A.4 — dedupe and the two-timestamp rule (REQ-FIN-040..051).

Pure: no database, no clock, no model.

THE PROBLEM. The same purchase arrives up to three times: an alert email at the moment of the
swipe, an API row while it is pending, and a CSV row once it has settled. Each carries a
different amount (a tip lands between pending and posted) and a different date (settlement is
commonly the next day). Treated naively that is one dinner counted three times, at three
different amounts, on two different days.

WHY TWO TIMESTAMPS AND NOT ONE (REQ-FIN-040/041). `occurred_at` is the swipe; `posted_at` is the
settlement. They answer different questions and the layers that read them are disjoint:

  * BEHAVIOURAL analysis reads occurred_at and never posted_at. A Thursday 22:40 bar charge that
    settles on Friday is a Thursday night, and reading posted_at would move every late-week
    evening into the weekend -- manufacturing the weekend pattern the analysis was looking for.
  * RECONCILIATION reads posted_at and never occurred_at, because a balance is about money that
    has actually moved.

REQ-FIN-042 makes the collapse of the two an INGEST rejection rather than a lint, because once
both columns hold the settlement date the swipe time is gone and no later repair can recover it.

WHY 25% AND NOT AN EXACT AMOUNT (REQ-FIN-046). The tip lands between pending and posted, so an
exact-amount key would fail on precisely the transactions this system cares most about -- the
restaurant and bar charges. 25% absorbs a standard tip; the observed delta is recorded in
`tip_delta` so the tolerance can later be calibrated against Joe's own data rather than against
a guess.

WHY AMBIGUITY IS NEVER RESOLVED AUTOMATICALLY (REQ-FIN-047). Two $40 charges at the same
merchant on the same day are commonly two real meals, not one duplicate. Merging them destroys a
transaction; queueing them costs one question.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

AMOUNT_TOLERANCE = 0.25            # REQ-FIN-043/046
DATE_WINDOW_DAYS = 3               # REQ-FIN-043
P2P_WINDOW_HOURS = 72              # REQ-FIN-049
P2P_PROVIDERS = ("venmo", "cash app", "cashapp", "paypal", "zelle")
NETTED_CATEGORIES = frozenset({"bar", "restaurant", "liquor"})   # REQ-FIN-050
ATM_LABEL = "destination unknown"                                # REQ-FIN-051

BEHAVIOURAL_TIMESTAMP = "occurred_at"      # REQ-FIN-041
RECONCILIATION_TIMESTAMP = "posted_at"


class IngestRejected(Exception):
    """REQ-FIN-042. Rejected at ingest, not flagged later: the swipe time is unrecoverable."""


@dataclass
class Canonical:
    id: str
    account: str
    merchant_normalized: str
    amount: float
    occurred_at: dt.datetime
    posted_at: dt.datetime | None = None
    sources: tuple = ()
    tip_delta: float | None = None
    category: str | None = None
    not_same: frozenset = field(default_factory=frozenset)      # REQ-FIN-048


def check_timestamps(row, *, swipe_available):
    """REQ-FIN-042. Writing the settlement date into both columns is an ingest rejection.

    Only when a distinct swipe timestamp WAS available from some source. A CSV row that genuinely
    carries only a date is not a defect -- it is a limitation, handled by the `date_only` flag
    elsewhere -- and rejecting it would refuse the only finance data this system currently has.
    """
    if swipe_available and row.get("occurred_at") == row.get("posted_at"):
        raise IngestRejected(
            f"REQ-FIN-042: source {row.get('source_id')!r} carries a distinct swipe timestamp, "
            f"but the write would put the settlement date in both columns; once collapsed the "
            f"swipe time cannot be recovered")
    return True


def reader_for(layer):
    """REQ-FIN-041. The two layers read disjoint columns, and this is where that is stated."""
    if layer == "behavioural":
        return BEHAVIOURAL_TIMESTAMP
    if layer == "reconciliation":
        return RECONCILIATION_TIMESTAMP
    raise ValueError(f"REQ-FIN-041: unknown layer {layer!r}; there are exactly two")


def candidates(observation, canonicals, *, tolerance=AMOUNT_TOLERANCE,
               window_days=DATE_WINDOW_DAYS):
    """REQ-FIN-043. Match on account, amount within 25%, date within 3 days, merchant equal.

    The tolerance is applied to the EXISTING (pending) amount, per REQ-FIN-046's wording: the tip
    is a fraction of what was authorised, not of what finally settled.
    """
    out = []
    for c in canonicals:
        if c.account != observation["account"]:
            continue
        if c.merchant_normalized != observation["merchant_normalized"]:
            continue
        base = abs(c.amount)
        if base and abs(observation["amount"] - c.amount) > tolerance * base:
            continue
        days = abs((observation["occurred_at"].date() - c.occurred_at.date()).days)
        if days > window_days:
            continue
        out.append(c)
    return tuple(out)


def merge(observation, canonicals, *, review_queue=None):
    """REQ-FIN-044/045/046/047/048. Append the source, or queue the ambiguity.

    Returns the canonical the observation belongs to, or None when it was queued. Nothing is
    merged when more than one candidate matches: two $40 charges at the same merchant on the same
    day are commonly two real meals, and merging destroys a transaction while queueing costs one
    question.
    """
    matches = [c for c in candidates(observation, canonicals)
               # REQ-FIN-048. An adjudication Joe has already made is permanent.
               if observation.get("canonical_hint") not in c.not_same]
    if len(matches) > 1:
        if review_queue is not None:
            review_queue.append({"status": "ambiguous_dedupe",
                                 "candidate_ids": tuple(c.id for c in matches),
                                 "observation": observation.get("source_id"),
                                 "note": ("Two or more canonical transactions match. Merging "
                                          "would destroy one; this asks instead.")})
        return None
    if not matches:
        return None
    c = matches[0]
    c.sources = tuple(c.sources) + (observation["source_id"],)      # REQ-FIN-044
    if observation.get("status") == "posted":
        # REQ-FIN-045. The posted amount and settlement date win; the EARLIEST occurred_at is
        # preserved, because the swipe happened when it happened and settlement does not move it.
        c.tip_delta = round(observation["amount"] - c.amount, 2)    # REQ-FIN-046
        c.amount = observation["amount"]
        c.posted_at = observation.get("posted_at") or observation["occurred_at"]
        c.occurred_at = min(c.occurred_at, observation["occurred_at"])
    return c


def adjudicate_not_same(a, b):
    """REQ-FIN-048. Joe says these are two different purchases. Permanent, both directions."""
    a.not_same = frozenset(a.not_same) | {b.id}
    b.not_same = frozenset(b.not_same) | {a.id}
    return a, b


def link_p2p(inbound, outbound_transactions, *, window_hours=P2P_WINDOW_HOURS):
    """REQ-FIN-049. An inbound P2P receipt near a bar or restaurant charge is a split tab.

    Neither row is deleted. The inbound money is real and the outbound charge is real; what is
    wrong is only the inference that Joe spent the gross. A `transfers` row records the link so
    the netting is auditable rather than baked into an amount.
    """
    if not any(p in (inbound.get("merchant_normalized") or "").lower() for p in P2P_PROVIDERS):
        return ()
    window = dt.timedelta(hours=window_hours)
    return tuple({"inbound_id": inbound["id"], "outbound_id": t.id,
                  "amount": round(float(inbound["amount"]), 2),
                  "hours_apart": round(abs((inbound["occurred_at"] - t.occurred_at)
                                           .total_seconds()) / 3600.0, 1)}
                 for t in outbound_transactions
                 if (t.category or "").lower() in NETTED_CATEGORIES
                 and abs(inbound["occurred_at"] - t.occurred_at) <= window)


def net_of_transfers(transactions, transfers):
    """REQ-FIN-050. Netted AND gross, side by side, never netted silently.

    Showing only the net would hide that a $120 evening happened; showing only the gross would
    claim Joe spent $120 when he spent $40. Both are facts and the pair is the honest answer.
    """
    by_outbound: dict = {}
    for t in transfers:
        by_outbound[t["outbound_id"]] = by_outbound.get(t["outbound_id"], 0.0) + t["amount"]
    gross = sum(float(t.amount) for t in transactions
                if (t.category or "").lower() in NETTED_CATEGORIES)
    reimbursed = sum(by_outbound.get(t.id, 0.0) for t in transactions
                     if (t.category or "").lower() in NETTED_CATEGORIES)
    return {"gross": round(gross, 2), "net": round(gross - reimbursed, 2),
            "reimbursed": round(reimbursed, 2),
            "display": f"{gross - reimbursed:.2f} net of {reimbursed:.2f} reimbursed "
                       f"(gross {gross:.2f})"}


def atm_treatment(transaction):
    """REQ-FIN-051. Labelled everywhere it appears, and excluded from every category rollup.

    Excluded rather than filed under 'cash': filing it would put a real amount under a category
    nobody chose, and the whole point is that the destination is not known. The label travels
    with the row so a surface cannot show the amount without it.
    """
    if not transaction.get("is_atm"):
        return {"label": None, "in_category_rollup": True}
    return {"label": ATM_LABEL, "in_category_rollup": False,
            "note": ("An ATM withdrawal has no known destination. Its amount is excluded from "
                     "every category rollup rather than filed under one nobody chose.")}


def category_rollup(transactions):
    """REQ-FIN-051 applied: ATM amounts never enter a category total, and the exclusion is
    reported so the total can be checked."""
    totals: dict = {}
    excluded = 0.0
    n_excluded = 0
    for t in transactions:
        if t.get("is_atm"):
            excluded += float(t["amount"])
            n_excluded += 1
            continue
        totals[t.get("category")] = round(totals.get(t.get("category"), 0.0)
                                          + float(t["amount"]), 2)
    return {"totals": totals, "excluded_atm_amount": round(excluded, 2),
            "excluded_atm_n": n_excluded,
            "note": (f"{n_excluded} ATM withdrawal(s) totalling {excluded:.2f} are excluded: "
                     f"{ATM_LABEL}.") if n_excluded else ""}
