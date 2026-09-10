"""B8/B20 §A — the evidence ladder's contract (REQ-TIER-002..052).

Every other engine in this system references a tier. This is where one is assigned, where it may
not be changed, and what may be said at each rung.
"""
import pytest

from tools.engines.tier_contract import (ABSENT_SENTENCE, COVERAGE_FLOOR, EFSA_SCALE,
                                         NO_PROBABILITY, PARTIAL_SENTENCE,
                                         REQUIRED_FINDING_FIELDS, TIERS, TierViolation,
                                         assign_tier, candidate_edge_destination,
                                         check_causal_word, check_exploratory_copy,
                                         check_identifier, coverage_demotion, demote,
                                         effect_size, experimental_guard, finding_row,
                                         insufficient_response,
                                         may_ship_continuous_exploration, narration_write_guard,
                                         render_guard, render_insufficient, verbal_probability)


def test_REQ_TIER_002_a_tier_is_stored_with_what_makes_it_auditable():
    assert REQUIRED_FINDING_FIELDS == ("tier", "code_version", "n", "n_eff", "coverage")
    finding_row(tier="DESCRIPTIVE", code_version="v1", n=30, n_eff=12.1, coverage=0.9)
    with pytest.raises(TierViolation, match="REQ-TIER-002"):
        finding_row(tier="DESCRIPTIVE", code_version="v1", n=30, n_eff=12.1, coverage=None)


def test_REQ_TIER_003_the_narration_layer_may_never_write_the_tier():
    """If a narrator could set it, the strength of a claim would be decided by whichever
    component is best at producing confident prose — exactly backwards."""
    assert narration_write_guard("statistics", "tier")
    assert narration_write_guard("narration", "text")
    with pytest.raises(TierViolation, match="REQ-TIER-003"):
        narration_write_guard("narration", "tier")


def test_REQ_TIER_004_a_tier_mismatch_discards_the_PROSE_not_the_label():
    """The sentence was written for a tier the evidence does not support. Relabelling it leaves a
    CONFIRMED-shaped sentence flying an EXPLORATORY flag."""
    out = render_guard("CONFIRMED_OBSERVATIONAL", "EXPLORATORY",
                       rendered="Sleep drives your spending.",
                       template="Sleep and spend co-occurred on 12 days.", finding_id="F-1")
    assert out["used"] == "deterministic_template"
    assert out["tier"] == "EXPLORATORY"
    assert "drives" not in out["text"]
    assert out["rows"][0]["rule"] == "REQ-TIER-004"


def test_REQ_TIER_004_a_matching_tier_passes_the_prose_through():
    out = render_guard("EXPLORATORY", "EXPLORATORY", rendered="A generator flagged this.",
                       template="t")
    assert out["used"] == "model" and out["rows"] == ()


def test_REQ_TIER_010_counts_sums_means_and_regimes_are_DESCRIPTIVE():
    for kind in ("count", "sum", "mean", "trend", "regime_state", "seasonal_decomposition"):
        assert assign_tier({"kind": kind}) == "DESCRIPTIVE", kind


def test_REQ_TIER_011_a_candidate_edge_gets_a_register_row_and_NO_findings_row():
    """A findings row is what surfaces read. A candidate is not a finding."""
    d = candidate_edge_destination({"from": "a", "to": "b"})
    assert d["table"] == "hypothesis_register" and d["status"] == "CANDIDATE"
    assert d["findings_row"] is False


def test_REQ_TIER_015_016_EXPERIMENTAL_requires_the_system_s_own_randomizer():
    """No volume of observational data becomes an experiment, so the check is on the assignment
    MECHANISM, not on the sample size."""
    trial = {"randomizer_assigned": True, "prespecified_blocks_complete": True,
             "prespecified_primary_analysis_ran": True}
    assert assign_tier(trial) == "EXPERIMENTAL"
    assert assign_tier({**trial, "prespecified_blocks_complete": False}) == "INSUFFICIENT"
    assert assign_tier({"kind": "mean", "n": 100_000}) == "DESCRIPTIVE"


def test_REQ_TIER_016_an_observational_finding_labelled_EXPERIMENTAL_is_refused():
    assert experimental_guard({"tier": "CONFIRMED_OBSERVATIONAL"})
    with pytest.raises(TierViolation, match="REQ-TIER-016"):
        experimental_guard({"tier": "EXPERIMENTAL", "randomizer_assigned": False})


def test_REQ_TIER_021_caused_is_permitted_only_at_EXPERIMENTAL():
    """The one word whose misuse cannot be recovered by a qualifier in the next sentence."""
    assert check_causal_word("Caffeine caused the change.", "EXPERIMENTAL") == ()
    for tier in ("DESCRIPTIVE", "EXPLORATORY", "PROMOTED", "CONFIRMED_OBSERVATIONAL"):
        assert check_causal_word("Caffeine caused the change.", tier) == ("caused",), tier
    assert check_causal_word("Caffeine preceded the change.", "PROMOTED") == ()


def test_REQ_TIER_022_granger_cause_appears_nowhere():
    """Granger causality is about predictive precedence, not causation, and the name says
    otherwise — a column called granger_cause is read as causal by everyone downstream and by
    every model that sees the schema."""
    assert check_identifier("predictive_lead")
    stem = "gran" + "ger"
    tail = "cau" + "se"
    for bad in (f"{stem}_{tail}", f"{stem}{tail.title()}", f"{stem} {tail}",
                f"x_{stem}_{tail}_y"):
        with pytest.raises(TierViolation, match="REQ-TIER-022"):
            check_identifier(bad)


def test_REQ_TIER_022_the_repository_contains_no_granger_identifier():
    """The requirement says "anywhere in the codebase", so this checks the codebase."""
    import pathlib
    import re as _re
    root = pathlib.Path(__file__).resolve().parents[1]
    hits = []
    for f in list(root.glob("tools/**/*.py")) + list(root.glob("migrations/*.sql")):
        # Assembled so this test does not itself become the violation it detects.
        pattern = "gran" + "ger" + "[_ ]?" + "cau" + "se"
        for i, line in enumerate(f.read_text(errors="ignore").split("\n"), 1):
            if _re.search(pattern, line.lower()):
                hits.append(f"{f.name}:{i}")
    assert hits == [], hits


def test_REQ_TIER_024_an_effect_size_is_absolute_with_its_unit_named():
    """"18% lower" is unreadable without the base, and the base is exactly what a reader supplies
    from memory — usually wrongly."""
    assert effect_size(-22, "minutes")["text"] == "-22 minutes"
    with pytest.raises(TierViolation, match="REQ-TIER-024"):
        effect_size(-18, "minutes", of_outcome_pct=-18)
    with pytest.raises(TierViolation, match="REQ-TIER-024"):
        effect_size(-22, None)


def test_REQ_TIER_026_the_numeral_comes_first_and_the_efsa_term_follows():
    """Numeral first because the term is the part a reader remembers and the number is the part
    that constrains it; leading with the word lets the word do the work alone."""
    out = verbal_probability(92)
    assert out["term"] == "very likely" and out["text"] == "92% (very likely)"
    assert out["text"].index("92") < out["text"].index("very likely")
    assert verbal_probability(99.5)["term"] == "almost certain"
    assert verbal_probability(50)["term"] == "about as likely as not"
    assert verbal_probability(0.5)["term"] == "almost impossible"
    assert len(EFSA_SCALE) == 9


def test_REQ_TIER_027_no_probability_at_all_is_a_normal_return_value():
    out = verbal_probability(None)
    assert out["text"] == NO_PROBABILITY and out["numeric"] is None
    assert "0–100%" in out["text"]


def test_REQ_TIER_030_the_partial_form_states_the_estimate_and_all_four_numbers():
    r = insufficient_response("low_n_eff", point=-22, interval=[-40, -4], n=30, n_eff=9.1,
                              coverage=0.71, data_required="about 40 more paired days")
    assert r["form"] == "partial" and r["sentence"] == PARTIAL_SENTENCE
    assert (r["point"], r["n"], r["n_eff"], r["coverage"]) == (-22, 30, 9.1, 0.71)
    assert r["suppressed"] is False


def test_REQ_TIER_030_the_partial_form_refuses_to_omit_one_of_its_numbers():
    with pytest.raises(TierViolation, match="REQ-TIER-030"):
        insufficient_response("low_coverage", point=-22, interval=[-40, -4], n=30, n_eff=9.1,
                              coverage=None, data_required="more days")


def test_REQ_TIER_031_the_absent_form_names_the_missing_input_and_what_would_fix_it():
    r = insufficient_response("metric_absent", missing_input="hrv_sdnn_ms",
                              answerable_when="the Watch resumes recording HRV",
                              data_required="about 60 days once it does")
    assert r["form"] == "absent" and r["sentence"] == ABSENT_SENTENCE
    assert r["missing_input"] == "hrv_sdnn_ms"
    with pytest.raises(TierViolation, match="REQ-TIER-031"):
        insufficient_response("metric_absent", data_required="x")


def test_REQ_TIER_032_an_INSUFFICIENT_result_is_never_suppressed():
    """Suppressing a weak result looks like modesty and is not: it hides that the question was
    asked and that something was computed."""
    r = insufficient_response("sign_unstable", point=1, interval=[-1, 3], n=20, n_eff=6.0,
                              coverage=0.8, data_required="more days")
    assert r["suppressed"] is False and r["point"] == 1


def test_REQ_TIER_033_034_a_response_with_no_way_forward_is_rejected():
    with pytest.raises(TierViolation, match="REQ-TIER-033"):
        insufficient_response("low_n_eff", point=1, interval=[0, 2], n=20, n_eff=6.0,
                              coverage=0.8)
    out = render_insufficient({"form": "partial", "next": None})
    assert out["form"] == "absent" and "REQ-TIER-034" in out["rejected"]


def test_REQ_TIER_033_a_proposed_trial_satisfies_the_requirement_as_well_as_data():
    r = insufficient_response("no_adjustment_set", missing_input="an adjustment set",
                              answerable_when="a DAG is registered",
                              proposed_trial="12 weekly blocks of caffeine on/off")
    assert "randomized trial would answer it" in r["next"]


def test_REQ_TIER_044_a_demotion_needs_no_human_approval():
    """Requiring approval to LOWER a claim would leave overstated findings standing while the
    approval was pending — and the person whose approval is wanted is the person the overstated
    claim is addressed to."""
    out = demote({"tier": "CONFIRMED_OBSERVATIONAL"}, "PROMOTED", reason="negative control failed")
    assert out["tier"] == "PROMOTED" and out["human_approval_required"] is False
    with pytest.raises(ValueError):
        demote({"tier": "PROMOTED"}, "CONFIRMED_OBSERVATIONAL", reason="x")


def test_REQ_TIER_045_a_thin_adjustment_set_renders_a_confirmed_finding_INSUFFICIENT():
    """The adjustment set is what makes a confirmed finding confirmed. If the metrics doing the
    adjusting are half-missing, the finding is resting on a control that is not there."""
    f = {"tier": "CONFIRMED_OBSERVATIONAL", "id": "F-1"}
    out = coverage_demotion(f, adjustment_coverage={"steps": 0.9, "hrv_sdnn_ms": 0.31})
    assert out["tier"] == "INSUFFICIENT"
    assert out["insufficiency_reason"] == "low_coverage"
    assert out["thin_adjustment_metrics"] == ("hrv_sdnn_ms",)
    assert coverage_demotion(f, adjustment_coverage={"steps": COVERAGE_FLOOR})["tier"] == \
        "CONFIRMED_OBSERVATIONAL"


def test_REQ_TIER_045_a_lower_tier_finding_is_untouched_by_the_coverage_rule():
    f = {"tier": "PROMOTED"}
    assert coverage_demotion(f, adjustment_coverage={"x": 0.1}) == f


def test_REQ_TIER_051_the_label_surface_precedes_the_generation_that_feeds_it():
    """Ship the generator first and its output has nowhere labelled to go, so it lands on
    whatever surface exists — which is a surface built for findings."""
    blocked = may_ship_continuous_exploration(surface_acceptance_passed=False)
    assert blocked["allowed"] is False
    assert "precedes the generation" in blocked["reason"]
    assert may_ship_continuous_exploration(surface_acceptance_passed=True)["allowed"] is True


def test_REQ_TIER_052_a_confirmed_verb_inside_the_exploratory_vocabulary_is_refused():
    """The vocabulary itself has to be clean, not just the sentence: a confirmed-tier verb in the
    exploratory list would let the linter pass a sentence that reads as settled."""
    ok = ("a generator flagged", "candidate", "exploratory, not a finding", "may", "might")
    assert check_exploratory_copy("A generator flagged this; it may matter.", ok) == ()
    with pytest.raises(TierViolation, match="REQ-TIER-052"):
        check_exploratory_copy("x", ok + ("predicts",))


def test_REQ_TIER_052_a_confirmed_verb_in_the_SENTENCE_is_reported():
    ok = ("a generator flagged", "candidate", "may")
    assert check_exploratory_copy("Sleep predicts spend.", ok) == ("predicts",)


def test_the_ladder_itself_is_the_six_rungs_every_other_engine_references():
    assert TIERS == ("INSUFFICIENT", "DESCRIPTIVE", "EXPLORATORY", "PROMOTED",
                     "CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL")
