# ADR-0088 — The migration chain is not self-contained, and the six unapplied files are ordered correctly

Status: accepted
Date: 2026-09-09
Tool: `tools/verify_migration_chain.py`

## Why this was built

Six migrations are written and unapplied — 0049, 0050, 0052, 0053, 0054, 0055 — and applying
them is a production write Joe authorises. The risk he was being asked to accept was never
"does this SQL parse." It is *"does this SQL parse after the five before it, against the
objects they create."* A file that is individually valid can still fail on the real database
because a dependency landed in a different order, and mid-apply is the worst place to find out.

So: apply every migration, in order, to a disposable PostgreSQL 17 server, from empty.

## Result

**CHAIN CLEAN — 54 migrations, 469 statements, applied in order from empty.** All six
unapplied files are included. The order is coherent and every object a later migration
references is created by an earlier one.

This is not a claim that production will accept them: production carries 0001-0051 plus real
rows and this starts empty. What it rules out is the failure this sequence can actually have.

## The finding

**The chain broke at 0020 and the reason matters more than the fix.** `0020_checkin_mirror.sql`
reads `public.checkins`, and *no migration file creates it*. Thirty-four `public.*` tables are
in that position: the old stack created them, the chain depends on them, and nothing in the
repository defines them.

So **"apply every migration to a fresh database" is not currently a recovery path.** If the
Supabase project were lost tomorrow, the repository could not rebuild the schema — it would
stop at 0020 and every later migration touching a legacy table would follow. That is a real
gap in the disaster story and it had never been tested, because nobody had ever run the chain
from empty.

`migrations/_legacy_prerequisites.sql` now records those 34 tables' shapes, generated from the
live catalog by `--refresh-legacy`. Column names and types only: no rows are read, and a
column name is not an observation about Joe, so it is safe in Git. It is a *prerequisite*, not
a migration — it is deliberately named with a leading underscore so `run_migration.py`'s
`[0-9][0-9][0-9][0-9]_*.sql` glob never picks it up and it can never be applied to production.

A second benefit: the generated shapes mean a legacy column drift now fails in this verifier,
loudly, instead of inside a function under test where it reads as a defect in the caller.

Of note in that list: the old stack already had `public.inferred_events` and `public.workouts`.
`core.inferred_events` (0054) is a different table in a different schema and does not collide,
but the overlap is worth knowing before B14R reads legacy data.

## What this does not settle

Whether the legacy tables should be *reconstructible* — real DDL under a migration number,
with their own ADR — or whether the recovery story should be "restore the Supabase backup" is
a decision, not an implementation detail, and it is Joe's. Recorded as OQ-58.

Nothing here applies anything. The six migrations remain unapplied.
