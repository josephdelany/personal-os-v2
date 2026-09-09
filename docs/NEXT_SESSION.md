# Checkpoint

Verified against Git 2026-09-09. Branch `session-21-recovery-and-ask`, HEAD `666fe43`,
based on `b606c64` (main).

## Active unit

**M2 — deterministic Ask. REOPENED.**

**Correction.** An earlier version of this checkpoint said "M2 closed every acceptance item
except two". That claim was not supported and is withdrawn. An adversarial review of
`db815e0..45535eb` executed ~35 probes against a disposable server and found the closure false
on six checklist lines. The review's own summary: *"The M2 closure claim is not supported."*
It was right, and the error was mine: I read a passing suite as evidence of coverage the suite
did not have — several of my own tests asserted less than their names claimed.

M3's shared prerequisite (`lib/egress.py`, migration 0052, the planner) is built and committed
and stands on its own evidence; M2 is reopened ahead of it.
Per EXECUTION_PLAN, M3 pulls only the shared prerequisites from B12/B16 forward — numeric
build order is not a dependency schedule — then completes B11.2, then the rest of B12/B16.

Outcome: one egress contract (`lib/egress.py`) with a shared usage/budget ledger, so that
Ask's planner, nutrition lookup and media transcription account against one budget rather
than three. Requirement IDs: REQ-CAP-035..042 (neuron budget), REQ-NUT §E egress, RULE-28
($0 recurring), RULE-29 (egress logging to `ops.egress_log`).

Acceptance cases: every outbound model call writes an `ops.egress_log` row before the
response is used; the shared budget is decremented once per call and is visible to all three
consumers; exceeding it degrades to the deterministic path rather than billing; no coordinate
or home location can reach a prompt; a failed call is recorded, not silently retried.

### Previously active — M2, now closed except

- **`spend`** — HELD on B14's merchant/category cascade (ADR-0062). Each blocked case is
  mapped to its dependency there. Do not widen the substring match.
- **Replay against a correction to an earlier day** — OQ-45. `analysis.panel` is rebuilt
  wholesale and has no per-observation `recorded_at`. The as-of cutoff IS proven.
- **B11.2** — now the active unit's successor, once the shared egress contract exists.

Outcome: `spend` meets the finance contract instead of matching a descriptor substring.
Requirement IDs: REQ-ASK-005/009/021/023/027, REQ-FIN-050/051 and the §D/§G spend
requirements; RULE-12 (one owner per measure).

Acceptance cases, from EXECUTION_PLAN's M2 checklist:

- agreed merchant/category semantics — not descriptor `ILIKE`
- currencies handled explicitly rather than assumed USD
- deduplication of the same purchase arriving more than once
- refunds and inbound transfers excluded or netted per REQ-FIN-050
- ATM withdrawals labelled destination-unknown and excluded from category rollups (REQ-FIN-051)
- totals, counts, typical week and top merchants all returned
- absent data returns the stored refusal form, never a zero total

**Dependency, stated plainly:** merchant/category resolution is B14's cascade and does not
exist. A descriptor-only path cannot close this contract, and inventing merchant semantics
inside Ask would create a second owner of a measure B14 owns (RULE-12). The next action is
therefore to establish which part is closable now — see below — not to widen the substring.

## Next action

Read `specs/02-capture-nutrition/requirements.md` REQ-CAP-035..042 and REQ-NUT §E, then
build `lib/egress.py` with the shared budget ledger. What proves the unit complete: an
outbound call cannot be made without an `ops.egress_log` row and a budget decrement, proven
behaviourally, and the over-budget path degrades to deterministic rather than spending.

## Completed this session — do not redo

| Unit | Evidence | Commit |
|---|---|---|
| B13 drop-folder importers, migration 0051 | 28 tests; 300 MB memory bound; idempotency across 4 session timezones | `abe8b7e` |
| Gate-4 freshness mechanism, REQ-NFR-005..014 | 14 tests; first live run `fresh=0 stale=4 misconfigured=1 never_seen=12 unmonitored=6` | `844b7e5` |
| Schema-parameterised engines (ADR-0061), panel fill-only | OQ-52 closed without amending RULE-01 | `092c77b` |
| Ask `compare` cross-metric, `effect` direction + as-of replay, `contrast` window disclosure | 45 tests | `db815e0` |
| Ask `trend` rolling-28; executor write separation proven | static + behavioural | `3da49ee` |
| Ask `entity` reachable, `search` carries records | 52 tests | `6225164` |
| M0 dependency tracking | clean clone of the branch runs the suite | `666fe43` |

## Last command, result and revision

M2 integration boundary, all at `45535eb`:

```
PYTHONPATH=. python3 tools/update_features.py --strict
    pytest: 206 passed, 0 failed, 0 errors, 114 skipped of 320 collected
python3 tools/test_local_sql.py   TZ=America/New_York   186 passed
python3 tools/test_local_sql.py   TZ=UTC                186 passed
PYTHONPATH=. python3 tools/check_invariants.py --core core   INVARIANTS: ALL PASS
PYTHONPATH=. python3 tools/validate_layout.py                41 passed, 0 warnings, 0 failed
git diff --check                                             clean
PYTHONPATH=. python3 tools/check_freshness.py --no-log       fresh=0 stale=4 misconfigured=1
                                                             never_seen=12 unmonitored=6  [exit 1]
```

320 collected = 206 against production + 114 on the disposable server. Nothing skipped in
both. `ops/features.json` unchanged — no ledger entry corresponds to Ask, B13 or freshness.

The production suite and invariants predate the four Ask commits, all of which changed only
`migrations/0049_ask_core.sql` (unapplied) and local-SQL tests the production job skips.
They are due at the next integration boundary — the M2 close — not because context compacted.

## Status by field

| Deliverable | Implemented | Behaviourally tested | Deployed | Observed on real data |
|---|---|---|---|---|
| B13 importers | yes | yes (generated fixtures) | **no** — 0051 unapplied, verified live | **no** |
| Freshness checker | yes | yes | **no** — workflow not on main | one live read only |
| Ask describe/trend/rhythm/last/count_days | yes | yes | **no** — 0049 unapplied | no |
| Ask compare/contrast/effect | yes | yes | no | no |
| Ask search/entity | yes | yes | no | no |
| Ask replay (as-of cutoff) | yes | yes | no | no |
| Ask replay (after corrections) | **no** — OQ-45 | no | no | no |
| Ask spend | descriptor-scoped, disclosed | yes, for what it measures | no | no |
| B11.2 planner | **no** | no | no | no |

Verified live this session: migration 0051 is **not** applied — neither the `file_import`
enum label nor its registry rows exist in `core`.

## Held on Joe — external, batched

| # | Action | Why held | Blocks |
|---|---|---|---|
| 1 | `PYTHONPATH=. python3 tools/run_migration.py --core core --ops ops --only 0051 --verify --commit` | Production write; permission classifier refused and I did not work around it | All of M1: no import can commit |
| 2 | Apple Health export + Takeout (Chrome/YouTube only) → `~/PersonalOS_Drop/` | Your devices | Recovery of the gap since 2026-07-28, recoverable now |
| 3 | Health Auto Export metric selection; is OwnTracks running? (OQ-50) | Your phone | Live capture restart; import recovers history, not the feed |
| 4 | OQ-51: is `apple_watch.steps` the same measurement as `health_history.steps`? Is `screen_active_hours` = `attention.screen_active_min` ÷ 60? | Claims about data | Canonical `steps` blind since 2026-06-23 |
| 5 | OQ-48: the four `screen_*` session/binge thresholds | Definitions live in the old stack's code | Re-deriving those metrics |
| 6 | OQ-53: is the panel's day axis the 04:00-ET subject day or the UTC date? | Affects every metric | The old/new stack boundary seam |
| 7 | GitHub default branch `v2-day1` vs `main` (OQ-47) | Repository setting | Whether scheduled jobs run current code |

M2–M5 proceed while these are held. **0 of 17 monitored metrics are fresh**, and items 1–3
are the only things that change that.
