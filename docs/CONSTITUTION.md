# CONSTITUTION

The stable core. Everything else in this repository is checked against this
document. It changes rarely, by explicit decision, recorded as an ADR.

**Item cap: 30 numbered rules.** If a 31st is proposed, one must be retired or
merged. This cap exists because the previous specification reached 617 KB with
no mechanism preventing accumulation, and became unusable to both a human and
a model. Enforced in CI by `.claude/rules/constitution-cap.md`.

Each rule carries an **enforcement tier**:

| Tier | Meaning |
|---|---|
| **SQL** | A query in CI proves it. A violation fails the build. |
| **LINT** | A static check on code, copy, or migrations fails the build. |
| **TEST** | An acceptance test covers it, named with the rule ID. |
| **REVIEW** | Only a human or the adversarial reviewer agent can catch it. |

---

## THE FIRST RULE

**RULE-00 — Never weaken a gate, a threshold, an invariant, or a test to make
it pass.** *(Tier: REVIEW + LINT)*
Inherited verbatim from the previous specification, where it was rule 14 and
was the best thing in it. If a gate fails, the system is wrong, or the gate is
wrong and must be changed by a recorded decision with an argument attached —
never by quietly editing the number. A commit that lowers a threshold and does
not reference an ADR is rejected. This rule is first because every other rule
in this file can be defeated by breaking it.

---

## I. DATA INTEGRITY

**RULE-01 — No fabricated data, anywhere, ever.** *(Tier: REVIEW + LINT)*
No placeholder rows, synthetic records, sample values, or example data in any
real table, in any environment, for any reason including testing and
demonstration. Missing data produces a documented gap, never a plausible value.
Test fixtures live under `tests/fixtures/` and never touch a production table.
*Rationale: in July 2025 an agent deleted a production database and generated
4,000 fabricated records to cover the loss. A crash is visible; a plausible
fake number is not.*

**RULE-02 — Ingested payloads are immutable and append-only.**
*(Tier: SQL + REVIEW)*
`raw_captures` and `atoms` accept INSERT only. UPDATE and DELETE are revoked at
the grant level, not merely avoided by convention. Corrections are new rows
that supersede, never edits in place.
```sql
-- CI check RULE-02
select count(*) from information_schema.role_table_grants
where table_name in ('raw_captures','atoms')
  and privilege_type in ('UPDATE','DELETE');  -- must be 0
```

**RULE-03 — Everything is bitemporal.** *(Tier: SQL)*
Every fact carries both when it happened (`occurred_at`, and `subject_day` on a
04:00 local boundary) and when the system learned it (`recorded_at`). A query
for "what was true on date D" returns what was known then, not what is known
now. *This is not retrofittable — see ADR-002.*

**RULE-04 — No metric may include data recorded after its window closed.**
*(Tier: SQL)*
Point-in-time correctness. This is the single query that proves bitemporality
actually works rather than merely existing in the schema.
```sql
-- CI check RULE-04
select count(*) from derived_measures d
join atoms a on a.id = any(d.source_atom_ids)
where a.recorded_at > d.window_end;  -- must be 0
```

**RULE-05 — A measured value and an inferred value never share a column.**
*(Tier: SQL + LINT)*
Every value carries its lane, its confidence, its provenance, and the
`code_version` that produced it. No number is rendered anywhere without its
lane. A rendering path that can display a value without also having access to
its lane is a defect, not a shortcut.

**RULE-06 — Never impute.** *(Tier: LINT + TEST)*
A missing value stays missing. No carry-forward, no mean-fill, no
interpolation, no "assume typical". Coverage is reported alongside every
aggregate; an aggregate over insufficient coverage refuses rather than
estimates.

**RULE-07 — Presence is three-valued.** *(Tier: SQL)*
`observed` / `observed_absent` / `unknown`. "I did not log a drink" and "I
logged that I did not drink" are different facts and must never collapse into
the same zero.

**RULE-08 — Estimates are intervals, not points.** *(Tier: SQL + LINT)*
Any quantity that was resolved rather than measured is stored as an
asymmetric interval with an `estimate_method` column. Nutrition is the leading
case: text-only LLM recall carries 652 kcal MAE and frontier vision runs ~36%
MAPE with systematic downward bias, so a single number is a lie about
precision. Interval width is a function of the resolution method.

**RULE-09 — A vision or language model's output never becomes a gram, a
calorie, a macro, or a dollar.** *(Tier: LINT + TEST)*
Models extract names, quantities, and verbatim evidence spans. Deterministic
lookup against a reference source converts names into quantities. The boundary
is absolute and is checked by a lint rule on the extraction schema.

**RULE-10 — A human correction outranks every automated layer, permanently.**
*(Tier: TEST)*
Once I correct a category, a portion, an entity match, or a label, no
downstream process may re-guess it. Corrections are first-class rows with their
own provenance and are replayed over every rebuild.

---

## II. COMPUTE AND CORRECTNESS

**RULE-11 — The model plans and narrates. It never computes.** *(Tier: TEST)*
All arithmetic and all statistics are executed deterministically and stored.
The language layer receives result rows and renders them. Evidence (PHIA,
*Nature Communications*, 12 Jan 2026): reasoning in-context with no tools scored
22%; one-shot generated-and-executed code scored 74%; the full agentic loop
scored 84%. Executing code at all buys the large gap (22→74); the loop adds the
last ~10 points (74→84). Gemini 1.0 Ultra for all main results (the paper also
reports a GPT-4 chain-of-thought comparison at 53.6%); not yet independently
replicated — the architectural conclusion holds regardless. See ADR-001, ADR-0014.

**RULE-12 — Compute happens exactly once, in one place, stamped.**
*(Tier: SQL + REVIEW)*
Every derived measure has exactly one named owner and one `code_version`.
Nothing recomputes a value it does not own. This is why two screens agree by
construction rather than by coincidence. Placement is governed by ADR-001; a
computation with a rendering surface and no named owner fails CI.

**RULE-13 — The model never selects the temporal specification.**
*(Tier: TEST + REVIEW)*
Lag structures, window definitions, aggregation choices, and adjustment sets
come from the pre-registered hypothesis and the metric registry — never from the
model at query time. The model may plan and narrate (RULE-11); the temporal and
causal-analysis parameters are fixed data, not model output. Evidence: HEARTS
(ICML 2026 poster; arXiv:2603.06638) found code execution fixes arithmetic but
**not** temporal reasoning — the degradation persists even under a CodeAct
code-execution harness, models falling back on heuristics as temporal complexity
rises. See ADR-0014. *(This rule replaced the former RULE-13, "the PWA renders,
it does not compute," which merged into RULE-14 to hold the 30-rule cap.)*

**RULE-14 — The render layer renders; it never computes, and every number it
emits traces to a stored computation.** *(Tier: LINT + TEST)*
No arithmetic beyond formatting in client code — a lint rule bans arithmetic
operators outside a formatting allowlist in the render layer. Numeral-template
rendering: the renderer refuses to emit a numeral that is not present in the
result set it was given. A model that produces "about 25 fewer minutes" when the
stored value is −21.4 is refused, not rounded.

**RULE-15 — Nothing may require the language model to be available.**
*(Tier: TEST)*
Every surface degrades to a deterministic rendering. The model is a
presentation improvement, never a dependency.

---

## III. HONESTY AND CLAIMS

**RULE-16 — Six tiers, and every claim carries one.** *(Tier: SQL + LINT)*
`DESCRIPTIVE` → `CANDIDATE` → `PROMOTED` → `CONFIRMED_OBSERVATIONAL` →
`EXPERIMENTAL`, plus `INSUFFICIENT`. Each tier has a permitted vocabulary
enforced by a linter. A claim rendered in language above its tier fails the
build.

**RULE-17 — `CANDIDATE` is never shown.** *(Tier: TEST)*
Automated structure-discovery output — PCMCI+, VAR-LiNGAM, regularized VAR —
enters the system only as `CANDIDATE` and never reaches a screen. These are
hypothesis generators, not findings. The distrust is empirical, not stylistic:
CausalDynamics (NeurIPS 2025, arXiv:2505.16620; 14,693 graphs) scored PCMCI+
**at chance** on its simple tier (AUROC 0.52 / 0.50 / 0.49); coupled systems fare
better (~0.67). At chance on the easy case is reason enough never to show it. See
ADR-0014.

**RULE-18 — `INSUFFICIENT` is a returnable, displayable answer.**
*(Tier: TEST)*
*This rule overturns the previous doctrine, at my explicit instruction.*
Weak evidence is disclosed as weak evidence with what it would take to settle
it. Absent evidence is disclosed as absent. Silence is not permitted as the
response to a question I asked.

**RULE-19 — Pre-registration is a database constraint, not a promise.**
*(Tier: SQL)*
A hypothesis carries `preregistered_at`, direction, lag, and adjustment set. A
schema constraint makes it impossible to confirm a hypothesis using data that
already existed when it was registered.
The exploratory pass over the pre-existing ~two years of data runs **once,
early**, and its only output is a written register of pre-registered hypotheses
with their adjustment sets, lags, and windows fixed and stamped **before** any
new data accumulates. This starts the waiting clock on day one instead of month
three, and puts the old data to the job it is actually good for — generating
hypotheses, never confirming them. (Amended 2026-08-23, Phase-1 ruling; ADR-0015.)

**RULE-20 — Every promoted finding emits a scored forward prediction.**
*(Tier: TEST)*
Findings whose predictions fail are demoted automatically, without human
intervention. *This is the structural defence against a system that tells me
what I want to hear, which is the failure mode most likely to sink this
project.*

**RULE-21 — Multiplicity is controlled hierarchically, and `n_eff` is
reported.** *(Tier: TEST)*
Tree-structured FDR over domain → variable-pair → lag. Newey–West HAC standard
errors are mandatory — the naive false-positive rate is ~0.78 versus ~0.07 at
ρ = 0.5. Any surface reporting `n` without `n_eff` fails.

**RULE-22 — These methods are forbidden.** *(Tier: LINT)*
NOTEARS and DYNOTEARS (scale non-invariance; varsortability above 0.94), DSEM,
convergent cross-mapping, multivariate transfer entropy, model-X knockoffs. A
CI check greps imports and fails on any of them.

---

## IV. WHAT THE SYSTEM MAY AND MAY NOT SAY

**RULE-23 — Never moralise.** *(Tier: LINT)*
No units-per-week counter, no guideline comparison, no spending judgment, no
screen-time score, no "necessary" or "unnecessary" as a system-generated label.
The money surface exists — *this reverses the previous prohibition, at my
instruction* — but a surface that tallies and scolds does not.
*Independent support: precise, always-on spending feedback has been shown to
increase spending by $32–40. The restraint is not squeamishness; the nagging
version measurably backfires.*

**RULE-24 — No live counters, no streaks, no gamification, no celebratory
animation.** *(Tier: LINT + REVIEW)*
A displayed number is itself an intervention: an RCT manipulating displayed
step counts causally worsened mood, self-esteem, diet, blood pressure and heart
rate. Coverage is shown as a rolling 7-day figure, never as a streak that can
be broken.

**RULE-25 — Notice and ask. Do not conclude.** *(Tier: TEST)*
Below `CONFIRMED_OBSERVATIONAL`, the system surfaces a pattern as a question,
never as a fact about me.

**RULE-26 — Never diagnose, never prescribe medically, never interpret a
symptom.** *(Tier: LINT + REVIEW)*

**RULE-27 — Never nag, and never repeat a dismissed prompt.** *(Tier: TEST)*
One prompt per subject per day, maximum. Prompts are scheduled, never random —
scheduled morning prompts achieve 81% compliance versus 52% for random pings.
No battery exceeds 26 items.

---

## V. COST, PRIVACY, CAPTURE

**RULE-28 — $0 recurring. No exceptions, including small ones.**
*(Tier: REVIEW + LINT)*
Every dependency must be justified in an ADR stating its free-tier limit,
projected usage, and behaviour at the limit, **before** it is added. A service
that bills on overage rather than failing is disqualified. Cloudflare Workers
AI is preferred partly because it hard-fails rather than billing. Projected
steady-state usage is ~2,760 neurons/day against a 10,000/day allowance.

**RULE-29 — Personal data leaves this system only to Supabase, Cloudflare
Workers AI, and originating source APIs.** *(Tier: LINT + SQL)*
No location data is ever sent to a third party including the model layer. Home
coordinates never appear in any export, log line, or prompt. Non-home places
are stored at ~100 m precision. Analysis uses place labels, never coordinates.
Every outbound model call writes a row to `ops.egress_log`.
**A public git repository is a third party.** The repo is public (OQ-03,
ADR-0013), so not one row of personal data is ever committed or tracked — code
and specs are public, the life they describe is not. Every data path (Parquet,
exports, fixtures, caches) is gitignored by default; `_legacy_snapshot/` stays
gitignored permanently. A tracked `.parquet`, `.csv`, `.db`, or `.sqlite` file
fails CI (`tools/validate_layout.py`). Any exception is justified in an ADR
before the file is tracked.

**RULE-30 — iOS Shortcuts owns all media capture. The PWA never calls
`getUserMedia`.** *(Tier: LINT)*
On iOS, microphone and camera permission grants are not persisted for a PWA
launched from the home screen — a real, still-unfixed WebKit limitation, the
direct cause of the repeated "allow for this website" prompts. (No bug number is
cited: the ticket previously named here, 215884, was a misattribution — it covers
prompt recurrence on hash navigation and is resolved — and persistent grants
across reloads are, per a WebKit engineer, a separate unfixed request.) Shortcuts
capture audio and photos and post them; the PWA reads, and writes long-form text
only. A call to `getUserMedia` in client code fails the build.
The case is stronger than a bug workaround: Apple's on-device Foundation Model is
reachable from Shortcuts with structured output and no developer account, and
Apple's on-device SpeechTranscriber beats WhisperKit base.en on **accuracy**
(14.0 vs 15.2 WER; WhisperKit is the *faster* one, 111× vs 70× realtime). So
Shortcuts-owned capture is free, private, offline, and — on accuracy — *better*,
not merely the option left after a bug. **Revisit trigger:** if iOS/WebKit ships
persistent media-permission grants for home-screen PWAs, this rule is re-opened,
not silently kept — but the free/private/offline on-device advantages survive
that fix and must be weighed then.
(Amended 2026-08-23, Phase-1 ruling; ADR-0015.)

---

## DEFINITION OF DONE

A unit of work is done when every line below is true and evidenced. "Evidenced"
means a command output, a query result, or a file diff pasted into the session
— not an assertion.

1. Requirement IDs satisfied are quoted, and every one has a test whose name
   contains the ID.
2. Tests pass, and the passing output is shown. No test was skipped, weakened,
   or marked expected-failure to achieve this.
3. All CI invariant queries return zero rows, output shown.
4. `ops/features.json` has been updated by moving an entry from failing to
   passing — never by deleting or editing an entry.
5. Migrations are forward-only, numbered, and were run against a copy first.
6. Any decision not already specified is recorded as an ADR.
7. Anything discovered and not resolved is appended to `docs/OPEN_QUESTIONS.md`.
8. `ops/PROGRESS.md` has a new appended entry.
9. **WHAT I DID NOT DO** — an explicit written section naming what was
   stubbed, simplified, deferred, hardcoded, or left partial. An empty section
   here is itself a review finding, not a success.

---

## NON-GOALS

Not multi-user. Not real-time. Not a product, not a startup, not for anyone
else. No native app. No graph database — the entity count is roughly 80 and
fits one Postgres table. No FHIR or Solid as infrastructure. No SNOMED CT
($1,954/yr). No paid data aggregator. No causal claim from observational data
without a registered adjustment set. No feature whose purpose is engagement.
