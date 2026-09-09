---
name: session-start
description: Restore the Personal OS checkpoint at startup or after compaction without repeating unchanged verification.
---

Read `docs/NEXT_SESSION.md`, `CLAUDE.md` and `docs/CONSTITUTION.md`. Inspect the current
branch, Git status and latest commits. Read `docs/EXECUTION_PLAN.md` and only the
requirements, ADRs and open questions relevant to the active unit.

State the active outcome, remaining acceptance cases and next action. Continue that
unit. Historical roadmap phase labels cannot override the current delivery plan.

Use prior test evidence only for its recorded revision/environment. Run affected tests
when changes or new evidence invalidate it; full checks belong at integration boundaries.
Compaction alone is not a reason to repeat a full suite. A real regression requires
diagnosis and repair; it does not require stopping all independent authorized work.

If the checkpoint conflicts with Git, correct the checkpoint from observed evidence.
Never infer deployed or real-data success from a local commit or fixture pass.
