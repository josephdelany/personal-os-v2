# ADR-0062: Ask's `spend` measures statement descriptors, and says so

## Status
Accepted. Closes the closable part of EXECUTION_PLAN M2's `spend` acceptance item and records
the remainder as held against B14/B17 with the dependency named. Supersedes the placeholder
branch removed in `3077620`.

## Date
2026-09-09

## The conflict, stated once

M2's checklist requires `spend` to meet "agreed merchant/category semantics, currencies,
deduplication, refunds and transfers per finance requirements, totals/counts/typical-week/
top-merchant contract", and adds: *"A descriptor-only partial implementation cannot close the
full contract."*

That is correct, and it cannot be satisfied at M2, because **merchant and category resolution
is a twenty-four-requirement subsystem that does not exist**:

- REQ-FIN-070..074 — the merchant cascade: exact pattern, regex by specificity, fuzzy match at
  a 0.80 `SequenceMatcher` floor, provisional merchants, a review queue, and Joe's
  confirmation writing back into `merchant_patterns`.
- REQ-FIN-080..093 — the categorizer: descriptor-hash memory, merchant-entity category, an MCC
  prior capped at 0.60 confidence, pgvector kNN over Joe's own corrections, a
  confidence-gated model at 0.80, then asking Joe — with `category_embeddings` holding only
  Joe-confirmed labels and kNN routed to review below 100 examples.

None of those tables, engines or thresholds exist. They belong to B14/B17, which
EXECUTION_PLAN schedules at M4.

## Decision

**Ask does not implement merchant resolution.** RULE-12 gives each measure exactly one owner,
and `BACKEND_ARCHITECTURE` states that a second consumer reuses a contract rather than
reimplementing the formula. A substring match written here would become a second, weaker
definition of "spend at a merchant" — and, being the only one that exists, would silently
become the definition.

What `spend` does instead is **measure something narrower and name it exactly**:

> the sum of `transaction` atoms whose **statement descriptor contains** the requested text,
> over the requested range.

That is a well-defined, correct measurement. It is not "spend at merchant X", and the answer
says so in its own sentence — not only in this ADR, because the caveat has to be present at
the moment the number is read:

> Charges matching "mcdonalds" over the last 10 days total 20.75 usd across 2 charges, about
> 14.53 usd a week. This is matched on the statement descriptor; merchant resolution is not
> built, so charges recorded under another descriptor are not included.

A McDonald's charge settling as `SQ *MCD 8005551212 CA` is a real charge this does not find.
**The total is a floor, not a total**, and a test asserts exactly that case.

### Also closed now

- **Currency is checked, not assumed.** More than one unit among the matched atoms refuses
  with `mixed_currency` rather than summing. `transaction_amount_usd` is the only unit B13
  writes, so a second unit means an importer changed and the query is no longer valid.
  Converting here would invent a rate.
- **Outflows and inflows are reported separately and never netted.** REQ-FIN-050 nets inbound
  P2P transfers against bar and restaurant spend, but only through *linked* `transfers` rows.
  Netting an arbitrary refund into a total silently changes what the number means and the
  reader cannot undo it.
- **A weekly rate accompanies the total**, since totals alone do not compare across windows
  of different length.
- **A question with no named subject is refused** rather than searching on the whole question
  text, which would report "no charges" for a question the executor simply could not read.
- **Absent data returns the stored refusal form**, and its `would_raise_it` names the real
  limitation rather than implying the record is empty.

### Held, with the blocking dependency named

| Acceptance case | Blocked on |
|---|---|
| Merchant semantics — resolve `SQ *COFFEE 8005551212 CA` to a merchant entity | REQ-FIN-070..074, B14 |
| Category semantics and category rollups | REQ-FIN-080..093, B14 |
| Top merchants | needs merchant identity; descriptor grouping is not the same list |
| ATM labelled destination-unknown and excluded from rollups (REQ-FIN-051) | needs categorization |
| Canonical-transaction dedupe across alert / pending / posted (REQ-FIN-043..048) | B17 |
| Netting linked inbound transfers (REQ-FIN-050) | needs the `transfers` table, B17 |
| Typical week as a *habit* figure rather than an arithmetic rate | needs §D's occasion counting |

**M2's `spend` item therefore does not close.** It is recorded here as held rather than
marked complete, and rather than rediscovered next session.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Descriptor-scoped and disclosed (adopted)** | Bounded, correct about what it measures, useful the moment real charges exist, and cannot be mistaken for the merchant contract. |
| Refuse `spend` entirely until B14 | Rejected. The measurement is real and answerable; refusing a question the data can answer is its own dishonesty (RULE-18 exists to stop exactly that). |
| Implement a substring "merchant" match and call the contract met | Rejected. It creates a second owner of a B14 measure (RULE-12) and produces a plausible wrong number — the failure mode the whole finance spec is arranged against. |
| Pull B14 forward into M2 | Rejected as a scope decision, not a technical one: it is a twenty-four-requirement subsystem with a review queue and a labelled-example threshold, and EXECUTION_PLAN places it at M4. Recorded here so the sequencing is a decision rather than a drift. |

## Consequences

- `spend` answers usefully as soon as a statement is imported, with its own limits attached.
- When B14 lands, this operation must be **re-pointed at the merchant entity**, and the
  `match_method` field is the marker for that: any stored computation carrying
  `statement_descriptor_contains` predates merchant resolution and must not be compared with
  one that does not.
- No test asserts that descriptor matching *is* merchant matching. The reset's warning
  against writing a test that agrees with an incidental implementation choice applies here
  most sharply, because a passing test would have made the gap invisible.
