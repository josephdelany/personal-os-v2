"""B12 — nutrition resolution (REQ-NUT §D/§E; ADR-0056).

Every fixture is synthetic. Nothing reaches the network: the source-API path takes an explicit
transport, and these tests exercise the deterministic half — the cache, the interval widths and
the ABV→ethanol conversion — which is where the numbers actually come from.
"""
import datetime as dt
import json
import os

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import nutrition

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from real migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_nut_pytest"
OPS = "ops_nut_pytest"
CONFIG = "config_nut_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")


def world(cur):
    cur.execute(f"CREATE SCHEMA {CORE}")
    cur.execute(f"CREATE SCHEMA {OPS}")
    cur.execute(f"CREATE SCHEMA {CONFIG}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    # config.strings is created by 0047 in production; the two rows 0050 seeds are what matter.
    cur.execute(f"""CREATE TABLE {CONFIG}.strings (
        key TEXT PRIMARY KEY, value TEXT NOT NULL, note TEXT)""")
    body = _real_migration(CORE, OPS).replace("config.", f"{CONFIG}.")
    from tools.run_migration import split_statements
    for stmt in split_statements(body):
        cur.execute(stmt)
    return cur


def _real_migration(core, ops):
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    return (root / "migrations" / "0050_nutrition.sql").read_text() \
        .replace("__CORE__", core).replace("__OPS__", ops)


def cache_food(cur, name, source, nutrients, serving_g=None, brand=None):
    cur.execute(f"""INSERT INTO {CORE}.foods_cache
        (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)""",
        (name, source, name, brand, json.dumps(nutrients), serving_g))


# ------------------------------------------------------------------ interval widths

def test_REQ_NUT_035_to_040_the_width_comes_from_the_registered_method(sql_connection):
    """RULE-08: the interval width is a function of how the value was obtained.

    A single kcal number is a lie about precision — text-only LLM recall carries 652 kcal MAE.
    The widths live in a table because RULE-00 forbids quietly editing a threshold, and this
    reads them from it rather than restating them.
    """
    cur = world(sql_connection.cursor())
    widths = nutrition.interval_widths(cur, CONFIG)

    assert widths["labelled"] == (0.90, 1.10)          # REQ-NUT-036
    assert widths["portion_table"] == (0.80, 1.20)     # REQ-NUT-037
    assert widths["weighed"] == (0.90, 1.10)           # REQ-NUT-035 / ADR-0005
    assert widths["photo_estimate"] == (0.75, 1.60)    # REQ-NUT-038

    lo, pt, hi = nutrition.apply_width(500, "labelled", widths)
    assert (lo, pt, hi) == (450.0, 500.0, 550.0)
    assert lo <= pt <= hi                              # REQ-NUT-034
    sql_connection.rollback()


def test_REQ_NUT_039_the_photo_interval_is_asymmetric_in_the_documented_direction(sql_connection):
    """The bias is systematic UNDER-estimation, so the interval must be wider ABOVE.

    A symmetric ±40% was considered and rejected: it encodes the wrong shape of error and reads
    as more careful than it is.
    """
    cur = world(sql_connection.cursor())
    widths = nutrition.interval_widths(cur, CONFIG)
    lo, pt, hi = nutrition.apply_width(1000, "photo_estimate", widths)
    assert (lo, pt, hi) == (750.0, 1000.0, 1600.0)
    assert (hi - pt) > (pt - lo), "the interval must be wider above the point than below"
    sql_connection.rollback()


def test_REQ_NUT_040_an_unresolved_item_has_no_value_at_all(sql_connection):
    """A gap stays a gap. A zero would be a claim that the item had no calories."""
    cur = world(sql_connection.cursor())
    widths = nutrition.interval_widths(cur, CONFIG)
    assert nutrition.apply_width(None, "labelled", widths) == (None, None, None)

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "sphinx casserole", grams=200, schema=CORE, config=CONFIG)
    assert e.value.item_text == "sphinx casserole"
    assert any(t["source"] == "foods_cache" and t["hit"] is False for t in e.value.tried)
    sql_connection.rollback()


def test_REQ_NUT_042_a_mixed_meal_takes_the_widest_method(sql_connection):
    """A meal is only as well known as its least well known item.

    Taking the narrowest — or the commonest — would make a photo-estimated side dish disappear
    into a labelled main.
    """
    cur = world(sql_connection.cursor())
    widths = nutrition.interval_widths(cur, CONFIG)
    assert nutrition.widest_method(["labelled", "photo_estimate"], widths) == "photo_estimate"
    assert nutrition.widest_method(["labelled", "portion_table"], widths) == "portion_table"
    assert nutrition.widest_method(["labelled"], widths) == "labelled"
    assert nutrition.widest_method(["nonsense"], widths) is None
    sql_connection.rollback()


# ------------------------------------------------------------------ cache-first and precedence

def test_REQ_NUT_012_resolution_reads_the_cache_and_scales_by_grams(sql_connection):
    cur = world(sql_connection.cursor())
    cache_food(cur, "big mac", "usda_branded",
               {"kcal": 257.0, "protein_g": 12.5, "fat_g": 14.0}, serving_g=219.0)

    r = nutrition.resolve_item(cur, "big mac", grams=219, schema=CORE, config=CONFIG)
    lo, pt, hi = r["nutrients"]["kcal"]
    assert round(pt) == 563                            # 257 per 100 g x 2.19
    assert lo < pt < hi
    assert r["method"] == "weighed", r                 # a stated weight, generic composition
    assert r["grams"] == 219.0


def test_RULE_10_joes_own_portion_outranks_every_source(sql_connection):
    """A correction is permanent: nothing downstream re-guesses it (§D.4)."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "porridge", "usda_foundation", {"kcal": 68.0}, serving_g=250.0)
    cur.execute(f"""INSERT INTO {CORE}.portions (canonical_name, grams, source)
                    VALUES ('porridge', 400, 'usda')""")
    cur.execute(f"""INSERT INTO {CORE}.portions (canonical_name, grams, source)
                    VALUES ('porridge', 320, 'joe')""")

    r = nutrition.resolve_item(cur, "porridge", schema=CORE, config=CONFIG)
    assert r["grams"] == 320.0, "Joe's portion must win"
    assert r["method"] == "joe"
    assert round(r["nutrients"]["kcal"][1]) == 218      # 68 per 100 g x 3.2


def test_REQ_NUT_040_a_food_with_no_portion_and_no_weight_is_unresolved(sql_connection):
    """Knowing the composition is not knowing the quantity. Inventing a serving would be the
    plausible value RULE-06 forbids."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "lentil stew", "usda_foundation", {"kcal": 90.0})   # no serving_g
    with pytest.raises(nutrition.Unresolved):
        nutrition.resolve_item(cur, "lentil stew", schema=CORE, config=CONFIG)


def test_REQ_NUT_012_a_serving_count_uses_the_cached_serving_size(sql_connection):
    cur = world(sql_connection.cursor())
    cache_food(cur, "protein bar", "off_product", {"kcal": 380.0, "protein_g": 30.0},
               serving_g=60.0)
    r = nutrition.resolve_item(cur, "protein bar", servings=2, schema=CORE, config=CONFIG)
    assert r["grams"] == 120.0
    assert round(r["nutrients"]["kcal"][1]) == 456
    assert r["method"] == "off_product"


def test_REQ_NUT_033_an_absent_nutrient_stays_absent(sql_connection):
    """A source that does not report fibre does not mean zero fibre."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "steak", "usda_foundation", {"kcal": 271.0, "protein_g": 25.0},
               serving_g=200.0)
    r = nutrition.resolve_item(cur, "steak", grams=200, schema=CORE, config=CONFIG)
    assert set(r["nutrients"]) == {"kcal", "protein_g"}
    assert "fiber_g" not in r["nutrients"]


# ------------------------------------------------------------------ drink -> ethanol

def test_REQ_NUT_066_ethanol_is_computed_deterministically_from_volume_and_abv(sql_connection):
    """RULE-09: the model never emits a gram. It supplies the name and the volume; this
    computes the ethanol, and does not accept one as an argument."""
    cur = world(sql_connection.cursor())
    # A 355 ml can at 5.0% ABV: 355 x 0.05 x 0.789 = 14.005 g, about one standard drink.
    r = nutrition.resolve_drink(cur, volume_ml=355, abv_percent=5.0, abv_from_label=True,
                                schema=CORE, config=CONFIG)
    lo, pt, hi = r["alcohol_ethanol_grams"]
    assert round(pt, 3) == 14.005
    assert r["ethanol_density_g_per_ml"] == 0.789
    assert round(r["alcohol_standard_drinks"][1], 3) == round(14.005 / 14, 3)
    assert "resolve_drink" in nutrition.resolve_drink.__qualname__

    # RULE-09 as a signature property: there is no parameter through which a model-supplied
    # ethanol or standard-drink value could enter.
    import inspect
    params = set(inspect.signature(nutrition.resolve_drink).parameters)
    assert not params & {"ethanol_grams", "standard_drinks", "alcohol_grams"}


def test_REQ_NUT_066_a_defaulted_abv_is_provenance_defaulted_not_extracted(sql_connection):
    """An assumed ABV is a modelled input, not a measurement (RULE-06)."""
    cur = world(sql_connection.cursor())
    labelled = nutrition.resolve_drink(cur, volume_ml=330, abv_percent=4.5,
                                       abv_from_label=True, schema=CORE, config=CONFIG)
    assumed = nutrition.resolve_drink(cur, volume_ml=330, abv_percent=4.5,
                                      abv_from_label=False, schema=CORE, config=CONFIG)
    assert labelled["provenance"] == "extracted"
    assert assumed["provenance"] == "defaulted"


def test_REQ_NUT_067_an_assumed_input_can_never_produce_a_degenerate_interval(sql_connection):
    """Only a labelled volume against a label ABV may narrow toward a point.

    Everywhere else the assumption must be VISIBLE as width — a point estimate would let an
    assumed ABV masquerade as a measured one.
    """
    cur = world(sql_connection.cursor())
    for kwargs in ({"abv_from_label": False, "volume_is_estimated": False},
                   {"abv_from_label": True, "volume_is_estimated": True},
                   {"abv_from_label": False, "volume_is_estimated": True}):
        r = nutrition.resolve_drink(cur, volume_ml=500, abv_percent=6.0,
                                    schema=CORE, config=CONFIG, **kwargs)
        lo, pt, hi = r["alcohol_ethanol_grams"]
        assert lo < pt < hi, f"{kwargs} produced a degenerate interval"
        assert r["method"] == "portion_table"
        # And the standard-drink count carries the same uncertainty, not a tidy point.
        dlo, dpt, dhi = r["alcohol_standard_drinks"]
        assert dlo < dpt < dhi

    narrow = nutrition.resolve_drink(cur, volume_ml=500, abv_percent=6.0, abv_from_label=True,
                                     volume_is_estimated=False, schema=CORE, config=CONFIG)
    assert narrow["method"] == "labelled"


def test_REQ_NUT_068_the_standard_drink_constant_is_configured_not_inlined(sql_connection):
    """REQ-NUT-068 calls 14 g a provisional placeholder. A number in a config row can be
    re-ruled; a number inlined in code gets copied."""
    cur = world(sql_connection.cursor())
    assert nutrition.constant(cur, "g_per_standard_drink", CONFIG) == 14.0
    cur.execute(f"UPDATE {CONFIG}.strings SET value = '10' WHERE key = 'g_per_standard_drink'")
    r = nutrition.resolve_drink(cur, volume_ml=355, abv_percent=5.0, abv_from_label=True,
                                schema=CORE, config=CONFIG)
    assert round(r["alcohol_standard_drinks"][1], 3) == round(14.005 / 10, 3)
    assert r["g_per_standard_drink"] == 10.0
    sql_connection.rollback()


def test_RULE_29_a_source_host_outside_the_allowlist_is_refused(sql_connection):
    """RULE-29 names the only destinations personal data may reach, and the allowlist is a
    TABLE — adding a destination is a visible data change, reviewable on its own."""
    from lib import egress
    cur = world(sql_connection.cursor())
    cur.execute(f"SELECT count(*) FROM {CONFIG}.egress_allowlist")
    assert cur.fetchone()[0] >= 3

    calls = []
    with pytest.raises(egress.PayloadRefused):
        egress.get_json(cur, "https://evil.example.com/v1/foods", "nutrition",
                        schema=CORE, ops=OPS, config=CONFIG,
                        _transport=lambda u, h, t: calls.append(u))
    assert calls == [], "no request may be issued to a host outside the allowlist"
    cur.execute(f"SELECT count(*) FROM {OPS}.egress_log")
    assert cur.fetchone()[0] == 0
    sql_connection.rollback()


def test_RULE_29_an_allowlisted_call_is_logged_without_its_request_body(sql_connection):
    """RULE-29 wants a row for every outbound call — and NOT a copy of what it carried.

    A nutrition query carries what Joe ate. A log that reproduces it turns the audit trail into
    a second copy of the record it audits, in a table with different access rules.
    """
    from lib import egress
    cur = world(sql_connection.cursor())

    def transport(url, headers, timeout):
        assert "gin%20and%20tonic" in url or "gin+and+tonic" in url, url
        return json.dumps({"foods": []}).encode()

    out = egress.get_json(cur, "https://api.nal.usda.gov/fdc/v1/foods/search", "nutrition",
                          params={"query": "gin and tonic"}, schema=CORE, ops=OPS,
                          config=CONFIG, _transport=transport)
    assert out == {"foods": []}

    cur.execute(f"SELECT destination, purpose, request_bytes, response_bytes, detail "
                f"FROM {OPS}.egress_log")
    destination, purpose, req_bytes, resp_bytes, detail = cur.fetchone()
    assert destination == "api.nal.usda.gov" and purpose == "nutrition"
    assert req_bytes > 0 and resp_bytes > 0
    detail = detail if isinstance(detail, dict) else json.loads(detail)
    assert detail["path"] == "/fdc/v1/foods/search"
    assert detail["n_params"] == 1
    # The food itself must not be in the log.
    blob = json.dumps(detail)
    assert "gin" not in blob.lower(), blob
    assert "ms" in detail, "the elapsed time is recorded"
    sql_connection.rollback()


def test_RULE_29_a_query_parameter_carrying_a_coordinate_is_refused(sql_connection):
    """Query parameters are payload. A source lookup is not an exemption from the screen."""
    from lib import egress
    cur = world(sql_connection.cursor())
    calls = []
    with pytest.raises(egress.PayloadRefused):
        egress.get_json(cur, "https://api.nal.usda.gov/fdc/v1/foods/search", "nutrition",
                        params={"query": "cafe near 12.34567,-45.67891"},
                        schema=CORE, ops=OPS, config=CONFIG,
                        _transport=lambda u, h, t: calls.append(u))
    assert calls == []
    cur.execute(f"SELECT count(*) FROM {OPS}.egress_log")
    assert cur.fetchone()[0] == 0, "a refused payload must not be logged as having left"
    sql_connection.rollback()
