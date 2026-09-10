# ADR-0106 — The nutrition source cascade, and the substitution it exists to prevent

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-NUT-012, 013, 014, 015, 016, 024, 036
**Completes:** B12 §D.2/D.3, listed in the checkpoint as explicitly unfinished ("the USDA legs
and the five-step cascade are unwritten"). The USDA *legs* remain blocked on Joe's api.data.gov
key; the cascade itself is not, and is now built and tested.

## Context

`tools/engines/nutrition.py` declared `SOURCE_PRECEDENCE` as a constant and **never used it**.
`resolve_item` performed a single cache lookup and raised `Unresolved` if it missed. The ordering
that the constant described existed only as documentation.

## Decisions

### The order is a claim about knowledge, not about convenience

| rank | source | what it knows |
|---|---|---|
| 1 | `joe` | he measured or entered it — nothing outranks the person who ate it |
| 2 | `usda_branded` | the manufacturer's own label for *this exact product* |
| 3 | `usda_foundation` | a laboratory analysis of the *generic* food |
| 4 | `off_product` | a crowd-sourced label, right far more often than not |

Each step down is a weaker claim about *this* item. Querying all four in parallel and taking
"the best match" would silently prefer whichever source happened to have the tidiest string,
which is a property of the string and not of the food.

### A branded item never falls back to a generic source — the rule that matters most

REQ-NUT-016 in one example: *"Chipotle chicken burrito"* resolving to USDA's generic
*"burrito, chicken"*. This is not a small error. A restaurant portion is routinely **double** the
generic, and **the resulting number looks entirely ordinary** — there is nothing on the plate or
in the row to mark it as wrong.

So a branded query may only be answered by a source that knows brands (`joe`, `usda_branded`,
`off_product`), and when none has it the item stays unresolved with its restaurant token intact
(REQ-NUT-015). **An unresolved item is a question Joe can answer; a plausible wrong number is
not.**

### "Could not find it" and "could not look" are different refusals

If no source was configured — no USDA key, OFF unreachable — every item comes back unresolved for
a reason that has nothing to do with the food. Reporting that as `no_source_match` would hand Joe
a review list of items nothing was ever going to resolve: **an operations failure disguised as a
data gap**, and one he would spend real effort on.

So `no_source_match` is used only when a source was actually asked and did not know the food.
Otherwise the reason is `no_source_available` and `review_reason` is `None` — not Joe's to review.

### A 429 stops that source for an hour, and the cascade continues past it

REQ-NUT-012. A rate limit is the provider saying stop; retrying around it gets the key banned, and
the failure mode of a banned key is *every future item unresolved*. The polite failure is also the
cheap one. The other sources have their own quotas and are unaffected, so the walk continues.

### `labelled` requires a brand owner

REQ-NUT-014. Without it, a labelled figure cannot be re-checked against the product it came from,
and `labelled` becomes a claim about precision with no referent. A branded match missing its brand
owner **raises** rather than resolving — it is a defect in the caller, not a result. Only
`usda_branded` claims `labelled`; a lab analysis of a generic food is not a label, and calling it
one would let a downstream `labelled` filter return figures no manufacturer ever published.

## Why every source is a callable

Each source is a function the caller supplies, so the ordering, the refusals and the brand rules
are **testable with no API key, no socket, and no dependency on Joe's USDA registration**. Sixteen
tests cover the cascade; none of them touches the network.

This also means the USDA legs can be written and dropped in without the cascade changing, and that
a missing key is an ordinary, recorded outcome rather than a crash.

## What remains

The USDA Branded and Foundation *legs* — the actual HTTP clients — are blocked on Joe creating an
api.data.gov key. That is unchanged, and is the only part of B12 §D.2/D.3 still outstanding. Under
RULE-29 that egress target also needs recording before first use.
