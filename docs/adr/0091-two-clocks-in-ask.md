# ADR-0091 — `ask` separates the subject-day cutoff from the knowledge-time cutoff

Status: accepted (migration 0058 prepared, NOT applied)
Date: 2026-09-09
Requirements: RULE-04, INV-4, REQ-ASK-030, REQ-INF-108. Supersedes the cutoff introduced by
this session's round-4 finding 2.

## The defect, and that I introduced it

Earlier today I closed a real finding: `spend` read atoms with a subject-day cutoff and no
`recorded_at` one, so an atom about an old day recorded today entered a replay of a question
asked before it existed. The repair added `AND a.recorded_at < (as_of + 1)::timestamptz` to
the three `spend` queries.

That repair used **one date as both boundaries**. `as_of` bounds which subject days count;
`recorded_at` bounds what the system had learned. They are different clocks, and Ask defaults
`as_of` to **yesterday** because today is an incomplete subject day — while an import is
recorded **today**. The consequence: every freshly imported or backfilled transaction was
invisible to every question asked with the default `as_of`. Bitemporally defensible; useless.

Demonstrated rather than argued. With 1,052 backfilled transaction atoms present,
"how much did i spend at hannaford last 500 days" returned:

- `as_of = 2026-09-09` → **INSUFFICIENT**
- `as_of = 2026-09-11` → **DESCRIPTIVE**, "a four-figure total usd across dozens of charges"

Nothing about the data changed between those two calls. Only the cutoff moved past the moment
the rows were written.

## This is the same mistake twice

ADR-0089 records the identical conflation in `analysis.f_daily_panel`, found the same day: it
passed `as_of` to both cutoffs and made all 33,355 imported health atoms invisible. Two
independent places, one wrong idea — that a question's date is also its knowledge horizon.

Writing it down because the shape will recur wherever a bitemporal store is queried by date:
**a date parameter that means "as of when" must say which clock it stops.**

## The decision

`public.ask(question, as_of)` becomes `public.ask(question, as_of, known_at DEFAULT now())`:

- **two arguments** — subject days up to `as_of`, using everything known now. The live case.
- **three arguments** — true replay: what the system would have said at that moment.

The two-argument form is dropped rather than kept alongside, because a 2-argument call would
otherwise be ambiguous between it and the 3-argument form's default. The legacy
`public.ask(text)` from the previous build is untouched and still serves the old PWA (OQ-17).

## A subtlety the tests had to learn

Postgres `now()` is the **transaction** timestamp, not the statement's. A row written during
the same transaction as the question is timestamped *after* `now()` and is correctly invisible
to it. That is the right semantic — the question is the transaction — but it made a fixture
that wrote an atom with Python's `datetime.now()` fail for a reason unrelated to the contract.
Fixtures now record at a realistic import time instead.

## What this does not fix

The legacy `analysis.panel` lane still has no `recorded_at`, so its half of OQ-45 remains open.
`spend`'s merchant and category semantics remain held on B14 (ADR-0062); the answer says so in
its own text.
