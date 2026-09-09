# Personal OS

Personal OS collects Joe's observations, preserves their sources, computes results,
and answers questions with explicit evidence and uncertainty. The current delivery
objective is a complete backend, followed by the frontend.

- [Current checkpoint](docs/NEXT_SESSION.md): active unit, evidence, next action and holds.
- [Execution plan](docs/EXECUTION_PLAN.md): milestones and exact completion criteria.
- [Backend architecture](docs/BACKEND_ARCHITECTURE.md): components and boundaries.
- [Agent instructions](CLAUDE.md): working rules and permissions.
- [Documentation map](docs/DOCUMENTATION_MAP.md): where authoritative information lives.

For a running goal, paste:

```text
Continue the existing work under CLAUDE.md and docs/EXECUTION_PLAN.md.
Read docs/NEXT_SESSION.md and inspect Git first. Complete the active unit against
its acceptance cases, checkpoint it, then take the next ready unit. Do not restart
or redesign. Keep genuine external dependencies held while continuing independent
backend work. Do not start frontend construction before the backend release gate.
```

A running agent must read this update at its next safe boundary. Editing these files
does not prove that an existing terminal has reloaded them.
