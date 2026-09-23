"""B12 §D.2/D.3: the USDA FoodData Central legs, from payload to retrievable atom.

The two USDA legs were the last unwritten part of B12. They were `UnconfiguredLeg` — a class
whose whole behaviour is to raise — and every requirement that named them (REQ-NUT-005, 009,
012, 013, 014) was therefore satisfied by nothing at all. ADR-0106's "What remains" gave two
reasons: no api.data.gov key, and an unrecorded egress target. **Only the first is still true.**
Migration 0050 has inserted `api.nal.usda.gov` into `config.egress_allowlist` since the table
existed, so RULE-29's recording requirement was already met.

A missing key blocks LIVE VERIFICATION. It does not block implementation, and it does not block
this file: the transport is a parameter, so every behaviour below is exercised against payloads
this file constructs. **Nothing here proves the client works against the real api.data.gov.**
That is a live check, it is listed as pending, and no test in this file should ever be read as
having performed it.

The file is in two halves, for the reason `tests/test_nutrition_off.py` is:

  * The pure half needs no database. It is the parser, the exact-match rule and the two ration
    windows, tested against fixed payloads.
  * The `@needs_sql` half enters through `nutrition.resolve_item` — the function the nightly
    resolver calls — and asserts on what actually happened: which legs were called, what
    reached `ops.egress_log`, what is in `core.foods_cache`, and what a downstream reader can
    retrieve from `atoms_current` afterwards. A green parser behind an uncalled leg is the
    exact failure ADR-0137 was written about, and it is not repeated here.

Every food below is invented. There is no real FDC record, no real key, and no personal data in
this file.
"""
import datetime as dt
import json
import os
import uuid
from pathlib import Path

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import nutrition, nutrition_cascade, nutrition_usda as usda
from tools.run_migration import split_statements

BRANDED, FOUNDATION = usda.BRANDED, usda.FOUNDATION

# Synthetic throughout. Not a key, not Joe's, and shaped so it cannot trip the RULE-29 screen.
KEY_ENV = {"USDA_FDC_API_KEY": "SYNTHETICKEYNOTREAL"}


# ================================================================ synthetic FDC payloads

def branded_food(fdc_id=999001, description="Synthetic Crunch Bar", brand_owner="Examplo Foods",
                 **kw):
    """One Branded record in the SEARCH endpoint's key shape. Invented, not fetched."""
    food = {
        "fdcId": fdc_id, "description": description, "dataType": "Branded",
        "brandOwner": brand_owner, "brandName": "Examplo",
        "servingSize": 40, "servingSizeUnit": "g",
        "foodNutrients": [
            {"nutrientId": 1008, "nutrientName": "Energy", "unitName": "KCAL", "value": 450.0},
            {"nutrientId": 1003, "nutrientName": "Protein", "unitName": "G", "value": 8.0},
            {"nutrientId": 1005, "nutrientName": "Carbohydrate", "unitName": "G", "value": 60.0},
            {"nutrientId": 1004, "nutrientName": "Total lipid", "unitName": "G", "value": 20.0},
            {"nutrientId": 1079, "nutrientName": "Fiber", "unitName": "G", "value": 3.0},
            {"nutrientId": 2000, "nutrientName": "Sugars", "unitName": "G", "value": 35.0},
            {"nutrientId": 1093, "nutrientName": "Sodium", "unitName": "MG", "value": 300.0},
        ],
    }
    food.update(kw)
    return food


def foundation_food(fdc_id=999500, description="Synthetic Rolled Oats", **kw):
    """One Foundation record. Generic by definition — no brand."""
    food = {
        "fdcId": fdc_id, "description": description, "dataType": "Foundation",
        "foodNutrients": [
            {"nutrientId": 1008, "unitName": "KCAL", "value": 380.0},
            {"nutrientId": 1003, "unitName": "G", "value": 13.0},
            {"nutrientId": 1005, "unitName": "G", "value": 67.0},
            {"nutrientId": 1004, "unitName": "G", "value": 7.0},
        ],
    }
    food.update(kw)
    return food


def detail_shaped(food):
    """The same food as the DETAIL endpoint returns it: nutrients nested under `nutrient`."""
    out = dict(food)
    out["foodNutrients"] = [
        {"nutrient": {"id": r["nutrientId"], "unitName": r["unitName"]}, "amount": r["value"]}
        for r in food["foodNutrients"]]
    return out


def search_transport(foods, log=None):
    """A `lib.egress` transport returning an FDC search body. Records every URL it was given."""
    def transport(url, headers, timeout):
        if log is not None:
            log.append(url)
        return json.dumps({"totalHits": len(foods), "currentPage": 1,
                           "foods": list(foods)}).encode()
    return transport


def failing_transport(exc):
    """A transport that raises. Used to prove a 429 is handled as 429 and nothing else is."""
    def transport(url, headers, timeout):
        raise exc
    return transport


def forbidden_transport(url, headers, timeout):
    """The strongest form of "no request was issued": if it is called, the test fails."""
    raise AssertionError(f"a USDA request was issued when none was permitted: {url}")


class Http429(Exception):
    """What `urllib` raises for a rate limit, reduced to the attribute REQ-NUT-012 turns on."""
    code = 429


# ================================================================ the parser (no database)

def test_REQ_NUT_005_the_fdc_id_is_stored_as_the_row_source_id():
    """REQ-NUT-005: the provenance of the number is auditable to a specific FDC record."""
    parsed = usda.parse_food(branded_food(fdc_id=123456), BRANDED)
    assert parsed["source_id"] == "123456"
    assert usda.cache_row(branded_food(fdc_id=123456), BRANDED)["source_id"] == "123456"


def test_REQ_NUT_005_a_food_with_no_fdc_id_is_refused_rather_than_stored():
    """A nutrient figure that cannot be traced to a record is not worth storing.

    Refusing is not pedantry: `foods_cache` keys on `(canonical_name, source, source_id)`, so a
    row with a NULL `source_id` is a row that can never be matched against the record it came
    from, and INV-1's "derived rows trace to raw captures" loses its far end.
    """
    food = branded_food()
    food.pop("fdcId")
    with pytest.raises(usda.UsdaMalformed) as e:
        usda.parse_food(food, BRANDED)
    assert e.value.reason == "no_fdc_id"


def test_REQ_NUT_014_a_branded_match_records_the_matched_brand_owner():
    """REQ-NUT-014: `labelled` is a claim that a named manufacturer published this number."""
    parsed = usda.parse_food(branded_food(brand_owner="Examplo Foods"), BRANDED)
    assert parsed["brand"] == "Examplo Foods"


def test_REQ_NUT_014_a_branded_food_with_no_brand_owner_is_refused():
    """A `labelled` figure with nothing to re-check it against is a defect, not a resolution.

    `nutrition_cascade.resolve` raises `ValueError` on such a match, which would take down a
    nightly batch. Refusing here converts that crash into an ordinary `no_source_match`
    outcome for one item, which is what REQ-NUT-027 asks for.
    """
    food = branded_food(brand_owner=None)
    food["brandName"] = None
    food["brandedFoodCategory"] = None
    with pytest.raises(usda.UsdaMalformed) as e:
        usda.parse_food(food, BRANDED)
    assert e.value.reason == "branded_without_brand_owner"


def test_REQ_NUT_016_a_foundation_food_never_carries_a_brand():
    """A Foundation food is generic by definition.

    If a stray `brandName` survived onto a Foundation row, `nutrition_cascade`'s
    BRANDED_SOURCES check would be satisfied by a generic laboratory analysis — which is
    precisely the substitution REQ-NUT-016 exists to forbid, arriving through the back door.
    """
    parsed = usda.parse_food(foundation_food(brandName="Should Be Ignored"), FOUNDATION)
    assert parsed["brand"] is None


def test_the_search_and_detail_payload_shapes_parse_identically():
    """FDC returns two different `foodNutrients` shapes. The same food must read the same.

    Handling only the shape this module happens to request would make the parser silently
    endpoint-specific, and the bug would appear the first time a Branded row was re-fetched by
    `fdcId` under REQ-NUT-008 rather than found by search.
    """
    food = branded_food()
    assert (usda.parse_food(food, BRANDED)["nutrients_per_100g"]
            == usda.parse_food(detail_shaped(food), BRANDED)["nutrients_per_100g"])


def test_a_nutrient_in_an_unexpected_unit_is_dropped_and_never_coerced():
    """Sodium stated in grams is not sodium in milligrams, and guessing is a 1000x error.

    The converted case and the unreadable case are both asserted, because a parser that
    dropped everything it did not recognise would pass a test that only checked the drop.
    """
    in_grams = branded_food(foodNutrients=[
        {"nutrientId": 1008, "unitName": "KCAL", "value": 100.0},
        {"nutrientId": 1093, "unitName": "G", "value": 1.5}])
    assert usda.parse_food(in_grams, BRANDED)["nutrients_per_100g"]["sodium_mg"] == 1500.0

    nonsense = branded_food(foodNutrients=[
        {"nutrientId": 1008, "unitName": "KCAL", "value": 100.0},
        {"nutrientId": 1093, "unitName": "furlongs", "value": 1.5}])
    parsed = usda.parse_food(nonsense, BRANDED)
    assert "sodium_mg" not in parsed["nutrients_per_100g"]
    assert any(d["why"] == "unexpected_unit" for d in parsed["dropped"])


def test_energy_in_kilojoules_only_is_converted_and_says_so():
    """A kcal derived from kJ is not the label's own kcal, and a later reader must be able
    to tell — otherwise a re-derivation from `raw` cannot reproduce how the number was got."""
    kj_only = branded_food(foodNutrients=[
        {"nutrientId": 1062, "unitName": "kJ", "value": 2000.0},
        {"nutrientId": 1003, "unitName": "G", "value": 5.0}])
    parsed = usda.parse_food(kj_only, BRANDED)
    assert parsed["nutrients_per_100g"]["kcal"] == round(2000.0 / 4.184, 4)
    assert parsed["nutrient_provenance"]["kcal"]["converted_from_kj"] is True


def test_a_declared_kcal_outranks_the_atwater_derived_one():
    """1008 is a declaration; 2047 is computed from macros already in this row. Preferring the
    computed figure would double-count the error in the numbers it was computed from."""
    both = branded_food(foodNutrients=[
        {"nutrientId": 2047, "unitName": "KCAL", "value": 999.0},
        {"nutrientId": 1008, "unitName": "KCAL", "value": 450.0}])
    parsed = usda.parse_food(both, BRANDED)
    assert parsed["nutrients_per_100g"]["kcal"] == 450.0
    assert parsed["nutrient_provenance"]["kcal"]["fdc_nutrient_id"] == 1008


def test_a_value_past_a_physical_ceiling_is_dropped_not_clamped():
    """RULE-01: a clamped value is a fabricated one. 100 g cannot hold 300 g of protein.

    The ceilings are `nutrition_off`'s, imported rather than copied, so this also pins that
    the two source adapters screen on one set of numbers and cannot drift apart.
    """
    impossible = branded_food(foodNutrients=[
        {"nutrientId": 1008, "unitName": "KCAL", "value": 400.0},
        {"nutrientId": 1003, "unitName": "G", "value": 300.0}])
    parsed = usda.parse_food(impossible, BRANDED)
    assert "protein_g" not in parsed["nutrients_per_100g"]
    assert any(d["why"] == "above_physical_ceiling" for d in parsed["dropped"])
    assert parsed["nutrients_per_100g"]["kcal"] == 400.0, "the readable nutrients survive"


def test_a_serving_stated_in_millilitres_is_not_converted_to_grams():
    """REQ-NUT-019 semantics: a volume is not a mass without a density FDC does not publish.

    Converting at the density of water would be wrong by whatever the product's sugar or fat
    contributes, and it would be wrong invisibly — a plausible gram figure with no flag.
    """
    parsed = usda.parse_food(branded_food(servingSize=330, servingSizeUnit="ml"), BRANDED)
    assert parsed["serving_g"] is None
    assert parsed["notes"] == ["serving_stated_in_volume_ml"]


def test_an_ounce_serving_is_converted_because_an_ounce_is_a_mass():
    parsed = usda.parse_food(branded_food(servingSize=2, servingSizeUnit="oz"), BRANDED)
    assert parsed["serving_g"] == round(2 * 28.349523125, 4)


# ================================================================ the exact-match rule

def test_REQ_NUT_024_the_relevance_ranking_is_discarded_and_an_exact_match_required():
    """FDC's search is a ranker: `foods[0]` is whatever scored best, by a formula this system
    cannot audit. Taking it would resolve a query to a different food on a different day."""
    foods = [branded_food(fdc_id=1, description="Synthetic Crunch Bar Family Pack"),
             branded_food(fdc_id=2, description="Synthetic Crunch Bar")]
    match = usda.select_exact_match("Synthetic Crunch Bar", foods, BRANDED)
    assert match["fdcId"] == 2, "the exact description wins, not the first result"


def test_REQ_NUT_024_no_exact_match_is_not_found_rather_than_the_closest_thing():
    foods = [branded_food(fdc_id=1, description="Synthetic Crunch Bar Family Pack")]
    with pytest.raises(usda.UsdaNotFound) as e:
        usda.select_exact_match("Synthetic Crunch Bar", foods, BRANDED)
    assert e.value.reason == "no_exact_name_match"


def test_REQ_NUT_025_two_distinct_exact_matches_are_ambiguous_and_joe_picks():
    """Two products with the same name is the case REQ-NUT-025 exists for. Picking the
    lower `fdcId` would be a guess wearing a lookup's clothes."""
    foods = [branded_food(fdc_id=11), branded_food(fdc_id=22)]
    with pytest.raises(usda.UsdaAmbiguous) as e:
        usda.select_exact_match("Synthetic Crunch Bar", foods, BRANDED)
    assert sorted(e.value.detail["fdc_ids"]) == ["11", "22"]


def test_the_same_fdc_id_returned_twice_is_one_match_not_an_ambiguity():
    """Ambiguity is about DISTINCT foods. A duplicated record is one food listed twice, and
    refusing it would send Joe a review item about the API's pagination."""
    assert usda.select_exact_match(
        "Synthetic Crunch Bar", [branded_food(fdc_id=11), branded_food(fdc_id=11)],
        BRANDED)["fdcId"] == 11


def test_a_brand_token_must_also_match_for_a_branded_query():
    """REQ-NUT-016 again, at the matching layer: the right name under the wrong brand is the
    wrong product, and a restaurant portion is routinely double a supermarket one."""
    foods = [branded_food(brand_owner="Someone Else")]
    with pytest.raises(usda.UsdaNotFound):
        usda.select_exact_match("Synthetic Crunch Bar", foods, BRANDED, brand="Examplo Foods")
    assert usda.select_exact_match(
        "Synthetic Crunch Bar", foods, BRANDED, brand="Someone Else")["fdcId"] == 999001


def test_matching_ignores_case_and_punctuation_but_not_words():
    foods = [branded_food(description="Synthetic Crunch-Bar")]
    assert usda.select_exact_match("  synthetic crunch bar ", foods, BRANDED)
    with pytest.raises(usda.UsdaNotFound):
        usda.select_exact_match("synthetic bar", foods, BRANDED)


# ================================================================ the ration windows

def test_REQ_NUT_009_the_nine_hundredth_request_is_allowed_and_the_next_defers():
    """The boundary is asserted at exactly 900, in both directions, without waiting an hour."""
    quota = usda.Quota()
    for n in range(usda.REQUESTS_PER_HOUR):
        quota.acquire(BRANDED, now=1000.0 + n * 0.001)
    assert len(quota) == 900
    with pytest.raises(usda.UsdaRateLimited) as e:
        quota.acquire(BRANDED, now=1000.0 + 900 * 0.001)
    assert e.value.reason == "rate_limited_quota"
    assert e.value.provider is False, "our own arithmetic, not a complaint from api.data.gov"


def test_REQ_NUT_009_the_quota_is_shared_by_both_usda_legs():
    """One api.data.gov key serves both datasets, so 900 is the pair's ceiling, not each
    leg's. Two windows of 900 would permit 1,800 requests against a key metered at 1,000."""
    quota = usda.Quota(max_requests=2)
    quota.acquire(BRANDED, now=0.0)
    quota.acquire(FOUNDATION, now=1.0)
    with pytest.raises(usda.UsdaRateLimited):
        quota.acquire(BRANDED, now=2.0)


def test_REQ_NUT_009_the_window_slides_so_the_hour_is_trailing_not_fixed():
    quota = usda.Quota(max_requests=1)
    quota.acquire(BRANDED, now=0.0)
    with pytest.raises(usda.UsdaRateLimited):
        quota.acquire(BRANDED, now=usda.QUOTA_WINDOW_S - 1)
    quota.acquire(BRANDED, now=usda.QUOTA_WINDOW_S)      # the first request has aged out


def test_REQ_NUT_012_a_429_stops_both_legs_for_sixty_minutes():
    """REQ-NUT-012 says "stop issuing USDA requests" — not "stop issuing Branded requests".

    Continuing to Foundation against a key api.data.gov has just throttled is how a key gets
    banned, and the failure mode of a banned key is every future item unresolved.
    """
    quota = usda.Quota()
    quota.trip(now=0.0)
    for source in (BRANDED, FOUNDATION):
        with pytest.raises(usda.UsdaRateLimited) as e:
            quota.acquire(source, now=1.0)
        assert e.value.provider is True
    quota.acquire(BRANDED, now=usda.RATE_LIMIT_COOLDOWN_S + 1)   # the hour has passed


def test_REQ_NUT_012_a_cooldown_costs_no_quota_slot():
    """A source in its penalty box must not spend one of the 900 to discover that."""
    quota = usda.Quota()
    quota.trip(now=0.0)
    with pytest.raises(usda.UsdaRateLimited):
        quota.acquire(BRANDED, now=1.0)
    assert len(quota) == 0


# ================================================================ REQ-NUT-008, the two TTLs

def test_REQ_NUT_008_a_branded_row_expires_at_a_year_and_a_foundation_row_never_does():
    """A manufacturer can reformulate a product without renaming it; a laboratory analysis of
    a generic food is not superseded by the passage of time."""
    now = dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc)
    fresh = now - dt.timedelta(days=364)
    stale = now - dt.timedelta(days=366)
    assert usda.needs_refetch(BRANDED, fresh, now=now) is False
    assert usda.needs_refetch(BRANDED, stale, now=now) is True
    assert usda.needs_refetch(FOUNDATION, stale, now=now) is False
    assert usda.needs_refetch(FOUNDATION, None, now=now) is False


def test_REQ_NUT_008_the_dataset_decides_the_ttl_not_this_systems_bucket():
    """`data_type` is what the requirement names. SR Legacy sits in the `usda_foundation`
    bucket and is non-expiring for the same reason Foundation is."""
    now = dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc)
    stale = now - dt.timedelta(days=400)
    assert usda.needs_refetch(FOUNDATION, stale, now=now, data_type="SR Legacy") is False
    assert usda.needs_refetch(BRANDED, stale, now=now, data_type="Branded") is True


def test_REQ_NUT_006_REQ_NUT_007_neither_adapter_can_bulk_import_or_crawl():
    """REQ-NUT-006 forbids mirroring either database; REQ-NUT-007 forbids crawling menu data.

    `ontology_contract.check_menu_acquisition` has asserted REQ-NUT-007 since before either
    adapter existed, by refusing the strings "scrape"/"crawl"/"bulk_import"/"spider" — a
    contract about a word, not about code. What makes the requirement true is that neither
    module that can actually issue a request has a path that pages through a result set, and
    that is checked here against the shipped source of BOTH adapters.

    A structural check rather than a behavioural one, deliberately: the behaviour being
    forbidden is one nothing currently does, so there is no call to observe. What can be
    observed is that the loop which would do it is absent.
    """
    from tools.engines import nutrition_off as off
    assert usda.PAGE_SIZE <= 25
    assert "pageNumber" in Path(usda.__file__).read_text(), "one page, named explicitly"

    for module in (usda, off):
        source = Path(module.__file__).read_text()
        for forbidden in ("while True", "totalPages", "page += 1", "page_number +=",
                          "for page in", "/download", "full_download", "csv.gz"):
            assert forbidden not in source, \
                f"{forbidden!r} in {Path(module.__file__).name} looks like a bulk path " \
                f"(REQ-NUT-006/007)"


def test_REQ_NUT_009_the_implementation_is_bound_to_the_contracts_ceiling():
    """`tools/engines/ontology_contract.py` has asserted REQ-NUT-009 since before a USDA client
    existed, against `usda_budget` — a contract function describing what the ceiling SHOULD be.

    That is a legitimate thing to have, and it was also the whole of REQ-NUT-009's evidence: a
    module that returns `{"may_request": False}` was satisfying the requirement while nothing
    could issue a USDA request at all. Now that something can, the two numbers must be one
    number. Binding them here means a future edit to either is a test failure rather than a
    silent divergence between the rule and the code that enforces it.
    """
    from tools.engines import ontology_contract
    assert usda.REQUESTS_PER_HOUR == ontology_contract.USDA_HOURLY_CEILING

    # And the two agree at the boundary, not merely on a constant.
    assert ontology_contract.usda_budget(usda.REQUESTS_PER_HOUR - 1)["may_request"] is True
    assert ontology_contract.usda_budget(usda.REQUESTS_PER_HOUR)["defer"] is True
    quota = usda.Quota()
    for n in range(usda.REQUESTS_PER_HOUR):
        quota.acquire(BRANDED, now=float(n) * 0.001)
    with pytest.raises(usda.UsdaRateLimited):
        quota.acquire(BRANDED, now=float(usda.REQUESTS_PER_HOUR) * 0.001)


def test_REQ_NUT_005_the_implementation_satisfies_the_contracts_fdc_id_rule():
    """`ontology_contract.usda_row` refuses a row with no `fdc_id`. So does the real parser,
    and this pins that they refuse the SAME case rather than merely both having a rule."""
    from tools.engines import ontology_contract
    with pytest.raises(ontology_contract.NutritionStorageViolation, match="REQ-NUT-005"):
        ontology_contract.usda_row({"kcal_point": 289}, fdc_id=None)
    food = branded_food()
    food.pop("fdcId")
    with pytest.raises(usda.UsdaMalformed):
        usda.parse_food(food, BRANDED)


def test_a_missing_key_names_where_to_get_one():
    """A refusal that does not say what to do about it is a refusal nobody acts on."""
    with pytest.raises(usda.ApiKeyMissing) as e:
        usda.api_key({})
    assert "api.data.gov" in str(e.value) and "USDA_FDC_API_KEY" in str(e.value)


# ================================================================ the SQL half

needs_sql = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds migration 0050 in disposable schemas; local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_nutusda_pytest"
OPS = "ops_nutusda_pytest"
CONFIG = "config_nutusda_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")

DAY = "2026-09-11"
WHEN = "2026-09-11 12:30:00+00"


def world(cur):
    """Migration 0050 verbatim over the spine, in disposable schemas, inside a transaction
    that rolls back (RULE-01's ADR-0022 exception). Nothing is committed."""
    for schema in (CORE, OPS, CONFIG):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"CREATE TABLE {CONFIG}.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                f"note TEXT)")
    root = Path(__file__).resolve().parents[1]
    # 0071 REVOKEs on `anon`/`authenticated`, which Supabase supplies and a bare PostgreSQL 17
    # cluster does not. Created idempotently exactly as `tests/_import_fixture.build_spine`
    # does; without them the chain dies on `role "anon" does not exist` and every test in the
    # file fails for a reason that has nothing to do with what it is testing.
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    # The nutrition migrations IN ORDER. 0071 adds `food_aliases`, which REQ-NUT-001 step (1)
    # reads and REQ-NUT-004 writes; a fixture that stopped at 0050 would exercise a resolver
    # against a schema the resolver no longer targets.
    for migration in ("0050_nutrition.sql", "0071_food_and_portion_aliases.sql"):
        body = (root / "migrations" / migration).read_text() \
            .replace("__CORE__", CORE).replace("__OPS__", OPS).replace("config.", f"{CONFIG}.")
        for stmt in split_statements(body):
            cur.execute(stmt)
    return cur


def capture(cur):
    """One food capture. INV-1 needs a real capture for the atoms to point at."""
    cap_id = uuid.uuid4()
    cur.execute(
        f"""insert into {CORE}.raw_captures
              (capture_id, captured_at, source, trust_level, payload, processing_status)
            values (%s, %s, 'shortcut_text', 'trusted', %s::jsonb, 'enriched')""",
        (cap_id, WHEN, json.dumps({"kind": "food"})))
    return cap_id


def cache_food(cur, name, source, nutrients, serving_g=None, brand=None, source_id=None):
    cur.execute(f"""insert into {CORE}.foods_cache
        (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g)
        values (%s,%s,%s,%s,%s::jsonb,%s)""",
        (name, source, source_id or name, brand, json.dumps(nutrients), serving_g))


def sources_for(cur, *, transport=None, usda_on=True, quota=None, env=None):
    """The REAL `build_sources`, with Open Food Facts switched off so the assertions are
    unambiguously about the USDA legs. `usda_transport` is what makes the legs live without
    a key ever being used against api.data.gov."""
    return nutrition.build_sources(
        cur, schema=CORE, ops=OPS, config=CONFIG, off=False, usda=usda_on,
        usda_transport=transport, usda_quota=quota,
        usda_env=KEY_ENV if env is None else env)


def calls(sources):
    return {name: leg.calls for name, leg in sources.items()}


def walk(result_or_tried):
    tried = result_or_tried["tried"] if isinstance(result_or_tried, dict) else result_or_tried
    return [(t["source"], t["outcome"]) for t in tried if "outcome" in t]


def egress_rows(cur):
    """Every outbound call RULE-29 logged, SORTED — deliberately not in issue order.

    `egress_log.egress_id` is a `gen_random_uuid()` primary key and `occurred_at` defaults to
    `now()`, which in PostgreSQL is transaction start and therefore identical for every row
    written inside one rolled-back fixture. Neither column orders these rows, so ordering by
    one would make an assertion that passes or fails by luck. The ORDER of the walk is a real
    fact and it is asserted from `walk(result)`, which the cascade records itself.
    """
    cur.execute(f"select destination, purpose from {OPS}.egress_log")
    return sorted(tuple(row) for row in cur.fetchall())


def cached_rows(cur, name=None):
    sql = (f"select canonical_name, source, source_id, brand, nutrients_per_100g, serving_g "
           f"from {CORE}.foods_cache")
    params = []
    if name:
        sql += " where canonical_name = %s"
        params.append(name)
    cur.execute(sql + " order by canonical_name, source_id", params)
    return [tuple(row) for row in cur.fetchall()]


def current_atoms(cur, metric=None):
    """What a downstream reader sees. `atoms_current` is the view the panel and `ask` read."""
    sql = (f"select metric_key, value_low, value_point, value_high, estimate_method, unit, "
           f"provenance from {CORE}.atoms_current where kind = 'consume' "
           f"and metric_key is not null")
    params = []
    if metric:
        sql += " and metric_key = %s"
        params.append(metric)
    cur.execute(sql + " order by metric_key", params)
    return [tuple(row) for row in cur.fetchall()]


# ---------------------------------------------------------------- cache hit / cache miss

@needs_sql
def test_REQ_NUT_002_a_cached_food_never_reaches_the_usda_legs(sql_connection):
    """ACCEPTANCE: a cache hit avoids the external call.

    Asserted three ways, because each alone is weak. The transport FAILS if called — a call
    count cannot tell "we did not ask" from "we asked and ignored the answer". The USDA legs
    record zero calls. And `ops.egress_log`, the row RULE-29 requires for every outbound call,
    is empty.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "synthetic rolled oats", FOUNDATION, {"kcal": 380.0}, serving_g=50.0)
    sources = sources_for(cur, transport=forbidden_transport)

    result = nutrition.resolve_item(cur, "synthetic rolled oats", servings=1, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["from_cache"] is True
    assert result["source"] == FOUNDATION, "the cache reports the ROW's source, not `joe`"
    assert calls(sources) == {"joe": 1, BRANDED: 0, FOUNDATION: 0}
    assert egress_rows(cur) == []


@needs_sql
def test_REQ_NUT_001_a_cache_miss_reaches_the_configured_usda_cascade(sql_connection):
    """ACCEPTANCE: a cache miss reaches the configured cascade, and the answer is stored.

    This is the test that would have been impossible before this session: with both USDA legs
    as `UnconfiguredLeg` there was no path from a cache miss to a USDA answer at all.
    """
    cur = world(sql_connection.cursor())
    log = []
    sources = sources_for(cur, transport=search_transport([foundation_food()], log))

    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["source"] == FOUNDATION
    assert result["from_cache"] is False
    assert calls(sources) == {"joe": 1, BRANDED: 1, FOUNDATION: 1}, \
        "the branded leg was asked first and did not know it"
    assert walk(result)[-1] == (FOUNDATION, "match")
    # REQ-NUT-003: the answer is now a `foods_cache` row, keyed on the fdcId (REQ-NUT-005).
    assert result["food_id"] is not None
    rows = cached_rows(cur, "Synthetic Rolled Oats")
    assert [(r[1], r[2]) for r in rows] == [(FOUNDATION, "999500")]
    # RULE-29: every outbound call is logged, to the allowlisted host.
    assert egress_rows(cur) == [("api.nal.usda.gov", "nutrition:usda_branded_search"),
                                ("api.nal.usda.gov", "nutrition:usda_foundation_search")], \
        "both legs were asked, and both calls are logged to the allowlisted host"
    assert all("api_key=SYNTHETICKEYNOTREAL" in u for u in log), "FDC keys by query parameter"


@needs_sql
def test_REQ_NUT_013_the_brand_token_is_included_in_the_branded_query(sql_connection):
    """REQ-NUT-013: the restaurant or brand token goes INTO the USDA Branded search query.

    Asserted on the URL that was actually built, not on a parameter this test passed in.
    """
    cur = world(sql_connection.cursor())
    log = []
    sources = sources_for(cur, transport=search_transport([branded_food()], log))

    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=40, brand="Examplo Foods",
                                    sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    assert result["source"] == BRANDED
    assert len(log) == 1, "a branded item asks the branded leg and stops"
    assert "Examplo+Foods+Synthetic+Crunch+Bar" in log[0]
    assert "dataType=Branded" in log[0]


@needs_sql
def test_REQ_NUT_016_a_branded_item_never_falls_back_to_the_foundation_leg(sql_connection):
    """The rule that matters most. A generic laboratory analysis is not a restaurant portion.

    The Branded leg is asked and does not know the item; `usda_foundation` is then SKIPPED
    rather than asked, and the item stays unresolved with its brand token intact.
    """
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([foundation_food()]))

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, brand="Examplo Foods",
                               sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    outcomes = dict(walk(e.value.tried))
    assert outcomes[FOUNDATION] == "skipped_generic_source_for_branded_item"
    assert calls(sources)[FOUNDATION] == 0, "skipped means not called, not called and discarded"
    assert e.value.brand == "Examplo Foods", "the restaurant token survives verbatim"


# ---------------------------------------------------------------- human corrections

@needs_sql
def test_RULE_10_a_correction_from_joe_outranks_the_usda_legs(sql_connection):
    """ACCEPTANCE: human corrections outrank source results.

    Joe's own row sits in `foods_cache` with `source = 'joe'`, and the cache leg is step 1 of
    the cascade — so a corrected food never reaches USDA at all. The transport fails if it is
    called, which is what makes "outranks" mean "was never asked" rather than "was overridden
    afterwards".
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "Synthetic Crunch Bar", "joe", {"kcal": 111.0}, serving_g=40.0)
    sources = sources_for(cur, transport=forbidden_transport)

    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["source"] == "joe"
    assert result["nutrients"]["kcal"][1] == 111.0, "Joe's number, not a source's"
    assert calls(sources)[BRANDED] == 0 and egress_rows(cur) == []


@needs_sql
def test_RULE_10_joes_correction_survives_a_second_resolution_pass(sql_connection):
    """A nightly re-run must not quietly replace a correction with the source it corrected."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "Synthetic Crunch Bar", "joe", {"kcal": 111.0}, serving_g=40.0)
    cache_food(cur, "Synthetic Crunch Bar", BRANDED, {"kcal": 450.0}, serving_g=40.0,
               brand="Examplo Foods", source_id="999001")
    for _ in range(2):
        sources = sources_for(cur, transport=forbidden_transport)
        result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=100,
                                        sources=sources, schema=CORE, config=CONFIG, ops=OPS)
        assert result["source"] == "joe" and result["nutrients"]["kcal"][1] == 111.0


# ---------------------------------------------------------------- the five distinct failures

@needs_sql
def test_REQ_NUT_024_an_unavailable_source_is_not_a_statement_about_the_food(sql_connection):
    """ACCEPTANCE: failure produces an accurate unresolved status — and WHICH failure matters.

    No key means nothing was ever going to resolve. Reporting that as `no_source_match` would
    hand Joe a review list of foods to answer a question about an environment variable, so the
    reason is `no_source_available` and `review_reason` is None.
    """
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=forbidden_transport, env={})

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_available"
    assert e.value.review_reason is None, "an operations problem does not go on the review list"
    outcomes = dict(walk(e.value.tried))
    assert outcomes[BRANDED] == outcomes[FOUNDATION] == "not_configured"
    detail = next(t for t in e.value.tried if t["source"] == BRANDED)["detail"]
    assert "api.data.gov" in detail, "the refusal says what to do about it"


@needs_sql
def test_REQ_NUT_015_no_match_is_a_statement_about_the_food_and_reaches_review(sql_connection):
    """Both legs were ASKED and neither knew the food. That IS evidence about the food."""
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([]))       # an empty result set

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Unknown Thing", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_match"
    assert e.value.review_reason == "no_source_match"
    assert dict(walk(e.value.tried))[BRANDED] == "no_match"


@needs_sql
def test_REQ_NUT_025_an_ambiguous_match_is_unresolved_and_not_a_tie_break(sql_connection):
    """Two foods of the same name is a question for Joe. The reason is kept so he can see it
    was ambiguity rather than absence — they lead to different answers from him."""
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport(
        [foundation_food(fdc_id=1), foundation_food(fdc_id=2)]))

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_match"
    reasons = [t.get("reason") for t in e.value.tried if t.get("source") == FOUNDATION]
    assert "ambiguous_exact_match" in reasons
    assert cached_rows(cur) == [], "an ambiguous lookup stores nothing"


@needs_sql
def test_REQ_NUT_012_a_429_leaves_the_item_unresolved_and_substitutes_nothing(sql_connection):
    """REQ-NUT-012: stop, leave the item unresolved, and do NOT substitute another food.

    The last clause is the one worth proving: a generic oat record is sitting in the cache
    under a different name, and the refusal does not reach for it.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "oats generic", FOUNDATION, {"kcal": 380.0}, serving_g=50.0)
    quota = usda.Quota()
    sources = sources_for(cur, transport=failing_transport(Http429()), quota=quota)

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    outcomes = dict(walk(e.value.tried))
    assert outcomes[BRANDED] == "rate_limited_now"
    # The shared quota means the SECOND leg never issues a request at all.
    assert outcomes[FOUNDATION] == "rate_limited_now"
    assert quota.blocked_for(now=None) > 0
    assert e.value.reason == "no_source_available", \
        "a throttled source was not ASKED, so this is not evidence about the food"
    assert cached_rows(cur, "Synthetic Rolled Oats") == []


@needs_sql
def test_a_malformed_response_is_no_match_and_not_an_outage(sql_connection):
    """A record that exists and cannot be read is a fact about the food. A 503 is not, and
    filing one as the other turns a transient outage into a permanent gap."""
    cur = world(sql_connection.cursor())
    broken = foundation_food(foodNutrients=[{"nutrientId": 1008, "unitName": "furlongs",
                                             "value": 5.0}])
    sources = sources_for(cur, transport=search_transport([broken]))

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_match", "asked and answered unusably"
    reasons = [t.get("reason") for t in e.value.tried if t.get("source") == FOUNDATION]
    assert "no_readable_nutrient" in reasons


@needs_sql
def test_a_transport_failure_is_an_outage_and_not_a_missing_food(sql_connection):
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=failing_transport(RuntimeError("connection reset")))

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_available"
    assert dict(walk(e.value.tried))[BRANDED] == "request_failed"


@needs_sql
def test_REQ_NUT_009_an_exhausted_quota_defers_rather_than_reporting_a_missing_food(
        sql_connection):
    """Our own ceiling and the provider's 429 both stop USDA, and the cascade treats them
    alike — but the record must still say which happened, because only one is a complaint
    from api.data.gov and only one means the key is at risk."""
    cur = world(sql_connection.cursor())
    quota = usda.Quota(max_requests=0)
    sources = sources_for(cur, transport=forbidden_transport, quota=quota)

    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    assert e.value.reason == "no_source_available"
    detail = next(t for t in e.value.tried if t["source"] == BRANDED).get("detail", "")
    outcome = dict(walk(e.value.tried))[BRANDED]
    assert outcome == "rate_limited_now"
    assert egress_rows(cur) == [], "a deferred request is not issued, so nothing is logged"


# ---------------------------------------------------------------- intervals and persistence

@needs_sql
def test_REQ_NUT_035_a_usda_result_becomes_a_traced_interval_not_a_point(sql_connection):
    """ACCEPTANCE: reference results become correctly traced nutrient intervals.

    RULE-08: a point estimate is a lie about precision. A weighed quantity removes portion
    error but not composition error, so it takes the `weighed` width rather than collapsing.
    The arithmetic is checked against the stored width, not against a number typed here.
    """
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([foundation_food()]))

    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=200, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    low, point, high = result["nutrients"]["kcal"]
    assert point == 760.0, "380 kcal/100 g at 200 g, computed not asserted"
    assert low < point < high, "an interval, not a point (RULE-08)"
    widths = nutrition.interval_widths(cur, CONFIG)
    assert (low, point, high) == nutrition.apply_width(760.0, result["method"], widths)
    assert result["method"] == "weighed", "a stated weight is not a portion guess"
    assert result["estimate_method"] == FOUNDATION, \
        "the width APPLIED and the claim the source MADE are different facts"


@needs_sql
def test_REQ_NUT_014_a_branded_resolution_is_labelled_and_keeps_its_brand_owner(sql_connection):
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([branded_food()]))

    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=40, brand="Examplo Foods",
                                    sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    assert result["estimate_method"] == "labelled"
    assert result["brand"] == "Examplo Foods"


@needs_sql
def test_REQ_NUT_019_a_serving_count_uses_the_sources_own_serving_mass(sql_connection):
    """Serving semantics: two servings of a 40 g bar is 80 g, and the 40 comes from the FDC
    record rather than from a default this system invented."""
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([branded_food()]))

    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", servings=2, brand="Examplo Foods",
                                    sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    assert result["grams"] == 80.0
    assert result["nutrients"]["kcal"][1] == 360.0, "450 kcal/100 g at 80 g"


@needs_sql
def test_persistence_and_retrieval_preserve_unit_method_and_provenance(sql_connection):
    """ACCEPTANCE: persistence and retrieval preserve units, method and provenance.

    Retrieval goes through `atoms_current` — the view the panel and `ask` actually read —
    rather than through `atoms`, because an interval only a direct table select can see is an
    interval no downstream reader retrieves.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    sources = sources_for(cur, transport=search_transport([branded_food()]))
    result = nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=40, brand="Examplo Foods",
                                    sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    written = nutrition.persist_resolution(
        cur, result, raw_capture_id=cap, occurred_at=WHEN, subject_day=DAY,
        evidence_span="a synthetic crunch bar", schema=CORE)

    assert "kcal" in written
    rows = {r[0]: r for r in current_atoms(cur)}
    metric, low, point, high, method, unit, provenance = rows["kcal"]
    assert (float(low), float(point), float(high)) == result["nutrients"]["kcal"]
    assert method == "labelled", "REQ-NUT-014's claim survives the write"
    assert unit == "kcal", "the unit comes from metric_registry, not from the resolver"
    assert provenance == "inferred", "RULE-05/INV-5: a nutrient was never observed in a capture"
    assert rows["sodium_mg"][5] == "mg", "milligrams stay milligrams end to end"


@needs_sql
def test_the_stored_row_carries_the_fdc_id_so_the_number_can_be_rechecked(sql_connection):
    """REQ-NUT-005, end to end: from payload, through `foods_cache`, to something auditable."""
    cur = world(sql_connection.cursor())
    sources = sources_for(cur, transport=search_transport([branded_food(fdc_id=424242)]))
    nutrition.resolve_item(cur, "Synthetic Crunch Bar", grams=40, brand="Examplo Foods",
                           sources=sources, schema=CORE, config=CONFIG, ops=OPS)

    cur.execute(f"""select source, source_id, raw -> 'parse' ->> 'data_type',
                           raw -> 'parse' -> 'nutrient_provenance' -> 'kcal' ->> 'fdc_nutrient_id'
                      from {CORE}.foods_cache where canonical_name = 'Synthetic Crunch Bar'""")
    source, source_id, data_type, kcal_id = cur.fetchone()
    assert (source, source_id, data_type, kcal_id) == (BRANDED, "424242", "Branded", "1008")


# ---------------------------------------------------------------- idempotence

@needs_sql
def test_repeated_resolution_does_not_duplicate_the_cache_row(sql_connection):
    """ACCEPTANCE: repeated processing does not duplicate records.

    Second pass: the cache leg answers, so the transport is not reached at all and no second
    `foods_cache` row appears. That is REQ-NUT-002 and idempotence proving each other.
    """
    cur = world(sql_connection.cursor())
    first = sources_for(cur, transport=search_transport([foundation_food()]))
    nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=first,
                           schema=CORE, config=CONFIG, ops=OPS)
    before = cached_rows(cur)

    second = sources_for(cur, transport=forbidden_transport)
    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=second,
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["from_cache"] is True
    assert cached_rows(cur) == before, "no second row for the same food"
    assert len(egress_rows(cur)) == 2, "no third outbound call on the second pass"


@needs_sql
def test_repeated_persistence_does_not_double_a_days_calories(sql_connection):
    """The nightly resolver runs again tomorrow over the same capture. Twice the atoms would
    be twice the calories, and nothing downstream could tell that had happened."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    sources = sources_for(cur, transport=search_transport([foundation_food()]))
    result = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100, sources=sources,
                                    schema=CORE, config=CONFIG, ops=OPS)

    first = nutrition.persist_resolution(
        cur, result, raw_capture_id=cap, occurred_at=WHEN, subject_day=DAY,
        evidence_span="synthetic rolled oats", schema=CORE)
    second = nutrition.persist_resolution(
        cur, result, raw_capture_id=cap, occurred_at=WHEN, subject_day=DAY,
        evidence_span="synthetic rolled oats", schema=CORE)

    assert first and second == [], "the second pass writes nothing"
    assert len(current_atoms(cur, "kcal")) == 1


@needs_sql
def test_an_unresolved_item_is_not_added_to_the_review_list_twice(sql_connection):
    """A nightly re-run must not grow Joe's review list by one row per night for the same
    sandwich. REQ-NUT-027: unresolved is a normal outcome that recurs, not an error."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    sources = sources_for(cur, transport=search_transport([]))
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "Synthetic Unknown Thing", grams=100, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)

    first = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                        schema=CORE)
    second = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                         schema=CORE)

    assert first is not None and second is None
    cur.execute(f"select count(*) from {CORE}.unresolved_items")
    assert cur.fetchone()[0] == 1


# ---------------------------------------------------------------- the shipped storage shape

@needs_sql
def test_REQ_NUT_030_031_032_the_shipped_schema_stores_intervals_not_points(sql_connection):
    """REQ-NUT-030/031/032 were asserted only against `ontology_contract.check_storage_columns`
    — a function that refuses the STRING "kcal". That is a contract about a name; this is the
    table a nutrient actually lands in.

    The requirements name `kcal_low/_point/_high`. The system stores every nutrient as one
    `core.atoms` row per `metric_key` with a generic `value_low/_point/_high` triple, which
    satisfies them for energy and for every macronutrient at once rather than per nutrient.
    That is a real design decision and it deserves evidence at the schema, not a restatement.

    Migrations are the main session's to change; verifying what they shipped is a test.
    """
    cur = world(sql_connection.cursor())
    cur.execute("""select column_name, is_nullable from information_schema.columns
                    where table_schema = %s and table_name = 'atoms'""", (CORE,))
    columns = {name: nullable for name, nullable in cur.fetchall()}

    # REQ-NUT-030/031: the triple exists, for energy and macros alike.
    for needed in ("value_low", "value_point", "value_high", "metric_key"):
        assert needed in columns, f"{needed} missing from {CORE}.atoms"
    # REQ-NUT-030: and no column holds energy as a single unqualified number.
    for scalar in ("kcal", "calories", "energy", "value"):
        assert scalar not in columns, \
            f"{CORE}.atoms.{scalar} would hold energy as one unqualified number"
    # REQ-NUT-032: every row carrying an interval carries its method.
    assert "estimate_method" in columns

    # REQ-NUT-034, enforced by the database rather than by the resolver: asserted here because
    # a constraint nothing tries to violate is a constraint nobody knows is enabled.
    cap = capture(cur)
    cur.execute(f"select unit, state_class from {CORE}.metric_registry where metric_key = 'kcal'")
    unit, state_class = cur.fetchone()
    with pytest.raises(Exception) as e:
        cur.execute(
            f"""insert into {CORE}.atoms
                  (raw_capture_id, kind, metric_key, occurred_at, time_precision, subject_day,
                   subject_day_rule_version, presence, value_low, value_point, value_high,
                   estimate_method, unit, state_class, trust_level, provenance, code_version)
                values (%s, 'consume', 'kcal', %s, 'hour', %s, %s, 'observed',
                        500, 100, 900, 'labelled', %s, %s, 'trusted', 'inferred', 'probe')""",
            (cap, WHEN, DAY, nutrition.SUBJECT_DAY_RULE_VERSION, unit, state_class))
    assert "value" in str(e.value).lower() or "check" in str(e.value).lower(), \
        f"low > point was accepted, or failed for an unrelated reason: {e.value}"
    sql_connection.rollback()      # the failed statement poisons the transaction


# ---------------------------------------------------------------- REQ-NUT-017, the loop closes

@needs_sql
def test_REQ_NUT_017_joes_answer_writes_the_cache_row_the_alias_and_clears_the_item(
        sql_connection):
    """The review list was WRITE-ONLY. This is the path that empties it.

    `record_unresolved` filled `unresolved_items` every night and nothing could ever resolve a
    row, so the same item was re-asked, re-refused and re-listed indefinitely. All three writes
    REQ-NUT-017 names are asserted, because any one alone leaves the loop open.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    sources = sources_for(cur, transport=search_transport([]))
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150, sources=sources,
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)
    assert item_id is not None

    out = nutrition.accept_correction(cur, item_id, {"kcal": 250.0, "protein_g": 12.0},
                                      supplied_by="joe", serving_g=150.0, schema=CORE)

    # 1. the `foods_cache` row, with source 'joe'
    assert out["food_id"] is not None
    rows = cached_rows(cur, "the thing from the deli")
    assert [(r[1], r[2]) for r in rows] == [("joe", "the thing from the deli")]
    # 2. the alias. It IS written even though the phrase equals the canonical name. The old
    #    bridge skipped that case because a second `foods_cache` row would have been pure
    #    duplication; a `food_aliases` row is not, REQ-NUT-004 does not exempt it, and step (1)
    #    of REQ-NUT-001 should not depend on which spelling a food was resolved under.
    assert out["alias_id"] is not None
    cur.execute(f"select alias, verbatim, source from {CORE}.food_aliases")
    assert [tuple(r) for r in cur.fetchall()] == [
        ("the thing from the deli", "the thing from the deli", "joe")]
    # 3. the item leaves the review list, attributed
    cur.execute(f"select resolved_at is not null, resolved_by from {CORE}.unresolved_items "
                f"where item_id = %s", (item_id,))
    assert tuple(cur.fetchone()) == (True, "joe")


@needs_sql
def test_REQ_NUT_017_the_answer_then_resolves_the_food_without_asking_any_source(sql_connection):
    """The point of the three writes: the NEXT time those words are said, nothing is asked.

    This is the requirement that makes the review list worth maintaining, and it is asserted
    end to end — refuse, answer, then resolve again through the production entry point with a
    transport that fails if it is called.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources=sources_for(cur, transport=search_transport([])),
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)
    nutrition.accept_correction(cur, item_id, {"kcal": 250.0}, supplied_by="joe",
                                serving_g=150.0, schema=CORE)
    # The two calls the FIRST attempt made are already logged; what matters is that the
    # attempt after the answer adds none. Asserting an empty log here would assert the wrong
    # thing and would have passed only because the refusal happened to be free.
    before = len(egress_rows(cur))
    assert before == 2, "the first attempt did ask both USDA legs"

    result = nutrition.resolve_item(cur, "the thing from the deli", grams=100,
                                    sources=sources_for(cur, transport=forbidden_transport),
                                    schema=CORE, config=CONFIG, ops=OPS)

    assert result["source"] == "joe"
    assert result["nutrients"]["kcal"][1] == 250.0
    assert len(egress_rows(cur)) == before, "the answered food never reaches a source again"


@needs_sql
def test_REQ_NUT_017_an_alias_is_written_when_the_phrase_differs_from_the_name(sql_connection):
    """Joe answers "the thing from the deli" with a proper name. REQ-NUT-004: the phrase AS
    UTTERED must resolve next time, or he is asked the same question after saying the same
    words."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources=sources_for(cur, transport=search_transport([])),
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)

    out = nutrition.accept_correction(cur, item_id, {"kcal": 250.0}, supplied_by="joe",
                                      canonical_name="Turkey and Swiss Sandwich",
                                      serving_g=150.0, schema=CORE)
    assert out["alias_id"] is not None

    # Both the proper name and the phrase as uttered now resolve, from the cache, to Joe's row.
    for phrase in ("Turkey and Swiss Sandwich", "the thing from the deli"):
        result = nutrition.resolve_item(cur, phrase, grams=100,
                                        sources=sources_for(cur, transport=forbidden_transport),
                                        schema=CORE, config=CONFIG, ops=OPS)
        assert result["source"] == "joe" and result["nutrients"]["kcal"][1] == 250.0


@needs_sql
def test_REQ_NUT_017_answering_the_same_item_twice_writes_nothing_the_second_time(sql_connection):
    """A review list that re-opens on a second submission is a review list that grows."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources=sources_for(cur, transport=search_transport([])),
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)
    first = nutrition.accept_correction(cur, item_id, {"kcal": 250.0}, supplied_by="joe",
                                        schema=CORE)
    second = nutrition.accept_correction(cur, item_id, {"kcal": 999.0}, supplied_by="joe",
                                         schema=CORE)
    assert first is not None and second is None
    assert len(cached_rows(cur, "the thing from the deli")) == 1
    cur.execute(f"select nutrients_per_100g ->> 'kcal' from {CORE}.foods_cache "
                f"where canonical_name = 'the thing from the deli'")
    assert cur.fetchone()[0] == "250.0", "the second answer did not overwrite the first"


@needs_sql
def test_RULE_09_a_correction_must_name_the_person_who_supplied_it(sql_connection):
    """The one place a nutrient value enters from outside a source is a HUMAN path.

    RULE-09 keeps models from supplying figures. REQ-NUT-017's permission is for Joe, and a
    call site that cannot name a person cannot use the function — `supplied_by` is mandatory
    and checked before anything is written, so the refusal names the rule rather than arriving
    as a CHECK-constraint violation three writes later.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources=sources_for(cur, transport=search_transport([])),
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)

    for who in ("model", "workers_ai", "", None):
        with pytest.raises(nutrition.CorrectionRefused, match="RULE-09"):
            nutrition.accept_correction(cur, item_id, {"kcal": 250.0}, supplied_by=who,
                                        schema=CORE)
    assert cached_rows(cur, "the thing from the deli") == [], "nothing was written"


@needs_sql
def test_RULE_01_an_impossible_correction_is_refused_not_clamped(sql_connection):
    """Joe is authoritative about what he ate; he is not exempt from arithmetic.

    A typed 3000 where 300 was meant would enter as a `joe` row — the one source nothing
    outranks — and stay wrong until he noticed. A source payload's unreadable field is dropped
    and the rest kept; a person's answer is REFUSED whole, because it is a question that can
    be re-asked.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources=sources_for(cur, transport=search_transport([])),
                               schema=CORE, config=CONFIG, ops=OPS)
    item_id = nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY,
                                          schema=CORE)

    for bad, match in (({"protein_g": 300.0}, "physical ceiling"),
                       ({"kcal": -5.0}, "negative"),
                       ({"kcal": "not a number"}, "not a number"),
                       ({"calories": 250.0}, "not nutrients this system stores"),
                       ({}, "at least one nutrient")):
        with pytest.raises(nutrition.CorrectionRefused, match=match):
            nutrition.accept_correction(cur, item_id, bad, supplied_by="joe", schema=CORE)
    assert cached_rows(cur, "the thing from the deli") == []

    # And the item is still open, so the question can be asked again.
    cur.execute(f"select resolved_at from {CORE}.unresolved_items where item_id = %s", (item_id,))
    assert cur.fetchone()[0] is None


# ------------------------------------------------- REQ-NUT-001 step (1): food_aliases (0071)

@needs_sql
def test_REQ_NUT_001_REQ_NUT_002_an_alias_hit_serves_from_cache_with_no_network_request(
        sql_connection):
    """Step (1) of the resolution order is a `food_aliases` exact match, and REQ-NUT-002 says a
    hit there reads nutrients from `foods_cache` and issues NO network request.

    Proved with a transport that FAILS if called, so "no request" is demonstrated rather than
    inferred from a count.
    """
    cur = world(sql_connection.cursor())
    first = nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100,
                                   sources=sources_for(cur, transport=search_transport(
                                       [foundation_food()])),
                                   schema=CORE, config=CONFIG, ops=OPS)
    assert first["alias_id"] is not None
    calls_before = len(egress_rows(cur))

    # A DIFFERENT utterance of the same food, taught by hand — the shape REQ-NUT-004 creates.
    cur.execute(f"""insert into {CORE}.food_aliases (alias, verbatim, food_id, source)
                    select 'me oats', 'me oats', food_id, source from {CORE}.foods_cache
                     where canonical_name = 'Synthetic Rolled Oats'""")

    out = nutrition.resolve_item(cur, "me oats", grams=100,
                                 sources=sources_for(cur, transport=forbidden_transport),
                                 schema=CORE, config=CONFIG, ops=OPS)

    assert out["from_cache"] is True
    assert out["canonical_name"] == "Synthetic Rolled Oats", "the alias resolved to the food"
    assert out["source"] == FOUNDATION, "the row's own provenance, not 'joe' (RULE-10/INV-5)"
    assert out["nutrients"]["kcal"] == first["nutrients"]["kcal"]
    assert len(egress_rows(cur)) == calls_before, "REQ-NUT-002: no network request on an alias hit"


@needs_sql
def test_RULE_10_a_correction_outranks_a_food_reached_through_an_alias(sql_connection):
    """The ordering risk the union in `lookup_cached` exists to prevent.

    An alias points at exactly ONE food_id. If step (1) were consulted first and returned its
    row, an alias learned from a source would outrank a correction Joe made later for the same
    food — the resolver would answer with the source figure and never look at Joe's. Both sets
    are collected and the union is ranked by SOURCE_PRECEDENCE instead, so `joe` stays ahead
    however the row was reached.

    Written as a test because the sequential version passes every other test in this file.
    """
    cur = world(sql_connection.cursor())
    nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100,
                           sources=sources_for(cur, transport=search_transport(
                               [foundation_food()])),
                           schema=CORE, config=CONFIG, ops=OPS)
    # The alias points at the FOUNDATION row...
    cur.execute(f"""insert into {CORE}.food_aliases (alias, verbatim, food_id, source)
                    select 'porridge', 'porridge', food_id, source from {CORE}.foods_cache
                     where canonical_name = 'Synthetic Rolled Oats'""")
    # ...and Joe then corrects that same phrase.
    cache_food(cur, "porridge", "joe", {"kcal": 42.0}, serving_g=100.0)

    out = nutrition.resolve_item(cur, "porridge", grams=100,
                                 sources=sources_for(cur, transport=forbidden_transport),
                                 schema=CORE, config=CONFIG, ops=OPS)

    assert out["source"] == "joe", "the alias must not outrank a human correction"
    assert out["nutrients"]["kcal"][1] == 42.0, "Joe's number, not the source's 380"


@needs_sql
def test_REQ_NUT_004_the_alias_is_learned_once_however_often_the_phrase_recurs(sql_connection):
    """`UNIQUE (alias, food_id)` with ON CONFLICT DO NOTHING. A nightly re-run of the same
    capture must not grow the table by one row per night for the same sandwich."""
    cur = world(sql_connection.cursor())
    for _ in range(3):
        nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100,
                               sources=sources_for(cur, transport=search_transport(
                                   [foundation_food()])),
                               schema=CORE, config=CONFIG, ops=OPS)
    cur.execute(f"select count(*) from {CORE}.food_aliases")
    assert cur.fetchone()[0] == 1
    cur.execute(f"select count(*) from {CORE}.foods_cache")
    assert cur.fetchone()[0] == 1, "and no second cache row either"


@needs_sql
def test_REQ_NUT_004_an_alias_is_still_learned_for_a_food_already_in_the_cache(sql_connection):
    """`insert_cache_row` returns None when ON CONFLICT fired, which is the ordinary case for a
    food already cached. If the alias were skipped on that path a phrase would only ever be
    learned the very first time a food was seen — so `cached_food_id` reads the id back."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "Synthetic Rolled Oats", FOUNDATION, {"kcal": 380.0}, serving_g=50.0,
               source_id="999500")
    cur.execute(f"select count(*) from {CORE}.food_aliases")
    assert cur.fetchone()[0] == 0

    row = {"canonical_name": "Synthetic Rolled Oats", "source": FOUNDATION,
           "source_id": "999500"}
    alias_id = nutrition.remember_alias(cur, "  Me Oats  ", row, schema=CORE)

    assert alias_id is not None
    cur.execute(f"select alias, verbatim from {CORE}.food_aliases")
    assert [tuple(r) for r in cur.fetchall()] == [("me oats", "  Me Oats  ")], \
        "folded for matching, verbatim as uttered — REQ-NUT-004 means the second one"


@needs_sql
def test_an_alias_pointing_at_a_deleted_food_does_not_survive_it(sql_connection):
    """`ON DELETE CASCADE` in 0071. An alias resolving to nothing would be a phrase that reads
    as known and returns no nutrients — worse than an unknown phrase, which at least asks."""
    cur = world(sql_connection.cursor())
    nutrition.resolve_item(cur, "Synthetic Rolled Oats", grams=100,
                           sources=sources_for(cur, transport=search_transport(
                               [foundation_food()])),
                           schema=CORE, config=CONFIG, ops=OPS)
    cur.execute(f"select count(*) from {CORE}.food_aliases")
    assert cur.fetchone()[0] == 1
    cur.execute(f"delete from {CORE}.foods_cache where canonical_name = 'Synthetic Rolled Oats'")
    cur.execute(f"select count(*) from {CORE}.food_aliases")
    assert cur.fetchone()[0] == 0


# ---------------------------------------------------------------- RULE-01 / ADR-0082

@needs_sql
def test_RULE_29_the_api_key_reaches_neither_the_egress_log_nor_an_exception(sql_connection):
    """The key is a credential and it travels as a query parameter, because that is FDC's
    design rather than a choice made here. Two places it must not end up:

      * `ops.egress_log`, which records the host, the purpose, the path and the parameter
        COUNT — never the values. A log that reproduced the request would hold the key and a
        second copy of what Joe ate.
      * an exception, which a nightly job writes to its own log by a different route.

    Run with a real cursor and a real failure, so the request path is actually walked. An
    earlier version of this test passed `cur=None` and therefore proved nothing: it failed
    inside `egress.get_json` before the transport was ever reached.
    """
    cur = world(sql_connection.cursor())
    quota = usda.Quota()
    with pytest.raises(usda.UsdaTransient) as e:
        usda.search_foods(cur, "Synthetic Rolled Oats", FOUNDATION, quota=quota, env=KEY_ENV,
                          schema=CORE, ops=OPS, config=CONFIG,
                          _transport=failing_transport(RuntimeError("connection reset")))
    assert "SYNTHETICKEYNOTREAL" not in json.dumps(e.value.detail) + str(e.value)

    cur.execute(f"select purpose, detail::text from {OPS}.egress_log")
    rows = cur.fetchall()
    assert len(rows) == 1, "the attempt is logged even though it failed"
    purpose, detail = rows[0]
    assert purpose == "nutrition:usda_foundation_search"
    assert "SYNTHETICKEYNOTREAL" not in detail
    assert "Synthetic Rolled Oats" not in detail, \
        "the query carries what Joe ate and is not reproduced in the audit trail"


@needs_sql
def test_RULE_01_a_disposable_server_run_does_not_get_a_live_usda_transport(sql_connection):
    """A resolver pointed at a throwaway database must not spend one of REQ-NUT-009's 900 real
    slots or drop a live third-party payload into a fixture.

    This is the default path in this very test run — `PERSONAL_OS_TEST_SOCKET` is set — so it
    is asserted by building sources WITHOUT an injected transport and finding the legs
    unconfigured. A test that wants the leg injects one, which is visible in the call.
    """
    cur = world(sql_connection.cursor())
    sources = nutrition.build_sources(cur, schema=CORE, ops=OPS, config=CONFIG, off=False,
                                      usda_env=KEY_ENV)
    for name in (BRANDED, FOUNDATION):
        assert isinstance(sources[name], nutrition.UnconfiguredLeg)
        assert sources[name].detail == nutrition.USDA_TRANSPORT_REFUSED
    assert nutrition_cascade.resolvable_sources(sources) == ("joe",)


def test_REQ_NUT_013_014_food_category_does_not_establish_supplier_identity():
    food=branded_food(brand_owner='Examplo Foods',brandedFoodCategory='Snack Bars')
    with pytest.raises(usda.UsdaNotFound):
        usda.select_exact_match(food['description'],[food],BRANDED,brand='Snack Bars')
    food['brandOwner']=None
    food['brandName']=None
    with pytest.raises(usda.UsdaMalformed,match='branded_without_brand_owner'):
        usda.parse_food(food,BRANDED)


def test_REQ_NUT_016_retained_source_identity_overrules_misparsed_cache_brand():
    assert not nutrition.cached_row_answers_brand('usda_branded','Snack Bars','Snack Bars',
        {'usda_food':{'brandedFoodCategory':'Snack Bars'}})
    assert not nutrition.cached_row_answers_brand('usda_branded','Wrong','Wrong',
        {'usda_food':{'brandOwner':'Examplo'}})
    assert nutrition.cached_row_answers_brand('usda_branded','Wrong','Examplo',
        {'usda_food':{'brandOwner':'Examplo'}})
    assert not nutrition.cached_row_answers_brand('off_product','Wrong','Wrong',
        {'off_product':{'brands':'Examplo, Other'}})
    assert nutrition.cached_row_answers_brand('off_product','Wrong','Other',
        {'off_product':{'brands':'Examplo, Other'}})


def test_REQ_NUT_014_nontext_supplier_fields_do_not_create_manufacturer_identity():
    with pytest.raises(usda.UsdaMalformed,match='branded_without_brand_owner'):
        usda.parse_food(branded_food(brand_owner=None,brandName=True,brandedFoodCategory='Snack Bars'),BRANDED)


def test_REQ_NUT_014_unbranded_cache_query_cannot_label_a_category_as_manufacturer():
    class Cursor:
        def execute(self,*args):pass
        def fetchall(self):
            return [('Fixture bar','usda_branded',{'kcal':450},40,'Snack Bars',
                     uuid.uuid4(),'fixture-category',{'usda_food':{'brandedFoodCategory':'Snack Bars'}},False)]
    assert nutrition.CacheLeg(Cursor())('Fixture bar',None) is None
