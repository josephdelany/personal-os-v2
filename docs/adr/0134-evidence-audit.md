# ADR-0134 — "685 of 685 proven" measured filenames, and the second column that was missing

Date: 2026-09-10. Status: accepted. Measurement and reporting decision; no schema, no
migration, no production connection change.

## The defect

`tools/audit_requirements.py`, at f1f7249, printed:

```
  685 of 685 requirements (100%) are proven by a test carrying their ID.
```

It computed that by globbing `tests/**/test_*.py`, matching `^\s*def\s+(test_\w+)\s*\(` with a
regular expression, and pulling requirement IDs out of the **function names**. It never started
pytest. It never opened a result file. It had no way to distinguish

- a test that passed,
- a test that failed,
- a test that was skipped,
- a test that was never collected,
- a test that asserts nothing at all,

because it never asked any of those questions. A requirement became "proven" the moment
somebody typed its ID into a function name. The word the tool printed was *proven*; the thing
it measured was *a filename*.

That figure was then quoted as a completion claim — `docs/NEXT_SESSION.md` opened with
"EVERY REQUIREMENT IS PROVEN: 685 of 685" — and it survived two reviews. The output was a
percentage, and a percentage is the one form of evidence nobody re-derives.

RULE-00 forbids weakening a gate to make it pass. This was worse and quieter: a gate that was
never a gate, reported as though it were one.

## The second defect, which fixing the first leaves standing

Reading results instead of names answers "did a named test run and pass?". It does not answer
"does anything but a test ever call the code that test exercises?", and the two were being read
as one word.

Measured at this revision: `tools/engines/` holds **55 modules**. **8** are transitively
reachable from a script a scheduled workflow starts; **5** more only from a hand-run script
with a `__main__` block. The remaining **42 are imported by `tests/` and by nothing else.**
They are libraries with no caller. Their tests pass. Passing proves the module's arithmetic.
It does not prove that any job, surface, or endpoint invokes it, and "proven" was being read as
though it did.

This ADR does not decide to fix that wiring. It decides to **stop it being invisible**.

## The decision

**1. Status comes from results, never from names.**
`tools/audit_requirements.py` was rewritten (commit b899489) to read `pytest --junitxml`
reports and report a six-level evidence ladder — DECLARED / MAPPED / TESTS_PASSED /
INTEGRATED / DEPLOYED / OBSERVED — monotonically, so "deployed" cannot be written above
skipped tests. Level 3 is named `TESTS_PASSED` and never `PROVEN`. With no result file, every
status is UNKNOWN and the tool says so rather than falling back to a name count. Two result
files may be merged, because CI runs the suite twice — live database, and disposable
PostgreSQL 17 (ADR-0082) — and each job skips the other's tests by design; a failure in any run
wins outright, and a pass requires a run that produced one.

**2. Reachability is a SEPARATE COLUMN, computed from the import graph, and never folded into
the completion figure.**
`tools/evidence_report.py` (new) classifies every first-party module as

- `scheduled` — transitively imported by a script named in `.github/workflows/*.yml` or
  `RUN_TONIGHT.sh`;
- `cli` — transitively imported only by a hand-runnable script;
- `tests-only` — nothing outside `tests/` imports it.

An entry point is read from the workflow files, not guessed from the presence of a `__main__`
block: a script nothing schedules is not a production entry point, and conflating the two is
the flattering answer that makes everything look reachable.

**3. "Named but empty" is a reported state.**
A requirement whose only passing named test contains no non-trivial assertion is reported
`vacuous`, not `passed`. JUnit records such a test as a clean pass — it really did not raise —
so results alone cannot catch it. The check follows calls into named helpers, because several
tests here legitimately delegate the assertion (`refuses(cur, ...)`,
`check_imports(...)`); inventing an absence is the same defect as inventing a presence, and
RULE-00 forbids both directions. Measured on this suite, a body-only rule flags 10 of 1340
test functions and all 10 are false positives of exactly that kind.

**4. The report is generated, never hand-edited.**
`tools/evidence_report.py` writes `docs/EVIDENCE_REPORT.md` and `--check` regenerates it and
exits 1 when the file on disk differs. A figure in that document cannot be improved with a text
editor.

**5. Neither column, alone or combined, is a completion figure.**
The report says so in its own header. A passing named test is evidence about the assertions in
that test — not about the requirement's whole sentence, and not about whether anything calls
the code. Levels 4-6 come only from a declared reference in `ops/requirement_evidence.json`,
which does not exist, so they are zero for every requirement and UNKNOWN is recorded as a state
rather than filled with an inference.

## Consequences

The honest figure is far below 685 and it is meant to be. What was lost is a number that was
never true; what is gained is a report whose every row names the test that produced it and the
run the test came from.

Work that was called complete on the old figure is not complete. In particular the 42
tests-only engines are unwired libraries, and no amount of green test output changes that —
which is precisely why the column exists.

`docs/NEXT_SESSION.md`, `docs/BACKEND_COMPLETION.md` and `ops/features.json` still quote or
depend on the superseded framing. Correcting them is not in this change and is owed.

## What this ADR does not claim

- It does not review whether each requirement's passing tests cover its sentence. 681 of them
  have not been read that way.
- It does not claim an import edge means the code is correctly wired, that its job ran, that a
  row landed, or that Joe saw the number. Reachability is a static fact about source text.
- It does not fix any wiring. Nothing in `tools/engines/` was connected to an entry point here.

## Note on how this was built

Two agents were assigned this defect concurrently in the same worktree. The first committed the
result-reading rewrite of `tools/audit_requirements.py`, its tests, and
`docs/REQUIREMENT_EVIDENCE_AUDIT.md` as b899489. The second added the reachability and
vacuity columns in `tools/evidence_report.py` rather than overwriting that work, as
`AGENTS.md` requires ("Only one agent owns a file at a time... Do not overwrite or stage
another active worker's changes"). `tools/evidence_report.py` therefore delegates every
"did it pass" question to `tools.audit_requirements.audit`, so exactly one implementation of
that question exists in the repository. Two evidence documents now stand —
`REQUIREMENT_EVIDENCE_AUDIT.md` (the hand-written ladder analysis and four disputed closures)
and `EVIDENCE_REPORT.md` (the generated two-column table). Consolidating them is owed and is
Joe's call.
