# Worker 3 — finish capture (B16) scheduling, import and freshness

Worktree `/Users/default/PERSONAL_OS_V2_capture_finish`, branch `work/capture-finish`,
created from `48745d9` (clean). Integration owner: Session 1 (main). Read `AGENTS.md`,
`CLAUDE.md`, `docs/CONSTITUTION.md`, `docs/NEXT_SESSION.md`, `docs/adr/0094-scheduled-local-import.md`
and `docs/build/B16*.md` first.

## You own these files. Nobody else edits them.

- `ops/capture_schedule.py`, `tools/check_freshness.py`, `tools/check_source_continuity.py`
- `tools/engines/capture_budget.py`, `capture_resilience.py`, `extraction.py`,
  `ingest_endpoint.py`, `vision_and_prompts.py`, `compliance.py`
- `tests/test_capture*.py`, `tests/test_freshness*.py` and new capture-specific tests
- **New** capture-specific workflow files under `.github/workflows/`

## You do NOT own

- `.github/workflows/analysis.yml` — main owns it. **Propose the exact edit; do not make it.**
- `tools/importers/apple_health.py` and `tools/import_drop.py` — **main owns both**, and is
  actively changing `apple_health.py` this session for workout-session import (R2). Do not edit
  either. If you need a change there, name the exact lines and request it.
- Migrations (main allocates every number — ask), `lib/`, `tools/engines/reconstruct*`.

## Where capture actually stands

- **The launchd import schedule is built and NOT installed, so it is not running.**
  `--emit-launchd` prints a plist carrying no credential, installs nothing, `RunAtLoad` false.
  Activation is a step Joe takes; do not install it yourself.
- Freshness detection is observed working in production: 9 fresh / 17 stale / 11 never seen /
  6 unmonitored.
- **`ops/capture_schedule.py` keeps "the job ran" separate from "data arrived."** Preserve that
  distinction absolutely — a heartbeat is not an import.

## The objective, in priority order

1. **`tools/engines/ingest_endpoint.py` is a complete, dependency-injected capture endpoint with
   no HTTP host.** `handle()` implements the whole REQ-CAP-003..018 contract — authenticate
   before reading the body, 400 with the raw body retained, `ON CONFLICT DO NOTHING` for a
   duplicate `capture_id`, insert strictly before any model call. Nothing serves it.
   `supabase/functions/location-ingest/index.ts` shows the deployment shape that exists.
   Getting captures actually arriving is the highest-value capture work.
2. **`extraction.py`, `capture_budget.py`, `capture_resilience.py` have no caller either.**
   Connect them on the path a real capture takes — extractive-only contract, the neuron budget
   and refusal, offline replay. Connect them because a capture needs them, never to improve a
   reachability statistic.
3. **Coordinate R8 (useful clarification) with main.** `vision_and_prompts.compute_schedule` /
   `prompt_times` is the prompt dispatcher. Main owns the reconstruction side, which already
   computes and now stores `discriminating_evidence` (migration 0069). **There must be exactly
   one dispatcher.** Main will not build a second one; propose the handoff shape and agree it
   before implementing.

## Blocked, and not your fault — do not work around it

- Gmail OAuth is Joe's; `email_ingest` cannot run without it.
- The Log Workout shortcut is not installed, so no set has ever been logged.
- OQ-55 (the Watch), OQ-57 (the 20 unruled Health types) are Joe's rulings. Do not infer a data
  definition from a similar name.

## Constraints

- **"Capture stopped" is wrong.** The *Watch* stopped, in five stages ending 2026-08-21. The
  phone never did. Do not restate the wrong version.
- Captures and atoms are append-only (INV-2). Derived rows trace to raw captures (INV-1).
- A rejected capture keeps its raw body — it is the only copy of whatever it was.
- Disposable PostgreSQL only (ADR-0082, RULE-01). Worker 1 owns the full database-heavy run.
- $0 recurring. A new dependency needs an ADR with limits, projected usage and failure at the
  limit, before it is added. Billing on overage is disallowed.
- Never weaken a test, threshold or gate to make it pass (INV-6 / RULE-00).

## Handoff

What now works end to end, through which command or endpoint, with what evidence and at which
revision; the exact `analysis.yml` edit you need, if any; the agreed R8 dispatcher shape.
Joe relays it to main.
