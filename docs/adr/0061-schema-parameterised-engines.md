# ADR-0061: The analysis engines take their schema names as parameters

## Status
Accepted. Resolves **OQ-52** without amending RULE-01. Changes `tools/engines/panel.py` and
`tools/check_freshness.py`; no migration, no deployed behaviour change.

## Date
2026-09-09

## Context

RULE-01's bounded exception permits a behavioural test to build a **disposable schema** and
says, in as many words, "never `core`, never `public`".

`panel.build` and `check_freshness.check` named `core`, `analysis` and `public` as string
literals. Proving their behaviour therefore meant creating schemas with exactly those names,
which the rule forbids. The first response to that was a docstring arguing that a temporary
PostgreSQL instance is a *stronger* isolation posture than a rolled-back transaction against
the real database, plus an `assert_disposable_server` guard checking the server's
`data_directory` sat under a temp root.

The adversarial review's objection was correct and is the reason this ADR exists:

> Both files' docstrings argue that a disposable server is a stronger isolation posture than a
> rolled-back transaction in a named schema. That argument may well be correct, but RULE-01's
> carve-out was widened by a docstring, not by an ADR amendment.

**A rule that can be widened by a comment is not a rule.** The argument may have been sound;
the process was not, and the process is the whole mechanism by which an integrity rule stays
worth anything.

## Decision

**Parameterise the engines instead of amending the rule.**

`panel.build(cur, schemas=None)` and `check_freshness.check(cur, schema, analysis)` take their
schema names as arguments, defaulting to the production names. The migrations have always
worked this way — `__CORE__` and `__OPS__` are substituted by the runner — so this makes the
engines consistent with the layer beneath them rather than introducing a new idea.

Names are interpolated, because an identifier cannot be a bind parameter, so each is validated
against `^[a-z_][a-z0-9_]*$` and an unknown schema role is rejected outright.

Consequences:

- Every test schema is now a throwaway name (`core_fresh_pytest`, `analysis_panel_pytest`,
  `public_panel_pytest`). **No test creates a schema called `core`, `analysis` or `public`.**
- RULE-01 is untouched. The question was whether to widen a constitutional rule; the answer was
  that the rule was right and the code was wrong.
- `assert_disposable_server` was **deleted**, not kept "just in case". It was a compensating
  control for a problem that no longer exists, and a guard that guards nothing is the same
  shape as the dead range-check this same session already had to answer for — a green thing
  that looks like enforcement and enforces nothing.
- Production is unaffected: `run_analysis.py` and the probes call `panel.build(cur)` with no
  argument and get the production names. Verified by running the full suite and the live
  freshness check after the change.

## Alternatives considered

| Option | Verdict |
|---|---|
| **Parameterise the engines (adopted)** | Removes the need for any exception. Costs one argument and a validation regex. |
| Amend RULE-01 to "a disposable schema, or any schema on a disposable server" | Rejected. It is a real argument, but amending an INTEGRITY rule requires Joe's ruling plus an adversarial review whose job is to break the change — a large process cost to buy something a keyword argument buys for free. |
| Keep the docstring argument and the server guard | Rejected. This is the status quo the review objected to, and the objection was about process, not about whether the guard worked. |
| Delete the tests | Rejected. They cover the precedence flip and the freshness classification, which are exactly the things that were wrong twice. |

## Note on scope

`check_freshness` gained an `--analysis` flag alongside its existing `--core`. Nothing else in
the repository was parameterised: the read RPCs live in migrations and already use the tokens,
and the remaining engines were not touched because nothing needed them to be. Widening this
pattern further is not implied.
