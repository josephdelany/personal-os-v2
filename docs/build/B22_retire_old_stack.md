# B22 — Retire the old stack, reclaim the storage, load the legacy atoms (migration 0064)

**What this is.** OQ-17 and OQ-29 closed. Once B13's importers feed the new stack, the
old repo (`josephdelany/Personal-OS`), its 8 `pg_cron` jobs, and its tables
(`public.signals`, `events`, `transactions`, `checkins`, `intraday`, `locations`, …
~174 MB) are redundant. This session cuts over, verifies nothing in the new stack reads
`public.*` anymore, retires the old jobs, archives the tables, reclaims the space, and —
now that the ceiling allows it — loads the legacy Parquet atoms that named analyses
need (ADR-0028's two loader defects fixed first). One session. **Irreversible steps
require Joe's explicit "yes" in the session, listed below.**

**ADRs:** ADR-0079 (cutover order and the archive), ADR-0080 (which legacy streams are
loaded as atoms and why).

## Order (each step has a proof before the next)
1. **Read audit.** `grep -rn "public\." migrations/ tools/ lib/` → every remaining
   reader of a legacy table listed. Each is either migrated to atoms/panel (B13 made
   that possible) or explicitly kept with a reason. `panel.py` must build from atoms +
   `legacy_daily` only; `get_timeline`, `search_record`, `get_entity`, `get_state.week_money`
   move to atoms/links. Proof: the grep returns only the migration files that *created*
   the old readers (historical), and a new test `test_ADR_0079_no_live_reader_of_public_tables`.
2. **Parity.** For 30 random days, `get_timeline(day)` before and after the cutover
   must return the same `n` and the same set of `(kind, text)` — paste the diff (should
   be empty; any difference is a bug in B13, fixed before continuing).
3. **Old jobs.** `SELECT jobid, jobname, schedule FROM cron.job` pasted; **Joe says
   "yes, unschedule"** → `cron.unschedule(jobid)` for each of the 8; the old repo's
   GitHub Actions disabled by Joe (list the exact workflow names for him). The keepalive
   is the *new* stack's (already the case).
4. **Archive, then drop.** For each legacy table: `COPY … TO STDOUT` → Parquet in the
   local archive (`_legacy_snapshot/` already has a manifest; extend it with sha256 and
   row counts; the archive itself never enters git), verify row counts match, then
   `DROP TABLE` — **only after Joe's explicit "yes, drop <table>"** per table (the guard
   hook blocks DROP; Joe runs the statement himself from the printed list, or grants the
   session a one-time exception recorded in PROGRESS). `pg_database_size` before/after
   pasted.
5. **Legacy atoms load (OQ-29).** Fix the two ADR-0028 loader defects (per-night sleep
   sessionization for the wake-day rule; `evidence_span` for dedup-secondary tables;
   the dead `txn_amount` registry row; the hardcoded exclusion constants) with tests,
   then load from Parquet **only the streams a named analysis needs** — ruling: the
   sleep intervals, HRV windows, RHR, respiratory rate, wrist temperature, SpO2, steps,
   HR samples *aggregated to hourly* (not 49,801 raw rows), body composition, calendar
   events, Chrome and YouTube history (the last two power search and entities). Sized
   against the new ceiling (paste the estimate before loading; must leave ≥ 150 MB
   free). Every loaded atom carries `raw_capture_id` of a per-source-file `file_import`
   capture (B13's model) — INV-1 holds for history too.
6. **Panel rebuild** from atoms; `legacy_daily` retained as the fallback for days no
   atom covers; parity check of the panel before/after (count per metric per year).

## Tests
```
test_ADR_0079_no_live_reader_of_public_tables
test_ADR_0079_timeline_parity_on_30_days
test_ADR_0028_sleep_night_straddling_0400_is_one_wake_day
test_ADR_0028_dedup_secondary_tables_have_evidence_span
test_ADR_0080_hourly_hr_aggregation_is_point_in_time
test_INV_1_every_legacy_atom_references_a_file_import_capture
test_ADR_0080_storage_headroom_at_least_150mb_after_load
```

## Done when
Every step's proof pasted; Joe's per-table "yes" quoted in PROGRESS; `pg_database_size`
before/after; the old repo's workflows disabled (Joe confirms); ADR-0079/0080; OQ-17,
OQ-20, OQ-29 closed; PROGRESS + WHAT I DID NOT DO.
