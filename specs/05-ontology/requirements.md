# 05 — ONTOLOGY — REQUIREMENTS (EARS)

**Status:** COMPLETE — 14 requirements, 0 acceptance scenarios (the taxonomy is
proven by a SQL CHECK plus behavioural INSERT-path tests, ADR-0022, not by Gherkin).
**Scope:** the closed vocabularies of the spine — the `atoms.kind` taxonomy, the
`entities.entity_type` taxonomy, and the controlled-vocabulary columns of an atom.
This is the spec ADR-0002 assumed and OQ-16 recorded as lost; the membership here is
**derived** from the 34 archived tables and the cited specs, not invented (ADR-0023).
**Blocking:** none. Undecided boundaries are tracked in `docs/OPEN_QUESTIONS.md`;
this header does not restate them.
**Grammar:** EARS (Mavin & Wilkinson). Five patterns only. SHALL is binding. SHOULD
is not used anywhere in this document.
**ID scheme:** `REQ-ONT-nnn` (ontology — atom kinds, entity types, controlled
vocabularies). Entity *resolution* (blocking keys, thresholds, review queue) is
Phase 4 and is deliberately not specified here (ADR-0004).

---

## 0. SYSTEM ACTORS

Named systems used in the SHALL statements below. Each name refers to exactly one
thing, so that every requirement has one owner.

| Name in requirements | What it is |
|---|---|
| **the atoms schema** | The `core` schema DDL and its constraints (migrations `0005`, `0014`). |
| **the entities schema** | The `core.entities` DDL and its constraints (migrations `0003`, `0014`). |
| **the database** | The live PostgreSQL instance enforcing the above at write time. |
| **the extraction service** | The component that turns a `raw_captures` payload into atoms (Phase 3). |
| **a schema migration** | A numbered forward-only file under `migrations/`. |

**Governing idea (ADR-0002, ADR-0023):** `kind` is the *coarse* observation class;
the *specific* measure lives in `atoms.metric_key` (a `metric_registry` reference).
The fine-grained archived series — heart rate, HRV, SpO2, walking speed, stride
length, and the rest — are registry rows, not kinds. This is what keeps the
taxonomy small and the inference layer registry-driven.

---

## A. THE ATOM KIND TAXONOMY

**REQ-ONT-001** (Ubiquitous) The atoms schema SHALL constrain `atoms.kind` to
exactly this closed set of 19 members: `transaction`, `consume`, `mood`,
`place_visit`, `workout`, `sleep`, `screen_session`, `vital_sample`,
`heart_rate_variability`, `body_measurement`, `activity_sample`, `location_fix`,
`web_visit`, `media_play`, `calendar_event`, `environment_sample`, `self_report`,
`note`, `context_fact`.

**REQ-ONT-002** (Unwanted behaviour) IF an atom is inserted whose `kind` is not a
member of the closed set of REQ-ONT-001, THEN the database SHALL reject the INSERT
and SHALL NOT store the row.

**REQ-ONT-003** (Ubiquitous) The extraction service SHALL record the specific
measure of an atom in `atoms.metric_key` as a `metric_registry` reference, and SHALL
NOT represent a specific measure by introducing a new `kind` value.

**REQ-ONT-004** (Unwanted behaviour) IF a new `kind` member is required, THEN it
SHALL be introduced only by a schema migration that also amends REQ-ONT-001 and is
recorded in an ADR, and SHALL NOT be introduced as an unconstrained free-text value.

---

## B. THE ENTITY TYPE TAXONOMY

**REQ-ONT-005** (Ubiquitous) The entities schema SHALL constrain
`entities.entity_type` to exactly this closed set of 6 members: `merchant`,
`place`, `food`, `person`, `media_channel`, `website`.

**REQ-ONT-006** (Unwanted behaviour) IF an entity is inserted whose `entity_type`
is not a member of the closed set of REQ-ONT-005, THEN the database SHALL reject the
INSERT and SHALL NOT store the row.

**REQ-ONT-007** (Ubiquitous) WHEN a human corrects an entity, the entities schema
SHALL record the correction as a new superseding row carrying `corrected_by_human`,
and SHALL NOT edit the corrected row in place, so that a human correction outranks
every automated layer permanently (RULE-10).

---

## C. CONTROLLED VOCABULARIES OF THE ATOM

**REQ-ONT-008** (Ubiquitous) The atoms schema SHALL record presence as exactly one
of `observed`, `observed_absent`, `unknown`, so that a logged absence and an
unlogged day never collapse into the same value (RULE-07).

**REQ-ONT-009** (Ubiquitous) The atoms schema SHALL record provenance as exactly one
of `extracted`, `inferred`, `defaulted`.

**REQ-ONT-010** (Ubiquitous) The atoms schema SHALL record aggregation legality as
`state_class` ∈ {`measurement`, `total`, `total_increasing`}, and SHALL record a
stored clock time using a `value_type` of `time_from_midnight` or `time_from_midday`
so that a time crossing midnight is not averaged as a raw number.

**REQ-ONT-011** (Unwanted behaviour) IF an atom's presence is `unknown`, THEN the
database SHALL reject any row that also carries a value, so that "not known" is never
stored as a number (RULE-07).

**REQ-ONT-012** (Ubiquitous) WHERE an atom carries a value, the atoms schema SHALL
require that value to carry its lane — both an `estimate_method` and a `state_class`
— so that a measured value and an inferred value never share a column unmarked
(RULE-05 / INV-5).

---

## D. IDENTITY AND TRACE

**REQ-ONT-013** (Ubiquitous) The atoms schema SHALL require every atom to reference
the immutable `raw_captures` row it derives from, so that every derived row traces to
a capture (INV-1).

**REQ-ONT-014** (Ubiquitous) The atoms schema SHALL store `subject_day` explicitly
together with the `subject_day_rule_version` that produced it, so that a future change
to the day-assignment rule is visible in the data rather than silently rewriting it
(ADR-0019).

---

## NON-GOALS

- **Entity resolution.** How a name becomes an entity — blocking keys, match
  thresholds, the review queue — is Phase 4 (ADR-0004). This spec fixes the
  `entity_type` vocabulary, not the algorithm that assigns it.
- **The metric registry contents.** REQ-ONT fixes that a specific measure lives in
  `metric_key`; the registry's per-metric rows (family, cadence, staleness, range)
  are governed by ADR-0002/ADR-0018, not enumerated here.
- **A `kind` per sensor series.** Deliberately rejected (ADR-0023): the fine health
  series are registry rows.

## ALTERNATIVES CONSIDERED

- **Native ENUM types for `kind`/`entity_type`.** Rejected (ADR-0023): these sets
  grow as feeds are added; a CHECK is extended by a cheap forward migration, whereas
  `ALTER TYPE` cannot run in a transaction and cannot retire a value.
- **Leave the columns open TEXT until Phase 3.** Rejected: the CHECK is cheapest over
  the empty tables now; adding it later is a migration over historical rows (OQ-23).
- **Pad to ADR-0002's "20".** Rejected: the evidence supports 19; a 20th category
  invented to hit a number is the fabrication the project forbids.

## UNRESOLVED QUESTIONS

These are boundary calls recorded in ADR-0023, revisited only if real extraction
(Phase 3) exercises them — not blocking:

- **O-Q1** — `mood` (spec-cited, standalone) vs `self_report` (other subjective
  check-in metrics). A future ruling could fold `mood` into `self_report` under a
  `metric_key`.
- **O-Q2** — `media_play` (a discrete watched/listened event) vs `screen_session`
  (a duration of screen use); and `heart_rate_variability` split out from
  `vital_sample`. Both boundaries are judgment calls.
- **O-Q3** — whether `entity_type` needs `brand`/`product` as a 7th type distinct
  from `merchant`, pending clearer evidence in the data.
