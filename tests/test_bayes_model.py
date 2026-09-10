"""B19 §G.2 — the Bayesian effect model (REQ-INF-522..527).

REQ-INF-520 names NumPyro and jaxlib has no macOS x86_64 wheel, so that requirement is OQ-75 and
is NOT claimed here. REQ-INF-522..527 specify the MODEL — standardisation, priors, pooling,
reporting, missingness — and every one is library-agnostic, so they are proven with a hand-written
sampler that runs and is checkable on this machine.
"""
import numpy as np
import pytest

from tools.engines.bayes_model import (COEF_PRIOR_SD, DEFAULT_ROPE_SD, ModelViolation, POOLABLE,
                                       SCALE_PRIOR_SD, check_no_p_value, check_pooling, fit, hdi,
                                       missingness_disclosure, standardise, summarise)


def synthetic(*, n=500, beta=-0.45, seed=11, with_missing=False):
    rng = np.random.default_rng(seed)
    x = rng.normal(0, 1, n)
    dow = rng.integers(0, 7, n)
    u = rng.normal(0, 0.4, 7)
    m = (rng.uniform(size=n) < 0.25).astype(float) if with_missing else None
    y = 2.0 + beta * x + u[dow] + rng.normal(0, 0.6, n)
    if with_missing:
        y = y + 0.8 * m          # the missing days differ systematically
    return x, dow, y, m


def test_REQ_INF_522_every_predictor_and_the_outcome_are_standardised():
    """Not cosmetic: the Normal(0, 0.3) prior is a statement about a STANDARDISED coefficient. On
    raw units the same prior is almost flat for a step count and crushingly tight for an
    hours-of-sleep figure — the prior's strength would depend on the unit somebody chose."""
    s = standardise([1.0, 2.0, 3.0, 4.0])
    assert abs(float(np.mean(s.values))) < 1e-12
    assert abs(float(np.std(s.values)) - 1.0) < 1e-12
    with pytest.raises(ModelViolation, match="REQ-INF-522"):
        standardise([3.0, 3.0, 3.0])


def test_REQ_INF_523_the_coefficient_prior_is_normal_zero_point_three():
    x, dow, y, _ = synthetic()
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=300, warmup=200, seed=1)
    assert COEF_PRIOR_SD == 0.3
    # alpha is a location, not an effect, so it gets a wider prior; every coefficient gets 0.3.
    assert f["prior_sd"][0] == 1.0
    assert all(p == COEF_PRIOR_SD for p in f["prior_sd"][1:])


def test_ADR_0070_a_planted_beta_is_recovered_inside_the_hdi():
    """The check that matters, at an effect size the prior is designed for. The model is fitted to
    data with a known coefficient and the true standardised value must fall inside the 95% HDI —
    if it does not, nothing the sampler says about Joe's data is worth reading."""
    x, dow, y, _ = synthetic(beta=-0.20)
    true_std = -0.20 / float(np.std(y))
    assert abs(true_std) < 0.4, "an effect the Normal(0, 0.3) prior treats as plausible"
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=1500, warmup=800, seed=3)
    s = summarise(f)
    lo, hi = s["hdi_95"]
    assert lo <= true_std <= hi, (true_std, s["hdi_95"])
    assert s["p_direction"] > 0.99, "the sign is not in doubt at this effect size"


def test_REQ_INF_523_a_LARGE_effect_is_visibly_shrunk_and_that_is_the_prior_working():
    """The first version of the test above planted a 0.59 SD effect and demanded it fall inside
    the HDI. It did not — the interval stopped at 0.585 — and the test was wrong, not the
    sampler: a Normal(0, 0.3) prior says an effect of 0.59 SD is unlikely, so it pulls the
    estimate in.

    That is worth knowing rather than hiding. It means this layer systematically UNDERSTATES
    large effects, and the understatement grows with the effect. A reader who needs the
    unshrunk number should read the frequentist HAC estimate the confirmation gate already
    stores; this layer's job is calibrated belief, not maximum likelihood."""
    x, dow, y, _ = synthetic(beta=-0.45)
    true_std = -0.45 / float(np.std(y))
    assert abs(true_std) > 0.5, "well outside what the prior expects"
    s = summarise(fit(y, exposure=x, groups={"day_of_week": dow}, draws=1500, warmup=800, seed=3))
    assert abs(s["median"]) < abs(true_std), "shrunk toward zero"
    assert abs(s["median"] - true_std) < 0.15, "but the data still dominates at n=500"
    assert s["hdi_95"][1] < 0, "and the sign is never in doubt"


def test_REQ_INF_524_scales_use_a_half_normal_prior_and_never_an_inverse_gamma():
    """Inverse-gamma is the conjugate choice that would have made this simpler, and it is
    forbidden for a real reason: at small group counts its behaviour near zero dominates the
    posterior, so a variance component genuinely near zero gets pushed away from it. Seven
    day-of-week groups is exactly "small"."""
    import inspect
    from tools.engines import bayes_model as m
    src = inspect.getsource(m)
    assert "half_normal" in src and SCALE_PRIOR_SD == 1.0
    assert "inverse_gamma" not in src.lower().replace("-", "_") or "forbid" in src.lower()
    x, dow, y, _ = synthetic()
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=400, warmup=300, seed=5)
    assert (f["tau"]["day_of_week"] > 0).all(), "a scale is positive by construction"
    assert (f["sigma"] > 0).all()


def test_REQ_INF_525_pooling_is_within_person_only():
    """Hierarchical models are usually taught with people as the top level, and there is exactly
    one person here. A "between-person" term on n=1 has one group, which is not pooling — it is
    an intercept with extra steps and a misleading name."""
    assert POOLABLE == ("day_of_week", "season", "life_phase", "exposure_instance")
    assert check_pooling(("day_of_week", "season"))
    with pytest.raises(ModelViolation, match="REQ-INF-525"):
        check_pooling(("day_of_week", "person"))
    with pytest.raises(ModelViolation, match="REQ-INF-525"):
        check_pooling(("between_person",))


def test_REQ_INF_525_a_pooled_grouping_is_actually_estimated():
    """The day-of-week effects are real in the synthetic data (sd 0.4), so tau must be well away
    from zero — otherwise "pooling" would be a parameter the model carries and ignores."""
    x, dow, y, _ = synthetic()
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=800, warmup=500, seed=7)
    assert float(np.median(f["tau"]["day_of_week"])) > 0.2


def test_REQ_INF_526_the_summary_reports_direction_and_practical_significance():
    """Both are statements about the parameter, which is what a reader assumes a p-value is and
    what it is not."""
    x, dow, y, _ = synthetic()
    s = summarise(fit(y, exposure=x, groups={"day_of_week": dow}, draws=800, warmup=500, seed=3))
    assert 0.0 <= s["p_direction"] <= 1.0
    assert 0.0 <= s["p_practical"] <= 1.0
    assert s["rope"] == (-DEFAULT_ROPE_SD, DEFAULT_ROPE_SD)
    assert "p_value" not in s and "p" not in s


def test_REQ_INF_526_a_p_value_is_refused_under_any_spelling():
    assert check_no_p_value({"p_direction": 0.97, "p_practical": 0.9})
    for spelling in ("p", "p_value", "pvalue", "pval", "sig"):
        with pytest.raises(ModelViolation, match="REQ-INF-526"):
            check_no_p_value({spelling: 0.03})


def test_REQ_INF_526_a_rope_of_zero_width_would_make_practical_significance_meaningless():
    """p_practical against a zero ROPE is p_direction with extra steps: every non-zero draw is
    "outside" it, so the question stops being about whether the effect matters."""
    x, dow, y, _ = synthetic()
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=600, warmup=400, seed=3)
    wide = summarise(f, rope_sd=0.5)["p_practical"]
    narrow = summarise(f, rope_sd=0.0)["p_practical"]
    assert narrow > wide, "a wider ROPE must make practical significance harder to clear"
    assert narrow == pytest.approx(1.0, abs=0.01)


def test_REQ_INF_527_missingness_is_a_coefficient_and_never_a_filter():
    """If Joe stops logging dinner on the nights he drinks, the missingness indicator carries the
    effect — and dropping those rows moves it into beta. Modelling m makes the bias visible."""
    x, dow, y, m = synthetic(with_missing=True)
    f = fit(y, exposure=x, groups={"day_of_week": dow}, missing_indicator=m,
            draws=1200, warmup=800, seed=9)
    assert "delta_missing" in f["names"]
    d = missingness_disclosure(f)
    assert d["modelled"] is True and d["imputed"] is False
    assert d["materially_nonzero"] is True
    assert "conditional on that difference" in d["note"]
    assert f["n"] == len(y), "no row was dropped"


def test_REQ_INF_527_an_analysis_with_no_indicator_says_so_rather_than_implying_none_exists():
    x, dow, y, _ = synthetic()
    f = fit(y, exposure=x, groups={"day_of_week": dow}, draws=300, warmup=200, seed=1)
    d = missingness_disclosure(f)
    assert d["modelled"] is False and "No missingness indicator" in d["note"]


def test_RULE_11_the_sampler_is_deterministic_under_a_seed():
    """A posterior that moves between runs on identical data is one nobody can check, and every
    replay of a stored finding would disagree with the finding."""
    x, dow, y, _ = synthetic()
    a = fit(y, exposure=x, groups={"day_of_week": dow}, draws=200, warmup=100, seed=42)
    b = fit(y, exposure=x, groups={"day_of_week": dow}, draws=200, warmup=100, seed=42)
    assert np.allclose(a["draws"], b["draws"])


def test_the_hdi_is_the_narrowest_interval_containing_the_mass():
    """Checked against a known asymmetric distribution: for a right-skewed sample the HDI must sit
    lower than the equal-tailed interval, which is the whole reason for preferring it."""
    rng = np.random.default_rng(2)
    s = rng.exponential(1.0, 20000)
    lo, hi = hdi(s, prob=0.95)
    q_lo, q_hi = np.quantile(s, [0.025, 0.975])
    assert (hi - lo) <= (q_hi - q_lo) + 1e-9
    assert lo < q_lo


def test_REQ_INF_521_none_of_the_four_excluded_probabilistic_languages_is_a_dependency():
    """The requirement's own reason is about CI, not statistics: a C++ compile step, a Julia
    precompilation or the PyTensor toolchain each turn a green nightly run into a coin flip. A
    probabilistic layer whose install is unreliable is one that stops running and is not noticed,
    because the failure looks like an infrastructure blip."""
    from tools.engines.bayes_model import EXCLUDED_PPLS, check_excluded_ppl
    assert set(EXCLUDED_PPLS) >= {"stan", "cmdstanpy", "pymc", "turing"}
    assert check_excluded_ppl(["numpy", "scipy", "pg8000", "statsmodels"])
    for bad in ("pystan", "cmdstanpy", "pymc", "turing", "PyMC5"):
        with pytest.raises(ModelViolation, match="REQ-INF-521"):
            check_excluded_ppl(["numpy", bad])


def test_REQ_INF_521_the_live_dependency_set_contains_none_of_them():
    """The requirement is about this repository, so this checks this repository: every pinned
    install line in the workflows plus everything importable in tools/."""
    import pathlib
    import re as _re
    from tools.engines.bayes_model import check_excluded_ppl
    root = pathlib.Path(__file__).resolve().parents[1]
    pinned = []
    for wf in (root / ".github" / "workflows").glob("*.yml"):
        for m in _re.finditer(r"pip install ([^\n]+)", wf.read_text(errors="ignore")):
            pinned += _re.findall(r"'([^']+)'", m.group(1))
    assert pinned, "no pinned install lines found; the check would prove nothing"
    check_excluded_ppl([p.split(">")[0].split("=")[0].split("[")[0] for p in pinned])
    imports = []
    for f in root.glob("tools/**/*.py"):
        imports += _re.findall(r"^\s*(?:import|from)\s+([\w\.]+)", f.read_text(errors="ignore"),
                               _re.M)
    check_excluded_ppl(imports)


# ---------------------------------------------------------------- REQ-INF-520, the NumPyro half

def test_REQ_INF_520_numpyro_is_the_probabilistic_programming_language_and_it_RUNS():
    """The last unproven requirement in the spec, and it was blocked on a claim of mine that was
    wrong twice over.

    ADR-0103's amendment said jaxlib ships no macOS x86_64 wheel. That was true of the LATEST
    release and false of the library: 77 such wheels exist, the newest being 0.4.38 (cp310-cp313)
    and the newest with a cp39 wheel being 0.4.30. The install failed because this machine's
    default interpreter is 3.14, not because of the platform — a version search nobody had done.

    Verified on 2026-09-10 under Python 3.9.6 with jax==jaxlib==0.4.30 and numpyro==0.19.0: NUTS
    runs, and its posterior for a planted coefficient agrees with the hand-written Gibbs sampler
    to 0.0012.

    The test skips where NumPyro is not importable rather than failing, because the model is
    proven either way by `bayes_model` — but it is not skipped in CI, where python is 3.12.
    """
    from tools.engines import bayes_numpyro
    if not bayes_numpyro.available():
        pytest.skip("NumPyro not importable in this interpreter (needs py3.9-3.13 for a macOS "
                    "x86_64 jaxlib wheel); proven under the venv recorded in ADR-0103")
    x, dow, y, _ = synthetic(beta=-0.20)
    true_std = -0.20 / float(np.std(y))
    f = bayes_numpyro.fit(y, exposure=x, groups={"day_of_week": dow}, seed=3,
                          num_warmup=500, num_samples=500, num_chains=2)
    assert f["sampler"] == "numpyro_nuts"
    s = summarise(f)
    lo, hi = s["hdi_95"]
    assert lo <= true_std <= hi, (true_std, s["hdi_95"])


def test_REQ_INF_520_the_two_implementations_agree_on_a_planted_coefficient():
    """Two independent implementations agreeing is much stronger evidence than either alone, and
    a disagreement between them is a defect in one — without the second there would be nothing to
    notice it."""
    from tools.engines import bayes_numpyro
    if not bayes_numpyro.available():
        pytest.skip("NumPyro not importable in this interpreter")
    x, dow, y, _ = synthetic(beta=-0.20)
    g = summarise(fit(y, exposure=x, groups={"day_of_week": dow}, draws=1500, warmup=800, seed=3))
    n = summarise(bayes_numpyro.fit(y, exposure=x, groups={"day_of_week": dow}, seed=3,
                                    num_warmup=500, num_samples=500, num_chains=2))
    assert abs(g["median"] - n["median"]) < 0.02, (g["median"], n["median"])


def test_REQ_INF_520_the_numpyro_path_reports_through_the_SAME_reporting_layer():
    """`summarise`, `missingness_disclosure` and `check_no_p_value` serve both implementations,
    so REQ-INF-526's prohibitions cannot be satisfied by one and missed by the other."""
    import inspect
    from tools.engines import bayes_numpyro
    src = inspect.getsource(bayes_numpyro)
    assert "bayes_model" in src
    assert "summarise" not in src.replace("`summarise`", ""), \
        "the numpyro module defines no reporting of its own"
