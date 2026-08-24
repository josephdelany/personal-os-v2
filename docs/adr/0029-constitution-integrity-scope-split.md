# ADR-0029 — Split the constitution into INTEGRITY and SCOPE; re-derive the SCOPE layer from the goal

- **Status:** ACCEPTED — ratified rule-by-rule at consequence level by Joe on
  2026-08-23, and applied to `CONSTITUTION.md` the same day (three-section
  restructure + the ten ratified rule changes; 21 unchanged rules verified
  byte-identical, 30-cap held). Companion: `docs/CONSTITUTION_RESTRUCTURE_PROPOSAL.md`.
- **Date:** 2026-08-23 (Session 11, Phase 2)
- **Deciders:** Joe (director), with the audit and drafting by Claude.
- **Supersedes/amends:** amends the *process* of ADR-0015 (Phase-1 ratification —
  "all 31 rules reviewed and kept," in batches of one-line summaries). Touches the
  wording (not the integrity core) of RULE-06, 13, 17, 19, 22, 23, 24, 25, 26, 29.
  Interacts with ADR-0013 (no personal data in git), ADR-0020 (trust/egress),
  ADR-0007/0021 (confirmation machinery). Does **not** touch any invariant.

---

## Context — the finding that forced this

RULE-29 forbade storing coordinates at all. That did not protect privacy; it
deleted an entire analytic domain (location), and with it degraded the primary
objective function's ground truth (gym attendance), the least-reliable number in
the system (alcohol exposure via bar/pub dwell), merchant+place purchase context,
and passive mobility constructs (radius of gyration, location entropy) with
published links to mood. It survived **eleven sessions** and only surfaced because
`locations` appeared as one "unfittable" line in a backfill map.

Joe's actual intent was never "no location." It was that **raw coordinates and home
never LEAVE the system** — not in an export, a log line, a commit, or a model prompt.
Storage in a restricted table with derived place labels and mobility metrics is fully
compatible with that intent. **The rule conflated storage with exposure.**

The audit this triggered (full text in `CONSTITUTION_RESTRUCTURE_PROPOSAL.md` §2)
went through all 30 rules, all 6 invariants, and the non-goals against eleven stated
wants. It found **not one bad rule but a systematic pattern**: 8–9 conflicts, all
clustered in the rules that express the *old* "health-tracker-with-restraint" framing,
written before the reframe ("consolidate ~8 apps / answer any question / prescribe /
location first-class") fully landed. Two conflicts are Tier-A: RULE-29 (a whole domain)
and the pre-registration cluster (the entire inferential engine vs. "everything in
conversation with everything, NOT a fixed set of hypotheses").

The six invariants are all pure integrity and **none forecloses a want** — a clean
result that is itself the evidence for the split.

## The deeper problem — ratification by summary

Joe ratified all 30 rules in Phase 1 (ADR-0015) in batches of five, reading one-line
summaries rather than consequences. RULE-29 proves that a rule can read as principled,
pass review, and silently amputate something Joe cares about. **The process error was
reading the summary, not the consequence.** It was Joe's and Claude's, not a defect in
any one rule's author.

The naive fix — "make the good rules immutable" — is wrong, and this ADR rejects it
explicitly. Immutability locks in mistakes: RULE-29 itself was ratified *as if*
principled. If a rule wrongly classified as integrity turns out to be scope-in-disguise
(the pre-registration cluster is exactly this risk), immutability would freeze the error.
**The fix is not immutability. The fix is that amendment requires reading the
consequence, not the summary.**

## Decision

### D1 — Three-section constitution

1. **INTEGRITY** — how we know something is true. Fabrication, append-only,
   bitemporality, traceability, no-guessing, compute-once, never-weaken-a-gate, all
   six invariants. These were *earned*: they caught the 450k-row double-count, the
   smeared archive, and two over-claims this week. They stay.
2. **SCOPE** — what the system may be about, capture, say, or do. Written before the
   reframe; revisable with an ADR. Each SCOPE rule carries its rationale and evidence
   inline, so a future reader amends against the reason, not a summary.
3. **HYBRID (split)** — rules that braid an integrity core with a scope shell. Each is
   split *in place*: the integrity clause is governed by the INTEGRITY amendment bar,
   the scope clause by the SCOPE bar. The split is recorded so the braid cannot silently
   re-form. RULE-13, 17, 19, 22, and 29 are the hybrids.

The 30-rule cap is preserved: no rule is renumbered or added. Hybrids keep their single
number with two internally-labelled clauses.

### D2 — Amendment by consequence, not by summary

- A **SCOPE** amendment requires a written statement of what the change makes possible,
  what it still forecloses, and its failure mode — ratified by Joe reading that, not a
  summary. Recorded as an ADR.
- An **INTEGRITY** amendment requires the above **plus an adversarial review whose job
  is to break the change** (the reviewer agent, or Joe, actively trying to construct the
  case where the amendment lets a false or fabricated thing through). Finding nothing is
  a failed review, re-run. This is deliberately heavier than SCOPE because an integrity
  failure is invisible (a plausible wrong number), where a scope failure is merely a
  missing capability Joe will notice and ask for.

### D3 — The seven rulings (Joe, this session)

1. **RULE-29 — OPEN (reword).** Store coordinates in a restricted table; derive place
   labels and mobility metrics. Coordinates and home never enter an export, log, commit,
   or prompt; non-home places egress at ~100 m. Add the lint. Location becomes a
   first-class domain. **Preserved unchanged:** ADR-0013 (no personal data tracked in
   git; a tracked `.parquet/.csv/.db/.sqlite` fails CI) and ADR-0020 (trust/egress,
   no coordinates to any model). Those are separate integrity concerns bundled in the
   old RULE-29 text and they do not move.
2. **PRE-REGISTRATION CLUSTER — SPLIT (dissent accepted in full).**
   - *Immutable:* you cannot confirm a hypothesis on the data that generated it;
     a CONFIRMED claim carries a frozen pre-registration.
   - *Open:* exploration is continuous (not once-early); exploratory output IS
     displayable, explicitly labelled as exploratory, never as a finding.
   - *Binding sequencing:* the tier-labelling surface is built and proven **before**
     continuous exploration ships. The label is the only thing standing between
     exploration and false confidence.
3. **RULE-25 — REWORD.** Below CONFIRMED the system MAY recommend with disclosed
   uncertainty; it MUST NOT assert as established. RULE-20's scored forward prediction
   and auto-demotion is the safety rail and stays.
4. **RULE-23 — REWORD.** Permit usage-based necessity (used/unused/unknown), top-spend,
   and neutral pattern teaching. Keep the judgment-vocabulary ban; build the linter.
   The $32–40 evidence argues against scolding, not against information.
5. **RULE-24 — REWORD.** Ban streaks, gamification, celebration, and step-count-style
   intervention displays. Permit plain progress metrics toward the strength objective.
6. **RULE-28 / no paid aggregator — NO CHANGE.** Joe's deliberate rule, not an accident.
   $0 holds. (OQ-09 SimpleFIN stays closed.)
7. **Clarifications.** RULE-26 — block medical diagnosis without blocking "you're
   under-slept, lift lighter today." RULE-22 — the method blocklist moves to SCOPE,
   revisable with evidence. RULE-06 — a modelled estimate carrying its own uncertainty
   (interval + lane=inferred, RULE-05/08) is not imputation.

### D4 — The prescription gap is real; scope REQ-ACT (plan only)

Verified against the corpus, not asserted: of 564 requirements, **none authorizes
prescription.** A grep of the specs for recommendation vocabulary returns 6 matches,
all prohibitions (medical), rejected interventions (real-time bar alert, remaining-budget
counter), or a research citation. Structurally, the two output surfaces are both
descriptive: REQ-ASK answers questions (its only forward clause, REQ-ASK-024, proposes
an *experiment*, not an action), and REQ-NAR is *narration restraint* (REQ-NAR-024 forbids
rendering any behaviour "with a judgment attached"). **Telling Joe what to do — the thing
he asked for first — is structurally excluded.** The REQ-ACT scope (when, evidence tier,
language, frequency, what-happens-when-wrong) is drafted in
`CONSTITUTION_RESTRUCTURE_PROPOSAL.md` §4. Authoring the requirements is **not** done in
this session (Joe: plan, do not execute).

## Consequences

- **Positive:** location becomes usable; open-ended inference becomes possible without
  laundering exploration as confirmation; the system can finally recommend (once REQ-ACT
  is authored and the tier-labelling surface exists); the constitution gains a legitimate
  home for "we understood Joe better later" instead of quietly overriding or quietly
  obeying a wrong rule.
- **Cost / risk:** the pre-registration split is the dangerous move — relaxing the
  "never shown / once early" shell without the tier-labelling surface in place would
  re-import HARKing and confirmation-seeking, and that failure is *invisible*. The
  sequencing constraint in D3.2 is load-bearing, not advisory. RULE-29's reword adds a
  place-resolution pipeline, restricted-access storage, and home-obfuscation on egress
  as new work with new failure modes.
- **What did NOT change:** all six invariants; RULE-00, 01, 02, 03, 04, 05, 07, 08, 09,
  10, 11, 12, 14, 15, 16, 18, 20, 21, 27, 28, 30 in substance; ADR-0013 and ADR-0020;
  the $0 rule.

## Alternatives considered

- **Individual amendments, rule by rule.** Rejected on the count and severity, not on
  effort: 8–9 conflicts from one root cause is a design signal. Patching preserves the
  framing that produced them and invites the same summary-level review that failed.
- **Two sections (INTEGRITY / SCOPE), no hybrid class.** Rejected: it forces a binary
  sort on rules that genuinely braid both (RULE-29's storage-vs-egress; the
  pre-registration core-vs-shell). A forced sort would either freeze a scope shell as
  integrity or expose an integrity core to the lighter bar.
- **Make INTEGRITY genuinely immutable.** Rejected per the RULE-29 lesson (see Context).

## Enforcement / follow-through (owed if ratified)

- RULE-29 lint: coordinates never appear in an export, log, commit, or prompt; home
  never egresses; non-home egress ≤ ~100 m precision.
- RULE-23 judgment-vocabulary linter (extends REQ-NAR-023's banned wordlist).
- Tier-labelling surface (exploratory vs finding) before continuous exploration.
- REQ-ACT requirement set authored (separately, consequence-ratified).
- `docs/DECISIONS.md` index row; `CONSTITUTION.md` restructured to three sections
  once ratified; ADR-0027's `locations`→Phase-4 deferral re-opened under the new RULE-29.

---

## Addendum — session-end reviewer findings (2026-08-23)

The adversarial reviewer ran on the session diff and found real defects. Recorded
here rather than by editing the accepted body (ADR immutability; cf. ADR-0013/0014
addenda). Corrections and disclosures:

- **MAJOR-1 — the "no requirement authorises prescription" claim (§D4) is CORRECTED.**
  It is false. `REQ-TIER-047/048/049` (`specs/04-reasoning/requirements.md:173-180`)
  already authorise and constrain recommendation emission below
  `CONFIRMED_OBSERVATIONAL`: REQ-TIER-048 permits a "decision-under-uncertainty"
  recommendation below CONFIRMED provided it carries tier, effect size + interval,
  `n`, `coverage`, and what-would-change-it; REQ-TIER-047 forbids phrasing it as a
  causal-effect claim below CONFIRMED; REQ-TIER-049 fails the build if it renders
  without tier + interval. The grep missed them because `\brecommend\b` does not match
  the noun "recommendation," and section A's claim-ladder tail was not read.
  **Consequence:** REQ-ACT is not "prescription from scratch." The recommendation
  *disclosure contract* already exists. What REQ-ACT adds is the action-*generation*
  machinery those requirements do not cover: **when** to recommend (proactive vs
  on-demand), **cadence** (vs RULE-27), the **scored-prediction/auto-demotion loop
  applied to recommendations** (RULE-20 today names findings), the **action vocabulary**,
  and an optional "what to do today" digest. OQ-30's evidence-tier floor is **partially
  pre-answered** by REQ-TIER-047/048 (below CONFIRMED, with disclosure) — narrowed
  accordingly. REQ-ACT must **reconcile with, not duplicate**, REQ-TIER-047-049.

- **MINOR-1 — corrected.** The Context line "RULE-13, 17, 19, 22, and 29 are the
  hybrids" is wrong. RULE-22 is **SCOPE** (D3.7 / §3H: "the method blocklist moves to
  SCOPE"). The HYBRIDs are **13, 17, 19, 29**, exactly as placed in `CONSTITUTION.md`.
  The constitution placement is authoritative; the Context line is the typo.

- **MINOR-2 — disclosed, reconciliation owed.** New RULE-25 ("MAY recommend") is in
  tension with unamended `REQ-FIN-190`/`REQ-FIN-198` (a co-occurrence "SHALL be phrased
  as an observation followed by a question... SHALL NOT be phrased as a conclusion").
  Not an invariant violation (a disclosed-uncertainty recommendation is not a
  conclusion), but constitution and finance spec now point different ways on the same
  behaviour. Added to OQ-30.

- **OBSERVATION-1 — disclosed honestly.** The RULE-29 `[INTEGRITY core]` wording
  narrowed "No **location data** is ever sent to a third party" → "No **coordinate**".
  This is a *ratified* consequence of the reframe (place labels may egress at ~100 m),
  not byte-preservation of that clause. The clause also *strengthened* (added "commit"
  to the leak list; "home never egresses at any precision"). Recorded as a real change,
  not as "intent byte-preserved."

- **MAJOR-2 — fixed this session.** The RULE-29 static coordinate lint was evadable on
  the JSON export form (`"lat": 51.5231`) — the single likeliest real leak — plus
  tuples and WKT. Strengthened to catch quoted-key, decimal-degree-pair, and
  WKT-POINT forms (proven inline against the reviewer's evasion cases; no false
  positives on the real repo). `tests/` excluded (synthetic fixtures, RULE-01). It
  remains a **tripwire, not coverage** — a static regex cannot prove absence of every
  encoding (geohash, split x/y); the **authoritative** enforcement is the runtime
  egress proof (owed Phase 3/4) + review. A committed regression test for the lint is
  owed.

The reviewer independently verified and confirmed sound: the changed-rule set is
exactly {06,13,17,19,22,23,24,25,26,29} (21 rules byte-identical); the 30-cap held and
numbers are contiguous; the RULE-19 immutable core cannot be read to permit confirming
on generating data (DB CHECK `confirmation_data_from >= preregistered_at`); ADR-0013 and
ADR-0020 clauses are retained in the new RULE-29 core.
