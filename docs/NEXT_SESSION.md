# Checkpoint

Rewritten 2026-09-09. One compact checkpoint, per the execution reset. Historical narrative
lives in `ops/PROGRESS.md`; this file is state, not story.

## Current unit

**B11.1 Ask — remaining operation contracts.** Four acceptance gaps closed (commit `db815e0`);
`spend`, `trend`, `search`/`entity` and executor read/write separation still open.

## Last command and result

```
python3 tools/test_local_sql.py            TZ=America/New_York   169 passed in 71.90s
python3 tools/test_local_sql.py            TZ=UTC                169 passed in 70.50s
PYTHONPATH=. python3 tools/validate_layout.py                    41 passed, 0 warnings, 0 failed
PYTHONPATH=. python3 tools/update_features.py --strict           206 passed, 0 failed, 0 errors,
                                                                 55 skipped of 261   (at 092c77b)
PYTHONPATH=. python3 tools/check_invariants.py --core core        INVARIANTS: ALL PASS
PYTHONPATH=. python3 tools/check_freshness.py --no-log            fresh=0 stale=4 misconfigured=1
                                                                  never_seen=12 unmonitored=6  [exit 1]
```

The production suite predates the last two commits (both local-SQL-only changes; the
production job skips those tests). Rerun it at the next integration checkpoint, not because
context compacted.

## Branch and commits

`session-21-recovery-and-ask`, based on `b606c64` (main).

```
db815e0  B11.1: compare cross-metric; effect direction + as_of; contrast window disclosure
3077620  B11.1 (partial): compare, contrast, spend replace placeholder branches
092c77b  Engines take schema names as parameters; panel attention fills (ADR-0061)
844b7e5  Gate-4 mechanism: freshness is data, not job (REQ-NFR-005..014; ADR-0060)
abe8b7e  B13: drop-folder importers (migration 0051; ADR-0057/0058/0059)
```

## Status by field — never collapsed into one word

| Deliverable | Implemented | Behaviourally tested | Deployed | Observed on real data |
|---|---|---|---|---|
| B13 importers | yes | yes (fixtures) | **no** — 0051 unapplied | **no** — no file dropped |
| Freshness checker | yes | yes | **no** — workflow uncommitted to main | partly — one live read |
| Panel attention fill | yes | yes | no | no |
| Ask compare/effect/contrast | yes | yes (disposable SQL) | no | no |
| Ask spend | partial | partial | no | no |
| B11.2 planner | **no** | no | no | no |

A fixture pass never fills the last two columns.

## Unresolved failures

None failing. Open *gaps* (not failures) are listed under the next unit.

## Next exact command

```
python3 tools/test_local_sql.py --tests tests/test_ask_operations.py
```
after implementing `trend`'s rolling-28-day output — the next bounded piece of B11.1.

## Held on Joe — batched

| # | Action | Why it is held | What it unblocks |
|---|---|---|---|
| 1 | `PYTHONPATH=. python3 tools/run_migration.py --core core --ops ops --only 0051 --verify --commit` | Production write; the environment's permission classifier refused it and I did not work around it | Every import path; `file_import` is not a valid capture source until then |
| 2 | Apple Health export + Google Takeout (Chrome/YouTube only) into `~/PersonalOS_Drop/` | Needs your devices | Recovery of the 43-day gap (2026-07-28 →), which is recoverable *now* and not later |
| 3 | Check Health Auto Export's metric selection and whether OwnTracks still runs | Needs your phone (OQ-50) | Live capture; the import recovers history but does not restart the feed |
| 4 | Rule OQ-51: is `apple_watch.steps` the same measurement as `health_history.steps`? Is `screen_active_hours` the same as `attention.screen_active_min` (and is /60 the right conversion)? | Claims about data; `CLAUDE.md` forbids a session deciding these | Canonical `steps` has been blind since 2026-06-23; `screen_active_hours` has never had a value |
| 5 | Rule OQ-48: the four `screen_*` session/binge thresholds | Definitions live in the old stack's code, which is not in this repository | Re-deriving those metrics from atoms |
| 6 | Rule OQ-53: is the panel's day axis the 04:00-ET subject day or the UTC date? | Affects every metric, not only attention | Removing the boundary seam at the old/new stack join |
| 7 | Confirm the GitHub default branch (`v2-day1` vs `main`) — OQ-47 | Repository setting | Whether scheduled jobs run the current code |

Items 1–3 are the ones that matter: **0 of 17 monitored metrics are fresh**, and no amount of
code changes that.

## Next unit after B11.1

Per the reset's build track, stage 3 pulls only the shared egress/budget prerequisites from
B12/B16 that B11.2 depends on — numeric build order is not a dependency schedule.
