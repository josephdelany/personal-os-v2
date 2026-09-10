"""B19 §G.2 — the Bayesian effect model (REQ-INF-522..527).

Pure: numpy only. No database, no clock, no probabilistic-programming library.

WHAT THIS IS AND IS NOT. REQ-INF-520 names NumPyro as the reasoning layer's sole probabilistic
programming language, and `jaxlib` ships no macOS x86_64 wheel, so that requirement cannot be
satisfied or tested on this machine (ADR-0103 as amended). OQ-75 is Joe's ruling and this module
does not pre-empt it.

But REQ-INF-520 and 521 are the only two of the eight that name a LIBRARY. REQ-INF-522 through
527 specify the MODEL -- standardisation, the priors, what may be pooled, what must be reported,
and how missingness enters -- and every one of them is library-agnostic. They are implemented and
tested here with a hand-written Gibbs sampler so that the model itself is a settled, checkable
thing, and OQ-75 becomes "which library runs a model that already works" rather than "should this
exist".

WHY GIBBS AND NOT SOMETHING CLEVERER. The model REQ-INF-520 specifies is a hierarchical LINEAR
model with Normal priors on its coefficients. Every coefficient block therefore has a closed-form
Normal conditional, which makes the sampler short, deterministic under a seed, and checkable
against a known answer -- and the check that matters is recovering a beta you planted.

WHY THE SCALES USE METROPOLIS AND NOT A CONJUGATE INVERSE-GAMMA. REQ-INF-524 forbids an
inverse-gamma prior on a scale parameter, and inverse-gamma is precisely the conjugate choice
that would have made this simpler. It is forbidden for a real reason: at small group counts the
inverse-gamma's behaviour near zero dominates the posterior, so a variance component that is
genuinely near zero gets pushed away from it by the prior. A half-normal does not do that, and
the cost is a Metropolis step.

WHY MISSINGNESS IS A COEFFICIENT AND NOT A FILTER (REQ-INF-527). If Joe stops logging dinner on
the nights he drinks, the missingness indicator carries the effect and dropping those rows moves
it into the estimate. Modelling `m` with its own coefficient makes the bias VISIBLE -- and the
coefficient is reported, so an analysis that depends on missingness says so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

COEF_PRIOR_SD = 0.3            # REQ-INF-523
SCALE_PRIOR_SD = 1.0           # REQ-INF-524, half-normal(0, 1)
DEFAULT_ROPE_SD = 0.1          # REQ-INF-526 / OQ-10 placeholder
# REQ-INF-525. Within-person groupings only. There is no between-person level to add.
POOLABLE = ("day_of_week", "season", "life_phase", "exposure_instance")


class ModelViolation(Exception):
    pass


@dataclass(frozen=True)
class Standardised:
    values: np.ndarray
    mean: float
    sd: float


def standardise(x):
    """REQ-INF-522. Every predictor and every outcome, before fitting.

    Not cosmetic: the Normal(0, 0.3) prior of REQ-INF-523 is a statement about a STANDARDISED
    coefficient. On raw units that same prior means something different for every metric — it
    would be almost flat for a step count and crushingly tight for an hours-of-sleep figure, so
    the prior's strength would depend on the unit somebody chose.
    """
    a = np.asarray(x, dtype=float)
    m, s = float(np.nanmean(a)), float(np.nanstd(a))
    if s == 0:
        raise ModelViolation("REQ-INF-522: a predictor with zero variance cannot be standardised "
                             "and carries no information about the outcome")
    return Standardised((a - m) / s, m, s)


def check_pooling(groupings):
    """REQ-INF-525. Within-person only; no between-person level exists to construct.

    Stated as a refusal because the mistake is natural: hierarchical models are usually taught
    with people as the top level, and there is exactly one person here. A "between-person" term
    on n=1 is a term with one group, which is not pooling — it is an intercept with extra steps
    and a misleading name.
    """
    bad = tuple(g for g in groupings if g not in POOLABLE)
    if bad:
        raise ModelViolation(
            f"REQ-INF-525: {list(bad)} is not a within-person grouping; partial pooling is over "
            f"{list(POOLABLE)} and there is no between-person level to construct on n=1")
    return True


def _half_normal_logpdf(x, sd=SCALE_PRIOR_SD):
    if x <= 0:
        return -np.inf
    return -0.5 * (x / sd) ** 2


def _sample_scale(current, effects, *, rng, sd_prior=SCALE_PRIOR_SD, step=0.15):
    """Metropolis step for a scale with a HALF-NORMAL prior (REQ-INF-524).

    Inverse-gamma would be conjugate and is forbidden: at small group counts its behaviour near
    zero dominates the posterior, pushing a genuinely-near-zero variance component away from
    zero. Seven day-of-week groups is exactly "small".
    """
    n = len(effects)
    ss = float(np.sum(np.asarray(effects) ** 2))

    def logp(t):
        if t <= 0:
            return -np.inf
        return -n * math.log(t) - ss / (2 * t * t) + _half_normal_logpdf(t, sd_prior)

    proposal = current * math.exp(rng.normal(0, step))
    # log-normal proposal is asymmetric; the Jacobian is the ratio of the values.
    if math.log(rng.uniform()) < (logp(proposal) - logp(current)
                                  + math.log(proposal) - math.log(current)):
        return proposal
    return current


def fit(y, *, exposure, adjustments=None, groups=None, missing_indicator=None,
        draws=2000, warmup=1000, seed=0, coef_prior_sd=COEF_PRIOR_SD):
    """The hierarchical linear model of REQ-INF-520, sampled with Gibbs + Metropolis-on-scales.

    `groups` maps a within-person grouping name to an integer index per observation.
    `missing_indicator` is the latent m of REQ-INF-527 — passed as data and given its own
    coefficient, never used to drop rows.
    """
    rng = np.random.default_rng(seed)
    groups = groups or {}
    check_pooling(tuple(groups))

    ys = standardise(y)
    xs = [standardise(exposure).values]
    names = ["beta"]
    for i, a in enumerate(adjustments or []):
        xs.append(standardise(a).values)
        names.append(f"gamma_{i}")
    if missing_indicator is not None:
        # REQ-INF-527. A coefficient, not a filter. If Joe stops logging dinner on the nights he
        # drinks, this coefficient carries that — and dropping the rows would move it into beta.
        xs.append(np.asarray(missing_indicator, dtype=float))
        names.append("delta_missing")
    X = np.column_stack([np.ones(len(ys.values))] + xs)
    names = ["alpha"] + names
    n, k = X.shape

    beta = np.zeros(k)
    sigma = 1.0
    u = {g: np.zeros(int(np.max(idx)) + 1) for g, idx in groups.items()}
    tau = {g: 0.5 for g in groups}
    # alpha gets a wider prior than the coefficients: it is a location, not an effect, and a
    # Normal(0, 0.3) on it would fight the data for no reason.
    prior_sd = np.array([1.0] + [coef_prior_sd] * (k - 1))

    keep = {"coefs": [], "sigma": [], "tau": {g: [] for g in groups}}
    for it in range(warmup + draws):
        resid_re = np.zeros(n)
        for g, idx in groups.items():
            resid_re += u[g][idx]

        # Coefficients: conjugate Normal given sigma and the random effects.
        prec = X.T @ X / sigma ** 2 + np.diag(1.0 / prior_sd ** 2)
        cov = np.linalg.inv(prec)
        mean = cov @ (X.T @ (ys.values - resid_re) / sigma ** 2)
        beta = rng.multivariate_normal(mean, cov)

        # Random effects: conjugate Normal given tau and sigma.
        fitted = X @ beta
        for g, idx in groups.items():
            other = np.zeros(n)
            for h, jdx in groups.items():
                if h != g:
                    other += u[h][jdx]
            r = ys.values - fitted - other
            for j in range(len(u[g])):
                sel = idx == j
                m_j = int(np.sum(sel))
                if m_j == 0:
                    u[g][j] = rng.normal(0, tau[g])
                    continue
                v = 1.0 / (m_j / sigma ** 2 + 1.0 / tau[g] ** 2)
                mu = v * float(np.sum(r[sel])) / sigma ** 2
                u[g][j] = rng.normal(mu, math.sqrt(v))
            tau[g] = _sample_scale(tau[g], u[g], rng=rng)

        resid = ys.values - fitted - sum(u[g][idx] for g, idx in groups.items()) \
            if groups else ys.values - fitted
        sigma = _sample_scale(sigma, resid, rng=rng)

        if it >= warmup:
            keep["coefs"].append(beta.copy())
            keep["sigma"].append(sigma)
            for g in groups:
                keep["tau"][g].append(tau[g])

    coefs = np.array(keep["coefs"])
    return {"names": tuple(names), "draws": coefs, "sigma": np.array(keep["sigma"]),
            "tau": {g: np.array(v) for g, v in keep["tau"].items()},
            "outcome_sd": ys.sd, "n": n,
            "standardised": True, "prior_sd": tuple(prior_sd)}


def hdi(samples, prob=0.95):
    """Highest-density interval — the narrowest interval containing `prob` of the mass."""
    s = np.sort(np.asarray(samples))
    m = int(np.floor(prob * len(s)))
    if m < 1:
        return (float(s[0]), float(s[-1]))
    widths = s[m:] - s[:len(s) - m]
    i = int(np.argmin(widths))
    return (float(s[i]), float(s[i + m]))


def summarise(fit_result, *, name="beta", rope_sd=DEFAULT_ROPE_SD):
    """REQ-INF-526. Probability of direction and of practical significance. Never a p-value.

    `p_direction` is the share of the posterior on the side of its own median, and
    `p_practical` the share outside a ROPE of ±rope_sd standard deviations. Both are statements
    about the parameter, which is what a reader assumes a p-value is and what it is not.
    """
    i = fit_result["names"].index(name)
    d = fit_result["draws"][:, i]
    med = float(np.median(d))
    p_dir = float(np.mean(d > 0)) if med > 0 else float(np.mean(d < 0))
    lo, hi = hdi(d)
    out = {
        "parameter": name,
        "median": round(med, 6),
        "hdi_95": (round(lo, 6), round(hi, 6)),
        "p_direction": round(p_dir, 4),
        "rope": (-rope_sd, rope_sd),
        "p_practical": round(float(np.mean(np.abs(d) > rope_sd)), 4),
        "n": fit_result["n"],
    }
    # REQ-INF-526's prohibition, enforced on the object rather than left to the renderer.
    assert "p_value" not in out and "p" not in out
    return out


def check_no_p_value(payload):
    """REQ-INF-526. No p-value on any user-facing surface, under any spelling."""
    keys = {str(k).lower() for k in payload}
    bad = tuple(sorted(k for k in keys if k in ("p", "p_value", "pvalue", "pval", "sig")))
    if bad:
        raise ModelViolation(
            f"REQ-INF-526: {list(bad)} — the surface reports probability of direction and of "
            f"practical significance, never a p-value; a p-value is a statement about data under "
            f"a null, and every reader takes it for a statement about the parameter")
    return True


def missingness_disclosure(fit_result):
    """REQ-INF-527. The missingness coefficient is REPORTED, not silently carried.

    An analysis that depends on missingness has to say so. If `delta_missing` is far from zero,
    the days Joe did not log differ systematically from the ones he did — and every estimate
    beside it is conditional on that.
    """
    if "delta_missing" not in fit_result["names"]:
        return {"modelled": False,
                "note": "No missingness indicator was supplied for this analysis."}
    s = summarise(fit_result, name="delta_missing")
    material = s["p_practical"] > 0.5
    return {"modelled": True, "imputed": False, "coefficient": s,
            "materially_nonzero": material,
            "note": (("The days with no observation differ systematically from the ones with "
                      "one, so every estimate here is conditional on that difference.")
                     if material else
                     "The missingness indicator carries little of the outcome.")}


# REQ-INF-521. The four excluded by name, with the requirement's own reasons.
EXCLUDED_PPLS = {
    "stan": "the CmdStan C++ compile step makes CI installation slow and fragile",
    "cmdstanpy": "the CmdStan C++ compile step makes CI installation slow and fragile",
    "pystan": "the CmdStan C++ compile step makes CI installation slow and fragile",
    "turing": "Julia precompilation makes CI installation slow and fragile",
    "pymc": "the PyTensor toolchain makes CI installation slow and fragile",
}


def check_excluded_ppl(dependencies):
    """REQ-INF-521. None of the four may be a dependency.

    The requirement gives its own reason and it is about CI rather than about statistics: a
    compile step, a Julia precompilation, or the PyTensor toolchain each turn a green nightly run
    into a coin flip. A probabilistic layer whose install is unreliable is one that stops running
    and is not noticed, because the failure looks like an infrastructure blip.

    This is a NEGATIVE requirement and is provable today; REQ-INF-520's positive half — that
    NumPyro is the sole PPL — is OQ-75, because jaxlib ships no macOS x86_64 wheel.
    """
    import re as _re
    found = []
    for d in dependencies:
        key = _re.sub(r"[^a-z]", "", str(d).lower())
        for name, why in EXCLUDED_PPLS.items():
            if key.startswith(name):
                found.append(f"{d} ({why})")
    if found:
        raise ModelViolation(f"REQ-INF-521: {found}")
    return True
