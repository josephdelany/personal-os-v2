# ADR-0092 — Merchant entities and `paid_to` links (B14.2, scoped to what has data)

Status: accepted (tooling prepared; depends on unapplied 0057 and the transaction backfill)
Date: 2026-09-09
Requirements: REQ-ONT-005, REQ-FIN-051, REQ-FIN-070..074, RULE-05, RULE-10, RULE-12, INV-1, INV-2.

## What the brief asked for, and why only part of it was built

B14's brief specifies link rules joining transactions to **visits** at **places**, meals to
charges, and workout sets to gyms, with time windows.

Checked before building: `core.entities` holds **0 rows**, and `core.atoms` contains no
`visit`, `consume`, `workout` or (before the backfill) `transaction` atoms. Those rules would
link nothing to nothing. Implementing them would satisfy the brief's checklist and deliver no
capability — the failure INTENT_COVERAGE names outright: *"a table and a linking rule do not
complete this unit."*

So this ADR covers the half with real data on both ends: **1,052 transaction atoms and 93
canonical merchants** resolved from Joe's own descriptors. The place/visit rules are recorded
as pending their inputs, not as done.

## Result against real data

| outcome | atoms |
|---|---|
| linked to a merchant entity | 616 (59%) |
| ATM / transfer / fee — not purchases (REQ-FIN-051) | 239 |
| awaiting Joe's confirmation (REQ-FIN-073) | 197 |
| **total** | **1,052** |

93 merchant entities. `Uber Eats` and `Uber Trip` resolve separately, which is correct — they
are different services under one brand.

## The three rules that make the edges trustworthy

1. **No edge without an identity.** A provisional resolution produces no entity and no link;
   it waits in the review queue. An unlinked transaction is a visible gap, a linked guess is an
   invisible error, and the second is far harder to notice six months later.
2. **No edge for a non-purchase.** An ATM withdrawal's destination is unknown *by definition* —
   the cash went somewhere the bank cannot see — so an edge to a merchant would assert a fact
   that does not exist (REQ-FIN-051).
3. **The edge inherits the cascade's confidence and invents none.** 1.0 from an exact pattern,
   the difflib ratio from a fuzzy match, nothing from a provisional. A fresh edge confidence
   would be a second opinion about one fact (RULE-12), and the weaker number would become
   indistinguishable from the stronger one downstream.

The entity's `provenance` follows RULE-05's vocabulary rather than being uniform: a pattern
match is `extracted` from a rule Joe's data supports; a fuzzy match is `inferred`. Storing both
as `extracted` would erase the distinction the column exists to keep.

## Known imperfection, stated rather than hidden

`Dunkin Q35` retains a residual store code, because the store-number rule requires a `#` and
this descriptor carries the code as a bare token. It means one Dunkin location resolves apart
from the others. It is a normalisation gap, it is visible in the entity list, and it is
tightened by a rule change rather than by editing the entity — entities are append-only.

## Blocked on inputs, not on design

The meal-charge-place links need `visit` and `consume` atoms, which need B15/B17 and the
location pipeline. `public.locations` holds 282 legacy rows and `public.place_book` 7 places,
so the raw material exists but has never been turned into atoms. That is the next dependency,
and it is a capture question, not a linking one.
