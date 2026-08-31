# REQ-WKT — Workout and the objective function

**Scope:** strength training capture and the derived measures that make strength
the system's **objective function** — e1RM, per-exercise volume, acute:chronic
workload, and progression over time. Body composition (lean mass, Kalman weight,
TDEE) is the *other half* of the objective and is specified separately in
`REQ-BOD`; this file references it and does not duplicate it.

**Why this file exists first among the missing sets** (`docs/REMEDIATION_PLAN.md`
Track 1.3): the previous hypothesis library had zero coverage of e1RM, sets, RPE,
or lean mass — zero coverage of the system's own stated purpose — and the
objective has neither data nor requirements. This is the requirements half; the
data half is `docs/OPEN_QUESTIONS.md` OQ-18 (interim capture must start now, it
cannot be backfilled).

Every requirement here says *what must be true*, never *how*. Formula and window
choices are registry/ADR decisions, flagged in UNRESOLVED QUESTIONS, not welded
into a requirement.

---

## A. CAPTURE — per set, extractive only

**REQ-WKT-001** (Ubiquitous) The capture path SHALL record strength training at the granularity of the individual set — each set carrying its exercise, load, repetitions, and RPE — and SHALL NOT record only a session-level aggregate (REQ-ONT-017, ADR-0030), so that e1RM, per-exercise volume, and progression are computable per set.

**REQ-WKT-002** (Ubiquitous) The capture path SHALL accept workout logs only through iOS Shortcuts or an interim manual logger and SHALL NOT capture in the PWA or call `getUserMedia` (RULE-30); the interim logger and its crude output are OQ-18.

**REQ-WKT-003** (Ubiquitous) The extraction service SHALL emit only extracted values for a set — an exercise `name`, a numeric `load`, and a numeric `reps`, all measured, plus a numeric `RPE` marked as a subjective self-report distinct from the measured numerics (RULE-05), each with its verbatim evidence span — and SHALL NOT emit an e1RM, a volume, or any computed training measure (RULE-09).

**REQ-WKT-004** (Event-driven) WHEN a load is captured, the capture path SHALL record its stated unit (kilograms or pounds) and SHALL store the load in a single canonical unit, and SHALL mark a bodyweight or assisted movement as such rather than recording a zero or absent load.

## B. STORAGE — set atoms and the exercise entity

**REQ-WKT-005** (Ubiquitous) The system SHALL store each set's exercise, load, repetitions, and RPE against the exercise entity and `metric_registry`, carried by `workout` atoms without a new `atoms.kind` (REQ-ONT-001), and SHALL keep every set individually addressable so per-set derivation is possible (REQ-ONT-017); whether a set is one atom per attribute sharing a set key or a single composite atom — and the exact registry keys it uses — is OQ-33 and is not fixed here, and the strength registry rows those keys resolve to are owed (a data write, like the alcohol seed), so the `atoms.metric_key` foreign key makes a set unwritable until they land.

**REQ-WKT-006** (Ubiquitous) The system SHALL resolve each set's exercise to a single canonical exercise entity and SHALL NOT let the same movement drift across free-text spellings; a human correction of that resolution outranks every automated match permanently (RULE-10).

**REQ-WKT-007** (Ubiquitous) The system SHALL store RPE as a coarsened self-report on its declared response scale with its rounding step (ADR-0018), and SHALL NOT store a subjective RPE as if it were a measured quantity (RULE-05).

## C. DERIVED MEASURES — deterministic, owned, versioned

**REQ-WKT-008** (Ubiquitous) The reasoning layer SHALL compute e1RM deterministically from a set's load and repetitions using a single named formula recorded in the metric registry, executed and stored with exactly one owner and one `code_version` (RULE-11, RULE-12), and the language layer SHALL NOT compute it.

**REQ-WKT-009** (Ubiquitous) The reasoning layer SHALL store e1RM as an interval carrying an `estimate_method` that names the formula (RULE-08), because a formula estimate from a submaximal set is resolved rather than measured and a single number would misstate its precision.

**REQ-WKT-010** (Unwanted behaviour) IF a set's repetitions fall outside the validated range of the e1RM formula, THEN the reasoning layer SHALL NOT compute an e1RM for that set and SHALL record the omission rather than extrapolate (RULE-06).

**REQ-WKT-011** (Ubiquitous) The reasoning layer SHALL compute per-exercise and per-session training volume deterministically as the sum over sets of load multiplied by repetitions, with one owner and one `code_version`, and SHALL trace every volume figure to the set atoms it summed (INV-1, INV-3).

**REQ-WKT-012** (Ubiquitous) The reasoning layer SHALL compute the acute:chronic workload ratio as acute workload over chronic workload across fixed window lengths drawn from the metric registry, never chosen by the model at query time (RULE-13); the specific window lengths are provisional placeholders (OQ-36), and every ACWR figure it renders SHALL say so until they are calibrated.

**REQ-WKT-013** (Ubiquitous) The reasoning layer SHALL compute every workout derived measure point-in-time correctly, including no set recorded after a measure's window closed (INV-4; the RULE-04 CI query activates against `derived_measures` in Phase 5, OQ-22), and SHALL stamp each with the `code_version` that produced it.

## D. PROGRESSION AND RENDERING — plain progress only

**REQ-WKT-014** (Ubiquitous) The render layer SHALL present strength progression as an e1RM or volume trend over time toward the stated objective, and SHALL NOT display a streak, a compliance score, a composite wellness score, or a celebratory animation (RULE-24).

**REQ-WKT-015** (Ubiquitous) The render layer SHALL emit no workout numeral that does not trace to a stored computation (RULE-14, INV-3), and SHALL NOT perform any arithmetic beyond formatting.

**REQ-WKT-016** (Ubiquitous) The render layer SHALL show training coverage as a rolling 7-day figure and SHALL NOT present it as a breakable streak (RULE-24).

**REQ-WKT-017** (State-driven) WHILE the language layer is unavailable, every workout surface SHALL still render its trends and figures through the deterministic template path (RULE-15).

## E. MISSING DATA, PRESENCE, CORRECTIONS, TIER

**REQ-WKT-018** (Ubiquitous) The reasoning layer SHALL NOT impute a missing training input — a skipped session is not zero volume — and SHALL report coverage alongside every training aggregate (RULE-06).

**REQ-WKT-019** (Event-driven) WHEN a rest day or a deliberately skipped session is logged, the system SHALL record it as an `observed_absent` training presence, distinct from an unlogged day recorded as `unknown` (RULE-07).

**REQ-WKT-020** (Ubiquitous) The system SHALL treat a human correction of an exercise, load, repetition count, or RPE as a first-class superseding row that outranks every automated value permanently and is replayed over every rebuild (RULE-10, RULE-02).

**REQ-WKT-021** (Ubiquitous) The reasoning layer SHALL render a workout derived measure at tier `DESCRIPTIVE` and SHALL NOT assert a causal or experimental strength claim from observational training data without the evidence its tier requires (RULE-16).

**REQ-WKT-022** (Ubiquitous) The reasoning layer SHALL treat strength progression (e1RM and volume over time) together with body composition (`REQ-BOD`) as the objective function the analysis is oriented toward, and SHALL NOT collapse the two into a single composite score (RULE-24).

## NON-GOALS

- Not a goal: an autonomous coach that prescribes the next session's sets and reps. Prescription is `REQ-ACT`, tier-gated and blocked on OQ-30; this file measures, it does not instruct.
- Not a goal: real-time rep counting, bar-speed, or form analysis from video. Capture is a logged set, not a sensor stream.
- Not a goal: a streak, badge, ring, or compliance score of any kind (RULE-24).
- Not a goal: importing a third-party training programme as ground truth about what Joe *should* do; a plan is context, not a measured fact.
- Not a goal: testing a true 1RM. e1RM is estimated from submaximal work precisely to avoid the injury and frequency cost of maximal testing.

## ALTERNATIVES CONSIDERED

- **Session-level storage with sets in a payload.** Rejected: REQ-ONT-017 / ADR-0030 fix per-set granularity because e1RM, per-exercise volume, and progression all need each set as a first-class row for the inference layer to iterate over; burying sets in a payload reintroduces the parsing RULE-14 forbids.
- **One hardcoded e1RM formula in code.** Rejected: it welds a design decision into behaviour and makes the formula unrevisitable. The formula is a registry-recorded, versioned choice (REQ-WKT-008), so recalibrating it is a data change, not a code change.
- **Deriving strength from perceived exertion alone.** Rejected: RPE is a coarsened subjective self-report (REQ-WKT-007); it modulates interpretation but is never the measured load.
- **A single "readiness" or "fatigue" score.** Rejected: ACWR is reported as its own ratio with its windows disclosed (REQ-WKT-012); a blended readiness score is the composite-wellness score RULE-24 forbids.

## UNRESOLVED QUESTIONS

*Full status is tracked in `docs/OPEN_QUESTIONS.md`; the entries below are the local record.*

- **WKT-Q1 — which e1RM formula, and which ACWR window lengths and smoothing?** Epley, Brzycki, Lombardi and others diverge most at high reps; ACWR admits 7:28 coupled/uncoupled and rolling/EWMA variants. These are provisional placeholders in REQ-WKT-008/012, to be set against Joe's real training data rather than guessed now (OQ-36; joins the OQ-10 placeholder set). Every figure they gate says so until calibrated.
- **WKT-Q2 — the atom-shape for one set's four attributes** (per-attribute atoms sharing a set key vs a composite value): OQ-33, deferred to this file's authoring and not fixed here.
- **WKT-Q3 — the interim capture tool and when logging starts:** OQ-18. Every week without capture is a week the objective function cannot be measured, and it cannot be backfilled.
- **WKT-Q4 — the exercise / muscle-group taxonomy for volume aggregation** is not enumerated; it must be large enough to separate movements Joe actually trains and small enough to audit, and it is not fixed here.
