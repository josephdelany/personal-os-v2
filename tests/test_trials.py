"""B19 §D — randomized micro-trials (REQ-INF-200..217).

Pure, so exercised exhaustively here. A trial is the only part of this system that asks Joe to
DO something, so almost every test below is about a refusal.
"""
import math

import pytest

from tools.engines.trials import (ALPHA, MAX_DEVIATION_RATE, MIN_POWER, Refusal, analyse,
                                  assign_blocks, blocks_required, detectable_effect,
                                  deviation_rate, effective_n, power, propose, result_tier,
                                  seed_for)


def test_REQ_INF_207_power_matches_the_closed_form_for_a_balanced_two_arm_contrast():
    """Checked against the formula by hand rather than against the implementation: with 12
    blocks the SE of the arm difference is sqrt(4/12)=0.577 SD, so an 0.8 SD effect sits 1.386
    SE from zero and power is Phi(1.386-1.96), about 0.28."""
    se = math.sqrt(4.0 / 12)
    assert se == pytest.approx(0.5774, abs=1e-4)
    assert power(12, 0.8) == pytest.approx(0.283, abs=0.005)
    assert power(2, 0.0) == 0.0, "a zero effect has no power to detect"


def test_REQ_INF_215_autocorrelation_lowers_power_rather_than_being_ignored():
    """Contiguous blocks share a boundary and a slow trend. Treating 12 blocks as 12
    independent observations inflates power at planning AND confidence at analysis — the same
    error twice, both times in the direction that flatters the trial."""
    assert power(12, 0.8, rho=0.3) < power(12, 0.8, rho=0.0)
    assert effective_n(12, 0.3) == pytest.approx(12 * 0.7 / 1.3)
    assert effective_n(12, 0.0) == 12


def test_REQ_INF_208_a_personal_trial_needs_a_large_effect_and_the_refusal_says_so():
    """The sobering arithmetic, stated rather than hidden: twelve two-week blocks can only
    detect about 1.6 SD at 80% power, and a 0.5 SD effect would need over a hundred blocks. Most
    proposals SHOULD be refused, and a system that quietly accepted them would spend Joe's
    compliance on trials that could not have seen anything."""
    assert detectable_effect(12) == pytest.approx(1.617, abs=0.01)
    assert blocks_required(0.5) == 126


def test_REQ_INF_208_an_underpowered_proposal_is_refused_with_both_counter_offers():
    """A refusal that only says "not enough power" leaves Joe with nothing to decide. It must
    carry the duration that WOULD work and the effect the requested duration COULD see."""
    r = propose("caffeine_mg", "sleep_minutes", block_days=7, n_blocks=6, mde_sd=0.4,
                role="lever")
    assert isinstance(r, Refusal) and r.reason == "underpowered"
    assert r.required_blocks and r.required_blocks > 6
    assert r.detectable_effect and r.detectable_effect > 0.4
    assert "0.80 is the floor" in r.detail


def test_REQ_INF_206_a_trial_shorter_than_six_weeks_is_refused_with_the_block_count_needed():
    """Below six weeks the result cannot reach EXPERIMENTAL, so running it buys a tier the
    observational path already offers at no cost to Joe."""
    r = propose("caffeine_mg", "sleep_minutes", block_days=7, n_blocks=4, mde_sd=3.0,
                role="lever")
    assert isinstance(r, Refusal) and r.reason == "below_minimum_duration"
    assert r.required_blocks == 6


def test_REQ_INF_203_a_block_no_longer_than_the_washout_is_refused():
    """Each block would begin before the previous exposure wore off, so the arms bleed together
    and the contrast is diluted toward zero — a bias TOWARD the null, which reads as a clean
    negative result rather than as a broken design."""
    r = propose("caffeine_mg", "sleep_minutes", block_days=3, n_blocks=20, mde_sd=3.0,
                washout_days=3, role="lever")
    assert isinstance(r, Refusal) and r.reason == "block_shorter_than_washout"


def test_REQ_INF_216_an_exposure_that_is_not_a_lever_is_never_randomised():
    """Randomising something Joe only observes would assign an arm nobody can comply with."""
    for role in ("context", None):
        r = propose("weather_temp", "sleep_minutes", block_days=7, n_blocks=12, mde_sd=3.0,
                    role=role)
        assert isinstance(r, Refusal) and r.reason == "exposure_is_not_a_lever"


def test_REQ_INF_217_a_declined_trial_is_not_re_proposed_for_seven_days():
    """Proposed, not imposed. Re-asking inside a week is nagging, and a system that nags gets
    ignored wholesale rather than declined per trial."""
    kw = dict(block_days=7, n_blocks=12, mde_sd=3.0, role="lever")
    r = propose("caffeine_mg", "sleep_minutes", declined_days_ago=3, **kw)
    assert isinstance(r, Refusal) and r.reason == "declined_recently"
    assert not isinstance(propose("caffeine_mg", "sleep_minutes",
                                  declined_days_ago=7, **kw), Refusal)


def test_REQ_INF_200_201_207_an_accepted_proposal_carries_every_registered_field():
    """REQ-INF-201 requires the COMPLETE row before the first assignment, and REQ-INF-213
    forbids changing the outcome or method afterwards. A trial that has to be edited after it
    starts was not thought through, and the register cannot express the edit."""
    plan = propose("caffeine_mg", "sleep_minutes", block_days=7, n_blocks=12, mde_sd=3.0,
                   role="lever")
    assert not isinstance(plan, Refusal)
    assert plan["analysis_method"] == "itt_block_means_hac"
    assert plan["primary_outcome_metric"] == "sleep_minutes"
    assert plan["power"] >= MIN_POWER
    assert plan["weeks"] == 12.0


def test_REQ_INF_202_the_assignment_is_stable_across_processes():
    """Python salts hash() per process, so a hash()-seeded sequence would differ on a rerun —
    and an assignment that changes when you look at it again is not a randomisation, it is a
    rewrite of history."""
    assert seed_for("trial-1") == seed_for("trial-1")
    assert seed_for("trial-1") != seed_for("trial-2")
    assert assign_blocks("trial-1", 12) == assign_blocks("trial-1", 12)
    assert assign_blocks("trial-1", 12) != assign_blocks("trial-2", 12)


def test_REQ_INF_203_arms_are_balanced_and_not_alternating():
    """ABABAB is perfectly confounded with any weekly or fortnightly rhythm, and Joe's life has
    several — pay dates, weekends, a training split."""
    arms = assign_blocks("trial-1", 12)
    assert arms.count("A") == 6 and arms.count("B") == 6, "balanced first"
    assert arms != ["A", "B"] * 6, "and not an alternation"
    odd = assign_blocks("trial-odd", 11)
    assert abs(odd.count("A") - odd.count("B")) == 1, "as balanced as an odd count allows"


def test_REQ_INF_202_a_trial_needs_two_arms():
    with pytest.raises(ValueError, match="at least two blocks"):
        assign_blocks("t", 1)


def test_REQ_INF_214_experimental_requires_all_three_conditions():
    """Every planned block completed, deviation at or below 20%, and the pre-specified analysis
    actually run. Any one missing gives INSUFFICIENT."""
    ok = result_tier(12, 12, 84, 8, analysis_ran=True, blinded=False)
    assert ok["tier"] == "EXPERIMENTAL", ok
    for kw in (dict(n_blocks_completed=10), dict(deviating_days=30),
               dict(analysis_ran=False)):
        args = dict(n_blocks_planned=12, n_blocks_completed=12, assigned_days=84,
                    deviating_days=8, analysis_ran=True, blinded=False)
        args.update(kw)
        assert result_tier(**args)["tier"] == "INSUFFICIENT", kw


def test_REQ_INF_211_a_failed_randomisation_is_not_demoted_to_an_observational_tier():
    """A half-finished randomisation is not an observational study — it is a randomisation that
    failed, and CONFIRMED_OBSERVATIONAL would credit it with a design it did not achieve."""
    r = result_tier(12, 12, 84, 40, analysis_ran=True, blinded=False)
    assert r["tier"] == "INSUFFICIENT"
    assert r["tier"] != "CONFIRMED_OBSERVATIONAL"
    assert "48% of assigned days deviated" in r["reasons"][0]


def test_REQ_INF_205_an_unblinded_trial_states_the_impossibility_in_its_result():
    """Not a footnote. An unblinded behavioural trial can move its own outcome through
    expectation alone, and the reader must be told at the point of reading."""
    r = result_tier(12, 12, 84, 4, analysis_ran=True, blinded=False)
    assert "expectation could contribute" in r["note"]
    blinded = result_tier(12, 12, 84, 4, analysis_ran=True, blinded=True)
    assert "expectation could contribute" not in blinded["note"]


def test_REQ_INF_210_itt_keeps_deviating_blocks_and_per_protocol_is_labelled_secondary():
    """Dropping deviating blocks is the substitution that makes adherence look like efficacy:
    the days Joe complied are the days he felt able to, and those differ from the rest in ways
    the exposure did not cause."""
    blocks = [("A", 10.0, False), ("A", 11.0, False), ("A", 30.0, True),
              ("B", 20.0, False), ("B", 21.0, False), ("B", 22.0, False)]
    itt = analyse(blocks)
    pp = analyse(blocks, per_protocol=True)
    assert itt["analysis"] == "itt" and itt["n_blocks"] == 6
    assert pp["analysis"] == "per_protocol" and pp["n_blocks"] == 5
    assert itt["delta"] != pp["delta"], "the deviating block must actually change the estimate"
    assert itt["label"].startswith("PRIMARY")
    assert pp["label"].startswith("SECONDARY")
    assert "not an unbiased estimate" in pp["label"]
    assert itt["deviating_blocks"] == 1


def test_REQ_INF_210_a_contrast_needs_two_blocks_in_each_arm():
    r = analyse([("A", 1.0, False), ("B", 2.0, False), ("B", 3.0, False)])
    assert isinstance(r, Refusal) and r.reason == "too_few_blocks_per_arm"


def test_REQ_INF_211_the_deviation_threshold_is_a_proportion_not_a_count():
    assert deviation_rate(84, 17) == pytest.approx(17 / 84)
    assert deviation_rate(0, 0) == 0.0
    assert MAX_DEVIATION_RATE == 0.20


def test_REQ_INF_204_205_blinding_is_a_physical_question_not_a_matter_of_effort():
    """Most of Joe's exposures are behavioural — he knows whether he had caffeine. A supplement in
    an identical capsule can be blinded, and where it CAN be it is not optional: an unblinded
    supplement trial measures the supplement plus his expectation of it, and the expectation is
    the larger of the two often enough to matter."""
    from tools.engines.trials import blinding
    b = blinding("vitamin_d_iu", admits_indistinguishable_placebo=True)
    assert b["blinded"] is True and b["until"] == "trial_completes"
    assert "expectation" in b["note"]

    u = blinding("caffeine_mg", admits_indistinguishable_placebo=False)
    assert u["blinded"] is False
    assert "no physically indistinguishable placebo" in u["impossibility"]


def test_REQ_INF_212_a_deviation_breach_notifies_ONCE_and_offers_a_shorter_block():
    """A shorter block is the right offer rather than "try harder": a 20% deviation rate usually
    means the block length does not fit Joe's life, and the fix is the design rather than the
    discipline. Repeating it would make a design problem feel like a personal one."""
    from tools.engines.trials import on_deviation_threshold
    out = on_deviation_threshold({}, deviation_rate=0.35, already_notified=False, block_days=14)
    assert out["notify"] is True and out["repeat"] is False
    assert out["offer"]["proposed_block_days"] == 7
    assert "may fit better" in out["text"]
    assert on_deviation_threshold({}, deviation_rate=0.35, already_notified=True,
                                  block_days=14) is None
    assert on_deviation_threshold({}, deviation_rate=0.10, already_notified=False,
                                  block_days=14) is None
