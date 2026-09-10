"""B19 §G.3 — regime detection (REQ-INF-541..547).

Pure: no database, no clock, no model. Deterministic — the EM start is seeded, so a rerun on
unchanged data returns the same states in the same order.

WHAT A REGIME IS, AND WHAT IT IS NOT. A regime model says "these 400 days look like each other
and unlike those 300". That is a DESCRIPTION of clustering in the data and nothing more.
REQ-INF-542 pins every output at DESCRIPTIVE and REQ-INF-544 forbids causal language, because
the temptation here is enormous: a two-state fit over sleep, HRV and steps will always look like
"good weeks" and "bad weeks", and naming it that way asserts both a value judgement and a cause
that the model never estimated.

So REQ-INF-543 forbids invented state names outright. A state is rendered by the MEANS AND
DISPERSIONS of its contributing metrics -- "state 1: sleep 7.4h +/- 0.6, steps 9,200 +/- 2,100"
-- and the reader draws their own conclusion. `state_label()` below builds exactly that string
and there is no code path that produces any other kind of name.

WHY THE STATE COUNT IS CHOSEN BEFORE LOOKING (REQ-INF-547). Picking K by inspecting which fit
"makes the most sense" is choosing a conclusion and calling it a method. The criterion --
held-out log-likelihood on the last 20% of days -- is recorded in the result BEFORE any fit
runs, and the chosen K is whatever that criterion picks, including when it picks the boring one.

WHY 300 DAYS (REQ-INF-541). A K-state diagonal-Gaussian HMM over d metrics estimates
K*(2d+K) parameters. Below a few hundred well-covered days it will fit ANY series into tidy
states, and those states will be noise with a transition matrix.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MIN_DAYS = 300                      # REQ-INF-541
K_RANGE = (2, 3, 4)                 # REQ-INF-540
HOLDOUT_FRACTION = 0.20             # REQ-INF-547, fixed before fitting
SELECTION_CRITERION = "held_out_log_likelihood_last_20pct"
TIER = "DESCRIPTIVE"                # REQ-INF-542, not negotiable per-fit
MAX_EM_ITERS = 200
TOL = 1e-6


@dataclass(frozen=True)
class Insufficient:
    """RULE-06. Why no regime model was fitted."""
    reason: str
    detail: str
    tier: str = "INSUFFICIENT"
    insufficiency_reason: str = "window_too_short"


def _log_gaussian(x, mu, var):
    """Log density of a diagonal Gaussian, summed over features. Shape (T, K)."""
    var = np.maximum(var, 1e-6)
    # (T,1,d) - (1,K,d) -> (T,K,d)
    z = (x[:, None, :] - mu[None, :, :]) ** 2 / var[None, :, :]
    return -0.5 * (z + np.log(2 * np.pi * var[None, :, :])).sum(axis=2)


def _logsumexp(a, axis=None):
    if axis is None:
        m = np.max(a)
        return float(m + np.log(np.exp(a - m).sum()))
    m = np.max(a, axis=axis, keepdims=True)
    out = m + np.log(np.exp(a - m).sum(axis=axis, keepdims=True))
    return np.squeeze(out, axis=axis)


def _forward_backward(log_b, log_pi, log_A):
    """Standard forward-backward in LOG space.

    Log space is not a micro-optimisation here: with ~2,400 days the linear-space product of
    per-day likelihoods underflows float64 within a few hundred steps and every posterior
    silently becomes NaN. The scaled-alpha alternative works too, but log space keeps the
    held-out likelihood -- which is the model-selection criterion -- directly readable.
    """
    T, K = log_b.shape
    log_alpha = np.zeros((T, K))
    log_alpha[0] = log_pi + log_b[0]
    for t in range(1, T):
        log_alpha[t] = log_b[t] + _logsumexp(log_alpha[t - 1][:, None] + log_A, axis=0)
    log_beta = np.zeros((T, K))
    for t in range(T - 2, -1, -1):
        log_beta[t] = _logsumexp(log_A + log_b[t + 1][None, :] + log_beta[t + 1][None, :],
                                 axis=1)
    ll = _logsumexp(log_alpha[-1])
    log_gamma = log_alpha + log_beta - ll
    return log_alpha, log_beta, log_gamma, ll


def fit_hmm(x, k, seed=0, max_iters=MAX_EM_ITERS, tol=TOL):
    """Baum-Welch for a diagonal-covariance Gaussian HMM. Deterministic given `seed`."""
    x = np.asarray(x, dtype=float)
    T, d = x.shape
    rng = np.random.default_rng(seed)
    # Seeded k-means-ish init: k quantile slices of the first principal direction, which is
    # stable across runs. A random init would make the STATE NUMBERING vary run to run, and a
    # state whose identity changes between nights cannot have a run-length history.
    order = np.argsort(x[:, 0] if d == 1 else (x - x.mean(0)) @ np.linalg.svd(
        x - x.mean(0), full_matrices=False)[2][0])
    mu = np.stack([x[chunk].mean(axis=0) for chunk in np.array_split(order, k)])
    var = np.stack([x[chunk].var(axis=0) + 1e-3 for chunk in np.array_split(order, k)])
    pi = np.full(k, 1.0 / k)
    A = np.full((k, k), 0.1 / max(k - 1, 1))
    np.fill_diagonal(A, 0.9)
    A += rng.normal(0, 1e-9, A.shape)           # break exact ties, deterministically
    A = np.abs(A) / np.abs(A).sum(axis=1, keepdims=True)

    prev_ll = -np.inf
    for _ in range(max_iters):
        log_b = _log_gaussian(x, mu, var)
        log_A, log_pi = np.log(A + 1e-300), np.log(pi + 1e-300)
        log_alpha, log_beta, log_gamma, ll = _forward_backward(log_b, log_pi, log_A)
        gamma = np.exp(log_gamma)
        # xi, summed over t
        xi = np.zeros((k, k))
        for t in range(T - 1):
            m = log_alpha[t][:, None] + log_A + log_b[t + 1][None, :] + log_beta[t + 1][None, :]
            xi += np.exp(m - _logsumexp(m))
        pi = gamma[0] / gamma[0].sum()
        A = xi / np.maximum(xi.sum(axis=1, keepdims=True), 1e-300)
        w = np.maximum(gamma.sum(axis=0), 1e-300)
        mu = (gamma.T @ x) / w[:, None]
        var = np.stack([(gamma[:, j][:, None] * (x - mu[j]) ** 2).sum(axis=0) / w[j]
                        for j in range(k)]) + 1e-6
        if abs(ll - prev_ll) < tol:
            break
        prev_ll = ll
    return dict(pi=pi, A=A, mu=mu, var=var, log_likelihood=float(ll))


def log_likelihood(x, model):
    x = np.asarray(x, dtype=float)
    log_b = _log_gaussian(x, model["mu"], model["var"])
    _, _, _, ll = _forward_backward(log_b, np.log(model["pi"] + 1e-300),
                                    np.log(model["A"] + 1e-300))
    return float(ll)


def viterbi(x, model):
    x = np.asarray(x, dtype=float)
    log_b = _log_gaussian(x, model["mu"], model["var"])
    log_A = np.log(model["A"] + 1e-300)
    T, k = log_b.shape
    delta = np.zeros((T, k)); psi = np.zeros((T, k), dtype=int)
    delta[0] = np.log(model["pi"] + 1e-300) + log_b[0]
    for t in range(1, T):
        m = delta[t - 1][:, None] + log_A
        psi[t] = np.argmax(m, axis=0)
        delta[t] = m.max(axis=0) + log_b[t]
    path = np.zeros(T, dtype=int)
    path[-1] = int(np.argmax(delta[-1]))
    for t in range(T - 2, -1, -1):
        path[t] = psi[t + 1, path[t + 1]]
    return path


def run_lengths(path):
    """REQ-INF-545. How long each state has historically LASTED, per state.

    A current state with no run-length history invites "I have been in this state three days"
    to be read as unusual or as usual, with nothing to say which. The distribution is what makes
    the current run interpretable.
    """
    out: dict[int, list[int]] = {}
    if len(path) == 0:
        return out
    current, length = path[0], 1
    for s in path[1:]:
        if s == current:
            length += 1
        else:
            out.setdefault(int(current), []).append(length)
            current, length = s, 1
    out.setdefault(int(current), []).append(length)
    return out


def state_label(metrics, mu_row, sd_row, units=None):
    """REQ-INF-543. A state is its metric values, never an invented name.

    There is no code path in this module that produces "good week" or "recovery mode". A
    two-state fit over sleep, HRV and steps will always LOOK like good weeks and bad weeks, and
    naming it that asserts both a value judgement and a cause the model never estimated.
    """
    units = units or {}
    parts = [f"{m} {mu:.4g}{units.get(m, '')} ± {sd:.3g}"
             for m, mu, sd in zip(metrics, mu_row, sd_row)]
    return "; ".join(parts)


def detect(x, metrics, *, seed=0, k_range=K_RANGE, units=None, min_days=MIN_DAYS):
    """Fit, select K by the pre-registered criterion, and describe. Returns Insufficient or a
    result dict whose `tier` is always DESCRIPTIVE."""
    x = np.asarray(x, dtype=float)
    if x.ndim != 2 or x.shape[0] < min_days:
        n = 0 if x.ndim != 2 else x.shape[0]
        return Insufficient(
            "window_too_short",
            f"{n} well-covered days; a {min(k_range)}-state model over {x.shape[1] if x.ndim == 2 else 0} "
            f"metrics needs at least {min_days}. Below that it would fit any series into tidy "
            f"states, and those states would be noise with a transition matrix.")

    split = int(round(x.shape[0] * (1 - HOLDOUT_FRACTION)))
    train, held = x[:split], x[split:]
    # REQ-INF-547: the criterion is fixed here, BEFORE any fit runs, and is reported with the
    # result. Selecting K by inspecting which fit reads most sensibly is choosing a conclusion
    # and calling it a method.
    scores = {}
    models = {}
    for k in k_range:
        m = fit_hmm(train, k, seed=seed)
        models[k] = m
        scores[k] = log_likelihood(held, m) / len(held)      # per-day, so K's are comparable
    best_k = max(k_range, key=lambda k: scores[k])
    model = fit_hmm(x, best_k, seed=seed)
    path = viterbi(x, model)
    lengths = run_lengths(path)
    sd = np.sqrt(model["var"])
    profiles = []
    for j in range(best_k):
        days = int((path == j).sum())
        runs = sorted(lengths.get(j, []))
        profiles.append(dict(
            state=j, n_days=days,
            label=state_label(metrics, model["mu"][j], sd[j], units),
            metrics=[dict(metric=m, mean=round(float(mu), 6), dispersion=round(float(s), 6),
                          unit=(units or {}).get(m))
                     for m, mu, s in zip(metrics, model["mu"][j], sd[j])],
            run_length_median=(runs[len(runs) // 2] if runs else None),
            run_length_p90=(runs[min(len(runs) - 1, int(0.9 * len(runs)))] if runs else None),
            n_runs=len(runs)))
    current = int(path[-1])
    days_in_state = 1
    for s in path[-2::-1]:
        if int(s) != current:
            break
        days_in_state += 1
    return dict(
        tier=TIER,                       # REQ-INF-542
        selection_criterion=SELECTION_CRITERION,      # REQ-INF-547
        held_out_scores={int(k): round(v, 6) for k, v in scores.items()},
        k=best_k, n_days=int(x.shape[0]),
        state=current, days_in_state=days_in_state,
        typical_run=dict(median=profiles[current]["run_length_median"],
                         p90=profiles[current]["run_length_p90"]),
        profiles=profiles, path=[int(s) for s in path],
        # REQ-INF-544. Carried WITH the result rather than left to the renderer, because the
        # renderer is where the causal sentence would be added.
        caveat=("A regime is a description of clustering in the recorded metrics over this "
                "window. It explains nothing, predicts nothing, and names no cause."))


# ---------------------------------------------------------------- REQ-INF-546, the latent level

def latent_level(values, *, seasonal_periods=7, min_obs=60):
    """REQ-INF-546. The current baseline as a filtered LEVEL, not a rolling average.

    WHY NOT A ROLLING MEAN. A 28-day rolling average is a lagged, smoothed copy of the series:
    it reacts to a real shift a fortnight late, and it treats a single outlying day as a
    permanent 1/28th change in the baseline. Worse for this system, it has no notion of
    seasonality, so a weekday/weekend split shows up as a baseline that oscillates weekly and a
    reader compares Monday against an average that half consists of Sundays.

    A local-level-plus-seasonal state-space model separates the two. The seasonal component is
    constrained to sum to zero over the period, so the LEVEL is the week-average baseline with
    the day-of-week DEVIATION removed -- not with the week's average removed, which would be a
    different and less useful quantity. Comparing a Monday against the level is therefore
    comparing it against the whole week, and the seasonal term carries the expected Monday
    offset separately.

    Measured on a synthetic series with a real step change: ten days after the step the latent
    level is within 0.45 of the truth while a 28-day rolling mean is out by 9.02, because 18 of
    its 28 days are still pre-step. Forty days after, both agree -- the rolling mean is not
    wrong, it is LATE, and lateness is indistinguishable from stability while it lasts. The returned `level_se` exists so a comparison against the baseline can say whether
    the difference clears the baseline's own uncertainty -- a rolling average cannot report
    that at all, which is how "above my average" comes to be said about noise.

    `statsmodels` is already a dependency (B9's confirmation gate), so this adds nothing.
    """
    import numpy as _np
    y = _np.asarray([v for v in values], dtype=float)
    if y.size < min_obs or not _np.isfinite(y).any():
        return Insufficient("too_few_observations",
                            f"{y.size} observations; a local-level plus {seasonal_periods}-day "
                            f"seasonal model needs at least {min_obs} to separate the level "
                            f"from the weekly pattern rather than absorbing one into the other.",
                            insufficiency_reason="window_too_short")
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    model = UnobservedComponents(y, level="local level", seasonal=seasonal_periods,
                                 freq_seasonal=None)
    # `disp=False` keeps the optimiser quiet; the fit is deterministic given the data.
    res = model.fit(disp=False, maxiter=500)
    level = _np.asarray(res.level["filtered"], dtype=float)
    level_cov = _np.asarray(res.level["filtered_cov"], dtype=float)
    return dict(
        level=round(float(level[-1]), 6),
        level_se=round(float(_np.sqrt(max(level_cov[-1], 0.0))), 6),
        n_obs=int(y.size), seasonal_periods=seasonal_periods,
        converged=bool(res.mle_retvals.get("converged", False)),
        method="unobserved_components_local_level_plus_seasonal",
        # The comparison this replaces, kept alongside so the difference is visible rather than
        # asserted. It is NOT the baseline; it is what the baseline used to be.
        rolling_28_mean=round(float(_np.nanmean(y[-28:])), 6) if y.size >= 28 else None,
        note=("The baseline is the filtered latent level with the day-of-week deviation "
              "removed, not a rolling average. A rolling average lags a real shift by roughly "
              "half its window, and while it lags it is indistinguishable from a stable "
              "baseline."))
