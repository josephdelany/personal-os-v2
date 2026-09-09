# Session continuity

Before doing project work, read `docs/NEXT_SESSION.md`, then `CLAUDE.md` and the
referenced project requirements. The handoff records the latest uncommitted work,
verification limits, and the exact restart point; older status documents can be
stale — including this one, so check its date against `ops/PROGRESS.md`.

**Updated 2026-09-09 (session 21).** The 2026-09-08 pause is lifted: Joe explicitly
directed session 21 to continue and finish the project. Implementation is active,
not paused. The previous instruction to wait for explicit permission no longer
applies and should not be re-applied.

The credential blocker recorded in the 2026-09-08 handoff is resolved (OQ-46 closed).
The live blocker is different and larger: **device-side capture stopped on 2026-07-28
and 0 of 17 monitored metrics are fresh**, while every scheduled job stayed green
because the jobs were alive and only their inputs were dead. Capture recovery
outranks the next build order, per the standing ruling in `CLAUDE.md`.

Two things need Joe rather than a session, and a session must not decide them alone:
the canonical-metric wiring defects (OQ-51) and the `screen_*` metric definitions
(OQ-48). Both are claims about data, not code.
