# Personal OS — shared entry point

Read `docs/NEXT_SESSION.md`, then `CLAUDE.md` and `docs/CONSTITUTION.md`.
Follow `docs/EXECUTION_PLAN.md` for work selection and completion, and
`docs/BACKEND_ARCHITECTURE.md` for component boundaries. Relevant requirements
and accepted ADRs remain binding. `docs/DOCUMENTATION_MAP.md` classifies references.

Implementation is active. Complete the backend before frontend construction.
Capture recovery has priority when actionable; external holds do not stop
independent backend work. Check Git and evidence dates rather than repeating
historical status. OQ-48/OQ-51 and other unresolved measurement decisions remain
Joe's; never infer data definitions from similar names.

Only one agent owns a file at a time. Isolate parallel implementation in worktrees
and disposable databases. Do not overwrite or stage another active worker's changes.
