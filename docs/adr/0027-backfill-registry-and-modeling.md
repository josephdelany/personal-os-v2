# ADR-0027: Legacy-backfill metric registry and per-stream modeling

## Status

Accepted

## Date

2026-08-23

## Context

ADR-0025 (reconciliation) and ADR-0026 (A′ lineage, gait) settled *how* legacy
atoms trace and *which kind* gait is. Executing the backfill needs a set of
further modeling decisions that were not specified anywhere and that the plan
under-scoped. This ADR records them so the dry-run builds against a settled
definition. It extends ADR-0018 (registry metadata) with the actual rows, and
ADR-0002/0019/0020 with the concrete legacy mappings. Directed by Joe
2026-08-23 (Phase 2, session 5): union-dedup, build the registry here, defer
locations, dry-run then stop; `plausible_low/high` left NULL (RULE-06 — ranges
are measured at the OQ-10 calibration, never guessed).

All decisions below were derived from **reading the actual archive**, not the
manifests: the plan's map was wrong in three ways (health double-counted at
~250k; `metric_catalog` is a derived-feature catalog not a units registry;
`locations` cannot be a scalar atom), all documented in ADR-0026.

## Decision

**1. `metric_registry` is populated fresh, from the observed streams.** One row
per measure the backfill writes (units taken verbatim from the source `unit`
column; `state_class='measurement'` for instantaneous samples; `family` groups
them for the RULE-21 FDR tree). `plausible_low/high` are **NULL** (RULE-06;
set at OQ-10). Self-report measures (`checkins`: energy, restored, drive) carry
`self_report=true` + `response_scale`/`n_scale_points`/`rounding_step` per
ADR-0018 (integer 1–5 scale observed). The exact rows the dry-run inserts are
printed by `tools/backfill_run.py --report` for review; the registry is
`metric_registry` (mutable, not append-only), so a wrong unit/family is a cheap
UPDATE later — unlike the atoms that reference it.

**2. Subject-day timezone = `America/New_York`.** Evidenced, not assumed: the
`health__*` timestamps carry `-0400`/`-0300` offsets, and the `pos__youtube`
naive timestamps align to `events` UTC at exactly −4h (EDT). `subject_day` is
computed on the ADR-0019 rule (04:00 local, by start instant, **sleep by wake
day**) in that zone, `subject_day_rule_version = 'legacy-v1-2026-08-23'`.
*Caveat recorded:* `pos__chrome` naive timestamps are UTC while `pos__youtube`
naive timestamps are Eastern — the old extractors were inconsistent; each stream
is normalized with its own verified offset before `subject_day` is computed.

**3. `provenance = 'extracted'`, `estimate_method = 'measured'`** for device
samples (pulled verbatim from a device payload; the interval collapses to a
point per the ADR-0002 measured rule). Not `inferred` — no model produced these.

**4. `trust_level` per ADR-0020.** Own-device health/body samples = `trusted`.
Atoms whose identity rests on a third-party-authored string —
`web_visit` (url/title), `media_play` (title/channel), `transaction` (merchant) —
= `untrusted`. **`trust_level` describes the string a model will read, NOT the
numeric value's reliability** (Joe): a `transaction` atom is `untrusted` because
the merchant text is third-party model-read input (ADR-0020 lethal-trifecta),
while the amount's reliability is carried separately by `provenance='extracted'`.
A future reader must not mistake `untrusted` for "the amount might be wrong."

**5. `recorded_at` = the backfill instant** (system-set by the 0012 trigger).
Correct under bitemporality: the *new* system learns these facts at backfill
time; `occurred_at` carries the true event time. No `now()` is faked as capture
time — capture time is not claimed at all (A′: the capture is a table-load).

**6. Union-dedup keys (per stream, each with its verified timezone).**
- Health samples: `(metric_key, occurred_at_utc_epoch, round(value,4))` across
  `intraday` + the 14 `health__*` tables (value-level identity confirmed).
- `web_visit` (chrome): `(url, visited_at)` with `pos__chrome` read as **UTC**.
- `media_play` (youtube): `(url, watched_at)` with `pos__youtube` read as **ET→UTC**.
- `calendar_event`: `(id, start)` across `events.calendar` + `pos__calendar_events`.
Each surviving atom records **which source(s) it came from in `evidence_span`**
(Joe's rider 2), format `evidence_span = '{table}#{rowkey}|src={source(s)}'`, so a
future value disagreement between the two exports is traceable without re-reading
the archive.

**7. Dedup surfaces as a named exclusion bucket `DUP_INTERNAL`** (Joe's rider 1),
= `rows_in − distinct_atoms_out` per stream. The archive's 810,933 still
reconciles exactly under ADR-0025; the count-drop is visible, not silent.

**8. Excluded-with-reason (reconciles, not dropped):**
- `locations` (282) — no coordinate columns on `atoms`; RULE-29 forbids storing
  coordinates; needs Phase-4 place-labeling. → OQ.
- **`pos__daily_health` — the WHOLE table (2,370 rows) is DERIVED** (Joe's
  ruling). It is an old-stack derived table of **daily rollups**; `env_db`/
  `headphone_db` are one aggregate value per date, and atomizing a source-computed
  aggregate as if it were an observation is exactly the measured-vs-inferred
  collapse **INV-5** forbids. If ambient sound is ever wanted as a real series it
  comes from **raw HealthKit**, never a legacy daily roll-up. (Earlier draft
  atomized the two env columns; reversed.)
- **Sleep — the stage is encoded in `metric_key`, one series per stage** (Joe's
  ruling): `sleep_inbed`, `sleep_core`, `sleep_deep`, `sleep_rem`, `sleep_awake`,
  `sleep_asleep_unspecified`, each with its own registry row (`family='sleep'`).
  This is queryable and fits the RULE-21 tree; `evidence_span` stays purely the
  source-row locator (rider 2), not overloaded with a category. Sleep atoms come
  from `health__sleep_intervals` (durational, 20,248); the point-form
  `intraday.sleep_stage` is `DUP_INTERNAL`.
- **Chrome `web_visit` disjoint check (rider 5) — resolved, 0 unresolved.** All
  15,096 distinct `pos__chrome_history` keys are present in `events.chrome_visit`
  (events ⊇ pos); the apparent ~2k gap was **2,326 within-`pos` exact duplicates**
  `(url, visited_at)`, already counted in `DUP_INTERNAL`. No genuine disjoint pos
  rows exist, so nothing is silently kept or dropped.

## Consequences

**Good.** The dry-run builds against one settled definition; every modeling call
is on record and reviewable before an irreversible write; the registry is
fixable post-hoc (mutable) while the atoms it anchors are not.

**Ruled by Joe 2026-08-23 (were provisional).** `env_db`/`headphone_db` →
**excluded as DERIVED** (INV-5, a source aggregate is not an observation); sleep
stage → **`metric_key` per stage** (not `evidence_span`); `transaction` stays
`untrusted` with the amount-reliability note above. The chrome disjoint question
is resolved (0 unresolved). No provisional modeling calls remain open in this
backfill.

## Alternatives considered

- **Map `metric_registry` from legacy `metric_catalog`.** Impossible — that
  table is the old stack's derived-feature catalog (`feature/domain/validity`),
  not measurement definitions (ADR-0026).
- **Guess `plausible_low/high`.** Rejected (RULE-06); NULL until OQ-10 measures them.
- **Atomize `locations` now.** Rejected (RULE-29 + schema-fit); deferred to Phase 4.
