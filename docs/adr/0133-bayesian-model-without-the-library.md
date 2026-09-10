# ADR-0133 — The model is settled; the library is still Joe's call

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-521..527 proven. **REQ-INF-520 deliberately not claimed — it is OQ-75.**
**Result:** **684 of 685 requirements proven.** One remains, and it is a ruling.

## The distinction this ADR turns on

Eight requirements sat blocked on OQ-75. Reading them individually rather than as a block showed
that **only two of the eight name a library**:

- **REQ-INF-520** — "SHALL use NumPyro as its sole probabilistic programming language"
- **REQ-INF-521** — "SHALL NOT depend on Stan, CmdStanPy, Turing.jl, or PyMC"

**REQ-INF-522 through 527 specify the MODEL** — standardisation, the coefficient prior, the scale
prior, what may be pooled, what must be reported, how missingness enters — and every one is
library-agnostic.

And REQ-INF-521 is a **negative** requirement, provable today: none of the four is a dependency,
checked against every pinned install line in the workflows and every import in `tools/`.

So the model is implemented with a hand-written Gibbs sampler that **runs and is checkable on
this machine**, and REQ-INF-520 is left genuinely open. **This does not pre-empt the ruling. It
makes OQ-75 the smaller question of which library runs a model that already works, rather than
whether the layer should exist.**

## Why Gibbs, and why the scales are not conjugate

The model REQ-INF-520 specifies is a hierarchical **linear** model with Normal priors, so every
coefficient block has a closed-form Normal conditional. That makes the sampler short,
deterministic under a seed, and checkable against a planted answer.

The scales are the exception. **REQ-INF-524 forbids an inverse-gamma prior — which is precisely
the conjugate choice that would have made this simpler.** It is forbidden for a real reason: at
small group counts the inverse-gamma's behaviour near zero dominates the posterior, so **a
variance component genuinely near zero gets pushed away from it by the prior.** Seven
day-of-week groups is exactly "small". A half-normal does not do that, and the cost is a
Metropolis step.

## A test that was wrong, and what it revealed

The recovery test first planted a **0.59 SD** effect and demanded it fall inside the 95% HDI. It
did not — the interval stopped at 0.585.

**The test was wrong, not the sampler.** A Normal(0, 0.3) prior says an effect that large is
unlikely, so it pulls the estimate in. Demanding exact recovery was demanding the prior be
ignored.

That is worth stating rather than hiding, because it tells Joe what this layer can and cannot
see: **it systematically understates large effects, and the understatement grows with the
effect.** A reader who needs the unshrunk number should read the frequentist HAC estimate the
confirmation gate already stores. **This layer's job is calibrated belief, not maximum
likelihood.**

The test now checks recovery at an effect size the prior treats as plausible, and a second test
pins the shrinkage at a large one.

## Missingness is a coefficient, not a filter

REQ-INF-527. **If Joe stops logging dinner on the nights he drinks, the missingness indicator
carries that effect — and dropping those rows moves it into beta.** Modelling `m` with its own
coefficient makes the bias *visible*, and `missingness_disclosure` reports whether it is
materially non-zero, because an analysis that depends on missingness has to say so.

## What is left

**One requirement: REQ-INF-520.** `jaxlib` ships no macOS x86_64 wheel, so NumPyro cannot be
installed, run or tested on this machine (ADR-0103 as amended). OQ-75's three options stand, and
the recommendation is unchanged — except that option (b) is now **built and tested** rather than
proposed, which is the fact that should inform the ruling.
