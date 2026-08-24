# PHASE 2 — LEGACY BACKFILL PLAN (atoms)

**Status: PLAN ONLY. No backfill executed. No atom written.**
Session of 2026-08-23 (Phase 2, session 4), by Joe's instruction: plan the backfill,
do not run it. The re-runnable, auditable map is `tools/backfill_map.py`; this document
is the narrative and the judgement calls. Gate-2 reconciliation semantics are ADR-0025.

The archive being mapped (verified against the two manifests under `_legacy_snapshot/`,
which carry a per-table row count and `sha256`):

- **Supabase** `public` schema — **426,282 rows / 34 tables** (`supabase_manifest.json`)
- **Local sources** (`personal_os.db`, `health_raw.sqlite`, `backup_2026-07-17/csv`) —
  **384,651 rows / 29 tables** (`manifest.json`)
- **Grand total — 810,933 rows / 63 tables.**

---

## 1. THE GATE-2 PROBLEM, STATED PLAINLY

ROADMAP Gate 2: *"Backfilled row count matches the Parquet archive."* Read as equality
(`atoms == 810,933`) it is **impossible without breaking the constitution**:

- **~111,113 rows (17 tables) are the OLD STACK's derived outputs** (`signals`, `insights`,
  `hypotheses`, `inferred_events`, `forecast_log`, `coach_recommendations`, baselines,
  anomalies, …). Making them atoms would fabricate a `raw_captures` lineage they never
  had (**INV-1**), and store *inferred* values in the same table as measured ones as
  though they were observed (**INV-5, RULE-01**).
- **~72,108 rows (6 tables) are cross-archive duplicates** — the same facts captured in
  two snapshots (`csv__events` ≈ `events`; `csv__transactions` + `pos__spend_transactions`
  ≈ `transactions`; `csv__signals` ≈ `signals`; `csv__insights` ≈ `insights`;
  `csv__ingest_status` ≈ `ingest_status`). A backup table that duplicates a canonical
  Supabase table is bucketed OVERLAP by *what it duplicates*, not the canonical's own
  nature. Ingesting both sides double-counts.
- **~2,639 rows are reference/registry data** (entities, taxonomies, `metric_catalog`) —
  they become `core.entities` / `metric_registry`, not atoms.
- **7 tables are empty.**

**Ruling (Joe, this session): reconciliation, not equality (ADR-0025).** Gate 2 passes
when **every archived row is accounted for** — either mapped to an atom *or* excluded
with a recorded reason — and the per-table sums are exact. `tools/backfill_map.py`
proves the sums (they total 810,933 with zero unaccounted rows).

## 2. RECONCILIATION SUMMARY (executed — `python3 tools/backfill_map.py`)

| bucket | tables | rows | disposition |
|---|--:|--:|---|
| **ATOM** (clean) | 13 | 135,362 | one `atoms.kind`, no judgement |
| **ATOM_J** (judgement) | 11 | 489,696 | an atom, but needs a schema split or a kind boundary call |
| **OVERLAP** (duplicate) | 6 | 72,108 | same facts as another archive snapshot — exclude the dup |
| **ENTITY** | 5 | 2,237 | reference → `core.entities` (Phase 4), not atoms |
| **REGISTRY** | 2 | 402 | → `metric_registry` / category reference |
| **DERIVED** (leave out) | 17 | 111,113 | old-stack inference/output; no `raw_captures` lineage |
| **OPERATIONAL** | 2 | 15 | ingest status / prompt queue |
| **EMPTY** | 7 | 0 | 0-row tables |
| **sum** | **63** | **810,933** | ✓ = 426,282 + 384,651 |

**Upper bound** on atom-eligible rows (ATOM + ATOM_J): **625,058** — an upper bound only,
because `intraday` fans *out* to many atoms per row while `events` sub-types and
`pos__daily_health` rollups drop *out*; the true atom count is knowable only after the
per-metric split is written (§4, §6). Explicitly excluded with a recorded reason:
**185,875**.

## 3. MAPS CLEANLY — 13 tables, 135,362 rows

Each maps to exactly one `atoms.kind` (ADR-0023); no boundary call.

| table(s) | kind |
|---|---|
| `locations` | `location_fix` |
| `health__hr_samples`, `health__resp_rate`, `health__rhr`, `health__spo2`, `health__wrist_temp`, `health__walking_hr` | `vital_sample` |
| `health__hrv_windows` | `heart_rate_variability` |
| `health__sleep_intervals` | `sleep` |
| `pos__body_composition` | `body_measurement` |
| `pos__calendar_events` | `calendar_event` |
| `pos__chrome_history` | `web_visit` (+ `website` entity) |
| `pos__youtube_history` | `media_play` (+ `media_channel` entity) |

## 4. NEEDS JUDGEMENT — 11 tables, 489,696 rows (this is where the ruling effort goes)

- **`intraday` (250,069)** — the largest single table. 11 columns, a *multi-metric*
  sample stream (steps, distance, flights, active energy, …). One archived row is not
  one atom: it fans out to several `activity_sample` atoms (and possibly `vital_sample`),
  each with a `metric_key`. **Row count will not be preserved 1:1 here** — this is the
  strongest reason Gate 2 cannot be a row-equality check.
- **`events` (65,922)** — a mixed raw event stream from the old stack. Needs a per-type
  split into the right kinds before any land as atoms; some sub-types may themselves be
  derived and drop out. Requires reading the actual schema (deferred to execution).
- **The five gait series (~170,285)** — `walking_speed`, `walking_step_length`,
  `walking_double_support`, `walking_asymmetry`, `walking_steadiness`. `vital_sample`
  vs `activity_sample` is a boundary call (ADR-0023 put `walking_hr` under
  `vital_sample`; the gait metrics were not explicitly placed). Leaning `vital_sample`
  with a `metric_key` each, but this is O-Q2 territory.
- **`pos__daily_health` (2,370)** — MIXED. Only the `env_db` / `headphone_db` columns
  are `environment_sample` atoms; the rest are *daily rollups* = future
  `derived_measures` (ADR-0023 guess #5), not atoms. Column-level split needed.
- **`transactions` (1,045)** — `transaction`, and the **canonical** of the three tx
  snapshots (see §5). `vo2max` (2) — sample vs derived. `checkins` (3) — `self_report`
  vs the spec-cited `mood` kind, split by metric (O-Q1).

## 5. EXCLUDE, WITH REASON

**OVERLAP — 6 tables, 72,108 rows (duplicates of a kept table):**
`csv__events` (older snapshot of `events`), `csv__transactions` + `pos__spend_transactions`
(same charges as `transactions`), `csv__signals` (dup of `signals`), `csv__insights` (dup
of `insights`), `csv__ingest_status` (dup of `ingest_status`). **Uniform rule:** a backup
table (`csv__*`, `pos__spend_transactions`) that duplicates a canonical Supabase table is
bucketed OVERLAP by *what it duplicates*, regardless of the canonical's own class — so the
duplicate is counted once as a duplicate, not split between OVERLAP and DERIVED at the
margin. The canonical is the Supabase copy (most recent, largest). **Open verification for
execution:** confirm the duplicate tables are subsets of their canonical (by natural key /
hash), not partially-disjoint — if disjoint rows exist, they are kept, not silently dropped.

**DERIVED — 17 tables, 111,113 rows:** old-stack computed outputs. Excluded from atoms
categorically (INV-1/INV-5/RULE-01). If any are ever wanted, they re-enter as Phase-5/6
`derived_measures` computed by *our* owned jobs from *our* atoms — never imported as
someone else's numbers.

**ENTITY / REGISTRY — 7 tables, 2,639 rows:** reference data → `core.entities` (Phase 4
resolution) and `metric_registry`; not observations.

**OPERATIONAL — 2 tables, 15 rows / EMPTY — 7 tables, 0 rows:** nothing to ingest.

## 6. WHAT THE EXECUTION SESSION STILL OWES (design, not yet decided)

1. **INV-1 lineage for legacy atoms.** Every atom must reference a `raw_captures` row.
   Backfilled atoms have no original capture. Proposal (for a ruling): create one
   `raw_captures` row per source *table load*, `source = 'legacy_archive'`, carrying the
   manifest's `sha256` and row count as auditable provenance — legitimate lineage, not a
   fabricated payload. The alternative (one capture per source row) multiplies
   `raw_captures` by ~600k. **Not decided here.**
2. **Bitemporal stamping.** `occurred_at` comes from the source row; `recorded_at` for a
   backfill is the archive/ingest instant, **not** `now()` faked as original capture
   time; `subject_day` is computed by the ADR-0019 rule with its `rule_version`.
3. **`trust_level`.** Own-device health/location = `trusted`; merchant strings, web
   titles, and any model-extracted field = `untrusted` (ADR-0020).
4. **The `intraday`/`events` fan-out** means the *atom* count is knowable only after the
   per-metric split is written — Gate 2's reconciliation is per-source-table (rows in →
   atoms out + excluded, with reason), never a single global equality.
5. **A backfill run must be idempotent and re-runnable** (write to `ops.runs`), and must
   be a dry-run-on-a-copy-first migration like every other (`run_migration.py` pattern).

## 7. FULL PER-TABLE MAP

Generated by `python3 tools/backfill_map.py --md` (re-run to verify; the tool asserts
the buckets sum to 810,933):

| source | table | rows | bucket | target / reason |
|---|---|--:|---|---|
| health_raw.sqlite | `health__hr_samples` | 49,801 | ATOM | vital_sample |
| personal_os.db | `pos__youtube_history` | 37,250 | ATOM | media_play (+media_channel entity) |
| health_raw.sqlite | `health__sleep_intervals` | 20,248 | ATOM | sleep |
| personal_os.db | `pos__chrome_history` | 17,422 | ATOM | web_visit (+website entity) |
| health_raw.sqlite | `health__hrv_windows` | 4,369 | ATOM | heart_rate_variability |
| health_raw.sqlite | `health__resp_rate` | 3,959 | ATOM | vital_sample |
| health_raw.sqlite | `health__spo2` | 1,376 | ATOM | vital_sample |
| personal_os.db | `pos__calendar_events` | 364 | ATOM | calendar_event |
| supabase | `locations` | 282 | ATOM | location_fix |
| health_raw.sqlite | `health__rhr` | 117 | ATOM | vital_sample |
| health_raw.sqlite | `health__walking_hr` | 100 | ATOM | vital_sample |
| health_raw.sqlite | `health__wrist_temp` | 64 | ATOM | vital_sample |
| personal_os.db | `pos__body_composition` | 10 | ATOM | body_measurement |
| supabase | `intraday` | 250,069 | ATOM_J | activity_sample (multi-metric split; some vital_sample) |
| supabase | `events` | 65,922 | ATOM_J | mixed raw event stream — per-type split needed |
| health_raw.sqlite | `health__walking_speed` | 51,954 | ATOM_J | gait |
| health_raw.sqlite | `health__walking_step_length` | 51,954 | ATOM_J | gait |
| health_raw.sqlite | `health__walking_double_support` | 45,169 | ATOM_J | gait |
| health_raw.sqlite | `health__walking_asymmetry` | 20,993 | ATOM_J | gait -> vital_sample or activity_sample |
| personal_os.db | `pos__daily_health` | 2,370 | ATOM_J | env cols -> environment_sample; rollups derived |
| supabase | `transactions` | 1,045 | ATOM_J | transaction — canonical of 3 tx snapshots |
| health_raw.sqlite | `health__walking_steadiness` | 215 | ATOM_J | gait |
| supabase | `checkins` | 3 | ATOM_J | self_report (+ spec-cited mood) — split by metric |
| health_raw.sqlite | `health__vo2max` | 2 | ATOM_J | vital_sample vs derived measure |
| backup_2026-07-17 | `csv__events` | 59,183 | OVERLAP | older snapshot of supabase.events |
| backup_2026-07-17 | `csv__signals` | 10,830 | OVERLAP | dup of supabase.signals (derived) |
| backup_2026-07-17 | `csv__transactions` | 1,030 | OVERLAP | dup of supabase.transactions |
| personal_os.db | `pos__spend_transactions` | 1,011 | OVERLAP | transaction dup of supabase.transactions |
| backup_2026-07-17 | `csv__insights` | 52 | OVERLAP | dup of supabase.insights (derived) |
| backup_2026-07-17 | `csv__ingest_status` | 2 | OVERLAP | dup of supabase.ingest_status (operational) |
| supabase | `entity_occurrences` | 902 | ENTITY | entity<->event links -> Phase-4 |
| supabase | `content_taxonomy` | 661 | ENTITY | media_channel |
| supabase | `entities` | 373 | ENTITY | old entity table -> Phase-4 resolution |
| supabase | `merchant_taxonomy` | 294 | ENTITY | merchant |
| supabase | `place_book` | 7 | ENTITY | place |
| supabase | `metric_catalog` | 354 | REGISTRY | -> metric_registry |
| supabase | `category_map` | 48 | REGISTRY | finance category reference |
| supabase | `signals` | 102,786 | DERIVED | old-stack computed signals |
| personal_os.db | `pos__baselines` | 4,540 | DERIVED | computed baselines |
| supabase | `validated_insights` | 1,413 | DERIVED | old-stack output |
| supabase | `insights_catalog` | 1,191 | DERIVED | old-stack output |
| supabase | `hypotheses` | 338 | DERIVED | old-stack output (Phase-6 re-authored fresh) |
| personal_os.db | `pos__anomalies` | 266 | DERIVED | old-stack output |
| supabase | `inferred_events` | 173 | DERIVED | old-stack INFERRED (INV-5) |
| supabase | `graph_structures` | 137 | DERIVED | old-stack output |
| supabase | `coach_recommendations` | 121 | DERIVED | old-stack output |
| supabase | `insights` | 64 | DERIVED | old-stack output |
| supabase | `forecast_log` | 51 | DERIVED | old-stack output |
| supabase | `experiments` | 16 | DERIVED | old-stack experiment defs |
| supabase | `goals` | 7 | DERIVED | old-stack goals |
| supabase | `ask_threads` | 6 | DERIVED | old-stack chat |
| supabase | `day_narratives` | 2 | DERIVED | old-stack narrative output |
| supabase | `briefs` | 1 | DERIVED | old-stack output |
| supabase | `confrontations` | 1 | DERIVED | old-stack output |
| supabase | `checkin_probes` | 13 | OPERATIONAL | prompt dispatch -> not atoms |
| supabase | `ingest_status` | 2 | OPERATIONAL | pipeline status |
| supabase | `checkin_probe_queue` | 0 | EMPTY | 0 rows |
| supabase | `context_facts` | 0 | EMPTY | context_fact kind, 0 rows |
| supabase | `experiment_assignments` | 0 | EMPTY | 0 rows |
| supabase | `reconcile_queue` | 0 | EMPTY | 0 rows |
| supabase | `workouts` | 0 | EMPTY | 0 rows (OQ-18: strength unmeasured) |
| personal_os.db | `pos__mood_log` | 0 | EMPTY | mood, 0 rows |
| backup_2026-07-17 | `csv__workouts` | 0 | EMPTY | empty file / parse error |

## WHAT I DID NOT DO

- **Did not execute any backfill, write any atom, or touch `core`.** Plan only.
- **Did not read the archived table *schemas*** — the `intraday`/`events` fan-out and the
  `pos__daily_health` column split are named as judgement calls but not resolved; that
  needs the actual columns, which is execution-session work.
- **Did not verify the OVERLAP tables are strict subsets** of their canonical. If any
  duplicate carries rows the canonical lacks, those are kept — flagged in §5, not yet
  checked by key/hash.
- **Did not decide the INV-1 lineage mechanism** (one `raw_captures` per table-load vs
  per-row) — §6.1, owed as a ruling before execution.
- **Did not settle the gait `vital_sample` vs `activity_sample` boundary** (O-Q2) — it
  changes ~170k atoms' kind and should be ruled before that split is written.
