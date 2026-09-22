# ADR-0142 — Autonomous backend execution and a local checkpoint monitor

Date: 2026-09-22. Status: accepted workflow direction from Joe.

## Authority and decision

Joe requested a completion plan, loops, crons and an adapting instruction sheet,
to be started later with `/goal`. Extend the existing EXECUTION_PLAN and
NEXT_SESSION rather than create another master plan. The goal owns one sequence
of bounded build/test/review/repair units through M6. It updates its next action,
evidence and holds after each unit and resumes that state after context handoff.
The eight quality review lenses apply at each relevant boundary. Failed cases
trigger diagnosis; external holds redirect work to independent dependencies.

Use macOS launchd for a lightweight 15-minute local checkpoint monitor. The monitor
reads NEXT_SESSION's one JSON control header, checks timezone-aware update/progress
timestamps, and atomically replaces an ignored local status snapshot. An advisory
90-minute age is a development-monitor setting, not a personal measurement or
acceptance threshold. Missing/malformed/future timestamps are unhealthy. A lock
prevents overlapping monitor writes. Repeated runs do not grow a log.

The monitor cannot assert backend release, modify instructions, launch coding
sessions, contact a network, use credentials, write a database or change the feature
ledger. There is no new dependency, service, account or recurring fee. It runs only
while the local user environment is available. Its last check timestamp is required
to distinguish a quiet monitor from a running one; its health is not app health.

## Consequences and limits

Enables repeatable continuation and bounded checkpoint diagnostics. It cannot
guarantee model-runtime uptime or restart an externally stopped goal. No native
recurring-agent management tool is exposed in the setup session. A stale advisory
is consumed by the next goal continuation, not delivered as a push notification.

Only work selection/instructions adapt automatically under the active agent.
Scope, requirements, invariants, reserved decisions and production permissions do
not adapt away. No deployment, personal-data disclosure, test-fixture exception,
frontend construction or claim of backend completion is authorized by this ADR.

Remove the temporary monitor after release; leave backend operational schedules
intact. Evidence of registration and execution, and verification results, belongs
in PROGRESS/NEXT_SESSION. There is no migration and no product requirement claimed
complete by this development tooling.
