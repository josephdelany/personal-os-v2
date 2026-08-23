# ADR-0023: The ontology taxonomy — closed `atoms.kind` and `entities.entity_type`

## Status

Accepted

## Date

2026-08-23

## Context

ADR-0002 specified a "closed 20-member `kind` enum" but the membership lived in the
ontology spec that was lost with the cloud workspace (OQ-16). ADR-0004 wanted a
closed `entity_type` set for the same reason and could not write one. So both
columns shipped as `NOT NULL TEXT` with no CHECK (migrations 0005, 0003): a typo or
an out-of-taxonomy value is currently accepted. `ops/features.json` F-006 cites
`REQ-ONT-001`, a requirement that existed in no spec (OQ-16). OQ-23 flagged that
adding the CHECK later is a forward migration over historical rows — cheap now
(tables empty, RULE-01), expensive once extraction (Phase 3) starts writing values.

Joe's instruction (Phase-2 session 3): write the REQ-ONT requirements now,
**derive** the taxonomy from what the 34 archived tables and the existing specs
actually contain — do not invent categories to fill space — and record what had to
be guessed. He ruled: requirements **plus** the enforcing CHECK migration now.

## Decision

**Altitude.** `kind` is the *coarse* observation class. The *specific* measure is
carried by `metric_key` (FK to `metric_registry`, already built in migration 0002).
This is ADR-0002's own design — "the statistics iterate over the registry, not over
hand-written pairs." The archive's ~40 fine-grained health series (separate tables
for heart rate, HRV, SpO2, walking speed, stride length, asymmetry, double-support,
steadiness, …) are therefore **registry rows, not kinds**. An exploratory pass that
proposed one `kind` per sensor series was rejected as folding the registry into the
enum.

**`atoms.kind` — 19 members.** Seven are cited by existing specs/ADRs (not guesses):

| kind | source |
|---|---|
| `transaction` | REQ-FIN-001 |
| `consume` | REQ-FIN-164 (alcohol, `props.class='alcohol'`) + REQ-NUT (meals) |
| `mood` | REQ-FIN-161 |
| `place_visit` | REQ-FIN-113 / REQ-FIN-161, ADR-0019 |
| `workout` | ADR-0019 |
| `sleep` | ADR-0019 |
| `screen_session` | ADR-0019 |

Twelve are derived from real archived tables:

| kind | grounded in (archived table) |
|---|---|
| `vital_sample` | `health__hr_samples`, `health__rhr`, `health__spo2`, `health__resp_rate`, `health__wrist_temp`, `health__walking_hr` |
| `heart_rate_variability` | `health__hrv_windows` |
| `body_measurement` | `pos__body_composition` |
| `activity_sample` | `intraday` activity series (steps, distance, flights, active energy) — the *sample* stream, not the `pos__daily_health` daily rollup (see guess #5) |
| `location_fix` | `locations` |
| `web_visit` | `pos__chrome_history` |
| `media_play` | `pos__youtube_history` |
| `calendar_event` | `pos__calendar_events` |
| `environment_sample` | `pos__daily_health` (`headphone_db`, `env_db`) |
| `self_report` | `checkins` (energy, stress, mental clarity, drive, day rating) |
| `note` | free-form PWA long-form text (`raw_captures.source = 'pwa_text'`) |
| `context_fact` | `context_facts` (standing life circumstances) |

**`entities.entity_type` — 6 members.** `merchant`, `place`, `food`, `person` (all
named in ADR-0004) + `media_channel` (`content_taxonomy`, 661 rows;
`pos__youtube_history.channel`) + `website` (`pos__chrome_history.domain`, 17k rows).

**Enforced by CHECK, not native ENUM.** `kind` and `entity_type` will grow as feeds
are added; a `CHECK (col IN (…))` is extended by a cheap forward migration
(drop + recreate the constraint over an append-only table), whereas `ALTER TYPE …
ADD VALUE` on a native enum cannot run inside a transaction and cannot remove a
value. The truly-fixed vocabularies (`presence`, `provenance`, `state_class`,
`time_precision`, `trust_level`) stay native ENUMs as built. Migration 0014 adds
`atoms_kind_taxonomy` and `entities_type_taxonomy` CHECKs over the empty tables.

**Extension rule.** A new `kind`/`entity_type` member is added only by a forward
migration that also updates REQ-ONT, with an ADR — never silently (REQ-ONT-003).

## What had to be guessed (recorded so a later change is visible)

1. **19, not ADR-0002's 20.** The evidence supports 19; the set was **not padded**
   to hit 20. ADR-0002's "20" was itself from the lost spec and is not sacred.
2. **`mood` vs `self_report`.** `mood` is spec-cited so it stays a standalone kind;
   the *other* subjective check-in metrics (energy, stress, clarity, drive, day
   rating) go under `self_report`. The boundary is a judgment; a future ruling
   could fold `mood` into `self_report` with a `metric_key`, or split further.
3. **`media_play` vs `screen_session`.** A discrete "watched/listened to X" event
   vs a *duration* of device/app use. Both grounded (YouTube history vs screen
   time); the line is mine.
4. **`heart_rate_variability` split out** from `vital_sample`. HRV is
   window-based and treated as a distinct high-value signal by analysts; it could
   fold into `vital_sample` as a metric_key.
5. **`activity_sample` is raw samples.** Daily activity rollups (`pos__daily_health`)
   are treated as future `derived_measures`, not atoms.
6. **`entity_type` omits `brand`/`product`** as a 7th type, pending clearer
   evidence that a brand is distinct from a merchant in this data.
7. **`note` and `context_fact`** are grounded in low-volume / empty tables
   (`pwa_text` captures; `context_facts` = 0 rows). Included because the "Mind" and
   "Context" sections (ADR-0002) and the capture sources demand them, not because
   the archive is dense there.

## Consequences

**Good.** OQ-23 is resolved: the taxonomies are closed and enforced while the
tables are empty (cheapest possible). REQ-ONT-001 now exists, so F-006's citation
is no longer dangling (OQ-16's REQ-ONT half). `kind` stays coarse and the registry
stays the place a new measure is added — no enum churn per metric.

**Bad / flagged.** Phase-3 extraction must emit only these 19 kinds / 6 types or a
forward migration must precede it; a mismatch is now a hard INSERT failure, not a
silent bad value (which is the point). The guessed boundaries (2–7 above) may need
a ruling once real extraction exercises them. `entities`/`links` remain
shape-only until Phase 4 (ADR-0004) — this ADR closes the *type vocabulary*, not
the resolution algorithm.

## Alternatives considered

- **Requirements only, leave columns open TEXT.** Rejected by Joe: the CHECK is
  cheapest over empty tables and OQ-23 explicitly warned about the later
  historical-row migration.
- **Native ENUM types.** Rejected: not extensible inside a transaction and a value
  cannot be retired; a CHECK over an append-only table is the evolvable choice for
  a set expected to grow.
- **One kind per archived series (the granular proposal).** Rejected: it duplicates
  `metric_registry` into the enum and breaks ADR-0002's registry-driven design.
- **Pad to 20 to match ADR-0002.** Rejected: inventing a 20th category to hit a
  number the lost spec happened to carry is exactly the "invent to fill space" Joe
  forbade.
