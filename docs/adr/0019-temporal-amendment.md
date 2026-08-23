# ADR-0019: Temporal amendment to ADR-0002 — intervals, transaction time, stored subject_day

## Status

Accepted (amends ADR-0002; amends RULE-03). Resolves OQ-06.

## Date

2026-08-23

## Context

ADR-0002 gave the atom four time columns: `occurred_at`, `recorded_at`,
`time_precision`, and a **generated** `subject_day` on a 04:00 local boundary.
Phase-2 planning (`docs/PHASE2_MIGRATION_PLAN.md`, Decision 5) found three gaps,
each non-retrofittable:

1. **Durational facts have no home.** A 45-minute workout, an 8-hour sleep, a
   screen session have a genuine start *and* end. `occurred_at`+`time_precision`
   describes an instant; a single instant cannot hold both ends. Turning *every*
   `occurred_at` into a range, by contrast, buys nothing for point events (a meal,
   a card swipe) and merely duplicates `time_precision`.
2. **"What did we believe on date D" is a `supersedes`-chain walk.** ADR-0002 has
   `recorded_at`+`supersedes` but no cheap way to ask which row was current at a
   past instant.
3. **A generated `subject_day` cannot express the rule Joe actually wants.** The
   04:00 boundary is assigned *by start instant* — except **sleep**, which is
   assigned to the day it *ends* (the wake date), matching both sleep-research
   convention and how Joe speaks ("last night's sleep" is this morning's). A
   generated column sees only one row's columns and cannot encode "by start
   except sleep by end" (it needs the atom's kind and its interval end).

## Decision

Amend the atom's temporal model (Joe's ruling, 2026-08-23):

- **Point events:** `occurred_at` (instant) + `time_precision`. `valid_interval`
  is NULL.
- **Durational atoms** (workout, sleep, screen session): `valid_interval
  tstzrange`, with a GiST index (btree_gist installed) so overlap (`&&`) analyses
  are exact. No overlap-*forbidding* constraint — overlapping atoms are legitimate
  (a meal during a workout).
- **Transaction time:** `recorded_at` (system-set at INSERT, never client-set —
  forced by a BEFORE INSERT trigger) anchors when the system learned the fact.
  Currency ("what do we currently believe") is **DERIVED from the supersedes
  graph** via the `atoms_current` view — a row is current iff nothing supersedes
  it.

  **CORRECTION discovered in implementation (2026-08-23), RATIFIED BY JOE the same
  day — resolution (a), derive.** The ruling as first recorded said "add `expired_at` (NULL =
  currently believed), so belief-as-of-D is one indexed range predicate over
  `[recorded_at, expired_at)`." Implementation found this **conflicts with INV-2 /
  RULE-02**: a stored `expired_at` would have to be *stamped onto the old row* when
  a correction supersedes it — an UPDATE, which INV-2 forbids ("never UPDATE") and
  the append-only trigger blocks. The constitution is explicit that a mechanism
  violating an invariant is rejected, so the invariant wins: `expired_at` is **not
  stored**; currency is derived from `supersedes`. The intent (cheap point-in-time
  belief) is preserved via the view/function, at the cost of the single-column
  index. **Two resolutions were possible; Joe ruled (a) on 2026-08-23:** (a) derive,
  as implemented here (keeps INV-2 absolute); (b) a narrow "supersession-seal"
  exception permitting a one-time UPDATE of only `expired_at` (would weaken INV-2's
  "never UPDATE" — rejected). Resolution (a) stands.
- **`subject_day` becomes application-computed and STORED**, not generated, and
  carries **`subject_day_rule_version`**. The rule: 04:00 local boundary, assigned
  by **start instant**, **except sleep atoms, assigned to the wake day**. Storing
  the rule version means a future change to the boundary rule is visible in the
  data, not a silent rewrite.

Postgres facts settling the mechanism (verified on the live instance,
PG 17.6): `temporal_tables`/`periods` extensions are absent and system versioning
is not in PG18/19, so transaction time is rolled by hand
(`recorded_at` + `supersedes`, currency derived — see the correction above).
`btree_gist` is installable and installed by the migration. Temporal PKs (`WITHOUT OVERLAPS`) shipped in **PG18**, not PG19; PG19
adds `FOR PORTION OF` and is still beta — neither is on Supabase, so DIY is the
only option, not a preference.

## Consequences

**Good.** Durational facts are first-class; overlap analysis is exact; point-in-
time belief is one range predicate; the subject-day rule is versioned and
auditable. Migration to native temporal features later is mechanical because the
range column already exists.

**Bad / transient.** Until this ADR's migration lands, RULE-03, ADR-0002 and this
record describe `subject_day` differently (generated vs stored) — a known,
flagged inconsistency, not a hidden one. RULE-00 is not in play: nothing is
weakened; a director-ruled amendment is recorded before the code, which is the
correct order.

**Enforcement.** `core.atoms` CHECK requires `occurred_at IS NOT NULL OR
valid_interval IS NOT NULL`; `subject_day` and `subject_day_rule_version` are NOT
NULL; the application computes them (RULE-13: the model never selects the temporal
specification).

## Alternatives considered

- **Blanket `tstzrange` for every `occurred_at`.** Rejected: machinery with no
  benefit for point events, and it duplicates `time_precision`.
- **Scalars only, no range.** Rejected: durational facts genuinely need two ends.
- **Keep `subject_day` generated with a plain by-start rule.** Rejected: cannot
  encode the sleep carve-out Joe requires.
