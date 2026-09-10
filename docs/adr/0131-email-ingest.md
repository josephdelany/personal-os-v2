# ADR-0131 — The alert carries the clock, and nothing later may take it away

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-017, 020..034
**Result:** **REQ-FIN is complete at 173 of 173.** Twelve of fourteen prefixes done.

## The rule the whole section turns on

REQ-FIN-022. **The alert email arrives at the moment of the swipe and carries the clock. The CSV
arrives days later carrying only a date.**

So the alert is the *only* source that will ever know a purchase happened at 22:40, and a
later-arriving observation of the same purchase must not overwrite it. **"More recent" and "more
accurate" are different things, and only one of them is true here.**

This is the same finding that produced §D.1's `occurred_at`/`posted_at` split, arriving from the
ingest side: a Thursday 22:40 bar charge whose time is replaced by a Friday date moves the whole
evening into the weekend.

## Template before model, and why that ordering is not an optimisation

REQ-FIN-024. **A per-sender regex either matches or it does not, and when it does the result is
exact. A model asked to parse the same email will always return something — and what it returns
is plausible whether or not it is right.**

Deterministic first is the difference between a parse that can fail loudly and one that cannot
fail at all.

REQ-FIN-025 is the loud failure: a sender **previously parsed successfully** whose template stops
matching means the bank changed its email format. That is **silent data loss with a clear cause
and a cheap fix — and nothing else in the system will notice it, because the transactions simply
stop appearing.**

REQ-FIN-026 keeps the model's output honest when it does run: `provenance='inferred'` with the
model's own confidence, because **a model-parsed amount and a regex-parsed one are different kinds
of number.**

## The pre-authorisation flag

REQ-FIN-028. **A $50 bar pre-auth commonly settles at $67 after tip.** An alert-derived amount
treated as final understates exactly the category where the gap is largest, **and understates it
in the direction that flatters.**

## Why no provider name may travel downstream

REQ-FIN-030/032/033. Every Tier 3 adapter is optional, free-tier, and liable to be reclassified
out from under this system at any time. **If a provider name reaches past `raw_transactions`, its
disappearance becomes a code change rather than a config change.**

REQ-FIN-033's clause is the load-bearing half: the subsystem stays fully functional with every
Tier 3 adapter disabled. **An adapter that fails open — leaving categorisation or recurrence
detection broken — turns an optional convenience into a single point of failure for the whole
subsystem**, and `on_adapter_error` raises rather than returning if any downstream function is
degraded.

## The credential distinction

REQ-FIN-031/034. **An mTLS client certificate authenticates *this system* to a provider. A bank
login authenticates *Joe* to his bank** — and storing one puts this repository in a different
category of thing entirely. The first is permitted from a GitHub Actions secret; the second, and
any headless browser, is refused.

## Verification

16 tests, no network. Requirements proven 642 → 657 (96%); REQ-FIN 18 unproven → **0**.

Not claimed: nothing is wired to Gmail. The OAuth credential is a standing Joe item, and it gates
*running* this — not the parsing templates, the fallback ordering, the adapter interface or the
credential prohibition, all of which are tested here.
