"""Detect an instrument change masquerading as a change in Joe's life (ADR-0096).

The rule this encodes has been violated twice in two domains: the Watch going silent made
September look like 40% less walking, and `bank_csv` handing over to `chase_email` made summer
look like 85% less spending. Both are a capture path changing under a metric whose name did
not, and a freshness check sees neither — freshness asks "did anything arrive", and the
question here is "did the same thing keep arriving".
"""
import datetime as dt

from tools.check_source_continuity import GAP_DAYS, RATE_CHANGE, findings


def span(source, first, last, n):
    return (source, dt.date.fromisoformat(first), dt.date.fromisoformat(last), n)


def test_RULE_06_a_handover_gap_is_reported_as_a_hole_not_as_zero_spending():
    """38 days with no transaction from any source is missing data, not a frugal month."""
    found = findings([], [span("bank_csv", "2024-05-15", "2026-05-13", 1011),
                          span("chase_email", "2026-06-20", "2026-09-05", 41)])
    kinds = {k for k, _ in found}
    assert "gap" in kinds
    gap = next(m for k, m in found if k == "gap")
    assert "38 days" in gap and "no transaction from any source" in gap


def test_RULE_12_a_rate_change_across_a_source_change_is_flagged_not_corrected():
    """The tool must not decide which instrument is right. It may be neither: the truth for
    that window was never captured, and asserting either number would manufacture one."""
    found = findings([], [span("bank_csv", "2024-05-15", "2026-05-13", 1011),
                          span("chase_email", "2026-06-20", "2026-09-05", 41)])
    rate = next(m for k, m in found if k == "rate_change")
    assert "not necessarily a change in spending" in rate
    assert "fewer" in rate


def test_RULE_06_one_continuous_source_raises_nothing():
    """A detector that fires on healthy data is noise, and noise gets ignored precisely when
    it matters."""
    assert findings([], [span("bank_csv", "2024-05-15", "2026-09-05", 1500)]) == []


def test_RULE_06_a_clean_handover_with_a_steady_rate_raises_no_rate_finding():
    """A source swap is not itself a problem. Only a swap that CHANGES what arrives is."""
    found = findings([], [span("old", "2026-01-01", "2026-06-30", 180),
                          span("new", "2026-07-01", "2026-09-30", 92)])
    assert not any(k == "rate_change" for k, _ in found), found
    assert not any(k == "gap" for k, _ in found), "a same-day handover is not a gap"


def test_the_thresholds_are_stated_and_not_incidental():
    assert 0 < RATE_CHANGE < 1, "a rate threshold above 1 could never fire on a decline"
    assert GAP_DAYS >= 1
