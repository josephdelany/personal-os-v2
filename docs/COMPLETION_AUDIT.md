# Project completion audit

Re-checked **2026-09-09** against the live database, after two adversarial review rounds. The objective remains the whole Personal
OS described in `docs/THE_FILE.md`, the specifications, the roadmap gates, and the B0–B23 /
L0–L8 build orders. This is an inventory, not a completion certificate. Earlier PROGRESS
entries are historical evidence; they do not prove current operation.

## What changed since the 2026-09-08 audit

| Claim in the previous audit | Status now |
|---|---|
| "current DB authentication fails" (SQLSTATE `28P01`) | **Resolved.** Connection succeeds; OQ-46 closed. |
| "94 passed, 5 failed, 104 errors" | **Resolved.** `206 passed, 0 failed, 0 errors, 55 skipped of 261 collected`, exit 0, against the live database; the 55 skips all execute on the disposable local server (127 passed there, verified under three timezones). The original failures were entirely the credential. |
| "no fresh DB evidence this turn" for invariants | **Run live: ALL PASS.** RULE-04 remains PENDING by the Phase-5 deferral (OQ-22), printed as pending, not counted as passed. |
| "September 6 handoff reports stale feeds" — historical | **Measured, and worse than reported.** See below. |

## The capture position, measured

Device-side capture stopped on **2026-07-28** and has not resumed. `public.intraday`
(`hr`, `hrv_window`, `spo2`, `sleep_stage`, `resp_rate`, `walking_*`), the browser-history
feed and OwnTracks all stopped within two days of each other. The `apple_sleep` / `apple_hrv`
/ `apple_circadian` / `apple_vitals` signal feeds are derived from `intraday` and stopped with
their input. Server-side pulls (`weather`, `gmail`, `calendar`, both keepalives) never stopped,
which is why `ops.runs` stayed green for 43 days.

`tools/check_freshness.py`, run 2026-09-09 before any repair:

```
freshness as of 2026-09-09  fresh=0 stale=4 misconfigured=1 never_seen=12 unmonitored=6
```

**Zero of seventeen monitored metrics are fresh.** That number, not the test count, is the
honest headline for the project's state.

The gap is **recoverable but not recovered**: Apple Health holds the samples on the phone and
Takeout holds the browser history. Nothing has been imported yet.

## Inventory

| Required outcome | Current evidence | Remaining proof / work |
|---|---|---|
| Continuous unattended capture | Measured: stopped 2026-07-28; 0/17 metrics fresh. `health_auto_export` posts daily but only aggregates, not intraday samples | Restore device-side capture (OQ-50); import the gap from Apple Health + Takeout; demonstrate a real unattended day |
| Freshness detection | **Built.** `tools/check_freshness.py`, REQ-NFR-005..014 authored, 14 tests, daily `freshness` workflow (ADR-0060) | Gate 4 still open: 0/17 sources inside their limit, and the withheld-feed demonstration has not been run. `never_seen` can still hide a naming mismatch a string comparison cannot detect (OQ-51) |
| File-drop recovery path | **Built.** Migration 0051, three importers, 28 tests incl. a 300 MB memory bound and a three-timezone idempotency proof (ADR-0057/0058/0059) | Migration 0051 **not applied to production**; no real file imported; institution headers unverified (OQ-49) |
| Reliable operational status | `tools/status.py` repaired earlier; invariants pass live; suite green | Source-level (not metric-level) freshness limits remain unspecified |
| Canonical metric wiring | **Two defects found.** `steps` wired to a source dead since 2026-06-23 while a live one exists; `screen_active_hours` wired to a metric that has never existed | OQ-51 — needs Joe's ruling per metric before any rewiring |
| B0–B10 backend | Committed migrations, engines, historical tests; suite green | Re-verify live schema/jobs; resolve disclosed limitations incl. recommendation interval assumptions |
| B11 Ask | Draft migration 0049 (untracked); calendar/descriptive paths and computation reads tested; its fixture now runs on the disposable server, where it had begun timing out against Supabase | Deterministic operations, provenance, replay, tier and numeral enforcement; planner; budget/egress; all B11 acceptance examples. Placeholder money/contrast branches must be **replaced, not shipped** |
| B12 nutrition | Build order only | Cache-first resolution, interval nutrients, egress client, acceptance checks |
| B13 importers | **This session.** See above | Live apply; a real import; panel `src` distribution before/after |
| B14 entities and links | Build order only | Resolution, cross-source links, correction precedence |
| B15 period and compare | Build order only | Both RPC contracts |
| B16 voice/photo capture | Build order only | Media storage, extraction/verifier, budget, real capture proof |
| B17 finance | Build order only | Gmail tier, recurrence, budgets, forecast, reconciliation, the canonical-transaction dedupe engine B13 deliberately did not build |
| B18 workouts | Build order only | Derived measures, rest-day presence |
| B19 inference remainder | Build order only | Registered methods, calibration, trials |
| B20 narration/ontology | Build order only | Vocabulary enforcement, closed taxonomies |
| B21 body/sleep/context | Build order only | Author missing requirements, implement, verify |
| B22 retirement | Old-stack freeze binding | Replacement must first capture for real; per-table approval required |
| B23 completion instrument | Absent | Requirement-by-requirement evidence; `open = 0` |
| L0–L8 interfaces | `app/index.html` exists; deployed interface unverified | Verify every screen against real RPCs |
| Roadmap Gates 0–8 | Gate 0 closed. Gate 4 mechanism built, gate open | Audit each gate against live evidence |

## The honest summary

654 requirements exist. The test suite is green and the invariants hold. **Neither fact means
the system is working**, because the thing it is for — collecting a life, continuously — has
been stopped since 2026-07-28 and 0 of 17 monitored metrics are fresh. The most valuable work
available is not the next build order; it is restoring capture and importing the gap while it
is still recoverable.
