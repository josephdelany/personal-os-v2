# ADR-0101 — What the third review changed, and why two rounds missed it

**Status:** accepted
**Date:** 2026-09-10
**Supersedes nothing. Amends:** ADR-0089 (atom panel), ADR-0090/0092 (merchant resolution),
ADR-0097 (strength measures), ADR-0098 (sleep timing).

## Context

Three adversarial reviews have now run against the six unapplied migrations.

| round | findings | caused by the previous round's repairs |
|---|---|---|
| first | 19 | — |
| second | 12 | 10 |
| third | 11 | 2 confirmed, 1 doubly dead |

All three ran against a green suite. The third round's most severe finding was **pre-existing
and untouched by both earlier rounds, which had each edited the very loop it lived in.**

## The decisions

### 1. A non-merchant is a resolution, and the ledger stores it

REQ-FIN-051 classifies ATM withdrawals, internal transfers and bank fees as *not merchants*.
The cascade returned `canonical=None, resolved_by='not_a_merchant', needs_review=False`, and
`entity_aliases` declared `canonical NOT NULL` with no such member in its `resolved_by` CHECK.
The writer commits after its loop and had no exception handling, so **one ATM descriptor rolled
back every pattern, every location token and every alias in the run** — and Joe's data reaches
that path routinely; the tool prints "7 are ATM/transfer/fee" as an ordinary line.

Three options were considered.

- *Skip them.* Loses a real, reusable answer and re-derives it every run.
- *Put the category in `canonical`.* Lets a downstream reader render "internal transfer" as a
  payee. That is INV-5's conflation with a different label on it.
- **Chosen:** `canonical` becomes nullable *only* for this case, paired with a required
  `non_merchant_kind`, enforced by one constraint. Neither "a nameless merchant" nor "an ATM
  called Starbucks" is representable.

The cost is that `canonical` is now nullable and every future consumer must decide whether a
non-merchant appears in merchant reporting at all. OQ-72 records that as Joe's to settle.

### 2. Device precedence bounds exclusion as well as inclusion

The second round excluded a whole night whenever any sleep component segment was unusable,
keyed on `(metric, day)` with **no device predicate** — while the composition itself reads only
the winning device. One truncated iPhone segment therefore deleted ninety minutes of complete
Watch data, and it failed in a way that reads as correct: the components stayed visible, so
"how much core sleep" answered while "how much sleep" went silent for the same night.

The rule is now: **an exclusion may not reach further than the lane it belongs to.** A bad
segment on a device precedence already decided not to read is not an exclusion, because nothing
was excluded.

That repair's comment also claimed the night was "excluded ENTIRELY **and counted**" while
nothing counted it — an anti-join with no counter, no column and no view, leaving an excluded
night indistinguishable from a night that never had data. `analysis.f_composed_exclusions`
now returns the dropped nights with a reason, including the case where *every* device is
unusable and no row is emitted at all.

### 3. RULE-13 is now true rather than asserted

ADR-0097 and 0061's header both claim a method's numbers are "DATA beside it rather than
constants in Python" and that "the windows and the formula set can be changed without a code
change". Nothing read `config.derivation_catalogue.parameters`. `strength.py` hardcoded both.
Changing the table changed no computed figure, and `specs/07-workout/requirements.md` names
"one hardcoded e1RM formula in code" as a **rejected** alternative on exactly that ground.

`strength.apply_catalogue_parameters()` now loads them, and the module stays pure — the rows are
pushed in by whatever holds a connection rather than pulled from inside the engine, so the
arithmetic remains exhaustively testable. An unknown formula name **raises** rather than being
dropped: silently ignoring it would narrow the interval, reporting *more* precision because of a
configuration error.

### 4. Joe's merchant review now changes a resolution

`review_merchants.py` wrote his confirmation to `config.merchant_patterns`; `build()` constructed
its pattern list purely from discovered forms and never read that table. `resolve()`'s
`human_alias` parameter — cascade step 1, "the answer, and it outranks every rule permanently" —
had exactly one caller in the repository, and it was a test.

So RULE-10's guarantee was enforced by a trigger on a table nothing wrote to and nothing read,
and the review sheet with 157 descriptors needing names terminated in a write nobody consumed.
Confirmation now writes the alias ledger as well, and the resolver reads both.

## The consequence worth carrying

Every defect above sat under a passing suite, and three sat under a test written to catch them:

- Two tests **read `resolve_merchants.py` as text** and grepped it for string literals. A crash
  on ordinary bank input passed them for a full round. Both also took a live-schema fixture and
  never used it, so they *skipped* in CI while looking like database tests.
- The catalogue-preservation test grepped `build_catalogue.py` for three literals. The code it
  described was a no-op for **100%** of the rows it was written to protect — and called
  `json.dumps` in a module that does not import `json`, so it would have raised `NameError` had
  it ever executed. Two defects hiding each other.
- 0061 was applied by **no pytest at all**; its two tests read the migration as text.

All are now tests that run the code, and each was verified to **fail against the old version**
before being accepted. That verification caught one of my own regression edits silently not
matching, which would have let me report a vacuous pass.

**A test that reads source text asserts what the code says, not what it does.** Three rounds of
review found thirty-one defects; the ones that survived longest were the ones with a test
already pointing at them.
