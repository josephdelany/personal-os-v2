# ADR-0030: Alcohol rides `consume`+registry; mobility scalars are derived measures; a strength set is one atom

## Status

Accepted

## Date

2026-08-24

## Context

The requirements audit (`docs/REQUIREMENTS_AUDIT.md`, Track 1.1) found three
ontology gaps against the eleven stated wants, all of them *live before* migration
`0014_ontology_checks.sql`'s `atoms.kind` CHECK hardens over append-only rows:

- **Want 9 (alcohol fully instrumented)** — `REQ-ONT-001`'s closed 19-member
  `atoms.kind` set contains no drink/alcohol member, and the ontology spec never
  mentions alcohol at all (zero `alcohol`/`drink`/`ethanol` tokens; no O-Q flags it,
  though O-Qs exist for lower-stakes boundaries). RULE-07's own worked example
  ("I logged that I did not drink") is alcohol. The most-emphasized instrumentation
  want had no ontology home.
- **Want 10 (location first-class)** — raw location is representable (`location_fix`,
  `place_visit` are members), but the six derived mobility scalars RULE-29 now makes
  first-class (radius of gyration, location entropy, commute, transit load, dwell,
  visit) had no obvious carrier.
- **Want 7 (strength as the objective function)** — `workout` is a member, but the
  spec was silent on whether a strength *set* (exercise, load, reps, RPE) is one
  atom per set or per session. e1RM, volume progression, and per-exercise trends —
  the objective function's core metrics — all need per-set resolution.

The `atoms.kind` CHECK is a **forward migration over append-only rows** (RULE-02):
adding a member later is a one-way door that must pass over history. So the shape of
these three answers had to be settled *before* the CHECK carries production data —
whether by adding a `kind` member (irreversible) or by confirming an existing carrier
(free). This ADR records the settled shapes; it takes **no migration**.

Spine facts verified against `migrations/0002_metric_registry.sql`,
`0005_atoms.sql`, `0014_ontology_checks.sql`:
- `consume` is already a member of the `atoms_kind_taxonomy` CHECK (0014).
- `atoms.metric_key` is a live FK to `metric_registry.metric_key` (0005:36).
- **No constraint ties which `kind` may carry a `metric_key`** — a `consume` atom
  can carry any registry key freely.
- `derived_measures` exists in **no** migration; it is the Phase-5 table behind
  RULE-04 PENDING (OQ-22).

## Decision

**1 — Alcohol (and caffeine, supplements, medication) ride `kind='consume'` + a
`metric_key`.** No new `atoms.kind` member, no migration. An alcohol serving is a
`consume` atom carrying a registry key such as `alcohol_standard_drinks` or
`alcohol_ethanol_grams`. This generalises to caffeine, supplements, and medication
rather than special-casing drink — the same coarse-kind-plus-registry pattern
REQ-ONT-003 already mandates. The `0014` CHECK is never touched.

Seeding the alcohol `metric_registry` rows is a **data INSERT** and a Track-1.2
*migration-boundary* task (deferred; see Consequences): each metric needs a
`state_class` (`total` per subject-day for both standard-drinks and ethanol-grams),
a `family` for the RULE-21 FDR tree, and plausible bounds.

**2 — Mobility scalars are derived measures, not atoms.** Radius of gyration,
location entropy, commute, transit load, dwell, and visit belong in
`derived_measures` with `metric_registry` entries — never a new `atoms.kind`. Raw
location capture (`location_fix`, `place_visit`) is already representable today; the
derived mobility layer lands with `derived_measures` in Phase 5. The `0014` CHECK
stays frozen — this is the load-bearing part of the ruling.

**3 — A strength set is one `workout` atom per set** (Joe's ruling, 2026-08-24),
carrying exercise, load, reps, and RPE. Not one atom per session. e1RM, volume
progression, and per-exercise trends all need per-set granularity, and strength is
the objective function. `workout` is already a `kind` member, so this is a
requirements/extraction-shape decision, not a migration — it governs how the
Phase-3/4 workout-capture path writes rows and how the (unwritten) `REQ-WKT` /
`REQ-ONT` requirements are authored.

## Consequences

**Good.** All three of the loudest wants (alcohol, location-mobility, strength) get
a settled ontology shape with **zero migrations** and the `0014` CHECK left frozen —
no one-way door taken on a guess. The `consume`+registry choice for alcohol
generalises to a whole class of ingestibles instead of accreting single-purpose
kinds. Per-set strength granularity is fixed before any workout data exists, so no
historical re-shaping is ever needed.

**Cost / owed (named, not hidden).** This ADR settles the *shapes* but builds
nothing:
- The alcohol `metric_registry` seed rows are **not** inserted — that is a data
  write (a migration-class operation) and stops at the Track-1.2 migration boundary,
  pending Joe.
- The mobility metrics are **designed-in, not buildable now** — `derived_measures`
  does not exist until Phase 5. A `core.atoms` or `derived_measures` query for radius
  of gyration returns nothing until then. Correct for a derived measure; reverses no
  decision.
- The abstinence-day capture path (`observed_absent` for a drink-not-taken, RULE-07)
  and the deterministic ABV→ethanol-grams conversion (`volume × ABV × 0.789`,
  RULE-09) are **requirement-authoring** owed under Missing-B, not covered here.
- `REQ-ONT` gains a requirement (or an O-Q resolution) stating that
  alcohol/caffeine/supplement/medication ride `consume`+registry, and the per-set
  strength shape. That spec edit is Track-1.2 work; this ADR is its rationale.

**Touches** OQ-27 (the `atoms.kind`/`entity_type` boundary is a requirements-layer
question) and closes the ontology half of OQ-31 (strength-set granularity ruled).

## Alternatives considered

- **Add `alcohol` (and per-mobility) members to `atoms.kind`.** Rejected: each is an
  irreversible forward migration over append-only rows, and `consume`+registry /
  `derived_measures`+registry carry the same information with no migration. Adding a
  kind is reserved for a genuinely new *coarse observation class*, which a drink and
  a mobility scalar are not.
- **One `workout` atom per session, sets in a JSON payload.** Rejected: e1RM and
  per-exercise volume trends need each set as a first-class row for the inference
  layer to iterate over (RULE-21 tree, metric registry); burying sets in a payload
  reintroduces the render/compute-layer parsing RULE-14 forbids and makes per-set
  provenance impossible.
