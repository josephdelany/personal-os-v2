# CONSTITUTION RESTRUCTURE — proposal for consequence-level ratification

> **Status: PROPOSAL. Nothing here is applied to `CONSTITUTION.md`.** This is the
> document Joe reads, rule by rule, at the level of *what each change makes possible
> and what it still forecloses* — the opposite of the batched one-line-summary
> ratification that let RULE-29 through. Decision record: ADR-0029.
>
> **How to ratify:** for each rule below, the line that matters is **CONSEQUENCE**.
> Read that. If the consequence is what you want, mark the rule ✅. If not, say so and
> it does not move. Nothing ships until every rule is marked.

---

## 1. The structure being proposed

Three sections, replacing the current flat list of 30. **No rule is renumbered or
added; the 30-cap holds.** Each rule is assigned to a section; five hybrids are split
in place.

| Section | Meaning | Amendment bar |
|---|---|---|
| **INTEGRITY** | How we know something is true. | Written consequence-analysis **+ an adversarial review that tries to break the change.** Finding nothing = failed review, re-run. |
| **SCOPE** | What the system may be about, capture, say, or do. | Written consequence-analysis, ratified by reading it (not a summary). Recorded as an ADR. |
| **HYBRID (split)** | An integrity core braided with a scope shell. | The integrity clause takes the INTEGRITY bar; the scope clause takes the SCOPE bar. |

The amendment bar *is* the fix. Immutability is not proposed, because RULE-29 was
ratified as if principled and was wrong — freezing it would have frozen the mistake.
What failed was reading the summary instead of the consequence. So the rule from now
on: **you cannot change a rule without stating, in writing, the consequence of the
change** — and for integrity rules, without someone actively trying to break it.

---

## 2. The audit result — every rule, classified, with the conflict named

Ranked within each tier by how much of a stated want it removes. **Wants** referenced:
(#1) everything-with-everything general inference, NOT fixed hypotheses; (#2) tell me
what to do today / prescription; (#3) find true things I didn't know; (#4) show me
myself honestly; (#5) answer any question; (#6) capture everything I'm exposed to;
(#7) strength/body-comp as objective; (#8) finance as a full system; (#9) alcohol fully
instrumented; (#10) location first-class; (#11) consolidate ~8 apps.

### 2A. INTEGRITY — stays. None forecloses a want.

| Rule | What it does | Verdict |
|---|---|---|
| RULE-00 | Never weaken a gate/threshold/invariant/test. | Stays. Forecloses nothing. |
| RULE-01 | No fabricated data. | Stays. Caught the July 4,000-row incident's class. |
| RULE-02 | raw_captures/atoms append-only. | Stays. |
| RULE-03 | Everything bitemporal. | Stays. |
| RULE-04 | No metric includes data after its window closed. | Stays. |
| RULE-05 | Measured and inferred never share a column. | Stays. **Enables** honest inference. |
| RULE-06 | Never impute. | Stays — **with a clarification** (§3G): a modelled estimate carrying its own uncertainty is not imputation. |
| RULE-07 | Presence is three-valued. | Stays. Enables #4. |
| RULE-08 | Estimates are intervals, not points. | Stays. Enables #1/#8 honestly. |
| RULE-09 | A model's output never becomes a gram/calorie/dollar; deterministic lookup does. | Stays. #8 receipts: the amount is a *verbatim extraction*, not a model estimate — compatible. |
| RULE-10 | Human correction outranks every automated layer. | Stays. Enables #4. |
| RULE-11 | Model plans and narrates, never computes. | Stays. #1 inference is executed deterministically — compatible. |
| RULE-12 | Compute once, one owner, stamped. | Stays. |
| RULE-14 | Render layer renders; every numeral traces. | Stays. |
| RULE-15 | Nothing may require the LLM to be available. | Stays (robustness). Forecloses nothing. |
| RULE-16 | Six tiers, every claim carries one. | Stays. The machinery #4 and REQ-ACT hang off. |
| RULE-18 | INSUFFICIENT is a displayable answer. | Stays. **Enables** #5. |
| RULE-20 | Every promoted finding emits a scored forward prediction; failure auto-demotes. | Stays. **The safety rail for #2.** |
| RULE-21 | Multiplicity controlled hierarchically; n_eff reported. | Stays. The honest cost of #1. |
| **INV-1…INV-6** | Lineage, append-only, traceability, point-in-time, lane separation, never-weaken. | **All stay. All pure integrity. None forecloses a want.** |

### 2B. SCOPE — revisable. Conflicts named.

| Rule | Forecloses | Severity |
|---|---|---|
| RULE-29 | #10 location entirely; degrades #7, #8, #9. | **Tier A (highest).** |
| RULE-25 | #2 prescription (only questions permitted below CONFIRMED). | High. |
| RULE-23 | #2, #8 (necessity, habit teaching), #9 (alcohol counter). | High. |
| RULE-24 | #7/#2 progress display. | Medium. |
| RULE-27 | #2 coaching cadence (one prompt/subject/day). | Low. Compatible with #2. |
| RULE-26 | #2 at the medical edge. | Low — clarify. |
| RULE-28 | #8 automated bank state. | Medium — **self-imposed, NO CHANGE.** |
| RULE-30 | capture *path* only (#6). | Low. Well-justified. |

### 2C. HYBRID — split. The dangerous ones.

| Rule | Integrity core (stays, INTEGRITY bar) | Scope shell (opens, SCOPE bar) | Forecloses |
|---|---|---|---|
| RULE-13 | The model never selects the temporal spec at query time (it plans/narrates). | — (the spec source can widen to the registry, not just a frozen hypothesis). | #1 |
| RULE-17 | Automated discovery cannot be *confirmed* or shown *as a finding*. | "Never reaches a screen" → **may be shown as explicitly-labelled exploratory**. | #1, #3, #5 |
| RULE-19 | Cannot confirm a hypothesis on data that existed at its registration; CONFIRMED carries a frozen pre-registration. | "Exploratory pass runs **once, early**" → **exploration is continuous**. | #1, #3 |
| RULE-22 | (none — it is a method-quality claim) | The forbidden-method blocklist becomes revisable with evidence. | method scope |
| RULE-29 | Coordinates/home never egress (export/log/commit/prompt); no coords to a model (ADR-0020); no personal data in git (ADR-0013). | "Never store coordinates / analysis uses labels never coordinates" → **store restricted, derive labels + mobility**. | #10 |

---

## 3. The rewrites — read each CONSEQUENCE

Below, each changed rule shows **NOW** (what the live text does), **PROPOSED** (the new
wording, verbatim enough to ratify), and **CONSEQUENCE** (what becomes possible, what
stays foreclosed, the risk). Unchanged rules are in §2A/§2B tables and not repeated.

### 3A. RULE-29 — location (Tier A) → SCOPE + a retained INTEGRITY clause

**NOW:** "No location data is ever sent to a third party… Home coordinates never appear
in any export, log line, or prompt. Non-home places are stored at ~100 m precision.
Analysis uses place labels, never coordinates." In practice this was read as *do not
store coordinates*, which deleted the domain.

**PROPOSED (SCOPE clause):** Coordinates are stored in a **restricted table** with
access separated from any egress-capable session. The system **derives place labels and
mobility metrics** (dwell, visit, radius of gyration, location entropy, commute/transit
load) from them. **Raw coordinates and the home location never enter an export, a log
line, a commit, or a model prompt.** Non-home places egress at ~100 m precision;
home never egresses at any precision. A lint fails the build if a coordinate or the home
location can reach an export, log, or prompt path.
**PROPOSED (retained INTEGRITY clause, unchanged in force):** No personal data is ever
tracked in git; a tracked `.parquet/.csv/.db/.sqlite` fails CI (ADR-0013). No coordinate
reaches any model; egress-reading and personal-reading capabilities never coexist in one
session (ADR-0020).

**CONSEQUENCE:** Location becomes a first-class domain (#10). Gym attendance becomes
ground truth for the objective function (#7); bar/pub dwell becomes no-self-report
alcohol exposure (#9); merchant+place gives true purchase context (#8). Privacy intent is
*unchanged* — the thing that was protected (coordinates/home leaving) is still protected,
now by an egress lint instead of a storage ban. **Risk:** a new place-resolution pipeline
and restricted-access controls are new surfaces with new failure modes; the lint is now
load-bearing. **Re-opens** ADR-0027's deferral of the `locations` backfill (Phase 4).

### 3B. Pre-registration cluster — RULE-13 / RULE-17 / RULE-19 → SPLIT

**NOW:** RULE-19 runs the exploratory pass "**once, early**"; RULE-17 says automated
discovery "**never reaches a screen**"; RULE-13 fixes the temporal spec to the
pre-registered hypothesis. Net effect: ask an open-ended question, the answer is
CANDIDATE-tier, CANDIDATE is never shown — so #1/#3/#5 are foreclosed in their
open-ended form.

**PROPOSED — INTEGRITY core (does not move, INTEGRITY amendment bar):**
- You **cannot confirm** a hypothesis using data that existed when it was registered.
- A **CONFIRMED** claim carries a **frozen pre-registration** (direction, lag, adjustment
  set, window), and the model never selects those parameters at query time.

**PROPOSED — SCOPE shell (opens, SCOPE amendment bar):**
- **Exploration is continuous**, not a single early pass. General probabilistic inference
  may run over the whole metric registry at any time (#1).
- **Exploratory output IS displayable**, carrying an explicit **EXPLORATORY** label,
  never presented as a finding and never in confirmed-tier vocabulary.

**BINDING SEQUENCING (Joe's ruling, load-bearing):** the **tier-labelling surface** —
the UI/render machinery that makes EXPLORATORY visually and linguistically
un-mistakable for a finding — is **built and proven before continuous exploration
ships.** The label is the only thing between exploration and false confidence.

**CONSEQUENCE:** "Everything in conversation with everything, NOT a fixed set of
hypotheses" (#1) becomes possible; discovery of things Joe didn't know (#3) can surface;
"answer any question" (#5) stops bottoming out at a hidden CANDIDATE. Confirmation
remains as strict as today — the defence against telling Joe what he wants to hear does
not move. **Risk (the one that matters most in this whole document):** continuous
exploration multiplies the multiplicity problem (RULE-21 gets harder), and if the
EXPLORATORY label is weak or absent, Joe over-trusts structure that scored *at chance*
(RULE-17's cited CausalDynamics evidence, AUROC ~0.52). This failure is **invisible** —
it produces plausible findings. Hence the sequencing constraint is a gate, not a
preference.

### 3C. RULE-25 — notice and ask → REWORD (SCOPE)

**NOW:** "Below CONFIRMED_OBSERVATIONAL, the system surfaces a pattern as a question,
never as a fact about me." For N=1 data, CONFIRMED may be far off or unreachable, so
prescription (#2) is effectively never permitted.

**PROPOSED:** Below CONFIRMED_OBSERVATIONAL the system **MAY recommend an action with
disclosed uncertainty and its evidence tier**, and **MUST NOT assert the underlying
pattern as established.** A recommendation names its tier, its uncertainty, and what
would raise it. RULE-20's scored forward prediction and auto-demotion applies to every
recommendation.

**CONSEQUENCE:** "Tell me what to do today" (#2) becomes permitted — as an explicitly
provisional recommendation, not a claim of fact. Honesty is preserved: the system still
cannot state an unconfirmed pattern as true. **Risk:** recommendations built on weak
evidence — mitigated structurally by RULE-20 (a recommendation that predicts and fails is
auto-demoted, no human in the loop). This rule is the hinge REQ-ACT (§4) hangs on.

### 3D. RULE-23 — never moralise → REWORD (SCOPE)

**NOW:** bans the "necessary/unnecessary" label, spending judgment, units-per-week
counter, guideline comparison. Collides with #8 (necessity inferred from usage; habit
teaching) and #9 (alcohol instrumented).

**PROPOSED:** The system **MAY** surface usage-based necessity (`used`/`unused`/`unknown`,
per OQ-07), top-spend rankings, and **neutral pattern teaching** (what happened, when,
how it covaries — without a verdict). The system **MUST NOT** attach a judgment,
guideline comparison, or moral label to any behaviour, rating, or total. The
judgment-vocabulary linter (extending REQ-NAR-023's banned wordlist) fails the build on a
violation.

**CONSEQUENCE:** Finance as a full system (#8) and alcohol instrumentation (#9) become
expressible as *information*; the thing shown to backfire ($32–40 overspend from precise
always-on feedback; nagging) stays banned. The distinction is **information vs. scolding**,
enforced by a linter, not left to taste. **Risk:** the boundary between "neutral pattern"
and "implied judgment" is a wording judgment; the linter reduces but does not eliminate it.

### 3E. RULE-24 — no live counters/streaks → REWORD (SCOPE)

**NOW:** "No live counters, no streaks, no gamification, no celebratory animation."
Read strictly, forecloses a plain progress display toward the strength objective (#7).

**PROPOSED:** The system **MUST NOT** display a streak, a compliance score, a composite
wellness score, a celebratory animation, or a step-count-style live intervention counter.
It **MAY** display plain progress metrics toward the stated strength/body-composition
objective (e.g. e1RM over time, lean-mass trend), shown without gamification and without
a broken-streak mechanic. Coverage remains a rolling 7-day figure.

**CONSEQUENCE:** #7's objective becomes *visible* (you can see whether you're getting
stronger) without importing the displayed-number-as-intervention harm (the step-count
RCT). **Risk:** "which number is an intervention" is a judgment call per surface; the ban
list is the guardrail.

### 3F. RULE-26 — medical boundary → CLARIFY (SCOPE)

**NOW:** "Never diagnose, never prescribe medically, never interpret a symptom." Risks
over-blocking lifestyle prescription (#2) at the edge.

**PROPOSED (clarification, not a loosening):** The system MUST NOT name a medical
condition, interpret a symptom, or recommend a medical action (dosing, medication,
treatment) — it returns the stored referral string with the data attached (REQ-ASK-028).
It **MAY** make a **behavioural/lifestyle recommendation** grounded in Joe's own logged
data ("you're under-slept; lift lighter today"), which is distinct from a medical claim
(REQ-ASK-029 already draws this line for *answers*; this extends it to *recommendations*).

**CONSEQUENCE:** #2 works for training/sleep/spend without the system pretending to be a
clinician. **Risk:** the behavioural/medical line is genuinely fuzzy at the edges (e.g.
"your resting HR is trending up"); when unsure, the rule defaults to the referral string.

### 3G. RULE-06 — never impute → CLARIFY (INTEGRITY)

**NOW:** "A missing value stays missing. No carry-forward, no mean-fill, no
interpolation." Could be misread to forbid any model-produced estimate, foreclosing #1.

**PROPOSED (clarification):** RULE-06 forbids **imputing a missing input and treating it
as measured.** It does **not** forbid a **modelled estimate that carries its own
uncertainty** — stored as an interval with `estimate_method` and lane=inferred
(RULE-05/08). An imputed mean-fill masquerading as data is forbidden; a posterior with an
honest interval is the system working as designed.

**CONSEQUENCE:** General probabilistic inference (#1) is unblocked without weakening the
no-guessing rule. Nothing about missing *inputs* changes.

### 3H. RULE-22 — forbidden methods → MOVE TO SCOPE (revisable)

**NOW:** a fixed blocklist (NOTEARS, DYNOTEARS, DSEM, CCM, multivariate transfer entropy,
model-X knockoffs), enforced by an import grep.

**PROPOSED:** Same blocklist, same CI grep — **but classified SCOPE**, revisable with
evidence via an ADR, because "which methods are too unreliable to use" is an
evidence-based scope-of-method choice that will change as the literature does, not an
invariant of truth.

**CONSEQUENCE:** No behavioural change today; the list can be updated with evidence
instead of being frozen. **Risk:** none material — the CI grep still enforces whatever the
current list is.

### 3I. Unchanged, stated for completeness

- **RULE-28 / non-goal "no paid data aggregator" — NO CHANGE.** $0 recurring holds; #8's
  automated bank state stays limited (OQ-09 SimpleFIN closed). Joe's deliberate rule.
- **RULE-27, RULE-30** — unchanged; low/no conflict.
- **Non-goals** — "no graph database" flagged for revisit *if* #1's inference scales
  (not now); "no causal claim without a registered adjustment set" is the pre-registration
  integrity core (3B) restated and stays.

---

## 4. REQ-ACT — scoping the prescription layer (PLAN ONLY, not authored this session)

**The finding, verified:** none of the 564 requirements authorizes prescription. The
output surfaces are REQ-ASK (descriptive answers) and REQ-NAR (narration *restraint*,
which forbids judgment). REQ-ASK-024's forward clause proposes an *experiment*, not an
action. So "tell me what to do" — Joe's first-stated want — has no home. REQ-ACT is that
home. It depends on RULE-25 (3C) being reworded first, and on the tier-labelling surface
(3B) existing.

A REQ-ACT set would need to cover, at minimum:

1. **WHEN the system may recommend.** Trigger conditions: on request ("what should I do
   today?"), and proactively at most within RULE-27's cadence (one prompt/subject/day,
   scheduled not random). A recommendation requires a *stored computation* behind it
   (same traceability as REQ-ASK-009/011) — no recommendation from model world-knowledge.
2. **On what EVIDENCE TIER.** The floor. Options for Joe to rule: (a) recommendations
   allowed from DESCRIPTIVE with mandatory uncertainty disclosure (maximally useful,
   maximally risky); (b) from PROMOTED upward only (safer, quieter); (c) tier-gated
   *language* — a DESCRIPTIVE recommendation must use hedged verbs ("might be worth"), a
   CONFIRMED one may use direct verbs ("do"). Recommendation: **(c)**, because it maps the
   existing per-tier vocabulary linter (REQ-NAR-020) onto actions rather than inventing a
   parallel gate. Every recommendation carries its tier and coverage, like every answer
   (REQ-ASK-020/021).
3. **In what LANGUAGE.** A new **action vocabulary per tier** in `tier_vocabulary`,
   linted like REQ-NAR-020/021: below CONFIRMED, imperative-with-hedge and always with the
   uncertainty and the "what would raise it" line; never a bare command, never a moral
   frame (RULE-23), never a medical directive (RULE-26/3F).
4. **How OFTEN.** Bounded by RULE-27 (≤1 prompt/subject/day, ≤26-item battery, never
   repeat a dismissed recommendation). A recommendation Joe declines is logged
   (`prompt_dispatch`, ADR-0017) and not re-issued.
5. **What happens when it turns out WRONG.** This is the crux and the reason REQ-ACT is
   safe to build. Every recommendation **emits a scored forward prediction** (RULE-20):
   the recommendation implies an expected outcome; the outcome is scored; a recommendation
   whose predictions fail is **auto-demoted**, and the pattern behind it is demoted, with
   no human in the loop. A recommendation is therefore a *falsifiable object with a
   track record*, not advice that evaporates. REQ-ACT must specify the demotion thresholds
   (these join OQ-10's placeholder-threshold set — set against real data, not guessed now).
6. **What it MUST NOT do.** No medical directive (referral string instead, REQ-ASK-028).
   No moralising (RULE-23). No streak/gamified nudge (RULE-24). No recommendation lacking
   a stored computation and a scored prediction. No coordinate or home location in the
   recommendation text (RULE-29).

**Open questions REQ-ACT raises (for OQ, not decided here):** the evidence-tier floor
(2 above); whether a proactive recommendation counts against RULE-27's single daily
prompt or is a separate channel; the demotion thresholds; whether Joe wants a daily
"what to do today" digest surface or only on-demand.

---

## 5. What Joe ratifies here

- [ ] The three-section structure (§1) and the amendment-by-consequence bars.
- [ ] Each rewrite in §3 — one ✅ per rule, read at its CONSEQUENCE line.
- [ ] The REQ-ACT scope (§4) as the plan for the prescription layer (authoring deferred).
- [ ] The binding sequencing: tier-labelling surface before continuous exploration (3B).

On ratification, the follow-through in ADR-0029 §"Enforcement / follow-through" is owed,
and `CONSTITUTION.md` is restructured into the three sections with all 30 numbers intact.
