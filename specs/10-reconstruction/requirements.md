# 10 — Evidence reconstruction and historical coverage

Status: specified 2026-09-09 at Joe's direction; implementation OPEN.
Scope: make the existing cross-source intelligence vision testable. Complements
REQ-INF cross-lens statistics and REQ-FIN usage inference; does not replace them.
Decision: ADR-0084. Acceptance cases: docs/INTENT_COVERAGE.md.

## A. Source-to-capability accounting

**REQ-REC-001** (Ubiquitous) The backend SHALL maintain a source inventory recording availability, record types, counts, event-date coverage, observed freshness, duplicate relationships, import status, analytical consumers and the reason for each unsupported or excluded type.

**REQ-REC-002** (Ubiquitous) The backend SHALL distinguish sources verified available from sources mentioned only in historical documents, and SHALL report the latter as unverified until their artifacts or live access are checked.

**REQ-REC-003** (Ubiquitous) The backend SHALL assign every inventoried record type an explicit disposition of used, pending implementation, duplicate, historical derived output, unavailable, or excluded with a recorded reason and owner.

**REQ-REC-004** (Ubiquitous) The backend SHALL maintain a derivation catalogue mapping each supported derived measurement to its input fields, formula or method version, units, time specification, missingness rules, earliest supported event date and analytical consumers.

### NON-GOALS
Blind bulk import; upgrading old inferred outputs into observations; discovering
private files outside project sources without an authorized task.
### ALTERNATIVES CONSIDERED
Counting imported rows alone cannot reveal unused fields, unavailable concept assets
or overlap. Separate availability, ingestion and analytical use instead.
### UNRESOLVED QUESTIONS
Existing OQ-48/49/51/53 govern measurement definitions and source reconciliation.
No decision about their meaning is made here.

## B. Reconstructing events from evidence

**REQ-REC-005** (Ubiquitous) The backend SHALL represent an inferred event separately from measured observations, carrying event-time bounds, knowledge time, source references, method version, uncertainty status and the existing evidence-tier vocabulary.

**REQ-REC-006** (Ubiquitous) The reconstruction engine SHALL select executable reconstruction methods from a versioned registry declaring required evidence, permissible outputs and temporal specifications, rather than executing model-generated rules or hardcoding one example as the entire engine.

**REQ-REC-007** (Ubiquitous) Every reconstructed event SHALL carry supporting evidence, contradicting evidence, considered alternative explanations and any unresolved ambiguity, with an empty alternative set explicitly disclosed when no alternative generator applies.

**REQ-REC-008** (Event-driven) WHEN multiple records describe the same originating event or copy the same source, the reconstruction engine SHALL preserve their common origin and SHALL NOT count them as independent corroboration without a registered dependence model.

**REQ-REC-009** (Unwanted behaviour) IF source coverage is insufficient to establish that an event did not occur, THEN the reconstruction engine SHALL retain unknown presence rather than infer absence from a missing record.

**REQ-REC-010** (Ubiquitous) The reconstruction engine SHALL distinguish an uncalibrated ranking or rule score from an estimated probability, and SHALL expose a numerical probability only with its stored estimation method and calibration evidence; where these are absent it SHALL report uncertainty as unquantified using permitted tier templates without unsupported verbal probability claims (REQ-TIER-026).

**REQ-REC-011** (Event-driven) WHEN evidence or a human correction changes an event interpretation, the backend SHALL append a superseding interpretation while preserving the earlier interpretation and the evidence available at its knowledge cutoff, with human corrections retaining precedence.

**REQ-REC-012** (Ubiquitous) A historical reconstruction query SHALL distinguish reconstruction using evidence available now from reconstruction using evidence known at the requested cutoff, and SHALL refuse the latter when its historical input state cannot be reproduced.

### NON-GOALS
Medical diagnosis; inferring personality or mental health from purchases; treating
venue presence as proof of specific consumption or lifting sets; a new evidence ladder.
### ALTERNATIVES CONSIDERED
Free-form model narrative cannot enforce provenance or temporal parameters. Fixed
meal-charge rules alone cannot cover multiple event families. Registry-based methods
with deterministic validation preserve extensibility and RULE-13/15.
### UNRESOLVED QUESTIONS
Implementation must reuse compatible provenance/links structures or record an additive
schema ADR before migration. No numerical confidence defaults are authorized here.
OQ-45 historical panel replay remains open; this specification does not waive it.
Event periods and knowledge cutoffs must be represented so late-import derivations
satisfy RULE-04. An implementation ADR must establish this before derived writes;
backdating recorded_at or weakening the invariant is forbidden.

## C. Turning reconstructed history into useful questions and findings

**REQ-REC-013** (Ubiquitous) Every analysis consuming inferred events SHALL record their uncertainty and source lineage and SHALL NOT treat those inputs as measured values or independent evidence for the same claim that generated them.

**REQ-REC-014** (Ubiquitous) The backend SHALL provide a registered query path returning reconstructed events with their evidence, alternatives, uncertainty, coverage and revision history through the existing owner-authenticated Ask/Record interfaces, including a deterministic response when no model is available.

**REQ-REC-015** (Event-driven) WHEN an unresolved event interpretation has distinguishable alternatives, the backend SHALL return the missing evidence that would distinguish them or explicitly state that no discriminating evidence has been identified, with any user prompt subject to existing cadence and dismissal rules.

**REQ-REC-016** (Ubiquitous) Before release, the backend SHALL execute acceptance cases covering multiple event families, contradictory and duplicated evidence, unknown presence, historical corrections, model unavailability and inferred-input propagation, recording each as passed or explicitly open rather than reporting a single meal example as complete reconstruction coverage.

### NON-GOALS
Guaranteed discovery, forced insight counts, causal confirmation from retrospective
exploration, or promotion of a chain above its weakest evidence.
### ALTERNATIVES CONSIDERED
A separate unrestricted detective chatbot would duplicate Ask and bypass its controls.
Extend existing registered operations and shared evidence structures instead.
### UNRESOLVED QUESTIONS
No new Joe action is needed to specify these behaviors. Model/service selection and
new dependencies retain the existing cost, privacy and ADR requirements.
