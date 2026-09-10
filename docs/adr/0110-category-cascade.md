# ADR-0110 — The categorisation cascade: why the order is the whole design

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-FIN-080..093 (§B.3), REQ-FIN-100..106 (§B.4)
**Implements:** B17 §B.3 and §B.4. Twenty-one requirements, none previously proven.

## Context

`tools/engines/categorise.py` existed and did something different: a majority-vote assigner over
observed category strings. The six-layer cascade §B.3 specifies was unwritten.

## Why the order is the requirement, not an implementation detail

| # | layer | what it knows |
|---|---|---|
| 1 | `hash` | this exact descriptor, already confirmed by Joe — certain |
| 2 | `merchant` | the merchant's default category |
| 3 | `mcc` | the acquirer's code — a weak prior, capped, never ground truth |
| 4 | `knn` | Joe's own corrected history, nearest five |
| 5 | `llm` | a guess, admitted only above 0.80 |
| 6 | `ask` | Joe |

Run in any other order this is a different system. **The LLM is cheap and fluent and will answer
every question put to it**, so a cascade that reaches for it early produces a fully-categorised
ledger that is 60% right — REQ-FIN-089's own figure for zero-shot accuracy. A ledger with no gaps
and a sixth of its rows wrong is worse than one with visible gaps, because nothing marks the wrong
rows.

REQ-FIN-091 is therefore enforced as an **explicit check that raises**, not merely by the LLM
being last in a list. A list can be reordered by a future edit; this is the one ordering whose
violation is invisible in the output.

## The judgements

**MCC is capped at 0.60 by the cascade, not by the layer.** The layer is supplied by the caller,
so trusting it to cap itself would put the ceiling outside the module that owes it. The reason for
the cap is specific: the same business codes differently across cards and departments, and **5812
(Eating Places) versus 5813 (Drinking Places) is set by the acquirer** — the exact distinction
every alcohol figure in this system depends on. A code chosen by a payment processor for its own
reasons cannot decide whether a charge was dinner or drinking.

**A missing layer abstains.** That is how REQ-FIN-084 is satisfied without a special case: MCC is
absent from CSV exports, alert emails and OFX alike, and absent is the normal case rather than an
error.

**`NeedsReview` has no `category` field at all.** REQ-FIN-090 forbids displaying a below-threshold
guess anywhere. A field holding the rejected guess is a field a renderer eventually reads "just to
show something", so the only reliable way to honour the rule is not to carry the value. A test
asserts the attribute does not exist and that the guessed string does not appear in the object's
repr.

**The kNN tie breaks on distance, not the alphabet.** Breaking on the category name would make the
answer depend on spelling.

**Below 100 confirmed examples the kNN layer still votes, and its vote goes to review.** The ~95%
accuracy figure is reported at roughly 100 labelled examples; below that the number is not
claimed, and borrowing it would cite a result the study did not produce.

**The prompt is an allowlist, built in one place.** A banlist has to anticipate every future
field, and the one it misses is the one that leaks. A caller wanting to add a field has to edit
`build_llm_prompt`, which is a visible change, rather than pass an extra key nobody notices.

**The taxonomy cap is a behavioural intervention, not tidiness.** Field Study 5 (n=251) found that
fragmenting spend into sub-categories *increased* total spending through mental-accounting
justification. So 25 leaves is enforced with a raise, not recommended in a comment.

## The correction loop

`apply_correction` **returns** the writes rather than performing them. That keeps the module pure,
and it makes REQ-FIN-102's "in the same transaction" a property a caller can be tested against
rather than a claim in a docstring.

REQ-FIN-103's propagation skips siblings whose `category_source` is already `user`: **Joe's earlier
decision on a specific row outranks the propagation of his later decision on the descriptor.**
Propagated rows are marked `user_propagated` so the two are distinguishable afterwards.

**A suspended layer (REQ-FIN-105) is still consulted**, with its answer routed to review rather
than auto-applied. Silencing it entirely would lose the signal that it has started working again.
Suspension also requires a full 50-item window — a layer suspended on three samples is a
capability lost to noise.

**REQ-FIN-104 exists because the aggregate hides the fault.** A categoriser that has quietly
become wrong presents as one that is fine unless the tally is per layer.

**REQ-FIN-106 orders by amount rather than date** and caps at 20, so a backlog of 400 is still a
twenty-minute job rather than a reason never to open the queue.

## Verification

24 tests, no network, no embeddings, no model. Every layer is a stub, so what is tested is the
cascade's own behaviour rather than a vendor's.

`tools/engines/categorise.py` is untouched and still serves the merchant-category population path
it was written for; the two do not yet meet. Wiring the cascade to real layers — a real embedding
store, a real model call — is separate work and is not claimed here.
