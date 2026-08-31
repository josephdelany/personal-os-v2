# REQ-LOC — Location: restricted storage, place resolution, mobility

**Scope:** what happens to a coordinate *after* it is captured (REQ-CAP-110) — how
it is stored under restricted access, resolved to a place, derived into mobility
metrics, and kept from ever leaving the system. Location is a first-class analytic
domain (RULE-29 SCOPE shell, ADR-0029); the privacy intent — coordinates and home
never *leave* — is unchanged and is now enforced by the egress boundary, not by
refusing to store.

**Relationship to REQ-CTX:** the "Not yet written" index entry bundled location
into `REQ-CTX` (context: location, media, alcohol, screen time). Alcohol is now
`REQ-NUT` §D.6 / Missing-B; location is substantial enough to be its own set and
the remediation plan names it `REQ-LOC` (Track 1.3). This file takes location;
`REQ-CTX` narrows to media and screen time and stays deferred.

Every requirement says *what must be true*, never *how*. Egress enforcement leans on
two static lints that now exist — the RULE-29 coordinate-literal tripwire and the
forbidden-import lint (`tools/validate_layout.py` section 11; OQ-15 RESOLVED this
session) — plus the runtime egress proof (`ops.egress_log`) owed when egress paths
are built (Phase 3), which is the authoritative enforcement a static regex cannot be.

---

## A. RESTRICTED STORAGE AND THE EGRESS BOUNDARY

**REQ-LOC-001** (Ubiquitous) The system SHALL store a captured coordinate only in a restricted store whose read access is separated from any session that holds an egress capability (RULE-29, ADR-0020), and SHALL NOT place a raw coordinate in `core.atoms` alongside egress-reachable rows.

**REQ-LOC-002** (Ubiquitous) The system SHALL never let a home coordinate leave at any precision and SHALL never emit any coordinate — home or non-home — into an export, a log line, a git commit, or a model prompt (RULE-29).

**REQ-LOC-003** (Event-driven) WHEN a place derived from a non-home coordinate is egressed, the system SHALL reduce its precision to no finer than approximately 100 metres, and SHALL egress a place label rather than the coordinate wherever a label suffices (RULE-29).

**REQ-LOC-004** (Ubiquitous) The system SHALL mark the `trust_level` of the location `raw_captures` row at ingest on the ADR-0020 column and SHALL carry that trust level with the coordinate into the restricted store, and SHALL treat a coordinate that arrived inside third-party content as `untrusted` (ADR-0020), so it reaches a model as quoted data, never as instruction.

**REQ-LOC-005** (Ubiquitous) The build SHALL fail if a coordinate literal or a home-location identifier is committed to the repository, enforced by the static tripwire in `tools/validate_layout.py`; this lint cannot prove the absence of every encoding, so the runtime egress proof (`ops.egress_log`) and review remain the authoritative enforcement (RULE-29, OQ-15).

## B. PLACE RESOLUTION

**REQ-LOC-006** (Event-driven) WHEN a coordinate cluster is resolved to a place, the system SHALL record the resolution as a place entity with its own provenance, and a human correction of that resolution SHALL outrank every automated match permanently (RULE-10).

**REQ-LOC-007** (Ubiquitous) The reasoning layer SHALL reason over resolved place labels and place entities, and SHALL NOT include a numeric coordinate in any payload sent to the language layer, any export, or any log line (RULE-29, REQ-INF-566).

**REQ-LOC-008** (Ubiquitous) The system SHALL designate the home place distinctly from every other place and SHALL apply the home egress ban (REQ-LOC-002) to that designation, and the home-geofence definition that decides what counts as home is OQ-37.

**REQ-LOC-009** (State-driven) WHILE a coordinate resolves to no known place, the system SHALL record the visit against an `unknown` place rather than guessing the nearest labelled one (RULE-06).

## C. MOBILITY METRICS — derived, owned, deterministic

**REQ-LOC-010** (Ubiquitous) The reasoning layer SHALL represent dwell, visit, radius of gyration, location entropy, commute, and transit load as `derived_measures` with `metric_registry` entries, and SHALL NOT introduce a new `atoms.kind` for any of them (ADR-0030); `derived_measures` is the Phase-5 carrier and does not exist until then, so these are designed-in, not queryable in Phase 2/4.

**REQ-LOC-011** (Ubiquitous) The reasoning layer SHALL compute every mobility metric deterministically with exactly one owner and one `code_version` (RULE-11, RULE-12), and the language layer SHALL NOT compute it.

**REQ-LOC-012** (Ubiquitous) The reasoning layer SHALL derive every mobility metric from the restricted coordinate store within the read/egress boundary (REQ-LOC-001), and SHALL surface only the aggregate — never the coordinates it aggregated (RULE-29).

**REQ-LOC-013** (Ubiquitous) The reasoning layer SHALL compute a mobility metric over fixed window lengths drawn from the metric registry, never chosen by the model at query time (RULE-13); the specific windows are provisional placeholders (OQ-37) and every figure they gate SHALL say so until calibrated.

**REQ-LOC-014** (Ubiquitous) The reasoning layer SHALL compute every mobility metric point-in-time correctly, with no fix recorded after the metric's window closed (INV-4; the RULE-04 CI query activates against `derived_measures` in Phase 5, OQ-22).

## D. MISSING DATA, TIER, DEGRADATION

**REQ-LOC-015** (Ubiquitous) The reasoning layer SHALL NOT impute a missing location — an unlogged interval is not a stay at the last known place — and SHALL report coverage alongside every mobility aggregate (RULE-06).

**REQ-LOC-016** (Event-driven) WHEN presence at a place is logged as not having occurred, the system SHALL record it as an `observed_absent` presence distinct from an unlogged interval recorded as `unknown` (RULE-07).

**REQ-LOC-017** (Ubiquitous) The reasoning layer SHALL render a mobility derived measure at tier `DESCRIPTIVE` and SHALL NOT assert a causal claim from observational movement data without the evidence its tier requires (RULE-16).

**REQ-LOC-018** (State-driven) WHILE the language layer is unavailable, every location and mobility surface SHALL still render through the deterministic template path (RULE-15).

## NON-GOALS

- Not a goal: storing or rendering a map with a home marker, or any surface that plots a raw coordinate. The system reasons over places and aggregates; the coordinate never reaches a render path (RULE-29).
- Not a goal: real-time tracking, geofencing alerts, or a live location share. Location is an analytic domain, not a surveillance feed.
- Not a goal: inferring a sensitive attribute (health, religion, relationships) from places visited. Place is context for the objective function, not a profiling input.
- Not a goal: a third-party location SDK that egresses coordinates. The capture path is the Shortcut (REQ-CAP-110); nothing else touches the coordinate.

## ALTERNATIVES CONSIDERED

- **Storing only place labels, never coordinates (the former RULE-29 ban).** Reversed by ADR-0029: coordinates ARE stored, restricted, and mobility metrics (radius of gyration, entropy) are derived from them — those metrics are impossible from labels alone. The privacy intent is preserved by the egress boundary, not by refusing to store.
- **Computing trust at read time.** Rejected (ADR-0020): provenance of trust is a fact about ingest, not recomputable later.
- **A single "mobility score."** Rejected: each metric is reported on its own with its window disclosed (REQ-LOC-013); a blended score is the composite RULE-24 forbids and hides which signal moved.
- **Deriving mobility inside an egress-capable session for convenience.** Rejected (REQ-LOC-012, ADR-0020): that reunites the read and egress capabilities the separation exists to keep apart.

## UNRESOLVED QUESTIONS

*Tracked in `docs/OPEN_QUESTIONS.md`; local record below.*

- **LOC-Q1 — the home-geofence definition and the mobility-metric windows and place taxonomy.** What radius (and dwell threshold) counts as "home"; the window lengths for radius of gyration, entropy, commute and transit load; and the place taxonomy granularity — all are provisional placeholders in REQ-LOC-008/013 (OQ-37; joins the OQ-10 placeholder set), to be set against Joe's real location data, not guessed now.
- **LOC-Q2 — the concrete restricted-store mechanism** (a separate schema, a separate role, a separate service) that realises REQ-LOC-001's read/egress separation is an ADR owed when the location table is built (Phase 4), not fixed here; ADR-0020 fixes the principle, not the table.
- **LOC-Q3 — whether the legacy location history in Parquet is loaded** into the restricted store, and when, is OQ-29 (the legacy backfill trigger), not decided here.
