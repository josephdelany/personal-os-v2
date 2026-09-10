# ADR-0135 — A conclusion built on a conclusion cannot outrank it

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-REC-016 (inferred-input propagation), REQ-REC-004/006, INV-5
**Migrations:** 0066 (column and CHECK), 0067 (second registered method)

## The finding this came from

An independent audit found that REQ-REC-016's test "checks a dictionary of acceptance labels
rather than executing reconstruction scenarios". It was right. The test built
`{family: "passed" for family in EVENT_FAMILIES_REQUIRED}`, handed it to `acceptance_report`, and
asserted that the report had seven keys and no aggregate verdict. It executed no reconstruction,
touched no database, and would have passed with the engine deleted.

REQ-REC-016 says the backend **SHALL EXECUTE** acceptance cases across seven situations. The old
test satisfied the sentence's grammar and none of its content.

## Why it could not simply be rewritten

Two of the seven cases were **not executable at all**:

- **multiple event families** — one method was registered, in one family. Coverage across
  families could be asserted but not run.
- **inferred-input propagation** — the engine had no concept of an inferred input. Every citation
  in `core.event_evidence` was implicitly a measurement. There was nothing to propagate through.

So the honest fix was not a better test. It was the missing capability, and then a test.

## The rule

**A reconstruction resting on an earlier reconstruction is capped at the tier of its weakest
inferred input.**

Without the cap, inferences promote each other:

> Infer A at DESCRIPTIVE from one source. Infer B from A and a second inference A'. B now has two
> independent supporting origins and reaches EXPLORATORY — which means "two independent sources
> corroborate". The system believes B more strongly than any measurement ever supported it, and
> every row in the chain is individually defensible.

**The cap is the weakest input, not an average.** Averaging lets a strong input launder a weak
one, which is the same failure one step further away from view.

`Evidence` now carries `provenance` (`measured` | `inferred`) and, for inferred citations, the
`input_tier` they were concluded at. An inferred citation without a tier raises: a conclusion
built on a guess that does not say how strong the guess was cannot be held below it.

## Why the constraint is in the database as well as the engine

`tools/engines/reconstruct.py` applies the cap and is the first line of defence. It is not the
only writer this table will ever have, and **a rule that lives only in the writer is a rule that
lasts until the second writer.** Migration 0066 adds `inferred_inputs text[]` and the CHECK
`cardinality(inferred_inputs) = 0 OR tier <> 'EXPLORATORY'`.

## The second method (0067)

`sleep_gap_explained`, family `data_coverage`: a night with no sleep record is *explained* by an
inferred Watch non-wear episode rather than unexplained. It exists to make two acceptance cases
executable, and it is a real distinction — but the wording of what it may conclude is doing
careful work:

> "no sleep record" is not "Joe did not sleep", and "explained" is not "Joe slept".

The gap remains missing and is never a zero. The method reports only which *kind* of gap it is,
which is what stops an analysis from treating the night as a zero or as an anomaly worth chasing.
It consumes an inference, so 0066 caps it at DESCRIPTIVE however many nights agree — two
inferences agreeing is not two sources, it is one method's opinion twice.

## How acceptance is run now

`tools/reconstruction_acceptance.py` executes all seven cases against a throwaway PostgreSQL 17
server it builds and destroys itself, and prints each as passed or **explicitly open with a
reason**. It is runnable directly (`python3 tools/reconstruction_acceptance.py`) because Joe
verifies outcomes by running things, and an acceptance run reachable only from inside pytest is
one he cannot run. It refuses to run against `core`, `public` or any other production schema.

The old test survives, renamed to
`test_REQ_REC_016_the_reporting_shape_refuses_a_single_aggregate_verdict`, and its docstring now
says what it does and does not prove. **Renaming it was not the fix** — the executed harness is
the fix; the rename stops the reporting-shape test from being read as the acceptance run.
