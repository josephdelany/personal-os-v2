---
name: session-start
description: Run at the beginning of every session, and again after any context compaction, to restore working state.
---

Do these in order. Do not begin implementation work until all seven are done
and reported.

1. **Orient.** Print the working directory, the current branch, and the last
   five commits with one-line messages.

2. **Reload the constitution.** Read `CLAUDE.md` and `docs/CONSTITUTION.md` in
   full. These are re-read every session because compaction silently drops
   them and a system that has forgotten its invariants will cheerfully violate
   all thirty.

3. **Read the last three entries** of `ops/PROGRESS.md`.

4. **Read `docs/OPEN_QUESTIONS.md`.** Anything in that file is something to
   ask Joe about, never something to decide alone. If today's work touches an
   open question, say so before starting.

5. **Read `ops/features.json`** and report the failing count. Entries are
   never deleted or edited to declare completion — they move from failing to
   passing when a named test proves it.

6. **Run the invariant queries** and the test suite. Report actual output. If
   something that was passing is now failing, stop and report before doing
   anything else — that is a regression and it outranks whatever was planned.

7. **State the phase** from `docs/ROADMAP.md`, and state in one sentence what
   this session is for. If the requested work belongs to a later phase, say so
   and stop.

Then, before writing any code: quote the requirement IDs this session will
satisfy. If there is no requirement ID for the work, the requirement is missing
and writing it comes first.
