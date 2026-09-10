#!/usr/bin/env python3
"""Detect an INSTRUMENT change masquerading as a change in Joe's life.

RULE-05, RULE-06, REQ-NFR-005..014 in spirit; ADR-0096.

THIS PROJECT HAS NOW MADE THE SAME MISTAKE TWICE, IN TWO DOMAINS.

  * Steps. The Watch and the iPhone both recorded whole days until 2026-08-21, when the Watch
    went silent. September averages ~2,200 steps against July's ~3,800. Nothing about Joe's
    walking changed; one of two instruments stopped.
  * Money. `bank_csv` captured 35-46 charges a month, $2,400-3,400, through 2026-05-13 and then
    stopped. `chase_email` took over on 2026-06-20 capturing 9-16 charges a month, $322-462 —
    roughly a third of the transactions and a seventh of the spend. Between them lies a 37-day
    window with no transaction at all.

Both look like a person who suddenly did much less. Both are a capture path changing under a
metric whose name did not. A freshness check cannot see either: after the backfill,
`transaction_amount_usd` is FRESH — its newest row is 2026-09-05 — and that is true and
useless, because freshness asks "did anything arrive" and the question here is "did the same
thing keep arriving".

WHAT IT FLAGS, and what it deliberately does not conclude. A source that stopped, a source that
started, a gap between them, and a rate that changed by more than the threshold across a source
change. It does NOT say the earlier or later figure is correct, and it does not correct
anything: which instrument to trust is a measurement decision (RULE-12) and the answer may be
"neither, the truth is missing". It reports, so that a trend spanning the boundary can be
refused or qualified instead of published.

    PYTHONPATH=. python3 tools/check_source_continuity.py
    PYTHONPATH=. python3 tools/check_source_continuity.py --months 18
"""
import argparse
import collections
import datetime as dt
import sys

from lib import db

RATE_CHANGE = 0.50          # a monthly rate moving by more than half, across a source change
GAP_DAYS = 7                # a silence longer than this between two sources is a hole


def monthly(cur, months):
    """Charges and absolute value per (month, source), from the legacy finance table."""
    cur.execute("""SELECT date_trunc('month', ts)::date, coalesce(source, 'unknown'),
                          count(*), round(sum(abs(amount)), 2)
                     FROM public.transactions
                    WHERE ts >= (now() - make_interval(months => %s)) AND amount IS NOT NULL
                    GROUP BY 1, 2 ORDER BY 1, 2""", (months,))
    return cur.fetchall()


def spans(cur):
    cur.execute("""SELECT coalesce(source, 'unknown'), min(ts)::date, max(ts)::date, count(*)
                     FROM public.transactions GROUP BY 1 ORDER BY 2""")
    return cur.fetchall()


def findings(rows, source_spans):
    out = []
    by_source = collections.defaultdict(list)
    for month, source, n, total in rows:
        by_source[source].append((month, n, float(total or 0)))

    # A source that stopped while another began: the hand-off nobody announced.
    ordered = sorted(source_spans, key=lambda s: s[1])
    for earlier, later in zip(ordered, ordered[1:]):
        gap = (later[1] - earlier[2]).days
        if gap > GAP_DAYS:
            out.append(("gap", f"{earlier[0]} last carried a charge on {earlier[2]}; "
                               f"{later[0]} first carried one on {later[1]} — {gap} days with "
                               f"no transaction from any source"))
        e_rate = earlier[3] / max((earlier[2] - earlier[1]).days, 1) * 30
        l_rate = later[3] / max((later[2] - later[1]).days, 1) * 30
        if e_rate and abs(l_rate - e_rate) / e_rate > RATE_CHANGE:
            direction = "fewer" if l_rate < e_rate else "more"
            out.append(("rate_change",
                        f"{earlier[0]} carried {e_rate:.0f} charges a month; {later[0]} carries "
                        f"{l_rate:.0f} — {direction}, a {abs(l_rate - e_rate) / e_rate:.0%} "
                        f"change across a SOURCE change, not necessarily a change in spending"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    conn = db.connect()
    cur = conn.cursor()
    try:
        rows, source_spans = monthly(cur, a.months), spans(cur)
        print(f"  {'month':<12}{'source':<14}{'charges':>8}{'abs total':>12}")
        for month, source, n, total in rows:
            print(f"  {str(month):<12}{source:<14}{n:>8}{float(total or 0):>12.2f}")
        print(f"\n  {'source':<14}{'first':<12}{'last':<12}{'charges':>8}")
        for source, first, last, n in source_spans:
            print(f"  {source:<14}{str(first):<12}{str(last):<12}{n:>8}")

        found = findings(rows, source_spans)
        if not found:
            print("\nNo source discontinuity detected.")
            return 0
        print(f"\n{len(found)} discontinuity finding(s):")
        for kind, message in found:
            print(f"  [{kind}] {message}")
        print("\nNeither figure is corrected and neither is called wrong. Which instrument to "
              "trust is a measurement decision (RULE-12), and the answer may be 'neither — the "
              "truth for that window was never captured'. A trend spanning the boundary should "
              "be refused or qualified, not published.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
