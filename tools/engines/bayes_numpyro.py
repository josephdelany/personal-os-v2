"""B19 §G.2 — the same model in NumPyro (REQ-INF-520..527).

REQ-INF-520 names NumPyro as the reasoning layer's sole probabilistic programming language, and
this is that implementation. `bayes_model.py` holds the identical model as a hand-written Gibbs
sampler; the two exist together on purpose and a test asserts they agree.

WHY BOTH. The Gibbs sampler runs anywhere numpy runs, which is what made the model checkable
while REQ-INF-520 was still open. Keeping it is not redundancy: it is the reference the NUTS
implementation is checked against, and two independent implementations agreeing on a planted
coefficient is much stronger evidence than either alone. A disagreement between them is a defect
in one of them, and without the second there would be nothing to notice it.

WHY THE VERSION PIN IS SPECIFIC AND LOW. jax dropped macOS x86_64 wheels after 0.4.38, and
0.4.30 is the newest with a cp39 wheel — which is what this machine's system interpreter is. The
pin is therefore not conservatism, it is the intersection of "runs in CI on linux/py3.12" and
"runs on the machine the code is written on". ADR-0103's amendment recorded the second constraint
as impossible; it was not, it was a version search nobody had done.

THE MODEL, unchanged from `bayes_model.py`:

    standardised outcome ~ Normal(alpha + beta*exposure + sum(gamma*adjustment)
                                  + u[dow] + u[season] + delta*missing, sigma)

with Normal(0, 0.3) on every coefficient (REQ-INF-523), half-normal(0, 1) on every scale
(REQ-INF-524), partial pooling over within-person groupings only (REQ-INF-525), and the
missingness indicator entering as a modelled term rather than a filter (REQ-INF-527).
"""
from __future__ import annotations

import numpy as np

from tools.engines.bayes_model import (COEF_PRIOR_SD, DEFAULT_ROPE_SD, ModelViolation,
                                       SCALE_PRIOR_SD, check_pooling, standardise)

NUM_CHAINS = 4          # ADR-0070
NUM_WARMUP = 1000
NUM_SAMPLES = 1000


def available():
    """Whether NumPyro can be imported here. The caller decides what to do about it."""
    try:
        import numpyro  # noqa: F401
        return True
    except Exception:                       # noqa: BLE001 — any import failure is unavailability
        return False


def _model(y, X, group_idx, n_groups, coef_prior_sd):
    import jax.numpy as jnp
    import numpyro
    import numpyro.distributions as dist

    k = X.shape[1]
    # REQ-INF-523. Normal(0, 0.3) on every standardised coefficient; alpha is a location rather
    # than an effect, so it is not squeezed by the same prior.
    alpha = numpyro.sample("alpha", dist.Normal(0.0, 1.0))
    coefs = numpyro.sample("coefs", dist.Normal(0.0, coef_prior_sd).expand([k]).to_event(1))
    mu = alpha + X @ coefs

    for name, idx in group_idx.items():
        # REQ-INF-524. Half-normal on the scale — never inverse-gamma, whose behaviour near zero
        # dominates the posterior at small group counts.
        tau = numpyro.sample(f"tau_{name}", dist.HalfNormal(SCALE_PRIOR_SD))
        u = numpyro.sample(f"u_{name}",
                           dist.Normal(0.0, tau).expand([n_groups[name]]).to_event(1))
        mu = mu + u[idx]

    sigma = numpyro.sample("sigma", dist.HalfNormal(SCALE_PRIOR_SD))
    numpyro.sample("obs", dist.Normal(mu, sigma), obs=y)


def fit(y, *, exposure, adjustments=None, groups=None, missing_indicator=None,
        seed=0, num_warmup=NUM_WARMUP, num_samples=NUM_SAMPLES, num_chains=NUM_CHAINS,
        coef_prior_sd=COEF_PRIOR_SD):
    """NUTS over the model of REQ-INF-520..527. Returns the same shape as `bayes_model.fit`.

    The same shape deliberately: `summarise`, `missingness_disclosure` and `check_no_p_value` in
    `bayes_model` are the reporting layer for both, so REQ-INF-526's prohibitions cannot be
    satisfied by one implementation and missed by the other.
    """
    if not available():
        raise ModelViolation(
            "REQ-INF-520: NumPyro is not importable in this interpreter. It installs on "
            "linux/py3.12 and on macOS x86_64 under jax==0.4.30 with cp39-cp313 — see "
            "ADR-0103 as amended twice.")
    import jax
    import numpyro
    from numpyro.infer import MCMC, NUTS

    numpyro.set_host_device_count(num_chains)
    groups = groups or {}
    check_pooling(tuple(groups))                       # REQ-INF-525

    ys = standardise(y)                                # REQ-INF-522
    cols, names = [standardise(exposure).values], ["beta"]
    for i, a in enumerate(adjustments or []):
        cols.append(standardise(a).values)
        names.append(f"gamma_{i}")
    if missing_indicator is not None:
        # REQ-INF-527. A modelled term, never a filter.
        cols.append(np.asarray(missing_indicator, dtype=float))
        names.append("delta_missing")
    X = np.column_stack(cols)

    gi = {g: np.asarray(idx, dtype=int) for g, idx in groups.items()}
    ng = {g: int(idx.max()) + 1 for g, idx in gi.items()}

    mcmc = MCMC(NUTS(_model), num_warmup=num_warmup, num_samples=num_samples,
                num_chains=num_chains, progress_bar=False, chain_method="sequential")
    mcmc.run(jax.random.PRNGKey(seed), np.asarray(ys.values), np.asarray(X), gi, ng,
             coef_prior_sd)
    s = mcmc.get_samples()

    draws = np.column_stack([np.asarray(s["alpha"]).reshape(-1, 1),
                             np.asarray(s["coefs"])])
    return {"names": ("alpha",) + tuple(names), "draws": draws,
            "sigma": np.asarray(s["sigma"]),
            "tau": {g: np.asarray(s[f"tau_{g}"]) for g in gi},
            "outcome_sd": ys.sd, "n": len(ys.values),
            "standardised": True,
            "prior_sd": (1.0,) + (coef_prior_sd,) * X.shape[1],
            "sampler": "numpyro_nuts", "num_chains": num_chains}
