# ADR-0014: Phase-1 research corrections to the constitution, and a new temporal-specification rule

## Status

Accepted. Amends the constitution (RULE-11, RULE-17) and adds a new numbered
rule at the RULE-13 slot, retiring the former RULE-13 by merging it into RULE-14
to hold the 30-rule cap (as `.claude/rules/constitution-cap.md` requires: a new
numbered rule needs a removal justified in an ADR, in the same commit).

## Date

2026-08-23

## Context

Three findings published *after* these documents were written make three of
their citations wrong or understated. Joe directed all three corrected during
the Phase-1 constitution ruling. The architectural conclusions do not change;
the evidence behind them does.

## Decision

**1. RULE-11 — PHIA numbers corrected (C1).** The constitution (and CLAUDE.md,
ADR-0001, `specs/04-reasoning`) quoted PHIA as "22% in-context vs 84% executed,"
which attributes the whole gap to executing code. PHIA (*Nature Communications*,
**12 Jan 2026**) actually reports three conditions: **22%** no-tools in-context,
**74%** one-shot generated-and-executed code, **84%** the full ReAct agentic
loop. Executing code at all buys the large gap (22→74); the loop adds ~10 more
(74→84). It used **Gemini 1.0 Ultra for all main results** (the paper also
reports a GPT-4 chain-of-thought comparison at 53.6%) and has **not been
independently replicated**. RULE-11's text now states the three-way breakdown and the caveats.
The conclusion — the model plans and narrates, never computes — is unchanged and
if anything better supported.

**2. RULE-17 — causal-discovery distrust strengthened (C3).** RULE-17 keeps
PCMCI+/VAR-LiNGAM/regularized-VAR output as `CANDIDATE`-only, never shown. The
justification was understated. CausalDynamics (NeurIPS 2025, arXiv:2505.16620;
14,693 graphs) scored **PCMCI+ at chance on its simple tier** (AUROC
0.52/0.50/0.49; coupled systems fare better, ~0.67). RULE-17 now cites it: the
distrust is empirical, not stylistic — at chance on the easy case is enough.

**3. New RULE-13 — the model never selects the temporal specification (C4).**
Lag structures, window definitions, aggregation choices, and adjustment sets
come from the pre-registered hypothesis and the metric registry, never from the
model at query time. Justification: **HEARTS (ICML 2026 poster; arXiv:2603.06638)**
found code execution fixes arithmetic but **not** temporal reasoning — the
degradation persists even under a CodeAct code-execution harness, models falling
back on heuristics as temporal complexity rises. So the RULE-11 remedy
(execute, don't reason in-head) does not cover temporal-structure choices; those
must be fixed data, not model output. Tier TEST + REVIEW.

**Holding the 30-cap.** Adding RULE-13 required retiring one rule. The former
RULE-13 ("the PWA renders, it does not compute") was the weakest standalone: a
corollary of RULE-11 (model never computes) and RULE-14 (every number traces to
a stored computation), both governed by ADR-0001. Its content — no arithmetic in
client code beyond formatting — **merged into RULE-14**, which is now "the render
layer renders; it never computes, and every number it emits traces to a stored
computation." No rule number was added or removed; RULE-13's slot was repurposed,
so the set stays contiguous RULE-00..RULE-30 at exactly 30 numbered rules.
`.claude/agents/reviewer.md`'s boundary-rule map was updated to match.

## Consequences

- The three corrected claims now match the post-dating research. Downstream
  shorthand ("84% vs 22%") in `specs/04-reasoning` was rewritten to
  "22%→74%→84%" pointing at the preamble decomposition.
- RULE-13 is a new enforceable boundary: a query path that lets the model pick a
  lag/window/aggregation/adjustment set fails review (and, once the reasoning
  layer exists, a test). No enforcing test exists yet — the reasoning layer is
  Phase 6 — so the rule is TEST + REVIEW with the TEST owed at that time.
- Anyone who referenced "RULE-13" as the render/no-compute rule must now read
  RULE-14; the reviewer map and this ADR record the move.
- METR's "19% slower" (OPERATING_MANUAL §5) is a fourth item from the same batch
  but touches no constitution rule; recorded there and in PROGRESS, not here.
  *(Correction 2026-08-23: an intermediate edit wrongly called this result
  "retracted" — nothing was retracted; the 2025 result stands as published and
  METR is only redesigning the experiment for selection effects. Fixed.)*

## Alternatives considered

- **Add RULE-31 without retiring anything.** Rejected: breaches the 30-cap,
  which exists because the previous spec reached 617 KB with no accretion brake.
- **Fold the temporal rule into RULE-11 instead of a new rule.** Rejected: Joe
  asked for a distinct, separately-enforceable rule; the failure mode (temporal
  reasoning) is different from the arithmetic one RULE-11 addresses, and burying
  it inside RULE-11 would hide it from the reviewer's boundary-rule pass.
- **Retire a different rule.** The former RULE-13 was the only genuine corollary;
  every other Section-II rule carries weight not covered elsewhere.

## Correction 2026-08-23 — post-hoc source verification

After this ADR was accepted, Joe verified the citations against primary sources
and three of the four were wrong as first written. The body above is corrected
inline; the errors are recorded here so the mistake is not silently erased:

- **CausalDynamics.** First written "AUROC ~0.47 — worse than chance." Wrong:
  PCMCI+ on the simple tier is 0.52/0.50/0.49 — **at chance, not below it** —
  over 14,693 graphs (585 simple, 14,096 coupled, 12 climate); coupled ~0.67 is
  fine. The rule's conclusion (never show it) is unchanged: at chance is enough.
- **PHIA.** "One model only" → **Gemini 1.0 Ultra for all main results** (a GPT-4
  chain-of-thought comparison at 53.6% is also in the paper). 4,000 is the
  objective benchmark, not the total question count. The 22/74/84 figures and the
  12 Jan 2026 date were verbatim correct.
- **HEARTS.** Upgraded from "arXiv preprint" to **ICML 2026 poster**; the
  temporal-reasoning degradation persists even under a CodeAct code-execution
  harness. RULE-13 is well founded.
- **METR** (recorded in OPERATING_MANUAL, not a rule): the "retracted" framing was
  false — see the corrected Consequences bullet above.
