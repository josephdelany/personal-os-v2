"""B19 §G.3 — regime detection and the latent baseline (REQ-INF-541..547).

Pure and deterministic, so exercised against synthetic series with a KNOWN answer. A regime
model is the easiest thing in this system to over-read: a two-state fit over sleep and steps
will always look like "good weeks" and "bad weeks", and almost every test below is about the
model refusing to say so.
"""
import numpy as np
import pytest

from tools.engines.regimes import (HOLDOUT_FRACTION, Insufficient, MIN_DAYS,
                                   SELECTION_CRITERION, TIER, detect, fit_hmm, latent_level,
                                   log_likelihood, run_lengths, state_label, viterbi)


def two_regimes(seed=7, block=50, blocks=16, n_metrics=2):
    """Eight alternating 50-day blocks of each of two genuinely different regimes."""
    rng = np.random.default_rng(seed)
    rows = []
    for b in range(blocks):
        mu = [7.5, 9500][:n_metrics] if b % 2 == 0 else [5.9, 4200][:n_metrics]
        sd = [0.5, 900][:n_metrics]
        rows.append(rng.normal(mu, sd, size=(block, n_metrics)))
    return np.vstack(rows)


def test_REQ_INF_541_below_300_well_covered_days_no_model_is_fitted():
    """A K-state diagonal-Gaussian HMM over d metrics estimates K*(2d+K) parameters. Below a few
    hundred days it fits ANY series into tidy states, and those states are noise with a
    transition matrix."""
    r = detect(two_regimes()[:MIN_DAYS - 1], ["sleep_hours", "steps"])
    assert isinstance(r, Insufficient)
    assert r.tier == "INSUFFICIENT"
    assert r.insufficiency_reason == "window_too_short"
    assert "noise with a transition matrix" in r.detail


def test_REQ_INF_541_exactly_the_threshold_is_enough():
    r = detect(two_regimes()[:MIN_DAYS], ["sleep_hours", "steps"])
    assert not isinstance(r, Insufficient), "300 days is the floor, not an exclusive bound"


def test_REQ_INF_540_543_the_states_recovered_are_the_states_generated():
    """The model is validated against a series whose true structure is known: two regimes, means
    7.5h/9,500 and 5.9h/4,200, switching every 50 days. If it cannot recover that, nothing it
    says about Joe's data is worth reading."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1)
    assert r["k"] == 2
    means = sorted(p["metrics"][0]["mean"] for p in r["profiles"])
    assert means[0] == pytest.approx(5.9, abs=0.15)
    assert means[1] == pytest.approx(7.5, abs=0.15)
    steps = sorted(p["metrics"][1]["mean"] for p in r["profiles"])
    assert steps[0] == pytest.approx(4200, abs=200)
    assert steps[1] == pytest.approx(9500, abs=200)


def test_REQ_INF_545_the_run_length_distribution_recovers_the_true_switching_period():
    """A current state with no run-length history invites "I have been in this state three days"
    to be read as unusual or as usual, with nothing to say which."""
    r = detect(two_regimes(block=50), ["sleep_hours", "steps"], seed=1)
    for p in r["profiles"]:
        assert p["run_length_median"] == pytest.approx(50, abs=2), p
        assert p["n_runs"] >= 7
    assert r["typical_run"]["median"] is not None
    assert r["typical_run"]["p90"] is not None
    assert r["days_in_state"] >= 1


def test_REQ_INF_545_run_lengths_are_computed_correctly_on_a_hand_checked_path():
    assert run_lengths(np.array([0, 0, 1, 1, 1, 0])) == {0: [2, 1], 1: [3]}
    assert run_lengths(np.array([])) == {}
    assert run_lengths(np.array([2])) == {2: [1]}


def test_REQ_INF_542_every_regime_output_is_DESCRIPTIVE():
    """Not negotiable per fit. A regime is a description of clustering; it explains nothing and
    predicts nothing, and any higher tier would claim it does."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1)
    assert r["tier"] == TIER == "DESCRIPTIVE"


def test_REQ_INF_543_a_state_is_rendered_by_its_metric_values_and_never_by_a_name():
    """A two-state fit over sleep and steps will always LOOK like good weeks and bad weeks.
    Naming it that asserts a value judgement AND a cause the model never estimated."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1,
               units={"sleep_hours": "h"})
    for p in r["profiles"]:
        assert "sleep_hours" in p["label"] and "±" in p["label"]
        for banned in ("good", "bad", "poor", "healthy", "optimal", "recovery", "burnout"):
            assert banned not in p["label"].lower(), p["label"]
    assert "7.5" in state_label(["m"], [7.5], [0.2])


def test_REQ_INF_544_no_causal_language_and_the_caveat_travels_with_the_result():
    """Carried WITH the result rather than left to the renderer, because the renderer is exactly
    where the causal sentence would be added."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1)
    assert "explains nothing" in r["caveat"]
    blob = " ".join(str(v) for v in r.values()).lower()
    for banned in ("because", "causes", "caused by", "leads to", "drives", "due to"):
        assert banned not in blob, f"causal language reached a regime output: {banned}"


def test_REQ_INF_547_the_selection_criterion_is_fixed_and_reported_with_every_fit():
    """Picking K by inspecting which fit "makes the most sense" is choosing a conclusion and
    calling it a method. The criterion is recorded before any fit runs."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1)
    assert r["selection_criterion"] == SELECTION_CRITERION == "held_out_log_likelihood_last_20pct"
    assert set(r["held_out_scores"]) == {2, 3, 4}, "every candidate K is scored and reported"
    best = max(r["held_out_scores"], key=lambda k: r["held_out_scores"][k])
    assert r["k"] == best, "K is whatever the criterion picks, including the boring one"


def test_REQ_INF_547_the_criterion_picks_the_simpler_model_on_two_regime_data():
    """The honest outcome: given data with two regimes, held-out likelihood prefers two states.
    A criterion that always preferred more states would be selecting complexity, not fit."""
    r = detect(two_regimes(), ["sleep_hours", "steps"], seed=1)
    assert r["k"] == 2, r["held_out_scores"]


def test_RULE_11_the_fit_is_deterministic_across_runs():
    """A state whose identity changes between nights cannot have a run-length history, and
    "you have been in state 2 for six days" would silently mean a different state each time."""
    x = two_regimes()
    a = detect(x, ["sleep_hours", "steps"], seed=1)
    b = detect(x, ["sleep_hours", "steps"], seed=1)
    assert a["path"] == b["path"]
    assert a["k"] == b["k"] and a["held_out_scores"] == b["held_out_scores"]


def test_RULE_11_the_forward_backward_survives_a_long_series_without_underflow():
    """In linear space the product of per-day likelihoods underflows float64 within a few
    hundred steps and every posterior silently becomes NaN — on a series length this project
    actually has (~2,400 days)."""
    x = two_regimes(block=150, blocks=16)
    m = fit_hmm(x, 2, seed=1)
    ll = log_likelihood(x, m)
    assert np.isfinite(ll), "log-likelihood underflowed"
    assert np.isfinite(m["mu"]).all() and (m["var"] > 0).all()
    assert len(np.unique(viterbi(x, m))) == 2


def test_REQ_INF_546_the_latent_level_beats_a_rolling_mean_right_after_a_real_shift():
    """The measured claim, not an asserted one. Ten days after a step change the 28-day rolling
    mean still has 18 pre-step days in it; the filtered level does not. Forty days after, they
    agree — the rolling mean is not wrong, it is LATE, and lateness is indistinguishable from
    stability while it lasts."""
    rng = np.random.default_rng(3)
    n, week = 200, np.array([0, 0, 0, 0, 0, 12, 12])
    truth = 75 + week.mean()

    y = np.where(np.arange(n) < n - 10, 60.0, 75.0) + week[np.arange(n) % 7] + rng.normal(0, 2, n)
    fresh = latent_level(y)
    assert abs(fresh["level"] - truth) < 1.5, fresh
    assert abs(fresh["rolling_28_mean"] - truth) > 5, "the rolling mean should still be lagging"
    assert abs(fresh["level"] - truth) < abs(fresh["rolling_28_mean"] - truth) / 5

    y = np.where(np.arange(n) < n - 40, 60.0, 75.0) + week[np.arange(n) % 7] + rng.normal(0, 2, n)
    settled = latent_level(y)
    assert abs(settled["rolling_28_mean"] - truth) < 1.5, "given time, the rolling mean catches up"


def test_REQ_INF_546_the_level_reports_its_own_uncertainty():
    """A comparison against the baseline must be able to say whether the difference clears the
    baseline's own uncertainty. A rolling average cannot report that at all, which is how
    "above my average" comes to be said about noise."""
    rng = np.random.default_rng(5)
    y = 60 + rng.normal(0, 2, 200)
    r = latent_level(y)
    assert r["level_se"] > 0
    assert r["converged"] is True
    assert r["method"] == "unobserved_components_local_level_plus_seasonal"


def test_REQ_INF_546_too_short_a_series_returns_a_reason_not_a_number():
    r = latent_level([1.0] * 20)
    assert isinstance(r, Insufficient) and r.insufficiency_reason == "window_too_short"


def test_REQ_INF_547_the_holdout_fraction_is_a_declared_constant():
    assert HOLDOUT_FRACTION == 0.20
