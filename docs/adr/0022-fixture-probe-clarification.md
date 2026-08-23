# ADR-0022: RULE-01 clarification — the rolled-back constraint probe

## Status

Accepted

## Date

2026-08-23

## Context

The Phase-2 spine ships INSERT-path guarantees that a rejection on an empty table
cannot reach: the `atoms` value/presence/lane CHECKs (RULE-05/07/08), the
`force_recorded_at` trigger that overrides a client-supplied `recorded_at`
(ADR-0002/ADR-0019), the `predictions` binary/continuous XOR (ADR-0021), and the
`hypothesis_register` freeze trigger's *legitimate* status-only-UPDATE path
(REQ-INF-103). The append-only *rejection* paths were proven behaviourally last
session with no fabricated row — a privilege/trigger denial fires on an empty
table. The *acceptance and coercion* paths cannot: proving that a legitimate row
is accepted, or that a bad recorded_at is silently corrected, requires an actual
INSERT.

RULE-01 forbids "placeholder, synthetic, sample, or example rows in any table, in
any environment, for any reason including testing," and says fixtures "never touch
a real table." Read literally, that blocks the only way to prove these
constraints — so they were verified **structurally only** (constraint/trigger
definitions present in the catalog), never behaviourally. That gap was raised as
OQ-21 by the session-end reviewer, 2026-08-23. This is the single largest untested
surface in the spine.

## Decision

RULE-01 is **clarified**, not weakened. A behavioural test MAY probe an
INSERT-path constraint under all of the following conditions, together:

1. It creates a **disposable schema** — never `core`, never `public`. The
   existing test harness already does this: `run_migration.apply(cur, "core_pytest",
   "ops_pytest")` builds a throwaway schema pair carrying the identical DDL.
2. It runs inside **one transaction that is rolled back**. Nothing is ever
   committed; the schema and every fixture row vanish when the transaction ends.
   (`tests/test_spine_invariants.py::spine_cursor` already rolls back in its
   `finally`.)
3. No fixture row is **ever read as data** by anything outside the test — it
   exists only to be accepted or rejected by the constraint under test, then
   discarded.

Anything that survives the transaction, or lands in `core`/`public`, or is read as
if it were a real observation, is fabrication and stays forbidden. The clarifying
text was added to RULE-01 in `docs/CONSTITUTION.md` and to the `<no_fabrication>`
block in `CLAUDE.md` the same day.

## Why this is a clarification, not a weakening (RULE-00)

RULE-01 exists because a plausible fake number that persists is invisible and
corrupts every downstream figure (the July 2025 4,000-fabricated-rows incident).
A rolled-back row in a disposable schema persists nowhere, is read as data
nowhere, and influences no figure — it is the opposite of the failure RULE-01
guards against. The rejection-path proofs from last session and these
acceptance-path proofs use the same disposable-schema-then-rollback mechanism; the
only new thing is that a row is briefly INSERTed inside the doomed transaction.
Nothing that RULE-01 protects is exposed. RULE-00 is therefore not in play; this
is a scope clarification recorded before the code that relies on it, which is the
correct order.

## Consequences

**Good.** The INSERT-path constraints become behaviourally proven, closing OQ-21.
The "legitimate `observed_absent` row" and "valid-interval-only nutrition estimate"
that RULE-07/RULE-08 promise can be *shown* to insert, not merely asserted to be
allowed by inspection of a CHECK.

**Bad / bounded.** The disposable schema is created on the live instance (there is
no second engine — the point of the harness is to test against the real PG 17.6).
The safety rests entirely on the rollback and on the schema name never being
`core`/`public`. A test that committed by mistake would leave a throwaway schema
behind; the mitigation is that the fixture uses `conn.rollback()` in `finally` and
never calls `conn.commit()`, and the schema name is a constant that is not `core`.

## Alternatives considered

- **Mirror the DDL into `tests/fixtures/` fixture tables (OQ-21 option b).**
  Rejected: the fixture DDL would drift from the real migration, so a test could
  pass against a stale copy of a constraint that the real table no longer carries —
  proving the wrong thing. Applying the *actual* migration to a disposable schema
  cannot drift.
- **Accept structural-only verification (OQ-21 option c).** Rejected: "the CHECK
  is present in the catalog" does not prove the CHECK does what its text says, and
  the whole project's stance (CLAUDE.md preamble) is that a thing is not proven
  because someone says so.
- **A separate throwaway database.** Rejected: same engine/extension guarantees
  are only free on the live instance; a rolled-back transaction on it is a
  stricter copy than a second database that could diverge in version or extensions
  (the same reasoning as `run_migration.py`'s dry run).
