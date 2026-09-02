# B21 — The unwritten specs, written and built: body composition, sleep & recovery, context (migration 0063)

**What this is.** `specs/REQUIREMENTS_INDEX.md` lists three subsystems "not yet
written": REQ-BOD (body composition — the other half of the objective function,
REQ-WKT-022), REQ-SLP (sleep and recovery), REQ-CTX (context: media and screen time).
This session authors them in EARS (same three mandatory subsections each) *and* builds
the derived measures they specify, because the data for all three already exists in
the panel. Two sessions (B21.1 author + ADR; B21.2 build).

**ADRs:** ADR-0076 (REQ-BOD numbered; the weight/TDEE model), ADR-0077 (REQ-SLP
numbered), ADR-0078 (REQ-CTX numbered). ADR-0005 (blocking REQ-BOD) is read first and
either satisfied or explicitly superseded in ADR-0076.

## B21.1 — Author the three spec files (`specs/10-body`, `specs/11-sleep`, `specs/12-context`)
Write them the way the existing eight are written: EARS, numbered, one requirement per
statement, NON-GOALS / ALTERNATIVES / UNRESOLVED per section, Gherkin scenarios (6 each),
traceability table. The content each must cover:

**REQ-BOD (≈25 IDs).** Weight as a noisy measurement: a **Kalman / local-level filter**
over daily weigh-ins giving a smoothed weight with an interval (RULE-08; never the raw
scale reading as "the truth"); trend per week with interval; **TDEE estimation** from
smoothed weight change and logged intake *only when intake coverage ≥ 0.80 over the
window* (RULE-06; else INSUFFICIENT with `low_coverage`); lean-mass only from a
measured source (Renpho/InBody import) never inferred from weight alone (INV-5); the
objective-function surface: e1RM trend × body mass trend, DESCRIPTIVE, no composite
score (RULE-24); no calorie targets prescribed (RULE-26 boundary: "eat X kcal" is
behavioural not medical — allowed only through B10 at PROMOTED+ with disclosure).

**REQ-SLP (≈25 IDs).** Sleep as intervals by wake day (ADR-0019); sleep debt as a
rolling deficit vs the personal median with an interval; regularity (the SRI, standard
formula, registry-owned); midpoint drift; the guardian (2-of-N autonomic) formalised
here with its thresholds in the registry (OQ-10) and its "pattern match, not a
diagnosis" string as a stored string; recovery = HRV/RHR/temperature relative to the
personal band, never a 0–100 "recovery score" (RULE-24); nap detection from intervals;
caffeine/alcohol timing links via B14; every metric point-in-time (INV-4).

**REQ-CTX (≈20 IDs).** Screen sessions, binge runs, late-night share, content diet
(novelty vs repeat from `media_play`/`web_visit` atoms), the health-search spike
detector (a descriptive count of health-related queries per week, RULE-26 applies to
what is *said* about it), calendar load (events/day, meeting minutes), weather as an
exogenous context metric (Open-Meteo, free, no key — through `lib/egress.py`; coordinates
for the weather call come from the **registered home place's rounded-to-0.1° centroid,
computed inside the DB** and passed as a single opaque parameter — the ADR must show
this satisfies RULE-29's "no coordinate egress" *or* rule that weather uses a
Joe-entered city name instead; default to the city name).

## B21.2 — Build (migration 0063)
Registry rows for every new metric; `analysis.derived_measures` rows from
`tools/engines/body.py`, `sleep.py`, `context.py` nightly; panel metrics; `config.domains`
rows updated (`body` hero → smoothed weight; `sleep` gains `why` rows for debt/regularity;
`content` gains novelty share; a new `weather` domain, pillar `life`); `get_domain`
modules follow automatically. Tests named after the new IDs (≥ 1 per ID for the
computational ones; the Gherkin scenarios as tests).

## Done when
Three spec files in `specs/`, `REQUIREMENTS_INDEX.md` counts updated (the layout gate
checks the index count — run it), ADR-0076..0078, migration, engines in nightly, the
`body`/`sleep`/`content`/`weather` envelopes pasted, tests, PROGRESS + WHAT I DID NOT DO.
