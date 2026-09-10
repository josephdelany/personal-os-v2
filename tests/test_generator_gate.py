"""B19 §F.1/§F.2 — generators generate, and the killed methods stay killed
(REQ-INF-400..413, 420..431).

A directed edge from a generator LOOKS like a finding. It is a hypothesis with an arrow drawn on
it, and most of these tests are about keeping those two apart.
"""
import pytest

from tools.engines.generator_gate import (DEFAULT_CI_TEST, GENERATOR_MIN_DAYS,
                                          GPDC_MAX_VARIABLES, GeneratorRefused, KILLED_METHODS,
                                          KilledMethod, MAX_BLOCK_VARIABLES,
                                          NONPARAMETRIC_MIN_DAYS, REFUSAL_STRING,
                                          TRANSFER_ENTROPY_MAX_VARIABLES, check_dag_learner,
                                          check_dependencies, check_imports, check_method,
                                          check_run, check_search_scope, check_transfer_entropy,
                                          corroboration_only, on_demand_outcome, prompt_payload,
                                          register_output, render_exploratory_surface,
                                          render_finding_surface)

NULL = {"discovery_count": 12, "null_median": 3, "null_p95": 7}


def test_REQ_INF_400_401_a_generator_output_goes_to_the_register_never_to_findings():
    out = register_output({"from": "a", "to": "b"}, transformation="detrend+deseasonalize",
                          null_calibration=NULL)
    assert out["table"] == "hypothesis_register" and out["status"] == "CANDIDATE"
    assert out["findings_row"] is False


def test_REQ_INF_409_a_candidate_records_the_transformation_applied():
    with pytest.raises(GeneratorRefused, match="REQ-INF-409"):
        register_output({}, transformation=None, null_calibration=NULL)


def test_REQ_INF_410_a_run_without_circular_shift_calibration_is_refused():
    """Without the null the discovery count has nothing to be compared against."""
    for missing in ("discovery_count", "null_median", "null_p95"):
        cal = {**NULL, missing: None}
        with pytest.raises(GeneratorRefused, match="REQ-INF-410"):
            register_output({}, transformation="detrend", null_calibration=cal)


def test_REQ_INF_403_a_candidate_on_a_finding_surface_refuses_AND_logs():
    """The log entry is what makes a leak visible rather than merely absent: a surface that
    quietly shows nothing looks identical to a surface with nothing to show."""
    out = render_finding_surface({"status": "CANDIDATE", "hypothesis_id": "H-1"})
    assert out["text"] == REFUSAL_STRING and out["rendered"] is False
    assert out["rows"][0]["reason"] == "candidate_leak"
    assert out["rows"][0]["table"] == "render_violations"


def test_REQ_INF_403_a_promoted_row_renders_on_the_finding_surface_normally():
    assert render_finding_surface({"status": "PROMOTED"})["rendered"] is True


def test_REQ_INF_402_the_same_row_renders_on_the_exploratory_surface_without_violation():
    """The row is not the problem; the surface is."""
    out = render_exploratory_surface({"status": "CANDIDATE"}, surface_proven=True)
    assert out["rendered"] is True and out["label"] == "EXPLORATORY"
    assert out["pushed"] is False, "exploratory output is never pushed at Joe"


def test_REQ_TIER_051_the_exploratory_surface_must_be_proven_before_it_renders():
    out = render_exploratory_surface({"status": "CANDIDATE"}, surface_proven=False)
    assert out["rendered"] is False and "REQ-TIER-051" in out["reason"]


def test_REQ_TIER_053_the_exploratory_surface_renders_candidates_and_nothing_else():
    out = render_exploratory_surface({"status": "PROMOTED"}, surface_proven=True)
    assert out["rendered"] is False


def test_REQ_INF_402_a_candidate_may_never_enter_a_language_layer_prompt():
    """The quietest of the three leaks and the worst: a model handed a candidate edge writes
    about it in the same voice it uses for a confirmed finding."""
    assert prompt_payload([{"status": "PROMOTED"}])
    with pytest.raises(GeneratorRefused, match="REQ-INF-402"):
        prompt_payload([{"status": "PROMOTED"}, {"status": "CANDIDATE"}])


def test_REQ_INF_404_a_generator_runs_on_blocks_of_at_most_twenty_variables():
    assert check_run(variables=list(range(MAX_BLOCK_VARIABLES)), well_covered_days=400)
    with pytest.raises(GeneratorRefused, match="REQ-INF-404"):
        check_run(variables=list(range(MAX_BLOCK_VARIABLES + 1)), well_covered_days=400)


def test_REQ_INF_405_below_two_hundred_days_no_generator_runs():
    """Below this a generator still returns edges; they are just wrong, and they arrive with a
    p-value. The floor exists because the method cannot refuse, so something outside it must."""
    assert check_run(variables=["a"], well_covered_days=GENERATOR_MIN_DAYS)
    with pytest.raises(GeneratorRefused, match="REQ-INF-405"):
        check_run(variables=["a"], well_covered_days=GENERATOR_MIN_DAYS - 1)


def test_REQ_INF_406_a_nonparametric_test_needs_five_hundred_days():
    for test in ("cmiknn", "cmisymb"):
        with pytest.raises(GeneratorRefused, match="REQ-INF-406"):
            check_run(variables=["a"], well_covered_days=NONPARAMETRIC_MIN_DAYS - 1,
                      ci_test=test)
        assert check_run(variables=["a"], well_covered_days=NONPARAMETRIC_MIN_DAYS, ci_test=test)


def test_REQ_INF_407_parcorr_is_the_default_and_gpdc_is_a_three_variable_subset():
    assert DEFAULT_CI_TEST == "parcorr"
    assert check_run(variables=list(range(GPDC_MAX_VARIABLES)), well_covered_days=400,
                     ci_test="gpdc")
    with pytest.raises(GeneratorRefused, match="REQ-INF-407"):
        check_run(variables=list(range(GPDC_MAX_VARIABLES + 1)), well_covered_days=400,
                  ci_test="gpdc")


def test_REQ_INF_412_an_on_demand_run_applies_every_floor_the_scheduled_run_would():
    """The requirement says so explicitly, so there is ONE function and `on_demand` changes
    nothing about the floors — it only adds the RULE-17 gate."""
    with pytest.raises(GeneratorRefused, match="REQ-INF-405"):
        check_run(variables=["a"], well_covered_days=10, on_demand=True)
    with pytest.raises(GeneratorRefused, match="REQ-INF-404"):
        check_run(variables=list(range(50)), well_covered_days=400, on_demand=True)


def test_REQ_INF_412_an_on_demand_run_is_gated_on_the_exploratory_surface():
    with pytest.raises(GeneratorRefused, match="REQ-TIER-051"):
        check_run(variables=["a"], well_covered_days=400, on_demand=True, surface_proven=False)
    assert check_run(variables=["a"], well_covered_days=400, on_demand=True,
                     surface_proven=True)["on_demand"] is True


def test_REQ_INF_413_an_on_demand_run_cannot_promote_or_trigger_confirmation():
    """The waiting clock is untouched, and the reason is structural: the confirmation job reads
    only observations at or after confirmation_data_from, set to now() at registration."""
    out = on_demand_outcome({"id": "r1"})
    assert out["findings_row"] is False
    assert out["may_promote"] is False and out["triggers_confirmation"] is False
    assert "pre-existing data cannot confirm" in out["note"]


def test_REQ_INF_408_411_a_var_family_edge_corroborates_and_never_promotes_alone():
    """Across 43 idiographic-network studies the median series length was 99, 8.8% tested
    normality, 11.6% evaluated stability and 7% were preregistered."""
    for method in ("var-lingam", "regularized_var", "graphical_var"):
        alone = corroboration_only({"source_method": method})
        assert alone["may_promote"] is False and "REQ-INF-408" in alone["reason"]
        both = corroboration_only({"source_method": method, "pcmci_also_produced": True})
        assert both["may_promote"] is True
    assert corroboration_only({"source_method": "pcmci+"})["may_promote"] is True


# ---------------------------------------------------------------- §F.2

def test_REQ_INF_420_428_every_killed_method_is_refused_by_name_with_its_requirement():
    for name, req in KILLED_METHODS.items():
        with pytest.raises(KilledMethod, match=req):
            check_method(name)
    assert check_method("pcmci+")


def test_REQ_INF_424_convergent_cross_mapping_is_refused_however_it_is_spelled():
    for spelling in ("convergent cross mapping", "convergent-cross-mapping",
                     "Convergent_Cross_Mapping"):
        with pytest.raises(KilledMethod, match="REQ-INF-424"):
            check_method(spelling)


def test_REQ_INF_425_transfer_entropy_is_capped_at_three_variables():
    assert check_transfer_entropy(TRANSFER_ENTROPY_MAX_VARIABLES)
    with pytest.raises(KilledMethod, match="REQ-INF-425"):
        check_transfer_entropy(TRANSFER_ENTROPY_MAX_VARIABLES + 1)


def test_REQ_INF_422_the_disqualifier_is_scale_non_invariance_not_the_family():
    """Varsortability exceeds 0.94 on standard benchmarks, so the recovered graph is largely an
    artifact of the variables' UNITS: change minutes to hours and the arrows move. A learner that
    IS scale-invariant is not caught, which is why the check asks about the property."""
    with pytest.raises(KilledMethod, match="REQ-INF-422"):
        check_dag_learner(continuous_optimization=True, scale_invariant=False)
    assert check_dag_learner(continuous_optimization=True, scale_invariant=True)
    assert check_dag_learner(continuous_optimization=False, scale_invariant=False)


def test_REQ_INF_429_a_forbidden_package_fails_the_build():
    """A method that is merely discouraged gets used by whoever is in a hurry."""
    assert check_dependencies(["numpy", "scipy"])
    for pkg in ("causalnex", "pyEDM", "skccm", "rEDM"):
        with pytest.raises(KilledMethod, match="REQ-INF-429"):
            check_dependencies(["numpy", pkg])


def test_REQ_INF_430_a_forbidden_import_fails_the_build_case_insensitively():
    assert check_imports("import numpy as np\nfrom scipy import stats\n")
    for src in ("from notears import fit\n", "import DYNOTEARS\n",
                "from x.knockoff import y\n", "import ccm\n"):
        with pytest.raises(KilledMethod, match="REQ-INF-430"):
            check_imports(src, where="m.py")


def test_REQ_INF_430_the_live_repository_imports_none_of_them():
    """The requirement is about the codebase, so this checks the codebase."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in root.glob("tools/**/*.py"):
        check_imports(f.read_text(errors="ignore"), where=str(f))


def test_REQ_INF_431_an_all_pairs_search_needs_both_guards():
    """Without the registry's direction constraints every pair is tested in both directions, and
    without the hierarchical FDR tree the family size is the square of the metric count."""
    assert check_search_scope(all_pairs=True, registry_constrained=True, hierarchical_fdr=True)
    assert check_search_scope(all_pairs=False, registry_constrained=False,
                              hierarchical_fdr=False)
    for kw in ({"registry_constrained": False}, {"hierarchical_fdr": False}):
        args = {"all_pairs": True, "registry_constrained": True, "hierarchical_fdr": True}
        args.update(kw)
        with pytest.raises(GeneratorRefused, match="REQ-INF-431"):
            check_search_scope(**args)


def test_REQ_INF_421_423_426_427_each_killed_method_is_named_with_its_own_requirement():
    """The block test above walks the whole map; these are the four whose IDs the map's own test
    name could not carry, and a requirement proven only inside a loop is one no audit can see."""
    assert KILLED_METHODS["dynotears"] == "REQ-INF-421"
    assert KILLED_METHODS["dsem"] == "REQ-INF-423"
    assert KILLED_METHODS["model_x_knockoffs"] == "REQ-INF-426"
    assert KILLED_METHODS["gimme"] == "REQ-INF-427"
    for name in ("dynotears", "dsem", "model_x_knockoffs", "gimme"):
        with pytest.raises(KilledMethod):
            check_method(name)


def test_REQ_INF_032_a_generator_run_is_calibrated_against_a_circular_shift_null():
    """The exposure series is rotated by a random offset, preserving each series' own
    autocorrelation — which a plain shuffle destroys, and a null built from shuffled data is
    easier to beat than the real one."""
    with pytest.raises(GeneratorRefused, match="REQ-INF-410"):
        register_output({}, transformation="detrend", null_calibration={})
    ok = register_output({}, transformation="detrend", null_calibration=NULL)
    assert ok["null_calibration"]["null_p95"] == 7
