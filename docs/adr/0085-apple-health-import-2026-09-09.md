# ADR-0085 — The 2026-09-09 Apple Health import, and the two defects it exposed

Status: accepted
Date: 2026-09-09
Authorised by: Joe, in session, for `/Users/default/Downloads/export.zip` from 2026-07-01.

## What was written

One `core.raw_captures` row (`source='file_import'`, capture_id
`bcc2795a-e454-47cc-8a14-ebe669bf6fff`) and **33,355 atoms** across 25 metric keys,
covering 2026-07-01 .. 2026-09-09. `core.atoms` went 5 -> 33,360. `check_invariants.py
--core core`: **ALL PASS**, orphan atoms 0 (INV-1).

Rejected, with reasons, from 659,000 parsed records: 534,115 outside the window,
91,430 of unmapped types, 32 workouts deferred to B18, 18 headphone-exposure readings
out of range, 1 sleep segment with no duration, 6 in-file duplicates.

Dedupe is sound. True duplicates — same metric, same instant or interval, same value,
same device — number **0**. Seven cross-device same-instant collisions were correctly
kept as distinct rows: the Watch and the iPhone each recorded the same flight climbed
one second apart, and those are two observations, not one observation twice.

## Defect 1 — RULE-08 is violated for every accumulating quantity

Apple exports steps, distance, flights, active energy and exercise minutes as
*interval* records with a start and an end. The importer stores `occurred_at = start`
and leaves `valid_interval` NULL. Sleep, by contrast, stores the interval correctly.

"3 steps" is not a fact about an instant. It is a fact about a six-minute window, and
RULE-08 exists to say so.

The consequence is worse than the imprecision. **Cross-device overlap is currently
undetectable in SQL.** Two devices reported `steps` on the same days until 2026-08-21
(Watch 2,130 rows; iPhone 1,901). Whether a daily sum double-counts depends on whether
their intervals overlap, and with `valid_interval` NULL there is nothing to compare —
an overlap query returns 0 because it has no operand, not because the answer is no.
A previous version of this analysis read that 0 as a clean result. It is a false
negative and must not be cited as evidence that daily sums are safe.

Nothing is lost. Every end timestamp is preserved verbatim in `evidence_span`
(`end=...`) on all 14,640 affected rows. The repair is forward-only: a corrected
re-derivation that appends rows with `valid_interval` populated and `supersedes` set.
`core.atoms` is append-only (INV-2, RULE-02) and no UPDATE is permissible.

Until that lands, **no summed daily total for a multi-device metric may be published**.
See OQ-54.

## Defect 2 — the capture loss is the Watch, and it is dated

`check_freshness.py` now runs against real rows: fresh 9, stale 17, never_seen 11,
unmonitored 6. It was 0 fresh before this import. The staged loss is now dated from
data rather than inferred:

| date | what stopped | source |
|---|---|---|
| 2026-07-22 | the three morning check-ins | Shortcut |
| 2026-07-28 | `sleep_asleep_min`, `sleep_inbed_min` | Watch |
| 2026-08-08 | `wrist_temperature_c` | Watch |
| 2026-08-14 | `respiratory_rate_bpm`, `sleep_awake/core/deep/rem_min` | Watch |
| 2026-08-21 | `active_energy_kcal`, `exercise_minutes`, `heart_rate_bpm`, `hrv_sdnn_ms`, `resting_hr`, `spo2_pct` | Watch |

Everything still fresh is iPhone-sourced: steps, flights, the four walking-gait
metrics, distance, headphone exposure. **Every stale metric is Watch-sourced.** The
diagnosis is therefore not "capture stopped" but "the Watch stopped syncing health
data, in stages, ending 2026-08-21, while the phone kept working."

This also invalidates a reading of the step counts. September averages ~2,200 steps
against July's ~3,800. That is iPhone-only capture replacing iPhone-plus-Watch
capture, not a collapse in activity. Any trend answer spanning 2026-08-21 is
confounded by the instrument, not by behaviour.

## The sleep definitions stay separate

Five distinct sleep concepts are now in the data and they are NOT interchangeable:
`sleep_asleep_min` (16 atoms, 3 days), `sleep_awake_min`, `sleep_core_min`,
`sleep_deep_min`, `sleep_rem_min` (23 days each), `sleep_inbed_min` (panel only), and
`sleep_minutes` — registered with a 3-day limit and **never observed under that key**.
They are not summed, mapped onto each other, or collapsed into a single duration.
Which of them means "how long did I sleep" is OQ-48 and remains Joe's ruling.

## What this does not do

It does not backfill before 2026-07-01, does not touch the legacy `public.*` tables,
and does not make `analysis.f_daily_panel` read these atoms. The panel still reads its
own sources; wiring it is a separate unit gated on OQ-54.
