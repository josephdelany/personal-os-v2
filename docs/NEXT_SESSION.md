# Checkpoint

Reconciled against Git 2026-09-09. Branch `session-21-recovery-and-ask`, HEAD `8793a17`,
based on `b606c64` (main). Nothing pushed; nothing applied to production.

## Active unit

**M2 — deterministic Ask. Open.** An adversarial review of `db815e0..45535eb` found the
earlier closure claim unsupported; it was withdrawn in `eac122a`. Every defect the review
executed is now repaired with the reproducing case as its acceptance test (`316f5c8`,
`3b65fa5`). M2 still does **not** close: two contracts below remain open.

## Next executable action

Re-run the M2 adversarial review against `8793a17` — the repairs have not themselves been
adversarially reviewed, and the last two rounds each found defects introduced by the previous
round's fixes. Command: the `reviewer` subagent scoped to
`db815e0..8793a17`, `migrations/0049_ask_core.sql`, `tools/engines/ask_planner.py`,
`tools/ask.py`, `lib/egress.py`.

## CLOSED — capability and evidence

| Capability | Evidence | Commit |
|---|---|---|
| Drop-folder importers, migration 0051 | 28 tests; 300 MB memory bound; idempotency across 4 session timezones | `abe8b7e` |
| Feed freshness, REQ-NFR-005..014 | 14 tests; live run `fresh=0 stale=4 misconfigured=1 never_seen=12 unmonitored=6` | `844b7e5` |
| Schema-parameterised engines (ADR-0061) | OQ-52 closed without amending RULE-01 | `092c77b` |
| Ask compare / effect / contrast / trend / search / entity | 77 operation tests | `db815e0` `3da49ee` `6225164` |
| Ask review repairs — crash, units, tier language, timezone replay, traces, verifier, ceiling | each with the reproducing case (ADR-0065) | `316f5c8` `3b65fa5` |
| Shared egress + neuron budget, migration 0052 (ADR-0063) | 11 tests; chain dry-run 418 statements | `497ff85` |
| Language planner + Ask client (ADR-0064) | 16 tests; deterministic fallback proven | `8793a17` |
| M0 — branch runnable from a clean checkout | fresh clone ran the suite: 179 passed | `666fe43` |

## ACTIVE — remaining M2 acceptance cases

1. **`spend`'s merchant/category contract.** Descriptor-scoped and disclosed (ADR-0062).
   Merchant semantics, category rollups, top merchants, ATM destination-unknown
   (REQ-FIN-051), canonical-transaction dedupe (REQ-FIN-043..048) and netting linked
   transfers (REQ-FIN-050) are **OPEN**, not deferred. Blocked on B14's REQ-FIN-070..093
   cascade. A recorded dependency permits switching tasks; it does not complete the
   requirement.
2. **Historical replay after corrections.** The as-of cutoff is proven; an answer holding
   steady after a correction to an EARLIER day is not, because `analysis.panel` is rebuilt
   wholesale and carries no per-observation `recorded_at` (OQ-45). **OPEN.**
3. **`get_entity` ignores the caller's `as_of`.** Now disclosed in the result
   (`as_of_matches_request`) rather than silently contradictory. Fixing it changes a B4/B14
   API. **OPEN.**
4. **The repairs are unreviewed.** Two review rounds each found defects introduced by the
   previous round's fixes. Until round three runs, "repaired" is a claim.

## BLOCKED — dependency, owner, affected capability

See the capture packet below. Nothing in M2–M5 is blocked by them.

## LIVE — what is actually deployed and observed working

**Deployed from this branch: nothing.** Verified against production this session:

- migration 0051 — **not applied**; neither the `file_import` enum label nor its registry rows exist
- migration 0052 — not applied
- migration 0049 (Ask) — not applied; every Ask result is from a disposable server running the migration text
- the `freshness` workflow — not on `main`, so it has never run
- `lib/egress.py` — **no call has ever been made**; every test injects a transport

Observed working on real data: the freshness checker's single live read, which reported
**0 of 17 monitored metrics fresh**. That number is unchanged by everything above.

## Evidence, with the revision it belongs to

```
python3 tools/test_local_sql.py   TZ=America/New_York   231 passed    at 3b65fa5
python3 tools/test_local_sql.py   TZ=UTC                231 passed    at 3b65fa5
python3 tools/test_local_sql.py   TZ=Asia/Tokyo         231 passed    at 3b65fa5
PYTHONPATH=. python3 tools/validate_layout.py           41 passed     at 8793a17
PYTHONPATH=. python3 tools/run_migration.py --core core_dryrun --ops ops_dryrun
                                                        418 statements, rolled back
```

Production-suite evidence (`206 passed, 0 failed, 0 errors, 114 skipped of 320`) belongs to
`092c77b` and is **stale** for the Ask work since. Due at the M2 integration boundary — which
is after the review in "next executable action", not before.

## Status by field — never collapsed

| Deliverable | Implemented | Behaviourally tested | Deployed | Observed on real data |
|---|---|---|---|---|
| B13 importers | yes | yes (generated fixtures) | no | no |
| Freshness checker | yes | yes | no | one live read |
| Ask operations | yes | yes (disposable server) | no | no |
| Ask spend | partial, disclosed | for what it measures | no | no |
| Shared egress + budget | yes | yes (injected transport) | no | **no call ever made** |
| Language planner | yes | yes (injected transport) | no | **no call ever made** |

---

## 2026-09-09 late — FIRST REAL DATA. Read this first after any compaction.

**Migration 0051 is APPLIED to production.** Joe ran it; invariants ALL PASS; `file_import`
is a valid capture source; registry 23 → 43 metrics, 17 → 37 monitored. This is the first
thing actually deployed from this branch.

**A real Apple Health export exists at `/Users/default/Downloads/export.zip`** — 14 MB zipped,
309 MB `export.xml`. Dry run (writes nothing) succeeded:

```
PYTHONPATH=. python3 tools/import_drop.py --file /Users/default/Downloads/export.zip --since 2026-07-01
  status imported, records_parsed 33361, atoms_written 33355, duplicates_skipped 6
  period 2026-07-01 .. 2026-09-09
  counters: type_not_mapped 91430, outside_window 534115,
            out_of_range:headphone_audio_exposure_db 18,
            sleep_segment_without_duration 1, workout_deferred_to_B18 32
```

**NEXT COMMAND — needs Joe (production write):**
```
PYTHONPATH=. python3 tools/import_drop.py --file /Users/default/Downloads/export.zip --since 2026-07-01 --commit
```

**Correction to earlier reporting, important.** "Capture stopped 2026-07-28" was true of
`public.intraday` only. `apple_watch` has rows on 29 of the last 30 days. The real pattern is a
STAGED loss: intraday 07-28; `sleeping_wrist_temp` 08-08; all `sleep_*` and `respiratory_rate`
08-14; `hr`/`hrv_sdnn`/`rhr`/`spo2`/`active_energy`/`exercise_min` 08-21; `withings` 08-23;
steps + walking metrics still current to 09-08. That looks like Health Auto Export's metric
selection shrinking over three weeks, not one break — check the phone.

"0 of 17 fresh" was true of the registry's CANONICAL names and misleading about whether data
arrives: live data sits under `apple_watch.hrv_sdnn` while the registry monitors `hrv_sdnn_ms`.
That is OQ-51, and it made the monitoring tell a worse story than the truth.

**Open from this import, to check before/after committing:**
- `type_not_mapped` 91430 — many HealthKit record types are not in the importer's HK table.
  Worth listing the top unmapped types and deciding which to add (a real gap, not a bug).
- The four `sleep_*` metric names 0051 registered already exist in the panel from the old
  stack, derived differently (old = its own calculation; new = sum of Apple Health stage
  segments). Same class as OQ-51 — verify before trusting a joined series.
