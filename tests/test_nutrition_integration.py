"""B12 end to end: `resolve_item` really walks the cascade (ADR-0106, ADR-0137).

These are not unit tests of the pieces. `tests/test_nutrition_cascade.py` proves the ordering
with stub sources, `tests/test_nutrition_off.py` proves the parser with fixed payloads, and both
did so while **nothing called either module** — `resolve_item` did one `foods_cache` lookup and
raised on a miss, and `SOURCE_PRECEDENCE` was a constant no code read. A green unit suite over an
unreachable module is the failure this file exists to make impossible.

So every test here enters through `nutrition.resolve_item`, the function on the execution path,
and asserts on what actually happened: which legs were called, how many times, what reached
`ops.egress_log`, and what is in `core.foods_cache` afterwards.

Nothing reaches the network. The Open Food Facts leg takes an explicit transport, and the tests
that must prove no request was issued install a transport that FAILS if it is called — a call
count alone cannot tell "we did not ask" from "we asked and ignored the answer".

Every food below is synthetic. There is no real product record and no personal data in this file.
"""
import json
import os

import pytest

from lib import egress
from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import nutrition, nutrition_cascade, nutrition_off

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds migration 0050 in disposable schemas; local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_nutint_pytest"
OPS = "ops_nutint_pytest"
CONFIG = "config_nutint_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")

CONTACT = {"PERSONAL_OS_CONTACT_EMAIL": "someone@example.org"}   # synthetic, not Joe's


def world(cur):
    """Migration 0050 verbatim in disposable schemas, inside a transaction that rolls back
    (RULE-01's ADR-0022 exception). Nothing is committed and no real table is touched."""
    from pathlib import Path
    from tools.run_migration import split_statements

    for schema in (CORE, OPS, CONFIG):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"CREATE TABLE {CONFIG}.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                f"note TEXT)")
    root = Path(__file__).resolve().parents[1]
    body = (root / "migrations" / "0050_nutrition.sql").read_text() \
        .replace("__CORE__", CORE).replace("__OPS__", OPS).replace("config.", f"{CONFIG}.")
    for stmt in split_statements(body):
        cur.execute(stmt)
    return cur


# ---------------------------------------------------------------- synthetic source payloads

def off_product(name="Synthetic Nut Spread", code="3017624010701", brand="Examplo", **kw):
    """One Open Food Facts product, in the API's own key shape. Invented, not fetched."""
    base = {"code": code, "product_name": name, "brands": brand,
            "nutrition_data_per": "100g", "serving_quantity": 30,
            "serving_quantity_unit": "g",
            "nutriments": {"energy-kcal_100g": 500.0, "proteins_100g": 6.0,
                           "carbohydrates_100g": 55.0, "fat_100g": 28.0,
                           "sugars_100g": 50.0, "salt_100g": 0.1}}
    base.update(kw)
    return base


def search_transport(products, log=None):
    """A `lib.egress` transport returning a legacy CGI search body. Records every call."""
    def transport(url, headers, timeout):
        if log is not None:
            log.append(url)
        return json.dumps({"count": len(products), "page_size": 20,
                           "products": list(products)}).encode()
    return transport


def forbidden_transport(url, headers, timeout):
    """The strongest form of "no request was issued": if it is called, the test fails."""
    raise AssertionError(f"a network request was issued when none was permitted: {url}")


def sources_for(cur, *, transport=None, off=True, limits=None):
    return nutrition.build_sources(cur, schema=CORE, ops=OPS, config=CONFIG, off=off,
                                   off_transport=transport, off_env=CONTACT, off_limits=limits)


def cache_food(cur, name, source, nutrients, serving_g=None, brand=None, source_id=None):
    cur.execute(f"""INSERT INTO {CORE}.foods_cache
        (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g)
        VALUES (%s,%s,%s,%s,%s::jsonb,%s)""",
        (name, source, source_id or name, brand, json.dumps(nutrients), serving_g))


def calls(sources):
    return {name: leg.calls for name, leg in sources.items()}


def walk(result_or_tried):
    """The cascade's own record of the walk: (source, outcome) in the order it happened."""
    tried = result_or_tried["tried"] if isinstance(result_or_tried, dict) else result_or_tried
    return [(t["source"], t["outcome"]) for t in tried if "outcome" in t]


def egress_rows(cur):
    """Every outbound call RULE-29 logged, as tuples — the driver returns lists.

    SORTED, deliberately not in issue order. `egress_log.egress_id` is a `gen_random_uuid()`
    primary key and `occurred_at` defaults to `now()`, which in PostgreSQL is transaction start
    and so identical for every row written inside one rolled-back fixture: neither column
    orders these rows. `ORDER BY egress_id` was therefore a random shuffle that happened to be
    invisible while every test here logged at most one call, and would have begun failing
    intermittently the moment one logged two. The order of the walk is a real fact and `walk()`
    asserts it from the record the cascade keeps itself.
    """
    cur.execute(f"SELECT destination, purpose FROM {OPS}.egress_log")
    return sorted(tuple(row) for row in cur.fetchall())


# ================================================================ the cache leg comes first

def test_REQ_NUT_002_REQ_NUT_012_a_cached_food_never_reaches_a_network_leg(sql_connection):
    """REQ-NUT-002: an exact cache match reads `foods_cache` and issues NO network request.

    Proved three ways at once, because each alone is weak: the Open Food Facts leg was never
    CALLED, the transport under it would have raised if it had been, and `ops.egress_log` — the
    row RULE-29 requires for every outbound call — is empty. The USDA legs were not called
    either, which is the actual content of "cache first": the cascade stopped at step 1.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "synthetic oat porridge", "usda_foundation",
               {"kcal": 70.0, "protein_g": 2.4}, serving_g=250.0)
    sources = sources_for(cur, transport=forbidden_transport)

    result = nutrition.resolve_item(cur, "synthetic oat porridge", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["from_cache"] is True
    assert result["source"] == "usda_foundation", "the cache reports the ROW's source, not `joe`"
    assert result["grams"] == 250.0
    assert round(result["nutrients"]["kcal"][1]) == 175           # 70 per 100 g x 2.5

    assert calls(sources) == {"joe": 1, "usda_branded": 0, "usda_foundation": 0,
                              "off_product": 0}, "the cascade must stop at the cache"
    assert egress_rows(cur) == [], "REQ-NUT-002: no request may be issued on a cache hit"
    sql_connection.rollback()


def test_REQ_NUT_001_REQ_NUT_036_a_cache_miss_falls_through_the_declared_order(sql_connection):
    """The order is now what RUNS, not what a constant says.

    Before ADR-0137 this assertion was impossible to make: `SOURCE_PRECEDENCE` was declared in
    `nutrition.py` and read by nothing, and a cache miss raised immediately. The sequence below
    is read off the walk the resolver actually performed.
    """
    cur = world(sql_connection.cursor())
    requests = []
    sources = sources_for(cur, transport=search_transport([off_product()], requests))

    result = nutrition.resolve_item(cur, "Synthetic Nut Spread", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert walk(result) == [("joe", "no_match"),
                            ("usda_branded", "not_configured"),
                            ("usda_foundation", "not_configured"),
                            ("off_product", "match")]
    assert calls(sources) == {"joe": 1, "usda_branded": 1, "usda_foundation": 1,
                              "off_product": 1}
    # REQ-NUT-005: the USDA legs say WHY they cannot answer, and it is not about the food.
    usda = next(t for t in result["tried"] if t["source"] == "usda_branded")
    assert "api.data.gov" in usda["detail"]
    assert len(requests) == 1, "exactly one Open Food Facts request for one item"
    sql_connection.rollback()


# ================================================================ REQ-NUT-016, the rule that matters

def test_REQ_NUT_015_REQ_NUT_016_a_branded_item_with_no_branded_source_keeps_its_token(
        sql_connection):
    """A restaurant portion is routinely double the generic and the number looks ordinary.

    The generic row is IN the cache and is a perfectly good answer to the unbranded question —
    the second half of this test resolves it — so the refusal below is the brand rule doing its
    job and not an empty cache. That control is the difference between this test and one that
    passes because nothing was there.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "synthetic chicken burrito", "usda_foundation",
               {"kcal": 150.0, "protein_g": 8.0}, serving_g=300.0)
    sources = sources_for(cur, transport=search_transport([]))     # OFF knows no such product

    with pytest.raises(nutrition.Unresolved) as raised:
        nutrition.resolve_item(cur, "synthetic chicken burrito", servings=1, brand="Testaurant",
                               sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    e = raised.value
    assert e.item_text == "synthetic chicken burrito" and e.brand == "Testaurant", "both verbatim"
    assert e.status == "unresolved"
    assert e.reason == "no_source_match" and e.review_reason == "no_source_match"
    outcomes = {t["source"]: t["outcome"] for t in e.tried if "outcome" in t}
    assert outcomes["usda_foundation"] == "skipped_generic_source_for_branded_item"
    # The cache was asked and refused the generic row itself: REQ-NUT-016 holds offline too,
    # where there is no request to notice the substitution.
    assert outcomes["joe"] == "no_match"

    # The control. Same row, same cache, no brand token — and it answers.
    generic = nutrition.resolve_item(cur, "synthetic chicken burrito", servings=1,
                                     sources=sources_for(cur, transport=forbidden_transport),
                                     schema=CORE, config=CONFIG, ops=OPS)
    assert round(generic["nutrients"]["kcal"][1]) == 450, \
        "the generic row was available all along; the brand rule is what refused it"
    sql_connection.rollback()


def test_REQ_NUT_014_a_cached_branded_row_with_no_brand_owner_is_a_defect_not_a_resolution(
        sql_connection):
    """The hole that opens the moment the cache becomes a cascade leg.

    `nutrition_cascade.resolve` refuses a `usda_branded` match with no brand owner — but that
    check is keyed on the LEG NAME, and the cache leg is registered as `joe`. A branded row read
    back from `foods_cache` therefore walks straight past it, and `foods_cache.brand` is
    nullable, so such a row is storable. The result would be `estimate_method='labelled'` with
    nothing to re-check it against: exactly the claim about precision with no referent ADR-0106
    forbids, and `labelled` is a TIGHT method downstream.

    The control below is the same row with its brand owner recorded, which resolves and IS
    labelled — so this test fails on the missing brand owner and not on the read.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "synthetic branded bar", "usda_branded", {"kcal": 400.0}, serving_g=50.0,
               brand=None, source_id="fdc-000001")
    sources = sources_for(cur, transport=forbidden_transport)
    with pytest.raises(ValueError, match="REQ-NUT-014"):
        nutrition.resolve_item(cur, "synthetic branded bar", servings=1, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    cache_food(cur, "synthetic labelled bar", "usda_branded", {"kcal": 400.0}, serving_g=50.0,
               brand="Examplo", source_id="fdc-000002")
    result = nutrition.resolve_item(cur, "synthetic labelled bar", servings=1, brand="Examplo",
                                    sources=sources_for(cur, transport=forbidden_transport),
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert result["estimate_method"] == "labelled" and result["brand"] == "Examplo"
    assert result["source"] == "usda_branded"
    sql_connection.rollback()


# ================================================================ REQ-NUT-024, two refusals

def test_REQ_NUT_024_could_not_find_it_and_could_not_look_are_different_outcomes(sql_connection):
    """Only one of these two facts is about the food, and only one belongs to Joe.

    With USDA unconfigured, the difference rests entirely on whether Open Food Facts was
    reachable. If it was and did not know the food, that is evidence Joe can act on. If it was
    not, every item comes back unresolved for a reason that has nothing to do with what he ate,
    and putting those on a review list spends his effort on an operations problem.

    The cache is deliberately not evidence either way: it cannot know a food nobody has ever
    looked up, so a cache miss alone must not turn "we could not look" into "we could not find".
    """
    cur = world(sql_connection.cursor())

    could_not_find = sources_for(cur, transport=search_transport([]))
    with pytest.raises(nutrition.Unresolved) as asked:
        nutrition.resolve_item(cur, "synthetic sphinx casserole", grams=200,
                               sources=could_not_find, schema=CORE, config=CONFIG, ops=OPS)
    assert asked.value.reason == "no_source_match"
    assert asked.value.review_reason == "no_source_match", "Joe can answer this one"
    # And what Open Food Facts actually said survives next to the walk.
    assert any(t.get("source") == "off_product" and t.get("reason") == "no_exact_name_match"
               for t in asked.value.tried)

    could_not_look = sources_for(cur, off=False)
    with pytest.raises(nutrition.Unresolved) as unasked:
        nutrition.resolve_item(cur, "synthetic sphinx casserole", grams=200,
                               sources=could_not_look, schema=CORE, config=CONFIG, ops=OPS)
    assert unasked.value.reason == "no_source_available"
    assert unasked.value.review_reason is None, "not Joe's to review"
    assert nutrition_cascade.resolvable_sources(could_not_look) == ("joe",), \
        "a registered-but-unconfigured leg must not be reported as able to answer"

    assert asked.value.reason != unasked.value.reason
    sql_connection.rollback()


def test_REQ_NUT_012_REQ_NUT_024_a_rate_limit_is_not_evidence_about_the_food(sql_connection):
    """REQ-NUT-011's window is spent, so the item is unresolved for an operational reason.

    The cascade must record that as `no_source_available` with no review reason and put the
    source in REQ-NUT-012's hour-long penalty box — not as "Open Food Facts has no such food",
    which would be a permanent gap created by a minute's throttling.
    """
    cur = world(sql_connection.cursor())
    limits = nutrition_off.Limits()
    for _ in range(nutrition_off.SEARCHES_PER_MINUTE):             # the window, exhausted
        limits.search.acquire()
    sources = sources_for(cur, transport=forbidden_transport, limits=limits)
    cooldowns = nutrition_cascade.Cooldowns()

    with pytest.raises(nutrition.Unresolved) as raised:
        nutrition.resolve_item(cur, "synthetic protein bar", servings=1, sources=sources,
                               cooldowns=cooldowns, schema=CORE, config=CONFIG, ops=OPS)

    assert raised.value.reason == "no_source_available"
    assert raised.value.review_reason is None
    assert dict(walk(raised.value.tried))["off_product"] == "rate_limited_now"
    assert cooldowns.active("off_product"), "REQ-NUT-012: the source stops for an hour"
    assert cooldowns.remaining("off_product") > 0
    assert egress_rows(cur) == [], "the window is checked before a request is issued"
    sql_connection.rollback()


# ================================================================ an Open Food Facts resolution

def test_REQ_NUT_003_REQ_NUT_014_REQ_NUT_034_an_off_resolution_lands_with_its_method_and_width(
        sql_connection):
    """The width is the method, and the method is the source that answered (RULE-08).

    The bounds are checked against `config.nutrition_interval_widths` rather than against 0.90
    and 1.10 written here: RULE-00 puts a threshold in a table so that changing it is a visible
    data change, and a test that restates the number would go on passing after the table moved.
    The table's own values are pinned by `test_nutrition.py`.
    """
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([off_product()]))

    result = nutrition.resolve_item(cur, "Synthetic Nut Spread", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["source"] == "off_product" and result["method"] == "off_product"
    assert result["estimate_method"] == "off_product"
    assert result["estimate_method"] != "labelled", \
        "REQ-NUT-014: only a USDA Branded match is a manufacturer's label"
    assert result["grams"] == 30.0                                 # the declared serving mass

    lo, pt, hi = result["nutrients"]["kcal"]
    assert round(pt, 4) == 150.0                                   # 500 per 100 g x 0.30
    rel_low, rel_high = nutrition.interval_widths(cur, CONFIG)["off_product"]
    assert (lo, hi) == (round(pt * rel_low, 4), round(pt * rel_high, 4))
    assert lo < pt < hi                                            # REQ-NUT-034
    assert result["nutrients"]["sodium_mg"][1] == round(0.1 * 1000 / 2.5 * 0.30, 4)

    # REQ-NUT-003: the row is in the cache, with the source's own identifier on it.
    cur.execute(f"SELECT source, source_id, brand, serving_g FROM {CORE}.foods_cache "
                f"WHERE canonical_name = 'Synthetic Nut Spread'")
    source, source_id, cached_brand, serving_g = cur.fetchone()
    assert (source, source_id, cached_brand, float(serving_g)) == \
        ("off_product", "3017624010701", "Examplo", 30.0)
    assert result["food_id"] is not None

    # RULE-29: the call is logged, and the log does not reproduce what Joe ate.
    assert egress_rows(cur) == [("world.openfoodfacts.org", "nutrition:off_search")]
    cur.execute(f"SELECT detail FROM {OPS}.egress_log")
    detail = cur.fetchone()[0]
    blob = json.dumps(detail if isinstance(detail, dict) else json.loads(detail)).lower()
    assert "nut" not in blob and "spread" not in blob, blob
    sql_connection.rollback()


def test_REQ_NUT_004_REQ_NUT_002_a_resolved_phrase_resolves_from_the_cache_next_time(
        sql_connection):
    """The phrase AS UTTERED, not the source's name for the product.

    Open Food Facts matches on a folded name, so "Synthetic  Nut-Spread!" finds the product
    called "Synthetic Nut Spread". `lookup_cached` matches on `lower(canonical_name)` and does
    not fold, so without REQ-NUT-004's alias the very same phrase would miss the cache tomorrow
    and spend another of REQ-NUT-011's fifteen requests on an answer already in hand.

    The second resolution runs against a transport that raises if it is called, so "it came from
    the cache" is proved rather than inferred from a count.
    """
    cur = world(sql_connection.cursor())
    phrase = "Synthetic  Nut-Spread!"
    first = nutrition.resolve_item(cur, phrase, servings=1,
                                   sources=sources_for(cur, transport=search_transport(
                                       [off_product()])),
                                   schema=CORE, config=CONFIG, ops=OPS)
    assert first["from_cache"] is False and first["alias_id"] is not None

    cur.execute(f"SELECT canonical_name, source, source_id, raw->>'alias_of' "
                f"FROM {CORE}.foods_cache ORDER BY canonical_name")
    rows = cur.fetchall()
    assert [r[0] for r in rows] == ["Synthetic  Nut-Spread!", "Synthetic Nut Spread"]
    assert {r[2] for r in rows} == {"3017624010701"}, "both keys name one source record (INV-1)"
    assert rows[0][3] == "Synthetic Nut Spread", "the alias says what it is an alias of"
    assert rows[1][3] is None, "the canonical row keeps the source payload, not an alias marker"

    second_sources = sources_for(cur, transport=forbidden_transport)
    second = nutrition.resolve_item(cur, phrase, servings=1, sources=second_sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert second["from_cache"] is True
    assert second_sources["off_product"].calls == 0
    assert second["nutrients"]["kcal"] == first["nutrients"]["kcal"]
    assert second["source"] == "off_product", "an alias does not relabel the provenance"
    assert egress_rows(cur) == [("world.openfoodfacts.org", "nutrition:off_search")], \
        "REQ-NUT-002: one request in total, for two resolutions of the same phrase"
    sql_connection.rollback()


# ================================================================ RULE-29 through the real path

def test_RULE_29_a_payload_refusal_is_never_reclassified_as_a_food_outcome(sql_connection):
    """A privacy refusal recorded as "Open Food Facts had no such food" would be retried
    tonight, and the item would sit on a review list as a data gap.

    `resolve_item` swallows Open Food Facts' four food-shaped failures on purpose; it must not
    swallow this one, so the exception has to travel all the way out through the cascade.
    """
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=forbidden_transport)
    with pytest.raises(egress.PayloadRefused):
        nutrition.resolve_item(cur, "lunch, latitude: the park", grams=200, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)
    cur.execute(f"SELECT count(*) FROM {OPS}.egress_log")
    assert cur.fetchone()[0] == 0, "a refused payload must not be logged as having left"
    sql_connection.rollback()


def test_ADR_0135_the_cascade_modules_have_a_caller_on_the_execution_path(sql_connection):
    """The defect this unit fixed, asserted directly rather than described.

    `nutrition_cascade` and `nutrition_off` were fully tested and entirely unreachable: no
    non-test module imported either, and `resolve_item` consulted neither. A test that only
    checked the import would pass on a module imported and never used, so this drives a
    resolution and reads the cascade's own fingerprints off the result — the `tried` walk it
    builds and the `off_product` leg name it assigns.
    """
    import inspect
    src = inspect.getsource(nutrition.resolve_item)
    assert "nutrition_cascade.resolve(" in src, "the cascade must be called, not described"

    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([off_product()]))
    result = nutrition.resolve_item(cur, "Synthetic Nut Spread", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)
    assert result["leg"] == "off_product"
    assert len(walk(result)) == len(nutrition_cascade.SOURCE_PRECEDENCE), \
        "every declared source appears in the walk, answered or refused"
    assert nutrition.SOURCE_PRECEDENCE is nutrition_cascade.SOURCE_PRECEDENCE, \
        "one definition of the order, not two"
    sql_connection.rollback()
