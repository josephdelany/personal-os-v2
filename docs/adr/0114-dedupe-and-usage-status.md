# ADR-0114 — Two timestamps, three tiers

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-040..051 (§A.4), REQ-FIN-110..116 (§C.1)
**Implements:** B17 §A.4 and §C.1. Fifteen previously-unproven requirements.

## §A.4 — the same purchase, three times

An alert email at the swipe, an API row while pending, a CSV row once settled. Each carries a
different amount (the tip lands between pending and posted) and a different date (settlement is
commonly the next day). Treated naively that is **one dinner counted three times, at three
amounts, on two days**.

### Two timestamps, and two layers that must not share them

`occurred_at` is the swipe; `posted_at` is the settlement. The layers reading them are disjoint
(REQ-FIN-041):

- **Behavioural** analysis reads `occurred_at` only. A Thursday 22:40 bar charge that settles on
  Friday is a Thursday night, and reading `posted_at` would move every late-week evening into the
  weekend — **manufacturing the weekend pattern the analysis was looking for.**
- **Reconciliation** reads `posted_at` only, because a balance is about money that has moved.

REQ-FIN-042 makes collapsing the two an **ingest rejection**, not a lint. Once both columns hold
the settlement date the swipe time is gone and no later repair recovers it. But the rejection
fires only when a distinct swipe timestamp *was* available: a CSV row that genuinely carries only
a date is a limitation, not a defect, and rejecting it would refuse the only finance data this
system currently has.

### 25%, and why not an exact amount

The tip lands between pending and posted, so an exact-amount key would fail on **precisely the
transactions this system cares most about** — restaurants and bars. 25% absorbs a standard tip,
and the observed delta is recorded in `tip_delta` so the tolerance can later be calibrated
against Joe's own data rather than against a guess.

### Ambiguity is never resolved automatically

Two $40 charges at the same merchant on the same day are commonly **two real meals, not one
duplicate**. Merging destroys a transaction; queueing costs one question. So more than one
candidate means nothing is touched and a `review_queue` row is written.

### Split tabs are linked, not netted away

An inbound P2P receipt within 72 hours of a bar charge writes a `transfers` row and **deletes
nothing** (REQ-FIN-049). The inbound money is real and the outbound charge is real; what is wrong
is only the inference that Joe spent the gross.

`net_of_transfers` therefore returns **both** figures. Showing only the net hides that a $120
evening happened; showing only the gross claims Joe spent $120 when he spent $40. Both are facts,
and the pair is the honest answer.

### ATM withdrawals are excluded, not filed under "cash"

Filing them would put a real amount under a category nobody chose, and the whole point is that
**the destination is not known**. The rollup reports what it excluded so the total can be checked.

## §C.1 — necessity is a tier, not a fact

Whether a purchase was worth making is not a fact this system can observe, so it does not model
one. What it can observe is whether the thing has been **used**, and even that has three states.

**Three tiers, not a boolean** (REQ-FIN-110). A boolean forces every purchase into used-or-not,
and the overwhelming majority are neither — there is simply no evidence either way. **Collapsing
`unknown` into `unused` is what turns a system that lacks data into a system that accuses.**

The same argument rules out a score: *"68% used"* is a number with no referent — there is nothing
it is 68% of — and it would be read as a judgement with decimal places.

**The default is `unknown` and moves only on evidence** (REQ-FIN-111). A gym membership with no
`place_visit` rows is not an unused gym membership; it is one about which nothing is recorded.

**A bare label is refused** (REQ-FIN-113). *"Unused"* alone is an accusation. *"Last gym
place_visit 71 days ago"* is a fact Joe can confirm, correct or explain — and that difference is
the difference between a system he argues with and one he trusts.

**The five words are banned on write, not filtered on display** (REQ-FIN-112). A stored word
leaks into an export or a prompt later, so `guard_words` runs inside the dataclass constructor.

**Confidence falls with the age of the evidence.** A visit yesterday says more about today than
one eleven weeks ago, and reporting both at the same confidence would flatten that.

### One thing deliberately not decided

REQ-FIN-114 says in its own text that how the spine represents a **direct human override** is
*"a modeling decision for Joe, not a spelling reconciliation"* — recorded as **OQ-32**, still
open. So `UsageStatus` accepts `inferred` and `joe` and **raises on any third provenance, naming
OQ-32 in the message**, rather than inventing a representation that would then be load-bearing.

## Verification

30 tests. Requirements proven 335 → 350 (51%); REQ-FIN unproven 51 → 36. Nothing is wired to real
data.
