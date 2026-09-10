"""B9 §C/§G.1 — pre-registration as a database constraint (REQ-INF-100..114, 500..508).

The difference between a discovery and a story is entirely a matter of WHEN the claim was written
down.
"""
import datetime as dt

import pytest

from tools.engines.preregistration import (ConfirmationAborted, E_VALUE_FLOOR,
                                           INFERENCE_INTERFACES, PreregistrationViolation,
                                           REGISTER_FIELDS, check_interface,
                                           confirmation_ceiling, confirmation_family,
                                           confirmation_rows, feature_snapshot_hash,
                                           future_exposure_check, include_new_metric,
                                           ingest_guard, legal_specifications,
                                           negative_control_battery, no_imputation,
                                           promote_to_registered, refute, register,
                                           revise_observation, hypotheses_from_registry)

NOW = dt.datetime(2026, 9, 1, 12, 0)
HYP = {"hypothesis_id": "H-1", "exposure_metric": "caffeine_mg", "outcome_metric": "sleep_minutes",
       "lag_days": 0, "direction": "negative", "transformation": "raw",
       "adjustment_set": ["dow"], "test_statistic": "hac_ols",
       "resolution_rule": "beta < 0 and q < 0.10"}


def test_REQ_INF_100_every_analytic_choice_is_fixed_before_confirming_data_exists():
    """Each of these can be chosen after seeing the data, and each choice is defensible on its
    own. Choosing all of them after the fact is how a null result becomes a finding without
    anybody lying."""
    assert set(REGISTER_FIELDS) >= {"lag_days", "direction", "transformation", "adjustment_set",
                                    "test_statistic"}
    with pytest.raises(PreregistrationViolation, match="REQ-INF-100"):
        register(**{k: v for k, v in {**HYP, "preregistered_at": NOW,
                                      "confirmation_data_from": NOW, "status": "PROMOTED"}.items()
                    if k != "lag_days"})


def test_REQ_INF_101_both_clocks_are_set_to_now_at_promotion():
    r = promote_to_registered(HYP, now=NOW)
    assert r["preregistered_at"] == NOW and r["confirmation_data_from"] == NOW
    assert r["status"] == "PROMOTED"


def test_REQ_INF_102_confirmation_data_may_not_predate_the_registration():
    """Confirming data that predates the registration is the data the hypothesis was mined
    from."""
    with pytest.raises(PreregistrationViolation, match="REQ-INF-102"):
        register(**{**HYP, "preregistered_at": NOW, "status": "PROMOTED",
                    "confirmation_data_from": NOW - dt.timedelta(days=1)})


def test_REQ_INF_104_both_clocks_filter_the_confirmation_window():
    rows = [
        {"subject_day": dt.date(2026, 9, 5), "ingested_at": NOW + dt.timedelta(days=5)},
        {"subject_day": dt.date(2026, 8, 1), "ingested_at": NOW + dt.timedelta(days=5)},
    ]
    kept = confirmation_rows(rows, confirmation_data_from=NOW)
    assert len(kept) == 1 and kept[0]["subject_day"] == dt.date(2026, 9, 5)


def test_REQ_INF_105_a_late_arriving_old_row_ABORTS_the_confirmation():
    """A row about last Tuesday that arrived today is not post-registration data — it is old data
    that showed up late, and a backfill can deliver thousands at once. Filtering on subject_day
    alone would let a single import silently supply the entire confirmation window."""
    rows = [{"subject_day": dt.date(2026, 9, 5), "ingested_at": NOW - dt.timedelta(days=1)}]
    with pytest.raises(ConfirmationAborted, match="REQ-INF-105"):
        confirmation_rows(rows, confirmation_data_from=NOW)


def test_REQ_INF_106_the_confirmation_family_size_is_persisted():
    """Two runs of different sizes produce different q-values from identical p-values, and
    without the stored size nobody can tell which one they are looking at."""
    f = confirmation_family([HYP, {**HYP, "hypothesis_id": "H-2"}], run_id="r1")
    assert f["family_size"] == 2 and f["persisted"] is True
    assert f["method"] == "benjamini_hochberg"


def test_REQ_INF_110_nothing_is_imputed_and_missingness_is_modelled():
    """An imputed value is indistinguishable from a measured one once it is in the matrix, and
    the imputation model's assumptions become the finding's assumptions without appearing
    anywhere in its provenance."""
    out = no_imputation([1.0, None, 3.0])
    assert out["imputed"] is False and out["n_missing"] == 1
    assert out["values"][1] is None
    assert out["missingness_modelled_explicitly"] is True


def test_REQ_INF_111_a_refutation_is_surfaced_rather_than_deleted():
    """A register that quietly drops its failures reports a success rate of 100% and means
    nothing. The refutations are the only evidence the gate does anything at all."""
    out = refute(HYP, reason="opposite sign at q < 0.10")
    assert out["status"] == "REFUTED"
    assert out["surfaced_to_joe"] is True and out["deleted"] is False


def test_REQ_INF_112_a_low_e_value_or_no_adjustment_set_caps_the_tier_at_PROMOTED():
    """The E-value at the limit nearest the null is the honest question: how strong would an
    unmeasured confounder have to be to explain this away? Below 1.5, "not very"."""
    assert confirmation_ceiling(e_value_at_limit=2.0,
                                has_minimal_adjustment_set=True)["max_tier"] == \
        "CONFIRMED_OBSERVATIONAL"
    low = confirmation_ceiling(e_value_at_limit=E_VALUE_FLOOR - 0.01,
                               has_minimal_adjustment_set=True)
    assert low["max_tier"] == "PROMOTED" and "explain this away" in low["reason"]
    none_set = confirmation_ceiling(e_value_at_limit=3.0, has_minimal_adjustment_set=False)
    assert none_set["max_tier"] == "PROMOTED"
    assert confirmation_ceiling(e_value_at_limit=None,
                                has_minimal_adjustment_set=True)["max_tier"] == "PROMOTED"


def test_REQ_INF_113_the_snapshot_hash_covers_the_whole_specification():
    """A hash over a description that omits a filter is a hash that certifies the wrong matrix."""
    a = feature_snapshot_hash({"metrics": ["a", "b"], "window": [1, 2], "filter": "x"})
    b = feature_snapshot_hash({"metrics": ["a", "b"], "window": [1, 2], "filter": "y"})
    assert a != b, "a changed filter must change the hash"
    assert a == feature_snapshot_hash({"window": [1, 2], "filter": "x", "metrics": ["a", "b"]}), \
        "key order must not"


def test_REQ_INF_114_a_revision_is_a_new_row_never_an_update():
    """The old row is what makes "what did the system believe last Tuesday" answerable at all."""
    old, new = revise_observation({"id": 1, "value": 10, "is_current": True, "source_rev": 3}, 12)
    assert old["is_current"] is False and old["value"] == 10
    assert new["is_current"] is True and new["value"] == 12 and new["source_rev"] == 4


# ---------------------------------------------------------------- §G.1

def test_REQ_INF_500_the_hypothesis_set_comes_from_the_registry_not_a_hardcoded_list():
    """A hardcoded list stops matching the data the first time a metric is added, and the
    mismatch is silent — the search simply never looks at the new metric."""
    registry = {"a": {}, "b": {}}
    assert hypotheses_from_registry(registry, [("a", "b"), ("a", "ghost")]) == (("a", "b"),)


def test_REQ_INF_501_a_new_metric_joins_the_next_scheduled_search_automatically():
    out = include_new_metric({}, "new_metric", active_since=dt.date(2026, 9, 1))
    assert set(out["new_metric"]["joins"]) == {"search", "regime_model", "coverage_report"}
    assert out["new_metric"]["at"] == "next_scheduled_run"


def test_REQ_INF_502_an_observation_with_no_registry_row_is_REFUSED():
    """Not stored-and-flagged: refused. A metric with no registry row has no unit, no state
    class, no plausible range and no staleness rule — and the row would sit there looking like
    data."""
    assert ingest_guard("steps", {"steps": {}})
    with pytest.raises(PreregistrationViolation, match="REQ-INF-502"):
        ingest_guard("mystery", {"steps": {}})


def test_REQ_INF_503_only_the_metric_s_declared_transforms_may_be_used():
    """A log transform is meaningful for a count and meaningless for a signed z-score, so the
    legal set is declared once beside the metric rather than chosen per analysis."""
    registry = {"steps": {"legal_transforms": ["raw", "log1p"]}}
    assert legal_specifications("steps", registry, ["raw", "log1p"]) == ("raw", "log1p")
    with pytest.raises(PreregistrationViolation, match="REQ-INF-503"):
        legal_specifications("steps", registry, ["raw", "boxcox"])


def test_REQ_INF_504_the_inference_layer_reaches_storage_through_exactly_three_interfaces():
    """A component that reads a table directly can see a column the panel deliberately does not
    expose — a raw row, an un-superseded value, a coordinate."""
    assert INFERENCE_INTERFACES == ("f_daily_panel", "v_metric_tree", "v_coverage")
    for name in INFERENCE_INTERFACES:
        assert check_interface(name)
    for name in ("core.atoms", "analysis.panel", "raw_captures"):
        with pytest.raises(PreregistrationViolation, match="REQ-INF-504"):
            check_interface(name)


def test_REQ_INF_506_507_a_fired_negative_control_suppresses_the_WHOLE_RUN():
    """Not just the offending finding. A negative control that fires means the pipeline is
    finding effects where there cannot be any, and there is no reason to believe the other
    findings from that run are different in kind."""
    registry = {"real": {}, "nc_1": {"is_negative_control": True},
                "nc_2": {"is_negative_control": True}}
    out = negative_control_battery(registry, effects={"nc_1": 0.4, "nc_2": 0.01}, threshold=0.3)
    assert out["passed"] is False and out["fired"] == ("nc_1",)
    assert out["suppress_entire_run"] is True

    clean = negative_control_battery(registry, effects={"nc_1": 0.01, "nc_2": 0.02},
                                     threshold=0.3)
    assert clean["passed"] is True and clean["suppress_entire_run"] is False
    assert clean["controls_run"] == ("nc_1", "nc_2"), "run on EVERY promotion attempt"


def test_REQ_INF_508_an_effect_surviving_a_FUTURE_shifted_exposure_is_an_artifact():
    """If tomorrow's caffeine predicts today's sleep, the association is not caffeine acting on
    sleep — it is something slower moving both, or a shared trend nobody removed."""
    bad = future_exposure_check(p_future=0.001)
    assert bad["artifact_detected"] is True and "artifact" in bad["verdict"]
    good = future_exposure_check(p_future=0.6)
    assert good["artifact_detected"] is False
    assert future_exposure_check(p_future=None)["ran"] is False
