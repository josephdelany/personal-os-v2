# Checkpoint

Verified against Git 2026-09-09. Branch `session-21-recovery-and-ask`, HEAD `666fe43`,
based on `b606c64` (main).

## Active unit

**M2 — deterministic Ask: the `spend` operation contract.**

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

Read `specs/03-finance/requirements.md` §D and §G in full, then record in an ADR which
`spend` sub-contract is answerable from `transaction` atoms alone and which genuinely
requires B14. Implement the closable part; hold the rest against B14 with the dependency
named. What proves the unit complete: every acceptance case above either passes a named
behavioural test or is recorded as held with its blocking dependency identified.

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

```
git clone --branch session-21-recovery-and-ask . && python3 tools/test_local_sql.py
    179 passed in 93.84s              at 666fe43, clean checkout

python3 tools/test_local_sql.py   TZ=America/New_York   179 passed   at 6225164
python3 tools/test_local_sql.py   TZ=UTC                179 passed   at 6225164
PYTHONPATH=. python3 tools/validate_layout.py           41 passed, 0 warnings, 0 failed
PYTHONPATH=. python3 tools/check_invariants.py --core core   INVARIANTS: ALL PASS   at 092c77b
PYTHONPATH=. python3 tools/update_features.py --strict  206 passed, 0 failed, 0 errors,
                                                        55 skipped of 261   at 092c77b
PYTHONPATH=. python3 tools/check_freshness.py --no-log  fresh=0 stale=4 misconfigured=1
                                                        never_seen=12 unmonitored=6  [exit 1]
```

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
| Ask spend | **partial** | partial | no | no |
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
