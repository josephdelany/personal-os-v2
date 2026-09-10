"""B17 §A.4 — dedupe and the two-timestamp rule (REQ-FIN-040..051).

The same purchase arrives up to three times — alert, pending, posted — at three amounts and on
two dates. Treated naively that is one dinner counted three times.
"""
import datetime as dt

import pytest

from tools.engines.dedupe import (AMOUNT_TOLERANCE, ATM_LABEL, Canonical, DATE_WINDOW_DAYS,
                                  IngestRejected, P2P_WINDOW_HOURS, adjudicate_not_same,
                                  atm_treatment, candidates, category_rollup, check_timestamps,
                                  link_p2p, merge, net_of_transfers, reader_for)

SWIPE = dt.datetime(2026, 9, 3, 22, 40)          # a Thursday night
SETTLE = dt.datetime(2026, 9, 4, 9, 0)           # settles Friday


def canonical(**kw):
    base = dict(id="c1", account="visa", merchant_normalized="JOES BAR", amount=40.0,
                occurred_at=SWIPE, category="bar")
    base.update(kw)
    return Canonical(**base)


def obs(**kw):
    base = dict(source_id="s2", account="visa", merchant_normalized="JOES BAR", amount=48.0,
                occurred_at=SWIPE, status="posted", posted_at=SETTLE)
    base.update(kw)
    return base


def test_REQ_FIN_041_the_two_layers_read_disjoint_columns():
    """A Thursday 22:40 bar charge settling Friday is a Thursday night. Reading posted_at would
    move every late-week evening into the weekend."""
    assert reader_for("behavioural") == "occurred_at"
    assert reader_for("reconciliation") == "posted_at"
    with pytest.raises(ValueError, match="REQ-FIN-041"):
        reader_for("both")


def test_REQ_FIN_042_collapsing_the_two_timestamps_is_rejected_at_ingest():
    """Rejected at ingest rather than flagged later: once both columns hold the settlement date
    the swipe time is gone and no repair can recover it."""
    with pytest.raises(IngestRejected, match="REQ-FIN-042"):
        check_timestamps({"source_id": "alert-1", "occurred_at": SETTLE, "posted_at": SETTLE},
                         swipe_available=True)
    assert check_timestamps({"occurred_at": SWIPE, "posted_at": SETTLE}, swipe_available=True)


def test_REQ_FIN_042_a_csv_row_with_only_a_date_is_a_limitation_not_a_defect():
    """Rejecting it would refuse the only finance data this system currently has."""
    assert check_timestamps({"occurred_at": SETTLE, "posted_at": SETTLE}, swipe_available=False)


def test_REQ_FIN_043_046_the_amount_tolerance_absorbs_a_tip():
    """An exact-amount key would fail on precisely the transactions this system cares most
    about — the restaurant and bar charges, where the tip lands between pending and posted."""
    assert AMOUNT_TOLERANCE == 0.25
    c = canonical(amount=40.0)
    assert candidates(obs(amount=48.0), [c]) == (c,), "a 20% tip still matches"
    assert candidates(obs(amount=51.0), [c]) == (), "beyond 25% it is a different charge"


def test_REQ_FIN_043_the_date_window_is_three_days():
    c = canonical()
    assert candidates(obs(occurred_at=SWIPE + dt.timedelta(days=DATE_WINDOW_DAYS)), [c]) == (c,)
    assert candidates(obs(occurred_at=SWIPE + dt.timedelta(days=DATE_WINDOW_DAYS + 1)), [c]) == ()


def test_REQ_FIN_043_a_different_merchant_or_account_never_matches():
    c = canonical()
    assert candidates(obs(merchant_normalized="OTHER BAR"), [c]) == ()
    assert candidates(obs(account="amex"), [c]) == ()


def test_REQ_FIN_044_045_046_a_posted_observation_supersedes_and_preserves_the_swipe():
    c = canonical(amount=40.0, sources=("s1",))
    merged = merge(obs(amount=48.0), [c])
    assert merged is c, "no second canonical transaction is created"
    assert merged.sources == ("s1", "s2")
    assert merged.amount == 48.0, "the posted amount wins"
    assert merged.posted_at == SETTLE
    assert merged.occurred_at == SWIPE, "the swipe happened when it happened"
    assert merged.tip_delta == 8.0, "recorded for later calibration"


def test_REQ_FIN_047_two_candidates_are_queued_and_nothing_is_merged():
    """Two $40 charges at the same merchant on the same day are commonly two real meals.
    Merging destroys a transaction; queueing costs one question."""
    a, b = canonical(id="c1"), canonical(id="c2")
    queue = []
    assert merge(obs(), [a, b], review_queue=queue) is None
    assert queue[0]["status"] == "ambiguous_dedupe"
    assert set(queue[0]["candidate_ids"]) == {"c1", "c2"}
    assert a.sources == () and b.sources == (), "nothing was touched"


def test_REQ_FIN_048_a_not_same_adjudication_is_permanent_and_bidirectional():
    a, b = canonical(id="c1"), canonical(id="c2")
    adjudicate_not_same(a, b)
    assert "c2" in a.not_same and "c1" in b.not_same
    # With the adjudication recorded, an observation hinting at c2 no longer matches c1.
    queue = []
    merge(obs(canonical_hint="c2"), [a], review_queue=queue)
    assert a.sources == ()


def test_REQ_FIN_049_an_inbound_p2p_receipt_near_a_bar_charge_is_linked_not_deleted():
    """The inbound money is real and the outbound charge is real. What is wrong is only the
    inference that Joe spent the gross."""
    bar = canonical(id="t1", amount=120.0, category="bar")
    inbound = {"id": "p1", "merchant_normalized": "VENMO PAYMENT",
               "occurred_at": SWIPE + dt.timedelta(hours=14), "amount": 40.0}
    links = link_p2p(inbound, [bar])
    assert links[0]["outbound_id"] == "t1" and links[0]["amount"] == 40.0
    assert links[0]["hours_apart"] == 14.0


def test_REQ_FIN_049_outside_seventy_two_hours_or_a_non_bar_merchant_there_is_no_link():
    bar = canonical(id="t1", category="bar")
    far = {"id": "p1", "merchant_normalized": "VENMO",
           "occurred_at": SWIPE + dt.timedelta(hours=P2P_WINDOW_HOURS + 1), "amount": 40.0}
    assert link_p2p(far, [bar]) == ()
    groceries = canonical(id="t2", category="groceries")
    near = {"id": "p2", "merchant_normalized": "VENMO", "occurred_at": SWIPE, "amount": 40.0}
    assert link_p2p(near, [groceries]) == ()


def test_REQ_FIN_049_a_non_p2p_inbound_row_is_not_a_split_tab():
    assert link_p2p({"id": "x", "merchant_normalized": "PAYROLL", "occurred_at": SWIPE,
                     "amount": 2000.0}, [canonical(category="bar")]) == ()


def test_REQ_FIN_050_the_net_and_the_gross_are_shown_together():
    """Showing only the net would hide that a $120 evening happened; showing only the gross would
    claim Joe spent $120 when he spent $40. Both are facts."""
    bar = canonical(id="t1", amount=120.0, category="bar")
    out = net_of_transfers([bar], [{"outbound_id": "t1", "amount": 80.0}])
    assert out["gross"] == 120.0 and out["net"] == 40.0 and out["reimbursed"] == 80.0
    assert "net of 80.00 reimbursed" in out["display"] and "gross 120.00" in out["display"]


def test_REQ_FIN_051_an_atm_withdrawal_is_labelled_and_excluded_from_every_rollup():
    """Excluded rather than filed under 'cash': filing it would put a real amount under a
    category nobody chose, and the point is that the destination is not known."""
    t = atm_treatment({"is_atm": True})
    assert t["label"] == ATM_LABEL and t["in_category_rollup"] is False
    assert atm_treatment({"is_atm": False})["in_category_rollup"] is True


def test_REQ_FIN_051_the_rollup_reports_what_it_excluded_so_the_total_can_be_checked():
    rows = [{"category": "dining", "amount": 40.0},
            {"category": "dining", "amount": 20.0},
            {"category": None, "amount": 200.0, "is_atm": True}]
    out = category_rollup(rows)
    assert out["totals"] == {"dining": 60.0}
    assert out["excluded_atm_amount"] == 200.0 and out["excluded_atm_n"] == 1
    assert ATM_LABEL in out["note"]
