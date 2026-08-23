# ADR-0011: The agent may not hand-write `ops/features.json`

## Status

Accepted (partial). This ADR records **one** decision in full — that the agent
is denied Edit/Write on `ops/features.json` at the harness permission level, and
why. It reserves the *mechanism* that will legitimately move an entry
failing→passing (`tools/update_features.py`) for authorship alongside the first
real proving test, in Phase 3. That deferral is a decision in itself and is
recorded below; the script's design is not, because it cannot be demonstrated
until a test exists to demonstrate it against.

## Date

2026-08-23

## Context

`ops/features.json` is the ledger of what has been proven to work. Definition of
Done item 4 already requires that an entry move from `failing` to `passing`
"never by deleting or editing an entry" — only by a named test proving it.
RULE-00 forbids weakening a gate to make it pass, and the whole system exists
because in July 2025 an agent covered a loss with fabricated data. An agent that
can hand-edit its own scorecard can mark its own work green, which is the same
failure mode wearing a different hat.

Prompted by the Reward-Hacking-Benchmark finding that environmental hardening
(removing the capability, not instructing against its use) cuts exploitation
~87.7% with no loss of task success, Joe directed two changes: deny the agent
write access to `features.json`, and stand up a `tools/update_features.py` that
flips an entry only after parsing pytest output that proves a test naming the
requirement ID actually passed.

The first is a pure capability removal and is applied now. The second ran into
three facts on disk (verified 2026-08-23):

- **No pytest suite exists.** Zero `test_*.py` files; `tests/` holds only an
  empty `fixtures/`. All 15 `features.json` entries are `failing` with
  `proving_test: null`.
- **CI does not run it and has nothing to feed it.** `.github/workflows/gates.yml`
  runs the layout gate and the guard behavioural test only.
- **No entry legitimately flips until Phase 3.** Features move to `passing` when
  the Big Mac slice's twelve Gherkin scenarios pass (ROADMAP Phase 3). We are in
  Phase 0.

A verification control that has never verified anything manufactures false
assurance — the same objection OQ-15 raises against the shell-level egress
guard. Writing the parser now means encoding a pytest-output contract with no
real producer to validate it against, and wiring into CI a step that flips
nothing. CLAUDE.md forbids building work that belongs to a later phase, and
holds that a thing whose only proof is assertion is not proven.

## Decision

1. **Deny the agent Edit and Write on `ops/features.json` at the permission
   level**, in `.claude/settings.json`:

   ```json
   "Edit(/ops/features.json)",
   "Write(/ops/features.json)"
   ```

   The single leading slash anchors to the project root (the settings source),
   i.e. `<project-root>/ops/features.json`. `deny` overrides the bare `Edit`/
   `Write` already in `allow`, so the agent's file-editing tools can no longer
   touch the ledger. This does **not** block a Python script's `open()` — the
   deny governs the Edit/Write *tools*, not filesystem writes from a program —
   so the sanctioned writer will still function when it exists.

   *Verified 2026-08-23, not asserted:* under these settings an `Edit` on
   `ops/features.json` is rejected by the permission engine with "File is in a
   directory that is denied by your permission settings" — it is stopped before
   execution, not merely discouraged. The leading-slash form resolves to the
   project root, as the harness confirmed empirically.

2. **Defer the sanctioned writer to Phase 3.** The script that flips an entry —
   proposed name `tools/update_features.py` — is authored with the first proving
   test so it can be demonstrated: given genuine green pytest output it flips
   exactly the one entry whose requirement ID the passing test names; given red
   or absent output it refuses. It is wired into CI at that point, not before.
   It does not exist yet, and is therefore referenced by description rather than
   by a resolvable path in the linted `DECISIONS.md` index. Until it lands, the
   correct state of every entry is `failing`, and the lock in decision 1 is what
   keeps it honest.

## Consequences

- The agent structurally cannot mark its own work passing. Good.
- There is a window (Phase 0–2) in which `features.json` has a lock but no
  writer. This is intended: nothing should change it in that window.
- The deferral leaves DoD item 4 partially unenforced by automation until
  Phase 3 — it remains enforced by the lock (nothing can flip an entry) and by
  review. When `update_features.py` lands it must arrive with its demonstration,
  or this ADR is not discharged.

## Alternatives considered

- **Write the script now with a self-test over captured pytest output.** Offered
  to Joe; declined in favour of deferral. It would exercise the parser but still
  wire a no-op step into CI and encode a contract against no real producer.
- **Relative path `Edit(ops/features.json)`.** Rejected: without a leading slash
  the pattern anchors to the launch cwd, not guaranteed to be the project root.
  The leading-slash form is the robust one.
