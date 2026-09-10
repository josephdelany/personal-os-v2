# ADR-0093 — `spend` answers about a merchant, not a substring

Status: accepted (migration 0059 prepared, NOT applied)
Date: 2026-09-09
Requirements: REQ-FIN-070..074, REQ-ASK-021, RULE-10, RULE-12, INV-4. Closes ADR-0062's hold.

## What changed

Until now `spend` summed transaction atoms whose **statement descriptor** contained the
requested text, and said so in its own answer. That was honest, and it was a floor rather than
a total: a Hannaford charge that settles as `SQ *HANN 8229` is a real charge the substring
never found.

B14 turned 440 raw descriptors into 93 merchant entities and 616 `paid_to` edges, so the
stronger measurement now exists. The subject resolves to a merchant entity first; only when
nothing resolves does the answer fall back to the descriptor match.

## The two are different measurements and the answer says which it performed

A merchant total counts every charge linked to that merchant *however its descriptor read*. A
descriptor match counts strings. Reporting both under one `match_method` would let a reader
assume the stronger one (RULE-12), so the result carries `resolved_merchant` or
`statement_descriptor_contains`.

**The caveat had to change with it, and that is the part worth recording.** The first working
version returned `match_method: resolved_merchant` while its *sentence* still read "merchant
resolution is not built". That combination is worse than either half alone: the prose is what
a reader sees, and it would have understated an answer that had in fact improved. Each path
now states its own real limitation —

- resolved: "charges under any of its descriptors are included; charges whose descriptor is
  still awaiting confirmation are not"
- fallback: "no merchant resolved for this subject, so charges recorded under another
  descriptor are not included"

An existing test asserted the old caveat's literal wording. Its obligation — the descriptor
path must say why a charge could be missing — is unchanged, so the test now asserts the
property rather than the string.

## The edge is read as of the knowledge time

Like the atoms (ADR-0091), a `paid_to` link is filtered on `recorded_at <= known_at`, and a
superseding link only counts once it exists. A merchant resolved next month does not change
the answer to a question asked today, and a human correction takes effect from when it was
made (RULE-10, INV-4).

A consequence worth stating: when a merchant resolves but its links are not yet visible at the
requested knowledge time, the answer is INSUFFICIENT — it does **not** quietly fall back to the
descriptor match, which would have found the charge. Falling back would make a replay return a
number the system could not have produced then.

## Verified against real data

Against production in a rolled-back transaction, with 1,052 backfilled atoms, 93 merchants and
616 links: Hannaford a four-figure total across dozens of charges via `resolved_merchant`; Wal Mart a similar four-figure total across
13; Uber Eats a three-figure total across 25. A subject with no entity — "costco" — correctly falls back and
says so.

## Still open

The 197 descriptors awaiting confirmation are excluded from every merchant total, which the
caveat states. Category-level spend ("how much on groceries") is not implemented:
`config.category_rules` has the shape and no rules, and REQ-FIN-051's exclusion of ATM amounts
from category rollups is enforced only by those atoms carrying no merchant edge.
