# ADR-0102 — Chains across lenses: what a multi-hop claim is allowed to say

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-560, 561, 562, 563, 564, 565; REQ-TIER-046
**Implements:** B19 §G.4. B19.1 (regimes, Bayesian layer) and B19.3 (micro-trials) remain
unstarted; both need dependencies this decision does not add.

## Context

A single hypothesis says "A moves B". A chain says "A moves B, and B moves C, so A may reach
C". Chains are the point of a cross-lens system — sleep reaching spending through energy is
exactly the kind of thing no single-domain app can see — and they are also **the easiest place
in this system to manufacture a confident falsehood**, because each hop multiplies the reader's
willingness to believe while the evidence multiplies downward.

## Decisions

### Attenuation is multiplicative and is the only magnitude a chain may report

Two edges of r=0.3 compose to ≈0.09 (REQ-INF-560). Ninety-one percent of the variance is gone
after two hops. A chain that reports the first edge's strength at its far end invites the reader
to carry 0.3 all the way through, so `attenuated_effect` is computed, stored and displayed.

The **sign is the product of the signs**, which produces the most counter-intuitive thing a
chain reports and the one a reader is most likely to get backwards: two negative edges compose
to a positive reach. Less sleep raising stress, and stress lowering spending, means less sleep
*raises* spending. It is computed rather than described.

This requires every edge to be on a **common standardized scale**. Multiplying a beta in
minutes-per-hour by one in dollars-per-step yields a number with no meaning and no unit — and it
would still print. The engine documents the requirement; the caller supplies standardized betas.

### The chain's tier is its weakest edge, enforced in the schema

A chain is a conjunction: it holds only if every edge holds. Taking the strongest edge's tier,
or an average, lets **one CONFIRMED link launder two guesses** (REQ-TIER-046).

The rule is enforced twice: in the engine, and as a CHECK on `analysis.chains`. The engine is
not the only possible writer — a later tool, a repair script or a hand-run INSERT all reach that
table, and an invariant enforced only in Python is enforced only for one caller. `path` uniqueness
(REQ-INF-561) and the k-nodes/k−1-edges relation are enforced the same way, the latter because
if `tiers` and `path` drift the weakest-edge CHECK starts guarding nothing.

Two copies of RULE-16's ladder now exist, `analysis.f_tier_rank` and `chains.TIER_ORDER`. A test
compares them directly rather than trusting them to stay aligned.

### Assembly from sub-threshold edges is permitted, with a sentence attached

REQ-INF-562 allows it. Every chain therefore carries `what_would_firm_it_up`, and that sentence
names **the binding edge**, not the chain as a whole — a generic "collect more data" is not a
next action. A chain the reader can neither act on nor improve is speculation presented as
analysis.

### `role` is declared in the registry, never inferred from an association

REQ-INF-565 forbids auto-promoting a `context` metric to `lever` on the basis of a discovered
association. **If the chain engine decided what was actionable, the rule would be enforced by
the one piece of code with an incentive to break it** — a chain starting at something Joe can
change is a more interesting chain. So the distinction is data in `metric_registry.role`,
written by a human, and no engine may write that column.

The default is `context`. The safe answer to "may Joe act on this?" is no, and an unclassified
metric is precisely the one nobody has considered. Defaulting to `lever` would make every new
metric actionable the moment it appeared.

A chain headed by a context metric is still **reported** — it is a real association and hiding
it would be its own distortion — but marked `actionable=false`.

### Ranking, pruning, and why confidence uses the minimum

REQ-INF-563: rank by |effect| × confidence, keep 20. The confidence of a conjunction is bounded
by its weakest link, so the **minimum** is used rather than a product. A product would punish a
long chain twice — once through attenuation, again through confidence — and the ordering would
then be driven by length rather than strength.

Ties break on the path itself, so a rerun on unchanged data returns the same order. Otherwise
"the top 20" reshuffles between runs and a reader sees movement that is not there.

Only the **pruned** set is stored. Keeping the full graph alongside would invite a later surface
to read it "just for context" and quietly undo the pruning.

### A single edge is not a chain

One edge is the hypothesis itself, which `get_findings` already surfaces. Storing it here would
double-count one piece of evidence in the reader's mind. `min_hops` defaults to 2 and the table
refuses a shorter path.

## Consequences

`analysis.chains` is empty and will stay empty until hypotheses reach PROMOTED. That is correct
and it is **not coverage**: the engine and its constraints are tested, nothing has been observed.

REQ-INF-564's six evidence fields all exist in `core.hypothesis_resolutions` — `n`/`n_eff` via
`core.findings`, the interval as `ci_lo`/`ci_hi`, the estimator as the register's
`test_statistic`, the family as `family_m`, and the reverse-direction check as `nc_exposure_p`,
which shifts the exposure forward by lag+7 days. That last one is a **future-exposure negative
control, not a fitted reverse regression**, and the engine's field is named `reverse_check` with
that distinction recorded here so no surface over-claims it.

`Edge` refuses construction when any of the six is missing. Refusing at construction is the only
place a caller assembling an envelope later cannot forget.
