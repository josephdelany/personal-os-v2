# ADR-0168 — Active-code layout gate excludes the reference archive

Date:2026-09-24. Status: accepted; gate-scope correction verified and independently reviewed.
RULE00/29, REQ-LOC-005 and FIN241/244/251/255. No application or data-access rule changes.

A separately requested file collection placed historical worktrees/prototypes at
.local/project-library. Its README and root instructions explicitly classify it
as private reference material, not active code. The layout walk treated nested
historical migrations as active code outside the root migrations directory and
reported52 failures. Moving the user's collection or weakening location rules is
not the remedy. Existing Git-tracked private-data/coordinate scans remain intact.

Use the same active-code boundary for layout, egress call-site and finance never-rule scanning.
The finance gate also found historical browser automation in the collection; its
patterns and reviewed offline-harness hash exception remain unchanged.
Exclude only this exact root-relative archive subtree from active code traversal.
Before skipping it, fail if root Git tracks anything beneath it or if its boundary
(or .local parent) is symlinked. Reject active file/directory symlinks into the
archive except the user-created root `Collected Files` navigation portal, only
when it resolves exactly to the archive root. Refuse root-tracked portal contents
or link as well. A portal targeting an archive subdirectory is not exempt. Keep active untracked and ignored code elsewhere in scope, including
similarly named paths and nested copies. Do not replace scanning with git ls-files.
Any inability to establish/scan this boundary fails the relevant gate, not a warning.

This permits storing reference files without classifying them as deployed code.
It still forbids committing archive contents or hiding active-code aliases there.
Failure mode is treating live code as reference material; explicit boundary, Git
tracking refusal, alias refusal and regression tests bound that risk. Existing
root imports/CI must not execute this private archive as application code.

Independent reviewer proposed these bounds. Regressions cover exact exclusion,
active ignored/untracked files, tracked archive refusal, file/directory aliases,
symlinked boundary and similarly named paths. Final implementation review accepted.

User confirmed the reorganization during this work. The local filing report
records19,904 indexed entries and explicitly says copies are not active code or
data admission. Ten boundary/error/finance regressions plus27existing finance
guard cases pass (37total); layout43pass. Final review accepted.

The full SQL integration also exposed test_egress scanning the same reference
archive. Its call-site patterns/exact exclusions remain unchanged while traversal
now uses this shared boundary. Final SQL1132passed1skip; writer1451passed959skip;
layout43pass. Source hashes and failed-run evidence retained locally.
