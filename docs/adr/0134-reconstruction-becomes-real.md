# ADR-0134 — The reconstruction capability was schema, not capability

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-REC-004, 005, 006, 008, 009, 010, 011, 012, 013; INV-4, INV-5; RULE-13
**Supersedes nothing.** Corrects a completion claim rather than a design.

## What was actually true

`core.inferred_events` has existed since migration 0054. `public.get_reconstruction` has existed
since 0055. `tools/engines/reconstruct.py` had unit tests covering every branch. And the
reconstruction capability **did not exist**, for three reasons that were each invisible on their
own:

1. **`config.reconstruction_methods` was empty.** RULE-13 says a method must be registered before
   it may run, and none was. The engine could conclude nothing about anything — not as a bug, but
   as the correct behaviour of a correctly built component with no inputs.
2. **Nothing wrote to the table.** The engine returned `Reconstruction` objects to its tests.
   `to_row` produced insert shapes that nothing inserted.
3. **Nothing read the table.** A stored reconstruction could be fetched only by an event id, and
   nothing produced an event id for anyone to hold. `ask` had no knowledge of the table at all.

Every unit test passed throughout. That is the point worth recording: **a component with full
branch coverage and no callers is indistinguishable, from the test suite, from a working
feature.** The suite was measuring the parts and the requirement was about the whole.

## What was built

- **Migration 0064** registers the first method, `watch_non_wear` (family `device_state`).
- **`tools/reconstruct_run.py`** is the runner and the only writer of `core.inferred_events`.
- **Migration 0065** extends `public.search_record` so reconstructions are findable through
  `ask`, with a knowledge bound for replay.
- **`tests/test_reconstruction_e2e.py`** walks the whole chain against a real database.

## The two design decisions worth keeping

**The event is the non-wear itself, not the wearing.** The engine has deliberately no code path
from missing evidence to `did_not_occur` (REQ-REC-009), because absence of a record is not
absence of the event — the single most tempting error in the feature. Defining the event as the
non-wear episode means the evidence *supports* it, and three-valued presence falls out of the
existing rules instead of being asserted by a new branch.

**The method requires phone capture.** A day with no Watch data and no phone data says nothing
about the Watch; capture as a whole was down. A day with phone data and no Watch data is
different in kind. Requiring `phone_capture_present` makes that distinction structural, and
REQ-REC-009 then returns `unknown` for the first case without anyone writing a branch for it.

## Two defects found by reading the runner's own output against production

Neither was caught by a unit test, and both were found by running the thing and reading what it
said:

1. **37 spurious `unknown` rows** about a device that demonstrably captured that day. The skip
   was keyed on the engine's *reason* rather than on the *evidence*.
2. **Every episode inflated from DESCRIPTIVE to EXPLORATORY.** The phone's presence and the
   Watch's absence were given separate `origin_group`s, so one HealthKit export read twice
   counted as two independent corroborations. `origin_group` is now the day's export.

The second is the one that matters. It is REQ-REC-008 — independence is distinct origins, never
row count — failing in the one place a unit test could not see it, because the unit test
constructed its own `Evidence` objects with the origins the test author intended.

## Consequence

A verified dry run against production evidence produces 34 non-wear episodes between 2026-07-05
and 2026-09-09, all at tier DESCRIPTIVE, `independent_support` 1, `rule_score` 1.0 and
`probability` NULL — no calibration exists, so uncertainty is reported as unquantified
(REQ-REC-010).
