---
name: session-end
description: Close a Personal OS work unit with evidence, scoped review, and a compact continuation checkpoint.
---

1. Apply `docs/CONSTITUTION.md` Definition of Done. Record the checks relevant to the
   change, exact results and tested revision. Backend integration requires the full
   suite, invariant queries, layout check and sanctioned feature-ledger writer.
   Documentation-only changes require link/configuration/layout verification.
2. Review the changed behavior and requirement coverage independently for implementation
   units and policy changes. Use the reviewer subagent when available. Review fixes and
   affected behavior; a clean review is valid if its coverage and limits are explicit.
3. Append a concise entry to `ops/PROGRESS.md`: outcome, requirements or maintenance
   scope, evidence, review findings/dispositions, commit if made, and WHAT I DID NOT DO.
   Preserve serious findings accurately, including disagreements. No invented omission
   is required when none remains; name verification limits honestly.
4. Update `docs/NEXT_SESSION.md` with the active/next unit, remaining acceptance cases,
   last command and revision, owned files and held actions. Preserve another active
   writer's checkpoint; coordinate ownership before updating the same file.
5. Make a scoped commit when authorized. Check tracked dependencies; do not stage
   unrelated work. Record deployment separately. Report outcome and next action.

Open questions are reserved decisions or unresolved facts. Ordinary bugs belong to the
active acceptance list or their assigned milestone, not an ever-growing approval queue.
