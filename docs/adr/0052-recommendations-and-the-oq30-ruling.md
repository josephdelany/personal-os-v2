# ADR-0052: Recommendations — the OQ-30 ruling, and how a recommendation carries its uncertainty

## Status
Accepted. Built by B10 (`docs/build/B10_recommendations.md`), migration 0047, session 20.
Closes OQ-30. Numbers REQ-ACT-001..012 in a new `specs/09-action/requirements.md`.

## Date
2026-09-02

## The ruling (Joe's standing want — "tell me what to do" — recorded as his ruling via advisor, verbatim from B10)
1. **Tier floor: option (c), tier-gated language, with a floor of PROMOTED for pattern-based
   recommendations.** Below CONFIRMED the verbs are hedged and the full REQ-TIER-048 disclosure set is
   attached; at CONFIRMED the verbs are direct. Nothing pattern-based is recommended from DESCRIPTIVE or
   EXPLORATORY.
2. **State-based standing orders are a separate, DESCRIPTIVE channel.** Joe registers his own rules in
   `config.standing_orders` (condition over today's z-scores/bands → instruction text). Applying his own rule
   to his own numbers is not an inference; it renders with tier DESCRIPTIVE, the numbers, and "your standing
   order". Seed two: guardian (≥2 autonomic signals firing) and sleep debt (below band two nights).
3. **Proactive channel = ASSESSMENT's one instruction, read-only, at most one per day**, separate from
   RULE-27's daily prompt (it is a surface, not a push).
4. **Demotion:** a recommendation is demoted when its finding demotes (REQ-TIER-041) or when its own forward
   prediction scores false twice consecutively (placeholder; OQ-10).
5. **Digest:** yes — the one instruction daily on ASSESSMENT; the full list on demand in THE DESK.

## The conflict this build had to resolve, and how
REQ-TIER-048 requires a recommendation below CONFIRMED to carry "the effect size with interval", and
REQ-TIER-049 **fails the build** if one renders without its tier and its interval. REQ-TIER-025 says the
reasoning layer "SHALL NOT render a frequentist confidence interval on any user-facing surface". A
recommendation surface must therefore show an interval that is not a frequentist confidence interval.

**Ruling: report a credible interval and a probability of direction, and name the method in every payload.**
- **PROMOTED** — Rubin's **Bayesian bootstrap**: Dirichlet(1,…,1) weights over the observed top- and
  bottom-quartile outcome values give a posterior for the median difference. Genuinely posterior, genuinely
  non-parametric, seeded from the recommendation's identity so it reproduces.
- **CONFIRMED_OBSERVATIONAL** — a **flat-prior normal posterior** from B9's HAC estimate and its standard
  error. Stated plainly, in the ADR and in the payload's `interval_method`: under a flat prior this is
  numerically the HAC interval; it is reported and read as a credible interval, with P(direction) beside it.
  That is a relabelling with a stated prior, not a new computation, and it is disclosed rather than hidden.
  A fully modelled posterior arrives with B19's NumPyro layer and supersedes it.
- The interval mass is **80%**, stated in the payload, not the conventional 95% — an 80% credible interval is
  the honest width for a decision aid at these sample sizes, and nothing downstream reads it as significance.

`prob_direction` is the direct probability-of-direction statement REQ-TIER-025 asks for.

## What else this build had to create because it did not exist
`analysis.render_violations` is referenced by four requirements across three specs (REQ-FIN-003,
REQ-NAR-004/025, REQ-ASK-015, REQ-TIER-054) and had never been created. Migration 0047 creates it. It is the
sink for every "the render layer refused" event, and REQ-ACT-012's referral substitution is its first writer.

## Consequences
- The system can say "do this" — hedged at PROMOTED, direct at CONFIRMED — and every such sentence carries a
  tier, an interval, `n`, coverage, the counter-frame, what would change it, and a scored forward prediction.
- Nothing pattern-based can be said from DESCRIPTIVE or EXPLORATORY, so the exploratory surface stays
  incapable of telling Joe what to do.
- A recommendation is withdrawn automatically when its backing finding falls or its own predictions fail
  twice, with a named notice, and never deleted.
- Today only standing orders can fire: there is no PROMOTED or CONFIRMED hypothesis, and there cannot be one
  before ~November 2026 (B9's timetable).

## Not built
Cadence beyond one-per-day; any push channel; a recommendation from a micro-trial (`EXPERIMENTAL` does not
exist); per-recommendation effect recomputation (the effect is read from the ledgered resolution row, so a
PROMOTED recommendation's interval is a normal posterior on the stored contrast delta rather than a Bayesian
bootstrap of the raw sides — the bootstrap is implemented and tested, and is used wherever the raw quartile
values are available to the generator); REQ-FIN-190/198 reconciliation, so no finance surface recommends
(carried out of OQ-30 into `specs/09-action` A-Q3, B17's to settle).
