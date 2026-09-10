"""B9 §B.1/§B.2/§B.3 — multiplicity, serial correlation, specification curves
(REQ-INF-001..009, 020..026, 030..038).

`speccurve.py` computes a curve. This is the discipline around it: what may be tested, how many
tests that makes, and what a sample size means when the observations are days in a row.
"""
import datetime as dt

import pytest

from tools.engines.multiplicity import (LAG_PROFILE, MONTHLY_SHIFTS, PipelineViolation,
                                        WEEKLY_SHIFTS, benjamini_hochberg,
                                        catalog_authored_before_results,
                                        check_multiplicity_method, check_washout, create_finding,
                                        curve_summary, default_output_format,
                                        discovery_count_vs_null, effective_n, estimate_row,
                                        extend_tree, hierarchical_fdr, lag_profile,
                                        null_shifts_required, persist_test, prune_search_space,
                                        render_curve, render_sample_size)

REGISTRY = {"sleep": {"can_be_cause": True, "can_be_effect": True},
            "weather": {"can_be_cause": True, "can_be_effect": False},
            "age": {"can_be_cause": False, "can_be_effect": True}}


def test_REQ_INF_005_pruning_happens_BEFORE_correction_so_it_buys_power():
    """Order is the whole point: a pair removed before correction does not count toward m, so
    pruning makes the surviving tests MORE powerful. Pruning afterwards would shrink the reported
    family while leaving the penalty already paid."""
    pairs = [("sleep", "weather"), ("age", "sleep"), ("sleep", "sleep")]
    kept = prune_search_space(pairs, REGISTRY)
    assert kept == (("sleep", "sleep"),)


def test_REQ_INF_001_002_the_tree_has_three_levels_and_a_family_needs_its_parent_rejected():
    """Yekutieli hierarchical FDR: this is what keeps each family small enough for BH to have
    power while still controlling error over the tree."""
    tree = [
        {"id": "d1", "parent": None, "level": "domain_pair", "m": 3, "pvalues": [0.001]},
        {"id": "v1", "parent": "d1", "level": "variable_pair", "m": 4, "pvalues": [0.01]},
        {"id": "v2", "parent": "dead", "level": "variable_pair", "m": 4, "pvalues": [0.001]},
    ]
    out = {r["family"]: r for r in hierarchical_fdr(tree)}
    assert out["d1"]["tested"] and out["v1"]["tested"]
    assert out["v2"]["tested"] is False
    assert out["v2"]["reason"] == "parent hypothesis not rejected"


def test_REQ_INF_007_every_descended_branch_reports_its_test_count_and_q_threshold():
    """A discovery whose family size and threshold are not reported cannot be judged by anyone
    reading it."""
    tree = [{"id": "d1", "parent": None, "level": "domain_pair", "m": 10,
             "pvalues": [0.001, 0.9]}]
    r = hierarchical_fdr(tree)[0]
    assert r["n_tests"] == 2 and r["m"] == 10 and r["q_threshold"] == 0.05


def test_REQ_INF_003_the_family_size_is_the_REGISTERED_one_not_the_list_length():
    """Deriving m from however many tests happened to run would let a crashed test silently make
    every surviving q-value smaller."""
    ps = [0.01, 0.02]
    assert benjamini_hochberg(ps, m=2) != benjamini_hochberg(ps, m=100)
    assert min(benjamini_hochberg(ps, m=100)) > min(benjamini_hochberg(ps, m=2))


def test_benjamini_hochberg_matches_a_hand_computed_example():
    """Checked against the formula rather than against the implementation: with m=4 and
    p=[0.01, 0.02, 0.03, 0.9], the step-up values are 0.04, 0.04, 0.04, 0.9."""
    q = benjamini_hochberg([0.01, 0.02, 0.03, 0.9], m=4)
    assert q[0] == pytest.approx(0.04) and q[1] == pytest.approx(0.04)
    assert q[2] == pytest.approx(0.04) and q[3] == pytest.approx(0.9)


def test_REQ_INF_004_plain_benjamini_yekutieli_is_not_the_primary_gate():
    """Its harmonic penalty is about 10.9 at m=30,000 — not conservatism but a gate nothing
    passes, and a gate nothing passes teaches you nothing about the world."""
    assert check_multiplicity_method("benjamini_hochberg")
    for name in ("benjamini_yekutieli", "Benjamini-Yekutieli", "BY"):
        with pytest.raises(PipelineViolation, match="REQ-INF-004"):
            check_multiplicity_method(name)


def test_REQ_INF_008_a_test_whose_family_is_not_registered_is_discarded():
    """It is not a test that was corrected for; it is a test nobody counted."""
    assert persist_test(family_id="f1", m=10, p_raw=0.01, q_adjusted=0.04,
                        registered_families={"f1"})
    with pytest.raises(PipelineViolation, match="REQ-INF-008"):
        persist_test(family_id="rogue", m=10, p_raw=0.01, q_adjusted=0.04,
                     registered_families={"f1"})


def test_REQ_INF_003_a_stored_test_carries_m_p_and_q():
    for missing in ("m", "p_raw", "q_adjusted"):
        kw = {"family_id": "f1", "m": 10, "p_raw": 0.01, "q_adjusted": 0.04,
              "registered_families": {"f1"}}
        kw[missing] = None
        with pytest.raises(PipelineViolation, match="REQ-INF-003"):
            persist_test(**kw)


def test_REQ_INF_009_the_family_catalog_may_not_be_authored_after_seeing_results():
    """Authoring it afterwards changes q-values without changing data, in whichever direction the
    person doing it wants."""
    assert catalog_authored_before_results(authored_at=dt.date(2026, 9, 1),
                                           first_result_at=dt.date(2026, 9, 2))
    with pytest.raises(PipelineViolation, match="REQ-INF-009"):
        catalog_authored_before_results(authored_at=dt.date(2026, 9, 3),
                                        first_result_at=dt.date(2026, 9, 2))


def test_REQ_INF_006_a_new_metric_extends_the_tree_and_m_moves_at_the_NEXT_run():
    """A family size that changes mid-run makes the q-values of tests already performed
    incomparable with the ones still to come."""
    out = extend_tree({"new_metric": {}}, existing_families=("variable_pair:sleep",),
                      recompute_at="next_scheduled_run")
    assert "variable_pair:new_metric" in out["families"]
    assert out["family_sizes_recomputed_at"] == "next_scheduled_run"
    assert "never mid-run" in out["note"]


# ---------------------------------------------------------------- §B.2

def test_REQ_INF_022_n_eff_is_n_times_one_minus_rho_over_one_plus_rho():
    """A metric with rho=0.6 over 400 days carries the information of about 100 independent
    ones."""
    assert effective_n(400, 0.6) == pytest.approx(100.0)
    assert effective_n(400, 0.0) == 400.0


def test_REQ_INF_020_021_024_an_estimate_needs_robust_errors_rho_and_maxlags():
    """An estimate with a naive standard error over autocorrelated days has an interval that is
    simply too narrow, and nothing downstream can tell."""
    ok = estimate_row(beta=-22, se=6, n=400, rho=0.6, maxlags=7, robust_method="newey_west")
    assert ok["n_eff"] == pytest.approx(100.0) and ok["maxlags"] == 7
    with pytest.raises(PipelineViolation, match="REQ-INF-020"):
        estimate_row(beta=-22, se=6, n=400, rho=0.6, maxlags=7, robust_method="ols")
    with pytest.raises(PipelineViolation, match="REQ-INF-021/024"):
        estimate_row(beta=-22, se=6, n=400, rho=None, maxlags=7, robust_method="hac")


def test_REQ_INF_025_no_rho_and_n_eff_means_no_findings_row():
    assert create_finding({"rho": 0.5, "n_eff": 100})["findings_row"] is True
    with pytest.raises(PipelineViolation, match="REQ-INF-025"):
        create_finding({"rho": None, "n_eff": None})


def test_REQ_INF_023_n_is_never_rendered_alone():
    """"n=400" is true and misleading; "n=400, n_eff=100" is neither."""
    assert render_sample_size(400, 100) == "n=400, n_eff=100"
    with pytest.raises(PipelineViolation, match="REQ-INF-023"):
        render_sample_size(400, None)


def test_REQ_INF_026_a_washout_without_robust_inference_is_forbidden():
    """Discarding the days around a transition makes the remaining points look cleaner and more
    independent than they are. A procedure that looks like extra rigour while being the opposite
    is the most dangerous kind."""
    assert check_washout(washout_days=3, robust_method="hac")
    assert check_washout(washout_days=0, robust_method="ols")
    with pytest.raises(PipelineViolation, match="REQ-INF-026"):
        check_washout(washout_days=3, robust_method="ols")


# ---------------------------------------------------------------- §B.3

def test_REQ_INF_031_the_curve_stores_count_median_sign_agreement_and_significant_fraction():
    s = curve_summary([0.2, 0.3, -0.1, 0.4], [0.01, 0.2, 0.6, 0.04])
    assert s["n_specs"] == 4
    assert s["sign_agreement"] == 0.75
    assert s["significant_fraction"] == 0.5


def test_REQ_INF_033_the_shift_counts_are_two_hundred_weekly_and_two_thousand_monthly():
    assert null_shifts_required("weekly") == WEEKLY_SHIFTS == 200
    assert null_shifts_required("monthly") == MONTHLY_SHIFTS == 2_000


def test_REQ_INF_034_the_observed_significant_fraction_never_renders_without_the_null():
    """"41% of specifications were significant" sounds decisive until the shuffled data produces
    38%. The null fraction is not a footnote to that number — it is what gives it a meaning."""
    s = curve_summary([0.2] * 10, [0.01] * 4 + [0.5] * 6)
    out = render_curve(s, {"significant_fraction": 0.38})
    assert "38%" in out["text"] and "40%" in out["text"]
    with pytest.raises(PipelineViolation, match="REQ-INF-034"):
        render_curve(s, None)


def test_REQ_INF_035_the_effect_is_a_lag_profile_over_five_lags():
    """A single lag coefficient reported as "the effect" is a choice among five, and the one
    chosen is the one that looked best."""
    assert LAG_PROFILE == (0, 1, 2, 3, 7)
    with pytest.raises(PipelineViolation, match="REQ-INF-035"):
        lag_profile({0: 0.2, 1: 0.1}, {0: 0.01, 1: 0.5})


def test_REQ_INF_036_significant_at_one_lag_and_sign_flipped_at_another_is_INSUFFICIENT():
    """That is the signature of noise, not of an effect."""
    out = lag_profile({0: 0.5, 1: -0.2, 2: 0.01, 3: 0.0, 7: 0.02},
                      {0: 0.01, 1: 0.4, 2: 0.6, 3: 0.9, 7: 0.7})
    assert out["tier"] == "INSUFFICIENT"
    assert out["insufficiency_reason"] == "sign_unstable"
    assert "signature of noise" in out["detail"]


def test_REQ_INF_036_a_consistent_profile_is_not_refused():
    out = lag_profile({0: 0.5, 1: 0.4, 2: 0.3, 3: 0.2, 7: 0.1},
                      {0: 0.01, 1: 0.4, 2: 0.6, 3: 0.9, 7: 0.7})
    assert out["tier"] is None


def test_REQ_INF_037_the_curve_is_the_DEFAULT_format_for_a_promoted_finding():
    """A single number with a curve hidden behind a click is a single number."""
    out = default_output_format({"tier": "CONFIRMED_OBSERVATIONAL"})
    assert out["format"] == "specification_curve"
    assert out["collapsed_by_default"] is False
    assert out["includes_choice_dashboard"] is True
    assert default_output_format({"tier": "DESCRIPTIVE"})["format"] == "summary"


def test_REQ_INF_038_a_discovery_count_is_reported_against_the_shuffled_null():
    """Twelve discoveries against a null median of three and a 95th of seven is a result; against
    a null median of eleven it is a Tuesday."""
    nulls = [1, 2, 3, 3, 4, 5, 6, 7, 7, 20]
    out = discovery_count_vs_null(12, nulls)
    assert out["null_median"] == pytest.approx(4.5), "sorted, (4+5)/2"
    assert out["null_p95"] == 20
    # The interesting half: 12 discoveries does NOT clear a null 95th percentile of 20, so the
    # run is not a result. An earlier version of this test asserted `is False or is True`, which
    # cannot fail and proved nothing.
    assert out["exceeds_null_p95"] is False
    assert discovery_count_vs_null(21, nulls)["exceeds_null_p95"] is True
    assert "shuffled data gives a median" in out["text"]
    with pytest.raises(PipelineViolation, match="REQ-INF-038"):
        discovery_count_vs_null(12, [])
