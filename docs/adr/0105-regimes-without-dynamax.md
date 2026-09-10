# ADR-0105 — Regimes: a hand-written HMM, and why the named library was not used

**Status:** accepted
**Date:** 2026-09-10
**Requirements:** REQ-INF-541, 542, 543, 544, 545, 546, 547. **Deviates from REQ-INF-540.**
**Depends on:** ADR-0103 as amended.

## The deviation, stated first

REQ-INF-540 says the layer "SHALL fit a Hidden Markov Model with between 2 and 4 latent states
over the daily feature vector **using `dynamax`**". That is a named library inside a requirement.

`dynamax` is not used. Two independent reasons, both discovered by attempting the install rather
than reading metadata:

1. It requires **`tfp-nightly`** — a nightly build with no pinnable version, whose contents
   change daily. RULE-28 requires stating what happens at the limit; for a dependency that is
   undefined tomorrow, that cannot be stated honestly.
2. It requires `jaxlib`, which **ships no macOS x86_64 wheel**. The development machine is an
   Intel Mac, so `dynamax` cannot be run or tested here at all.

**This is a deviation from an accepted requirement and it is Joe's to ratify, not mine to
assume.** OQ-74 records it. The behaviour every other requirement in §G.3 specifies is
implemented and tested; only the named implementation differs.

## What was built instead

Baum-Welch (EM) for a diagonal-covariance Gaussian HMM in `numpy`, ~80 lines, using libraries
already present since B9.

**Forward-backward runs in log space.** This is not a micro-optimisation: in linear space the
product of per-day likelihoods underflows float64 within a few hundred steps, and every
posterior silently becomes `NaN` — on series of the length this project actually holds
(~2,400 days). A test fits 2,400 days and asserts the log-likelihood is finite.

**The EM start is seeded and deterministic**, initialised from quantile slices along the first
principal direction rather than at random. A random start makes the *state numbering* vary
between runs, and a state whose identity changes overnight cannot have a run-length history:
"you have been in state 2 for six days" would mean a different state each time it is said.

## Validation against a known answer

The model is checked against synthetic data whose true structure is known — two regimes, means
7.5 h / 9,500 steps and 5.9 h / 4,200 steps, switching every 50 days:

- both state means recovered within 0.15 h and 200 steps,
- the run-length median recovered as **50**, the true switching period,
- **K = 2 selected** by the held-out criterion.

If it could not recover that, nothing it said about Joe's data would be worth reading.

## The decisions that are about honesty rather than fit

**K is chosen before looking (REQ-INF-547).** The criterion — held-out log-likelihood per day on
the last 20% — is a module constant, recorded in every result alongside the score for *every*
candidate K. Picking K by inspecting which fit "makes the most sense" is choosing a conclusion
and calling it a method. On two-regime data the criterion picks 2, which is the point: a
criterion that always preferred more states would be selecting complexity, not fit.

**A state has no name (REQ-INF-543).** There is no code path in the module that produces one. A
state is rendered as `sleep_hours 7.496h ± 0.482; steps 9371 ± 917`. This matters more here than
anywhere else in the system: a two-state fit over sleep and steps will *always* look like "good
weeks" and "bad weeks", and naming it that asserts both a value judgement and a cause the model
never estimated. A test asserts no label contains "good", "bad", "poor", "healthy", "optimal",
"recovery" or "burnout".

**The caveat travels with the result, not with the renderer (REQ-INF-544)**, because the renderer
is exactly where a causal sentence would be added. A test scans the entire returned structure for
"because", "causes", "leads to", "drives", "due to".

**Everything is DESCRIPTIVE (REQ-INF-542)**, as a module constant rather than a per-fit argument.

## REQ-INF-546 — the latent level, and the measured case against a rolling average

`UnobservedComponents` is `statsmodels`, already present, so this needed nothing new.

The claim that a filtered latent level beats a rolling mean is **measured, not asserted**. On a
synthetic series with a real step change and a strong weekly pattern:

| step occurred | latent level error | 28-day rolling mean error |
|---|---|---|
| 10 days ago | **0.45** | **9.02** |
| 40 days ago | 0.33 | 0.33 |

Ten days after a real shift, 18 of the rolling mean's 28 days are still pre-step. Forty days
after, the two agree. **The rolling mean is not wrong — it is late, and while it is late it is
indistinguishable from a stable baseline.** That is the failure mode worth naming: it does not
look like an error, it looks like nothing happening.

The level also reports `level_se`, so a comparison can say whether a difference clears the
baseline's own uncertainty. A rolling average cannot report that at all, which is how "above my
average" comes to be said about noise.

One precision point, corrected after measuring: the seasonal component is constrained to sum to
zero over the period, so the level is the week-average baseline with the **day-of-week deviation**
removed — not with the week's average removed. An earlier draft of the docstring said the latter,
which would have been a different and less useful quantity.

## What remains

**§G.2, the Bayesian effect layer, is the last unstarted piece of B19.** It is deferred rather
than replaced: NUTS with the priors REQ-INF-520..527 specifies is genuinely better served by
NumPyro than by anything hand-rolled, and the blocker is this machine's architecture, not the
library. OQ-75 puts the choice to Joe.
