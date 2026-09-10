# ADR-0103 — The dependencies B19.1 needs, what they cost, and what fails at the limit

**Status:** accepted
**Date:** 2026-09-10
**Governs:** RULE-28 / CLAUDE.md — "before dependencies are added, document limits, projected
usage and failure at the limit in an ADR; billing on overage is disallowed."
**Unblocks:** B19.1 (§G.3 regimes, §G.2 Bayesian effect layer). B19.3 needs nothing new.

## What is actually needed, and what already exists

The B19 brief lists `numpyro`, `jax[cpu]`, `dynamax`, `networkx` and `statsmodels`. Three of
those are **already installed** in `.github/workflows/analysis.yml`, pinned, since B9:

| package | status | first added for |
|---|---|---|
| `numpy`, `scipy` | present | B9 specification curve |
| `statsmodels` | present | B9 confirmation gate (HAC) |
| `networkx` | present | B9 DAG / backdoor sets |
| `jax` + `jaxlib` | **new** | B19.1 only |
| `numpyro` | **new** | B19.1 only |
| `dynamax` | **new** | B19.1 only |

So **B19.3 (randomized micro-trials) is not blocked by this ADR at all** — its power
calculation uses `statsmodels`, which is already here. That was worth checking before writing
anything: the brief's dependency list described the whole of B19, and treating it as a single
gate would have held back a unit that had no gate.

## Measured cost

Wheel sizes, read from PyPI on 2026-09-10 (manylinux x86_64, cp312):

| package | version | wheel |
|---|---|---|
| `jaxlib` | 0.11.1 | **87.9 MB** |
| `jax` | 0.11.1 | 3.3 MB |
| `numpyro` | 0.21.0 | 0.4 MB |
| `dynamax` | 1.0.2 | 0.2 MB |

`jaxlib` is the whole cost; the three libraries that do the modelling are under 4 MB combined.
It adds roughly 60–90 s of install to any job that needs it.

**All four are BSD/Apache licensed, pip-installable, and carry no service, no account, no API
key and no network call at runtime.** Nothing here can incur a charge by being used. The only
consumable is GitHub Actions time.

## The minutes budget, and the constraint that actually binds

`personal-os-v2` is a **public** repository, so Actions minutes are unlimited and the projected
usage below is zero-cost today. That is not a safe place to stop, because **OQ-67 recommends
making this repository private** — Joe's spending figures are in its git history. On the Free
plan a private repo gets 2,000 minutes a month, and GitHub bills **per job, rounded up to a
whole minute**.

Projected under that scenario:

| workflow | runs/mo | jobs | billed min/job | min/mo |
|---|---|---|---|---|
| extract (hourly) | 720 | 1 | 1 | **720** |
| tests (nightly) | 30 | 2 | 4 | 240 |
| analysis (nightly) | 30 | 3 | 2 | 180 |
| freshness (daily) | 30 | 1 | 2 | 60 |
| keepalive (daily) | 30 | 1 | 1 | 30 |
| | | | | **1,230 of 2,000** |

Adding B19.1 as its own nightly job at ~2 billed minutes costs **60 min/mo**, reaching 1,290 and
leaving 710 minutes of headroom. It fits.

**The finding that matters is not jax.** The hourly `extract` job consumes **720 of the 2,000
minutes — 59% of the budget — for a job whose measured median duration is 12 seconds.** Across a
month it does about 2.4 minutes of real work and is billed for 720, purely because per-job
rounding turns 12 seconds into a minute. If Joe takes OQ-67's advice and makes the repo private,
that job is the thing to fix, and jax is a rounding error beside it. Halving its frequency to
every two hours recovers 360 minutes — six times what B19.1 costs.

## Failure at the limit

Required by RULE-28, and the answers differ per limit:

- **Actions minutes exhausted (private repo only).** GitHub *stops running* workflows for the
  rest of the billing cycle; it does not bill. Consequence: the nightly analysis, the hourly
  extract and the keepalive all stop. **The keepalive stopping is the real damage** — a Supabase
  free project pauses after 7 days of inactivity, so a minutes exhaustion on day 1 of a cycle
  could pause the database before the cycle resets. Mitigation: the keepalive is the cheapest
  job here (1 min/run, 30/mo) and B19.1 must never be added to its workflow, so it cannot be
  starved by a modelling job. Recorded as a constraint, not a hope.
- **Job timeout.** `analysis.yml` sets `timeout-minutes`. A NUTS fit that does not converge is
  killed by the runner, the job fails loudly, and no partial result is written. B19.1 must write
  its outputs in one transaction at the end for this reason.
- **Fit does not converge (r_hat > 1.01 or low ESS).** This is a *modelling* limit, not a
  billing one, and it must not be papered over: the effect row is written with its `r_hat` and
  `ess`, and any surface reading it refuses to render an effect whose diagnostics failed. A
  non-converged posterior that renders as a clean interval is precisely the failure this project
  exists to avoid.
- **`jaxlib` drops the runner's Python or platform.** It is pinned; a resolution failure fails
  the job at install, before any write.

## Decision

Add `jax`, `jaxlib`, `numpyro` and `dynamax`, **pinned**, to a **new dedicated job** in
`analysis.yml` when B19.1 is implemented — not to the existing `refresh` or `resolve` jobs, and
never to `keepalive.yml`. A 90-second install must not sit in front of the panel refresh that
everything else depends on, and a modelling job that fails must not take the nightly refresh
down with it — the same reasoning that gave `resolve` its own job in B9.

B19.3 proceeds now, with no new dependency.

## What this ADR does not decide

Whether to make the repository private (OQ-67) and whether to reduce the hourly extract
frequency. Both are Joe's. This ADR records that **the second only becomes urgent if he chooses
the first**, and that the two are connected — which was not visible from either question alone.
