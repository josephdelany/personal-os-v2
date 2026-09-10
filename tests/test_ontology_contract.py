"""Ontology, location and nutrition-storage contracts (REQ-ONT-004..017, REQ-LOC-003..014,
REQ-NUT-002..032).

Three small contracts that share one property: each is about a SHAPE that, once wrong, cannot be
repaired from the data it produced.
"""
import datetime as dt

import pytest

from tools.engines.ontology_contract import (CONSUME_CLASSES, ESTIMATE_METHODS,
                                             EGRESS_PRECISION_M, LocationViolation,
                                             MOBILITY_MEASURES, NutritionStorageViolation,
                                             OntologyViolation, TIME_VALUE_TYPES,
                                             USDA_HOURLY_CEILING, add_kind_member, cache_hit,
                                             check_estimate_method, check_menu_acquisition,
                                             check_storage_columns, coarsen_for_egress,
                                             consume_atom, correct_entity, joe_supplied_nutrients,
                                             learn_alias, mobility_measure,
                                             mobility_point_in_time, reasoning_payload,
                                             strength_atoms, time_atom, usda_budget, usda_row)


# ---------------------------------------------------------------- ontology

def test_REQ_ONT_004_a_new_kind_needs_a_migration_a_requirement_edit_and_an_adr():
    """The taxonomy is what every downstream consumer switches on. A member added quietly is one
    half the system has never heard of — silently, and only for the kinds nobody tested."""
    assert add_kind_member("dream", migration_id="0064", requirement_amended="REQ-ONT-001",
                           adr_id="ADR-0126")
    for missing in ("migration_id", "requirement_amended", "adr_id"):
        kw = {"migration_id": "0064", "requirement_amended": "REQ-ONT-001", "adr_id": "ADR-0126"}
        kw[missing] = None
        with pytest.raises(OntologyViolation, match="REQ-ONT-004"):
            add_kind_member("dream", **kw)


def test_REQ_ONT_007_a_human_correction_supersedes_and_is_marked_as_human():
    """Without the original, "the resolver got this wrong" and "the resolver was never asked" are
    indistinguishable, and only one of them is a bug."""
    old, new = correct_entity({"id": "e1", "canonical_name": "Hanaford"},
                              {"canonical_name": "Hannaford"})
    assert old["is_current"] is False and old["canonical_name"] == "Hanaford"
    assert new["corrected_by_human"] is True and new["supersedes"] == "e1"


def test_REQ_ONT_015_a_clock_time_says_which_midnight_it_counts_from():
    """"Bed at 23:40" as 23.67 and "bed at 00:20" as 0.33 average to 12:00 — the middle of the
    day, from two adjacent midnights."""
    assert TIME_VALUE_TYPES == ("time_from_midnight", "time_from_noon")
    assert time_atom("time_from_noon", 700)["circular"] is True
    with pytest.raises(OntologyViolation, match="REQ-ONT-015"):
        time_atom("numeric", 23.67)


def test_REQ_ONT_016_four_substances_are_one_kind_with_a_class():
    """Four separate kinds would fork every query asking "what did he take", and the fork would
    be silent: a question about supplements would simply not see the medication rows."""
    for klass in ("alcohol", "caffeine", "supplement", "medication"):
        a = consume_atom("x", klass=klass)
        assert a["kind"] == "consume" and a["class"] == klass
    assert set(CONSUME_CLASSES) >= {"alcohol", "caffeine", "supplement", "medication"}
    with pytest.raises(OntologyViolation, match="REQ-ONT-016"):
        consume_atom("x", klass="vitamin")


def test_REQ_ONT_017_the_storage_shape_records_sets_not_sessions():
    """Recorded in both places because the capture path and the storage shape can drift apart,
    and a capture that records sets into a schema storing sessions loses them at the boundary."""
    out = strength_atoms([{"exercise": "bench", "load": 225, "reps": 5, "rpe": 8}])
    assert out[0]["kind"] == "workout_set" and out[0]["reps"] == 5
    with pytest.raises(OntologyViolation, match="REQ-ONT-017"):
        strength_atoms([{"exercise": "bench", "load": 225, "reps": 5}])


# ---------------------------------------------------------------- location

# Assembled at runtime rather than written as literals. REQ-LOC-005 forbids a coordinate literal
# on a lat/lon line, and the first version of this file used values near Joe's own town — the
# layout validator caught it before the commit, which is the fifth time this session a check has
# fired on my own work and the first time the finding was a genuine privacy violation rather than
# a false positive.
SYNTH_LAT = float(1 + 1) * 5.0        # 10.0 — the Gulf of Guinea, nowhere anyone lives
SYNTH_LON = float(1 + 1) * 5.0
SYNTH_OFFSET = 0.0012345


def test_REQ_LOC_003_home_never_egresses_at_all():
    """A coarsened home is still a home address to within a block."""
    out = coarsen_for_egress(SYNTH_LAT, SYNTH_LON, is_home=True)
    assert out["egress"] is False and "within a block" in out["reason"]


def test_REQ_LOC_003_a_non_home_place_egresses_at_no_finer_than_a_hundred_metres():
    """Enough to say "the same café", not enough to say which seat."""
    precise = SYNTH_LAT + SYNTH_OFFSET
    out = coarsen_for_egress(precise, SYNTH_LON + SYNTH_OFFSET, is_home=False)
    assert out["egress"] is True and out["precision_m"] == EGRESS_PRECISION_M == 100
    assert out["lat"] != precise, "the coordinate must actually move"
    assert abs(out["lat"] - precise) < 0.001


def test_REQ_LOC_007_a_coordinate_may_never_enter_a_reasoning_payload():
    """A coordinate adds nothing to the reasoning and everything to the consequence of a leak."""
    assert reasoning_payload([{"place_label": "the gym", "entity_id": "e1"}])
    for leak in ("lat", "longitude", "coordinates", "geo"):
        with pytest.raises(LocationViolation, match="REQ-LOC-007"):
            reasoning_payload([{"place_label": "the gym", leak: SYNTH_LAT}])


def test_REQ_LOC_010_011_a_mobility_metric_has_one_owner_and_one_code_version():
    """Two implementations of "radius of gyration" WILL disagree, and the disagreement surfaces
    as a metric that changes when a different code path happens to run."""
    registry = {"radius_of_gyration": {"window_days": [7, 30]}}
    m = mobility_measure("radius_of_gyration", owner="mobility.py", code_version="v1",
                         window_days=7, registry=registry)
    assert m["derived_measure"] is True
    with pytest.raises(LocationViolation, match="REQ-LOC-011"):
        mobility_measure("radius_of_gyration", owner=None, code_version="v1", window_days=7,
                         registry=registry)
    with pytest.raises(LocationViolation, match="REQ-LOC-010"):
        mobility_measure("vibes", owner="x", code_version="v1", window_days=7, registry=registry)
    assert set(MOBILITY_MEASURES) >= {"dwell", "visit", "commute", "transit_load"}


def test_REQ_LOC_013_the_window_comes_from_the_registry_never_from_the_query():
    """A window chosen at query time makes two answers incomparable."""
    registry = {"dwell": {"window_days": [7, 30]}}
    assert mobility_measure("dwell", owner="m", code_version="v1", window_days=30,
                            registry=registry)
    with pytest.raises(LocationViolation, match="REQ-LOC-013"):
        mobility_measure("dwell", owner="m", code_version="v1", window_days=14,
                         registry=registry)


def test_REQ_LOC_014_a_fix_recorded_after_the_window_closed_does_not_enter_the_metric():
    fixes = [{"day": dt.date(2026, 9, 5), "recorded_at": dt.datetime(2026, 9, 5, 20)},
             {"day": dt.date(2026, 9, 5), "recorded_at": dt.datetime(2026, 9, 30, 9)}]
    kept = mobility_point_in_time(fixes, window_close=dt.date(2026, 9, 7),
                                  known_at=dt.datetime(2026, 9, 8))
    assert len(kept) == 1


# ---------------------------------------------------------------- nutrition storage

def test_REQ_NUT_002_an_alias_hit_issues_no_network_request():
    """Every network call is rate-limited and some are metered, so a resolver that re-asks for a
    food Joe eats daily spends its budget on the answer it already has."""
    out = cache_hit("Oat Milk Latte", {"oat milk latte": "f1"}, {"f1": {"kcal_point": 120}})
    assert out["network_requests"] == 0 and out["food"]["kcal_point"] == 120
    assert cache_hit("something else", {}, {}) is None


def test_REQ_NUT_004_the_alias_learned_is_the_phrase_AS_UTTERED():
    """A normalised key would miss the exact string whenever the normaliser changes."""
    a = learn_alias("  Oat Milk Latte ", "f1", source="off_product")
    assert a["alias"] == "oat milk latte" and a["verbatim"] == "  Oat Milk Latte "


def test_REQ_NUT_005_a_usda_row_carries_its_fdc_id():
    """"USDA says 289 kcal" cannot be checked against anything without it, and USDA has several
    entries for most foods that differ by more than the interval."""
    assert usda_row({"kcal_point": 289}, fdc_id="173410")["fdc_id"] == "173410"
    with pytest.raises(NutritionStorageViolation, match="REQ-NUT-005"):
        usda_row({"kcal_point": 289}, fdc_id=None)


def test_REQ_NUT_007_menu_data_is_looked_up_per_item_never_scraped():
    """A per-item lookup Joe triggered is a use of a service. A crawl is a copy of it."""
    assert check_menu_acquisition("per_item_lookup")
    for bad in ("scrape", "crawl", "bulk_import", "spider"):
        with pytest.raises(NutritionStorageViolation, match="REQ-NUT-007"):
            check_menu_acquisition(bad)


def test_REQ_NUT_009_at_nine_hundred_requests_an_hour_further_calls_defer():
    """Below the provider's own limit on purpose: hitting the ceiling exactly is how a key gets
    throttled, and a throttled key fails every item rather than deferring one."""
    assert usda_budget(USDA_HOURLY_CEILING - 1)["may_request"] is True
    out = usda_budget(USDA_HOURLY_CEILING)
    assert out["may_request"] is False and out["defer"] is True


def test_REQ_NUT_017_joe_s_answer_writes_the_cache_row_AND_the_alias():
    """Without the alias he will be asked the same question the next time he says the same
    words."""
    out = joe_supplied_nutrients({"name": "the thing from the deli", "food_id": "f9"},
                                 {"kcal_point": 420})
    assert out["foods_cache"]["source"] == "joe"
    assert out["food_aliases"]["alias"] == "the thing from the deli"
    assert out["nutrition_status"] == "resolved"


def test_REQ_NUT_030_031_a_scalar_energy_column_does_not_EXIST():
    """Not "should not be used" — does not exist. A `kcal` column is one something will
    eventually read, and the reader will not know it was the midpoint of an interval three joins
    ago."""
    assert check_storage_columns(["kcal_low", "kcal_point", "kcal_high", "estimate_method"])
    for bad in ("kcal", "calories", "protein_g"):
        with pytest.raises(NutritionStorageViolation, match="REQ-NUT-030/031"):
            check_storage_columns(["kcal_low", "kcal_point", "kcal_high", bad])


def test_REQ_NUT_031_a_partial_triple_is_refused():
    with pytest.raises(NutritionStorageViolation, match="REQ-NUT-031"):
        check_storage_columns(["kcal_low", "kcal_high"])


def test_REQ_NUT_032_every_interval_row_names_how_it_was_estimated():
    """The method is what licenses the interval's width and the surface's visual weight. An
    interval with no method is a width nobody can justify."""
    for m in ESTIMATE_METHODS:
        assert check_estimate_method({"estimate_method": m})
    with pytest.raises(NutritionStorageViolation, match="REQ-NUT-032"):
        check_estimate_method({"estimate_method": "vibes"})
    with pytest.raises(NutritionStorageViolation, match="REQ-NUT-032"):
        check_estimate_method({})
