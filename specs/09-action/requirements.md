# 09 — ACTION LAYER: REQUIREMENTS (EARS)

**Spec:** `specs/09-action/requirements.md` · **Subject:** Personal OS, single user (Joe), n=1
**Grammar:** EARS (Mavin & Wilkinson). Five patterns only. `SHALL` is binding. `SHOULD` does not appear.
**Sources:** RULE-25 as reworded by ADR-0029; the OQ-30 ruling (ADR-0052, Joe via advisor, 2026-09-02);
REQ-TIER-047/048/049 (the disclosure contract, which already existed); the REQ-INF "Missing-E" trigger
(`specs/04-reasoning/requirements.md` line 541); RULE-20, RULE-26, RULE-27, REQ-NAR-020.

**ID scheme:** `REQ-ACT-nnn`. IDs are stable and never reused. Every implementation commit cites the IDs
it satisfies.

---

## 0. PREAMBLE — WHAT THIS LAYER IS, AND WHAT ALREADY DECIDED IT

Joe's standing want is "tell me what to do." RULE-25 permits it below `CONFIRMED_OBSERVATIONAL`
**provided** the recommendation names its tier, its uncertainty, and what would raise it, and provided it
never asserts the underlying pattern as an established fact. That is not re-litigated here.

Three requirements in `specs/04-reasoning` already fix the *disclosure* contract and are not restated here:
no causal-effect phrasing below `CONFIRMED_OBSERVATIONAL` per REQ-TIER-047; below that tier a recommendation
carries tier, effect size with interval, `n`, `coverage`, and what would change the answer per REQ-TIER-048;
and a recommendation rendered without its tier and interval fails the build per REQ-TIER-049. This document
adds only what those leave open: **who may be recommended from, how often, in what words, and what happens
when a recommendation turns out to be wrong.**

**The OQ-30 ruling this document implements (ADR-0052).** Tier-gated *language* (option (c)) with a floor
of `PROMOTED` for anything pattern-based; Joe's own registered rules are a separate `DESCRIPTIVE` channel,
because applying his rule to his numbers is not an inference; the proactive channel is one read-only
instruction per day on ASSESSMENT and is **not** a push, so it does not consume RULE-27's daily prompt.

---

## A. WHO MAY BE RECOMMENDED FROM

**REQ-ACT-001 (Ubiquitous)**
The action layer SHALL generate a `pattern` recommendation only from a hypothesis at tier `PROMOTED` or
`CONFIRMED_OBSERVATIONAL`, and SHALL NOT generate one from a hypothesis at `CANDIDATE`, `INSUFFICIENT`,
`REFUTED`, or from any `DESCRIPTIVE` or `EXPLORATORY` output.

**REQ-ACT-002 (Ubiquitous)**
The action layer SHALL generate a `pattern` recommendation only where the hypothesis's exposure metric is
present in `config.controllable_metrics` — the registry of the things Joe can actually move, each with the
lever in his own words, its unit, and its minimum worthwhile effect — and SHALL NOT recommend acting on a
metric he cannot control.

**REQ-ACT-003 (Ubiquitous)**
The action layer SHALL generate a `pattern` recommendation only where the absolute estimated effect on the
outcome is at least the `min_effect` registered for that outcome, and SHALL NOT emit a recommendation whose
effect is below the threshold at which Joe would notice or care. (`min_effect` values are placeholders under
OQ-10 and are calibrated against real data, not guessed.)

**REQ-ACT-004 (Ubiquitous)**
The action layer SHALL generate a `standing_order` recommendation only from a rule Joe himself registered in
`config.standing_orders`, SHALL evaluate that rule's stored condition against stored numbers, and SHALL
render it at tier `DESCRIPTIVE` with the numbers that fired it and the words "your standing order".

## B. IN WHAT WORDS

**REQ-ACT-005 (State-driven)**
WHILE the backing hypothesis is at tier `PROMOTED`, the action layer SHALL phrase the instruction with that
metric's registered **hedged** verb, SHALL attach the full REQ-TIER-048 disclosure set, and SHALL NOT use a
verb reserved for `CONFIRMED_OBSERVATIONAL`.

**REQ-ACT-006 (State-driven)**
WHILE the backing hypothesis is at tier `CONFIRMED_OBSERVATIONAL`, the action layer MAY phrase the
instruction with that metric's registered **direct** verb, and SHALL attach the adjustment set and the
E-value at the point estimate alongside the effect (REQ-TIER-023).

**REQ-ACT-007 (Ubiquitous)**
The action layer SHALL express every effect in absolute units of the outcome with the unit named
(REQ-TIER-024), SHALL state the counter-frame (REQ-TIER-028), and SHALL draw every verb and qualifier from
the per-tier closed vocabulary the REQ-NAR-020 linter reads.

## C. WHEN, AND HOW OFTEN

**REQ-ACT-008 (Ubiquitous)**
The action layer SHALL surface at most one instruction per subject day as the proactive recommendation, SHALL
make it read-only on a surface Joe pulls, and SHALL NOT push it; being a surface and not a prompt, it does
not count against RULE-27's one-prompt-per-subject-per-day limit.

**REQ-ACT-009 (Ubiquitous)**
The action layer SHALL rank candidates for that one instruction by tier first (`CONFIRMED_OBSERVATIONAL`
before `PROMOTED` before `DESCRIPTIVE` standing orders) and then by effect size relative to the metric's
`min_effect`, and SHALL make the full list available only on demand.

## D. WHAT HAPPENS WHEN IT IS WRONG

**REQ-ACT-010 (Ubiquitous)**
The action layer SHALL insert exactly one scored forward prediction into `predictions` in the same
transaction as every `pattern` recommendation it generates (RULE-20; the Missing-E trigger), and SHALL
record the prediction's identifier on the recommendation row.

**REQ-ACT-011 (Event-driven)**
WHEN the hypothesis backing a recommendation is demoted or refuted, or when that recommendation's own
forward predictions score false twice consecutively, the action layer SHALL set the recommendation's status
to `demoted` with a machine-readable reason, SHALL surface the demotion by name in the next brief
(REQ-TIER-043), and SHALL NOT require human approval to do so (REQ-TIER-044).

**REQ-ACT-012 (Unwanted behaviour)**
IF a generated instruction contains any term from the stored medical vocabulary, THEN the action layer SHALL
replace the instruction with the stored referral string (REQ-ASK-028), SHALL record the violation, and SHALL
NOT emit the original text — and no recommendation row SHALL ever be deleted; status is the only mutable
field.

---

## NON-GOALS
- Not a goal: recommending from a `DESCRIPTIVE` pattern. Joe's own rules are the only `DESCRIPTIVE` channel,
  and they are his rules, not the system's inferences.
- Not a goal: a push notification, a streak, or a nag (RULE-24, RULE-27).
- Not a goal: a medical, dosing, or treatment recommendation of any kind (RULE-26).
- Not a goal: ranking by anything the system cannot trace to a stored computation (INV-3).

## UNRESOLVED QUESTIONS
- **A-Q1** Every `min_effect` in `config.controllable_metrics` is a placeholder (OQ-10). They are guesses
  about what Joe would notice, and they gate whether a recommendation is emitted at all.
- **A-Q2** "Two consecutive false predictions" as the demotion trigger is a placeholder (OQ-10); the
  research fixes no count.
- **A-Q3** REQ-FIN-190 / REQ-FIN-198 still require a finance co-occurrence to be phrased as a question,
  never a conclusion, which is in tension with RULE-25 and with this document. They are unamended. Finance
  surfaces therefore do not recommend until that reconciliation is ruled (carried from OQ-30; B17's).
