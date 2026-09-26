# Personal OS — shared entry point

Read `docs/NEXT_SESSION.md`, then `CLAUDE.md` and `docs/CONSTITUTION.md`.
Follow `docs/EXECUTION_PLAN.md` for work selection and completion, and
`docs/BACKEND_ARCHITECTURE.md` for component boundaries. Relevant requirements
and accepted ADRs remain binding. `docs/DOCUMENTATION_MAP.md` classifies references.

For a backend `/goal`, follow EXECUTION_PLAN's autonomous loop through M6.
Update NEXT_SESSION's single control block and active-unit instructions at each
unit/handoff; resume them after compaction. Continue independent work around holds.
The local watchdog reports checkpoint age; it neither runs agents nor proves completion.

Implementation is active. Complete the backend before frontend construction.
Capture recovery has priority when actionable; external holds do not stop
independent backend work. Check Git and evidence dates rather than repeating
historical status. OQ-48/OQ-51 and other unresolved measurement decisions remain
Joe's; never infer data definitions from similar names.

Only one agent owns a file at a time. Isolate parallel implementation in worktrees
and disposable databases. Do not overwrite or stage another active worker's changes.

## Collected project files

Scattered Personal OS materials now live physically under `.local/project-library/`.
Read its `README.md` and search `FILE_INDEX.csv` when looking for earlier research,
build packages, prototypes or separate worktrees. Use explicit `rg --no-ignore --hidden`
searches for this local folder. Collection does not promote old plans into current
instructions or authorize publication of personal data.
