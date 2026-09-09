---
name: session-end
description: Run at the end of every session. Produces the evidence Joe uses to verify work he cannot read.
---

Joe is not an engineer and cannot verify by reading code. Everything below
exists so that verification is possible without reading code. Assertions are
not evidence; command output is evidence.

1. **Run the full test suite and the invariant queries.** Paste actual output.
   Not a summary of it.

2. **Update `ops/features.json`.** Move entries from failing to passing only
   where a named test proves it. Never delete an entry. Never edit an entry's
   text to make it describe what was built instead of what was required.

3. **Append to `ops/PROGRESS.md`**, newest last: the date, what was attempted,
   what works, what does not, the requirement IDs touched, and the commit hash.

4. **Write the Definition of Done checklist** from
   `docs/CONSTITUTION.md#definition-of-done`, item by item, with evidence for
   each.

5. **WHAT I DID NOT DO.** A written section naming everything stubbed,
   simplified, deferred, hardcoded, faked, or left partial — including things
   nobody asked about. **An empty section here is a review finding, not a
   success.** If this section is genuinely empty, say why you believe that and
   name the thing you were most tempted to skip.

6. **Append anything unresolved** to `docs/OPEN_QUESTIONS.md`, with the same
   format as the existing entries: the question, why it is open, what depends
   on it, and what would settle it.

7. **Invoke the `reviewer` subagent** on this session's diff. Include its
   findings verbatim, including the ones you disagree with, and say where you
   disagree and why. Do not summarise them favourably.

8. **State the single most likely thing to be wrong** with this session's work,
   in one sentence. Not the most likely thing to be *criticised* — the most
   likely thing to be *wrong*.
