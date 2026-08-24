# REMEDIATION PLAN — everything known to be wrong, and the order to fix it

Dated 23 August 2026, after the constitution audit (ADR-0029) and its ratification.

This is the complete list of known defects, gaps and unproven assumptions in the
project, ranked, sequenced, and costed in sessions. It exists so that "what's
still broken" is a document rather than something you have to hold in your head
or ask about.

**Principle for the ordering:** fix the things that get more expensive with
time, first. Document errors are cheap now and expensive after code depends on
them. Data that isn't captured is gone permanently. Everything else can wait.

---

## TRACK 0 — starts today, runs forever, not a session

**Capture.** Zero workouts. Zero food. Three self-reports total. One thousand
transactions and nothing since. Your primary objective function — strength and
body composition — has no data feed at all.

No phase of this build fixes that, and nothing can backfill it. Every week
without capture is a week the statistics layer can never use. Install a lifting
logger, photograph meals, keep a short nightly note. Crude is fine; Phase 3
imports crude perfectly well.

**This is the single highest-value action available to you and it does not
require the terminal.**

---

## TRACK 1 — the same error, one layer down (do before Phase 3)

### 1.1 Requirements audit — 1 session

The 564 requirements were written by three sub-agents in parallel, in a single
turn, before any rulings existed, under the framing the constitution audit just
overturned. They have never been checked against what you actually want.

One instance is already known and was found *by accident*: `REQ-NAR-024` does
not merely omit prescription — it forbids rendering any behaviour "with a
judgment attached." Nobody was looking for it.

Same audit as the constitution: every requirement checked against the eleven
stated wants, conflicts ranked by how much they remove, nothing changed.

**Expect this to find more than the constitution audit did.** Four times the
volume, written faster, never reviewed.

### 1.2 Requirements ratification and correction — 1–2 sessions

Read at consequence level, rule by rule, as with the constitution. Correct what
conflicts. Do not let unrelated tidying in.

### 1.3 The missing requirement sets — 2–3 sessions

These do not exist and are load-bearing:

- **REQ-ACT** — prescription. Scoped in ADR-0029 §4, not authored. When the
  system may recommend, on what evidence tier, in what language, how often, and
  what happens when it is wrong. This is the thing you asked for first.
- **REQ-LOC** — location. Unblocked by today's RULE-29 ruling. Place resolution,
  dwell and visit detection, mobility metrics, the restricted-access boundary,
  and the egress lint.
- **REQ-WKT** — workouts and the objective function. Flagged in session two,
  never written. Your primary objective has neither data nor requirements.
  e1RM, sets, RPE, volume, lean mass. **Write this one first of the three** —
  it is the only one where the absence is already costing you data.
- REQ-BOD, REQ-SLP, REQ-CTX, REQ-NFR — flagged as unwritten in
  `REQUIREMENTS_INDEX.md`. Lower priority; scope them, defer authoring.

---

## TRACK 2 — schema consequences of today's rulings (1 session)

Two additive migrations, both cheap now and expensive after Phase 3:

- **Restricted location table** plus place-label and mobility derivation, with
  access separated from any egress-capable session.
- **Recommendations table** — what was recommended, its evidence tier, its
  forward prediction, and what actually happened. Without this, RULE-20's
  auto-demotion cannot function and every recommendation is unaccountable.

Also re-opens ADR-0027's deferral of the `locations` backfill.

---

## TRACK 3 — infrastructure that is currently broken or unproven

### 3.1 Gate 0 — the keepalive is not registered — in progress

GitHub has the file and has not registered it as a workflow. No clock is
running. Your database survives today because the *old* stack pings it — luck,
not design. Until a keepalive fires and leaves an `ops.runs` row, Gate 0 stays
open and Supabase can pause.

### 3.2 Storage ceiling — known, quantified, untested

200.5 MB of 500 MB used before live capture stores anything. The plan is to
reclaim ~174 MB by retiring the old stack at Phase 3 (OQ-17), then load legacy
atoms from Parquet if a named analysis needs them (OQ-29). Neither step has
been executed.

### 3.3 The loader defects owed before any legacy load (OQ-29)

Recorded, unfixed, and they must be fixed before the deferred backfill ever
runs:

- `subject_day` is computed per stage-segment, so a night straddling 04:00 is
  split across two days — the by-wake-day rule needs per-night sessionisation.
- `evidence_span` names dedup-secondary tables that have no capture row.
- A dead `txn_amount` registry row, and hardcoded excluded-bucket constants in
  `backfill_run.py` that are not recomputed from the manifests.

### 3.4 Timezone inference — the load-bearing unverified assumption

`pos__chrome` read as UTC and `pos__youtube` as Eastern, inferred from
timestamp alignment, never confirmed against the source extractors. If either
is wrong, every web, media and calendar `subject_day` shifts and the
cross-export duplicate counts are skewed — and nothing in the database would
catch it.

---

## TRACK 4 — Phase 2.5, the gates that catch a lying build (2 sessions)

Unchanged from the earlier plan, and still correct to do before Phase 3:
fabrication check, forbidden-import lint (closes OQ-15 and lets RULE-29 claim
tier LINT), moved-threshold check, environmental hardening with randomised
fixtures, and the four legibility numbers — mutation score, complexity and
duplication, requirement-ID coverage, and a proven-count only the test runner
can increment.

**Scope discipline applies:** do not build a control that has nothing to check
yet. Specify it, name its trigger, defer the code.

---

## TRACK 5 — the dependency created today

Today's ratification made the **tier-labelling surface** load-bearing: continuous
exploration cannot ship until the machinery that makes EXPLORATORY
un-mistakable for a finding is built and *proven*.

That surface lives in Phase 7 — the least-specified phase in the project, and
the one where the answer is your taste rather than a passing test.

**Consequence:** a slice of Phase 7 must be pulled forward to precede Phase 6.
Scope it during the REQ-UI work rather than discovering it at Phase 6.

---

## SEQUENCE

| # | Work | Sessions |
|---|---|---|
| — | **Capture — starts today, parallel to everything** | — |
| 1 | Apply the ratified constitution restructure *(in flight)* | 0.5 |
| 2 | Fix keepalive registration; fire it; Gate 0 clock starts | 0.5 |
| 3 | **Requirements audit** | 1 |
| 4 | Requirements ratification + correction | 1–2 |
| 5 | **REQ-WKT** (objective function — write first) | 1 |
| 6 | REQ-ACT + REQ-LOC | 1–2 |
| 7 | Schema addendum: location table, recommendations table | 1 |
| 8 | Phase 2.5 gates | 2 |
| 9 | **Phase 3 — the Big Mac slice** | 6–12 |

Roughly **eight to ten sessions** before Phase 3 begins — of which six are the
document correction that today's audit showed is necessary. Nothing already
built is discarded. The schema, the migrations, the archive, the tests and the
integrity rules all stand.

---

## WHAT THIS PLAN DOES NOT CLAIM

It does not claim the project is now correct. Today proved that a systemic
error can survive eleven sessions of careful work, and the requirements audit
has not run yet.

What it claims is narrower and more useful: **every known defect is written
down, ranked, and sequenced, and the ones that get more expensive with time are
scheduled first.**

Three things remain genuinely unknowable in advance, and no plan removes them:
whether capture compliance holds, whether n=1 inference on this data yields
anything worth knowing, and whether an EXPLORATORY label actually stops a human
believing noise.
