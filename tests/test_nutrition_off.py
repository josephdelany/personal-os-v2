"""B12 — the Open Food Facts source parser (REQ-NUT §D.1/§D.2/§D.5; ADR-0066).

Nothing here reaches the network. `tools/engines/nutrition_off.py` issues every request
through `lib.egress.get_json`, which takes an explicit `_transport` seam, so the etiquette,
the allowlist gate and the four distinguishable failure outcomes are all provable without an
IP address — and the seam is a parameter, so what is substituted is visible in the signature.

Every payload below is synthetic and shaped after the real API responses: the Open Food Facts
v2 product read and the legacy CGI text search. No real product record is committed, and no
personal data appears in this file.

The file is in two halves. The first needs no database at all — parsing, units, barcodes,
matching and rate limiting are pure functions and are tested as such. The second builds the
real migration 0050 in disposable schemas and rolls it back (RULE-01's ADR-0022 exception), so
the allowlist gate is proved against the actual allowlist rather than a stub of one.
"""
import datetime as dt
import inspect
import json
import os

import pytest

from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import nutrition_off as off


CONTACT = {"PERSONAL_OS_CONTACT_EMAIL": "someone@example.org"}   # synthetic, not Joe's


def call_kw(**kw):
    """The keywords every request path requires: the contact address and a fresh pair of
    REQ-NUT-011 windows. `limits` has no default in the module, so this is not convenience —
    it is the only way to call these functions at all."""
    return {"env": CONTACT, "limits": off.Limits(), **kw}


def nutriments(**kw):
    """A per-100 g nutriments block in Open Food Facts' own key shape."""
    base = {"energy-kcal_100g": 539.0, "proteins_100g": 6.3, "carbohydrates_100g": 57.5,
            "fat_100g": 30.9, "sugars_100g": 56.3, "salt_100g": 0.107}
    base.update(kw)
    return base


def product(**kw):
    base = {"code": "3017624010701", "product_name": "Hazelnut Spread", "brands": "Examplo",
            "nutrition_data_per": "100g", "nutriments": nutriments()}
    base.update(kw)
    return base


# ================================================================ units and basis

def test_REQ_NUT_003_off_per_100g_fields_parse_into_this_systems_keys_and_units():
    """The x1000 that is silent when it is wrong.

    Open Food Facts reports `sodium_100g` in GRAMS; `core.metric_registry` stores `sodium_mg`
    in milligrams. A parser that passes the number through unchanged is off by a factor of a
    thousand and every downstream interval is arithmetically correct about the wrong figure.
    """
    parsed = off.parse_product(product(nutriments=nutriments(sodium_100g=0.428)))

    assert parsed["nutrients_per_100g"]["kcal"] == 539.0
    assert parsed["nutrients_per_100g"]["protein_g"] == 6.3
    assert parsed["nutrients_per_100g"]["carbs_g"] == 57.5
    assert parsed["nutrients_per_100g"]["fat_g"] == 30.9
    assert parsed["nutrients_per_100g"]["sugar_g"] == 56.3
    assert parsed["nutrients_per_100g"]["sodium_mg"] == 428.0        # 0.428 g -> 428 mg
    assert parsed["nutrient_provenance"]["sodium_mg"] == "sodium"
    assert parsed["basis"] == "100g"

    # The keys are exactly the ones nutrition.py reads back out of foods_cache.
    from tools.engines import nutrition
    assert set(parsed["nutrients_per_100g"]) <= set(nutrition.NUTRIENT_KEYS)


def test_REQ_NUT_033_a_nutrient_open_food_facts_does_not_report_stays_absent():
    """A product with no declared fibre does not have zero fibre. RULE-06."""
    parsed = off.parse_product(product())
    assert "fiber_g" not in parsed["nutrients_per_100g"]
    assert parsed["nutrients_per_100g"]["kcal"] == 539.0


def test_REQ_NUT_003_sodium_falls_back_to_salt_over_the_regulatory_factor_and_says_so():
    """salt = sodium x 2.5 is a definition in EU 1169/2011, not an estimate — but it is
    DERIVED, and INV-5 keeps a derived value distinguishable from a declared one."""
    parsed = off.parse_product(product(nutriments=nutriments(salt_100g=1.25)))
    assert parsed["nutrients_per_100g"]["sodium_mg"] == 500.0        # 1.25 g / 2.5 x 1000
    assert parsed["nutrient_provenance"]["sodium_mg"] == "salt"
    assert "sodium_derived_from_salt" in parsed["notes"]


def test_REQ_NUT_003_energy_falls_back_to_kilojoules_over_the_defined_factor():
    """4.184 kJ per kcal is a definition. An unlabelled `energy_100g` is NOT assumed to be
    kilojoules — the same number read on the wrong scale is a 4.184x error that looks fine."""
    n = nutriments()
    del n["energy-kcal_100g"]
    n["energy-kj_100g"] = 2255.0
    parsed = off.parse_product(product(nutriments=n))
    assert parsed["nutrients_per_100g"]["kcal"] == round(2255.0 / 4.184, 4)
    assert "kcal_derived_from_kj" in parsed["notes"]

    bare = nutriments()
    del bare["energy-kcal_100g"]
    bare["energy_100g"] = 2255.0                      # no unit stated anywhere
    assert "kcal" not in off.parse_product(product(nutriments=bare))["nutrients_per_100g"]


def test_REQ_NUT_003_a_per_serving_declaration_is_converted_not_relabelled():
    """`nutrition_data_per = serving` means the numbers are per serving. Storing them in a
    per-100 g column is wrong by whatever the serving weighs — the most convincing kind of
    wrong, because nothing about the row looks unusual."""
    parsed = off.parse_product(product(
        nutrition_data_per="serving", serving_size="30 g", serving_quantity=30,
        serving_quantity_unit="g",
        nutriments={"energy-kcal_serving": 161.7, "proteins_serving": 1.89}))

    assert parsed["basis"] == "serving"
    assert parsed["nutrients_per_100g"]["kcal"] == 539.0             # 161.7 x 100/30
    assert parsed["nutrients_per_100g"]["protein_g"] == 6.3
    assert parsed["serving_g"] == 30.0
    assert "converted_from_serving_using_declared_serving_mass" in parsed["notes"]


def test_REQ_NUT_021_the_sources_own_serving_size_is_read_but_never_invented():
    """REQ-NUT-021 lets an absent quantity fall back to the source's listed serving. The
    listed serving is read here; an absent one stays absent so the caller cannot mistake a
    default for a declaration."""
    assert off.parse_product(product(serving_quantity=30, serving_quantity_unit="g"))["serving_g"] == 30.0
    assert off.parse_product(product())["serving_g"] is None

    # A label writes the household measure first and the declared metric weight in
    # parentheses. Reading left to right takes "1 oz" and substitutes 28.35 g for the 28 g
    # printed on the pack — 1.2% on every nutrient in the row, in the same direction each time.
    assert off.parse_product(product(serving_size="1 oz (28 g)"))["serving_g"] == 28.0
    assert off.parse_product(product(serving_size="2 cookies (32g)"))["serving_g"] == 32.0
    assert off.parse_product(product(serving_size="28 g"))["serving_g"] == 28.0

    # A household measure with no weight anywhere is not a weight. "1 bar" resolves to
    # nothing rather than to a bar-shaped guess (REQ-NUT-021 defers to the review list).
    assert off.parse_product(product(serving_size="1 bar"))["serving_g"] is None


def test_REQ_NUT_025_a_serving_declared_in_millilitres_does_not_become_grams():
    """Millilitres to grams is a density. This system has measured no densities, and assuming
    1 g/ml would put a fabricated number in the column that exists to hold a real one."""
    parsed = off.parse_product(product(serving_size="250 ml", serving_quantity=250,
                                       serving_quantity_unit="ml"))
    assert parsed["serving_g"] is None
    assert parsed["serving_ml"] == 250.0
    assert "serving_declared_in_volume" in parsed["notes"]


# ================================================================ missing, malformed, ambiguous

def test_REQ_NUT_024_a_product_that_declares_no_nutrition_data_is_malformed_not_zero():
    with pytest.raises(off.OffMalformed) as e:
        off.parse_product(product(no_nutrition_data="on"))
    assert e.value.reason == "no_nutrition_data_flag"
    assert e.value.tried_entry()["hit"] is False


def test_REQ_NUT_024_a_per_serving_basis_with_no_serving_mass_refuses():
    """The one case where a plausible number is easiest to produce and least defensible: the
    serving weight would have to be guessed, and the guess would scale every nutrient."""
    with pytest.raises(off.OffMalformed) as e:
        off.parse_product(product(nutrition_data_per="serving", serving_size="1 bar",
                                  nutriments={"energy-kcal_serving": 200.0}))
    assert e.value.reason == "serving_basis_without_serving_mass"


def test_REQ_NUT_025_an_impossible_value_is_dropped_with_its_reason_never_clamped():
    """A clamped value is a value this system invented, and it is indistinguishable from a
    declared one once stored. 100 g cannot contain 340 g of protein (RULE-01)."""
    parsed = off.parse_product(product(nutriments=nutriments(proteins_100g=340.0)))
    assert "protein_g" not in parsed["nutrients_per_100g"]
    assert parsed["dropped"]["protein_g"]["value"] == 340.0
    assert parsed["dropped"]["protein_g"]["ceiling"] == 100.0
    assert parsed["nutrients_per_100g"]["kcal"] == 539.0             # the rest survives


def test_REQ_NUT_024_a_record_whose_macros_cannot_fit_in_100g_is_malformed():
    with pytest.raises(off.OffMalformed) as e:
        off.parse_product(product(nutriments=nutriments(
            proteins_100g=60.0, carbohydrates_100g=60.0, fat_100g=40.0)))
    assert e.value.reason == "macro_sum_exceeds_100g"


def test_REQ_NUT_024_a_blank_or_non_numeric_nutrient_is_missing_and_not_zero():
    """RULE-07: "not reported" and "reported as zero" are different facts."""
    parsed = off.parse_product(product(nutriments=nutriments(
        proteins_100g="", carbohydrates_100g="unknown", fat_100g="30,9")))
    assert "protein_g" not in parsed["nutrients_per_100g"]
    assert "carbs_g" not in parsed["nutrients_per_100g"]
    assert parsed["nutrients_per_100g"]["fat_g"] == 30.9             # European decimal comma
    assert parsed["nutrients_per_100g"].get("sugar_g") == 56.3


def test_REQ_NUT_024_a_product_with_no_usable_nutrient_or_no_name_is_malformed():
    with pytest.raises(off.OffMalformed) as e:
        off.parse_product(product(nutriments={"nutrition-score-fr_100g": 22}))
    assert e.value.reason == "no_usable_nutrient"
    with pytest.raises(off.OffMalformed) as e:
        off.parse_product(product(product_name="", product_name_en=None))
    assert e.value.reason == "no_product_name"
    with pytest.raises(off.OffMalformed):
        off.parse_product({})


def test_REQ_NUT_060_the_atwater_cross_check_is_advisory_and_never_a_stored_nutrient():
    """A computed energy figure may inform a review; it may not replace a declaration.
    INV-5 keeps measured and inferred separate, so this reports and changes nothing."""
    parsed = off.parse_product(product())
    assert parsed["energy_consistency"]["declared_kcal"] == 539.0
    assert parsed["energy_consistency"]["atwater_kcal"] == pytest.approx(533.3, abs=0.1)
    assert parsed["nutrients_per_100g"]["kcal"] == 539.0             # untouched by the check
    row = off.cache_row(product())
    assert "energy_consistency" not in row["nutrients_per_100g"]


# ================================================================ matching: no fuzz, no tie-break

def test_REQ_NUT_025_only_an_exact_normalised_name_matches():
    """REQ-NUT-025 forbids a fuzzy, partial or best-effort-similar match, so there is no
    scorer to tune. Accents, case, punctuation and spacing fold; meaning does not."""
    candidates = [product(code="1", product_name="Crème Brûlée"),
                  product(code="2", product_name="Creme Brulee Dessert")]
    assert off.select_exact_match("creme brulee", candidates)["code"] == "1"

    with pytest.raises(off.OffNotFound) as e:
        off.select_exact_match("creme brulee dessert cup", candidates)
    assert e.value.reason == "no_exact_name_match"


def test_REQ_NUT_016_REQ_NUT_013_ambiguity_is_not_tie_broken_but_a_brand_token_settles_it():
    """"Protein bar" is forty products. Picking the most popular one is a guess wearing a
    lookup's clothes, and REQ-NUT-016 names exactly this: a generic food's nutrients standing
    in for a named branded one."""
    candidates = [product(code="1", product_name="Protein Bar", brands="Alpha"),
                  product(code="2", product_name="protein bar", brands="Beta")]
    with pytest.raises(off.OffAmbiguous) as e:
        off.select_exact_match("protein bar", candidates)
    assert e.value.reason == "ambiguous_exact_match"
    assert e.value.detail["n"] == 2

    # A brand token from the evidence span disambiguates deterministically (REQ-NUT-013).
    assert off.select_exact_match("protein bar", candidates, brand="Beta")["code"] == "2"
    with pytest.raises(off.OffNotFound):
        off.select_exact_match("protein bar", candidates, brand="Gamma")


def test_REQ_NUT_025_the_match_is_deterministic_regardless_of_result_order():
    a = product(code="9", product_name="Oat Milk", brands="Alpha")
    b = product(code="1", product_name="Oat Milk", brands="Alpha")
    for order in ([a, b], [b, a]):
        with pytest.raises(off.OffAmbiguous) as e:
            off.select_exact_match("oat milk", order)
        assert e.value.detail["codes"] == ["1", "9"]
    assert off.select_exact_match("oat milk", [a, a.copy()])["code"] == "9"


# ================================================================ barcodes and freshness

def test_REQ_NUT_011_a_barcode_is_checked_before_it_costs_a_request():
    """Fifteen product reads a minute is the whole budget. Spending one to be told what the
    mod-10 check digit already knew is a request the next real item does not get."""
    assert off.normalise_barcode("3017624010701") == "3017624010701"
    assert off.normalise_barcode("016000275270") == "0016000275270"   # UPC-A padded to 13
    assert off.normalise_barcode(" 0 16000-27527 0 ") == "0016000275270"   # spaces and hyphens
    for bad in ("3017624010702", "12345", "abcdefghijklm", "", None):
        with pytest.raises(off.OffNotFound) as e:
            off.normalise_barcode(bad)
        assert e.value.reason in ("malformed_barcode", "barcode_check_digit_failed")


def test_REQ_NUT_008_an_off_cache_row_older_than_365_days_is_refetched():
    """Foundation and SR Legacy do not expire. A crowd-edited product does: the record can
    change under a name that did not."""
    now = dt.datetime(2026, 9, 9, tzinfo=dt.timezone.utc)
    assert off.needs_refetch(now - dt.timedelta(days=364), now) is False
    assert off.needs_refetch(now - dt.timedelta(days=366), now) is True
    assert off.needs_refetch(None, now) is True
    assert off.CACHE_TTL_DAYS == 365


# ================================================================ etiquette (REQ-NUT-010/011)

def test_REQ_NUT_010_the_user_agent_carries_the_contact_address_from_the_environment():
    """REQ-NUT-010 fixes the format. The address comes from the environment because a public
    Git repository is a third party (RULE-29) and an address in a source file is personal
    data committed to it."""
    assert off.user_agent(CONTACT) == "PersonalOS/1.0 (someone@example.org)"
    assert off.user_agent({"OFF_CONTACT_EMAIL": "a@b.co"}) == "PersonalOS/1.0 (a@b.co)"


def test_REQ_NUT_010_no_request_is_issued_when_the_contact_address_is_missing():
    """A requirement that says SHALL send a header is not satisfied by sending the request
    without it. And this is a misconfiguration of THIS system, not a fact about the food, so
    it is not an `OffUnusable` and never reaches `unresolved_items`."""
    for env in ({}, {"PERSONAL_OS_CONTACT_EMAIL": "   "}, {"PERSONAL_OS_CONTACT_EMAIL": "joe"}):
        with pytest.raises(off.ContactMissing):
            off.user_agent(env)
    assert not issubclass(off.ContactMissing, off.OffUnusable)

    def never(*a, **k):                                  # proves no transport was reached
        raise AssertionError("a request was issued without a User-Agent")
    limits = off.Limits()
    with pytest.raises(off.ContactMissing):
        off.fetch_product(_ExplodingCursor(), "3017624010701", env={}, limits=limits,
                          _transport=never)
    # And it cost nothing: a misconfiguration must not burn a minute's REQ-NUT-011 ceiling on
    # requests that never left the process.
    assert len(limits.product) == 0


def test_REQ_NUT_011_a_request_cannot_be_issued_without_the_rate_windows():
    """REQ-NUT-011 is not something a caller opts into. `limits` has no default, so the
    nightly batch that resolves forty items in nine seconds — the case the ceiling exists for
    — fails at the call site rather than at Open Food Facts' front door."""
    for fn in (off.fetch_product, off.search_products):
        parameter = inspect.signature(fn).parameters["limits"]
        assert parameter.default is inspect.Parameter.empty
        assert parameter.kind is inspect.Parameter.KEYWORD_ONLY

    with pytest.raises(TypeError):
        off.fetch_product(_ExplodingCursor(), "3017624010701", env=CONTACT,
                          _transport=lambda *a, **k: b"{}")


def test_REQ_NUT_011_the_two_rate_ceilings_are_separate_windows():
    """10 searches/min and 15 product reads/min are different limits on different endpoints.
    One shared counter would starve whichever ran second."""
    pair = off.Limits()
    assert (pair.search.max_calls, pair.product.max_calls) == (10, 15)

    for i in range(10):
        pair.search.acquire(now=i * 0.1)
    with pytest.raises(off.OffRateLimited) as e:
        pair.search.acquire(now=1.1)
    # The window frees up when the OLDEST of the ten calls (t=0.0) ages out, not when the
    # newest does: 60 - 1.1 seconds from now, and the caller is told exactly that.
    assert e.value.retry_after == pytest.approx(60 - 1.1, abs=1e-6)
    assert isinstance(e.value, off.OffTransient)          # defer, do not mark unresolved
    assert e.value.tried_entry()["reason"] == "rate_limited_search"

    for i in range(15):                                   # the product window is untouched
        pair.product.acquire(now=i * 0.1)
    with pytest.raises(off.OffRateLimited):
        pair.product.acquire(now=1.5)

    # The window SLIDES; it does not reset on the minute. At t=60.0 exactly one of the ten
    # calls (the one at t=0.0) has aged out, so exactly one more is allowed and the next is
    # still refused. A resetting window would let ten more through at t=60.0 and would breach
    # the published ceiling over any minute that straddles the boundary.
    pair.search.acquire(now=60.0)
    assert len(pair.search) == 10
    with pytest.raises(off.OffRateLimited):
        pair.search.acquire(now=60.0)
    pair.search.acquire(now=60.95)                     # the rest of the ten have now aged out
    assert len(pair.search) == 2


# ================================================================ RULE-09, as a signature

def test_RULE_09_REQ_NUT_061_no_function_in_this_module_accepts_a_nutrient_quantity():
    """REQ-NUT-060/061: no calorie, gram or macro this system stores may originate in a model.
    Asserted on the signatures rather than trusted of the callers — a parameter is the only
    way such a number could enter, so the absence of the parameter is the proof."""
    forbidden = {"kcal", "calories", "protein", "protein_g", "carbs", "carbs_g", "fat",
                 "fat_g", "fiber_g", "sugar_g", "sodium_mg", "grams", "nutrients",
                 "nutrients_per_100g", "ethanol_grams", "standard_drinks"}
    for name, fn in vars(off).items():
        if name.startswith("_") or not callable(fn) or getattr(fn, "__module__", "") != off.__name__:
            continue
        if isinstance(fn, type):
            continue
        params = set(inspect.signature(fn).parameters)
        assert not (params & forbidden), f"{name} accepts a model-suppliable quantity: {params & forbidden}"


def test_RULE_29_this_module_opens_no_socket_of_its_own():
    """`tools/validate_layout.py` bans a network-capable import outside `lib/egress.py`; this
    asserts it of this file specifically, so the parser cannot acquire a second outbound path
    without a test saying so.

    Checked against the PARSED imports rather than as a substring scan, for two reasons. A
    substring scan is defeated by `importlib.import_module` and by any aliasing, and — the
    reason it is written this way here — the repository-wide scanner in `tests/test_egress.py`
    searches every file for those very names, so a test that spelled them out would report
    itself as the violation it exists to prevent.
    """
    import ast
    from pathlib import Path

    # Everything this module is permitted to import: the standard library it parses with, and
    # the one sanctioned outbound path. A network-capable name is not on the list, so it fails
    # by being absent from the allowlist rather than by matching a ban list that can go stale.
    allowed = {"__future__", "datetime", "json", "os", "re", "time", "unicodedata",
               "collections", "lib"}
    imported, roots = set(), set()
    for node in ast.walk(ast.parse(Path(off.__file__).read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(f"{node.module}.{node.names[0].name}")
            roots.add(node.module.split(".")[0])

    assert roots <= allowed, f"unsanctioned import in the parser: {roots - allowed}"
    assert "lib.egress" in imported, "the parser must reach the network only through lib.egress"


# ================================================================ the transport seam

class _ExplodingCursor:
    """Reaching the database at all is a failure in the tests that use this."""

    def execute(self, *a, **k):
        raise AssertionError("no query should be issued on this path")

    def fetchone(self):
        raise AssertionError("no query should be issued on this path")


class _FakeCursor:
    """The narrowest cursor `lib.egress.get_json` needs: an allowlist answer and two logs.

    Used only for the outcome-classification tests, where what is under test is how a
    transport failure is CLASSIFIED. The allowlist gate itself is proved against the real
    migration in the SQL half below, because a fake that always says yes proves nothing
    about a gate.
    """

    def __init__(self, allowed=True):
        self.allowed, self.queries = allowed, []

    def execute(self, sql, args=None):
        self.queries.append((" ".join(sql.split()), args))
        self._last = sql

    def fetchone(self):
        if "egress_allowlist" in self._last:
            return (1,) if self.allowed else None
        return ("00000000-0000-0000-0000-000000000000",)


def test_REQ_NUT_024_a_503_is_deferred_and_is_not_a_statement_about_the_food():
    """Open Food Facts returns 503 often enough that this is a normal weekday. Recording it
    as "no such food" turns an outage into a permanent gap in the record."""
    cur = _FakeCursor()

    def flaky(url, headers, timeout):
        raise OSError("503 Service Unavailable")

    with pytest.raises(off.OffTransient) as e:
        off.fetch_product(cur, "3017624010701", **call_kw(_transport=flaky))
    assert e.value.reason == "request_failed"
    assert not isinstance(e.value, off.OffNotFound)
    assert not isinstance(e.value, off.OffMalformed)


def test_REQ_NUT_001_REQ_NUT_024_an_unknown_barcode_is_not_found_and_is_settled():
    cur = _FakeCursor()

    def absent(url, headers, timeout):
        return json.dumps({"status": 0, "status_verbose": "product not found",
                           "code": "3017624010701"}).encode()

    with pytest.raises(off.OffNotFound) as e:
        off.fetch_product(cur, "3017624010701", **call_kw(_transport=absent))
    assert e.value.reason == "barcode_not_in_off"
    assert e.value.tried_entry()["source"] == "off_product"


def test_REQ_NUT_010_the_contact_header_reaches_the_request_and_the_log_does_not():
    """The header must be sent (REQ-NUT-010); the log must not reproduce the query, because a
    nutrition lookup carries what Joe ate and a log that repeats it is a second copy of the
    record it audits."""
    cur, seen = _FakeCursor(), {}

    def capture(url, headers, timeout):
        seen["url"], seen["headers"] = url, headers
        return json.dumps({"status": 1, "product": product()}).encode()

    off.fetch_product(cur, "3017624010701", **call_kw(_transport=capture))
    assert seen["headers"]["User-Agent"] == "PersonalOS/1.0 (someone@example.org)"
    assert "3017624010701" in seen["url"]

    logged = " ".join(str(args) for _sql, args in cur.queries if args)
    assert "someone@example.org" not in logged            # the address is not logged
    assert "search_terms" not in logged


def test_REQ_NUT_001_REQ_NUT_006_a_search_reads_one_page_and_never_bulk_imports():
    """REQ-NUT-006/007: this system does not mirror Open Food Facts. One bounded page."""
    cur, seen = _FakeCursor(), {}

    def capture(url, headers, timeout):
        seen["url"] = url
        return json.dumps({"count": 2, "page_size": 20,
                           "products": [product(code="1"), product(code="2")]}).encode()

    got = off.search_products(cur, "hazelnut spread", page_size=20,
                              **call_kw(_transport=capture))
    assert len(got) == 2
    assert "page_size=20" in seen["url"] and "search_terms=hazelnut+spread" in seen["url"]

    def broken(url, headers, timeout):
        return json.dumps({"count": 0}).encode()          # no `products` key at all
    with pytest.raises(off.OffMalformed) as e:
        off.search_products(cur, "hazelnut spread", **call_kw(_transport=broken))
    assert e.value.reason == "search_response_without_products"


def test_REQ_NUT_003_a_resolved_product_becomes_a_foods_cache_row_that_keeps_its_payload():
    """ADR-0066 decision 2: `raw` keeps the source payload so a changed reading can be
    re-derived without spending another request."""
    cur = _FakeCursor()

    def found(url, headers, timeout):
        return json.dumps({"status": 1, "product": product(serving_quantity=30,
                                                           serving_quantity_unit="g")}).encode()

    row = off.lookup_by_barcode(cur, "3017624010701", **call_kw(
        _transport=found, fetched_at=dt.datetime(2026, 9, 9, tzinfo=dt.timezone.utc)))
    assert row["source"] == "off_product"                  # 0050's CHECK and the width table
    assert row["source_id"] == "3017624010701"             # provenance to a specific record
    assert row["brand"] == "Examplo"
    assert row["canonical_name"] == "Hazelnut Spread"
    assert row["serving_g"] == 30.0
    assert row["nutrients_per_100g"]["kcal"] == 539.0
    assert row["raw"]["off_product"]["code"] == "3017624010701"
    assert row["raw"]["parse"]["code_version"] == off.CODE_VERSION
    assert set(row) == {"canonical_name", "source", "source_id", "brand",
                        "nutrients_per_100g", "serving_g", "fetched_at", "raw"}


# ================================================================ against the real migration

pytestmark_sql = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds migration 0050 in disposable schemas; local server only")

CORE = "core_offnut_pytest"
OPS = "ops_offnut_pytest"
CONFIG = "config_offnut_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")


def world(cur):
    """Migration 0050 verbatim, in disposable schemas, inside a transaction that rolls back
    (RULE-01's ADR-0022 exception). Nothing is committed and no real table is touched."""
    from pathlib import Path
    from tests._import_fixture import _statements
    from tools.run_migration import split_statements

    for schema in (CORE, OPS, CONFIG):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"CREATE TABLE {CONFIG}.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, note TEXT)")
    root = Path(__file__).resolve().parents[1]
    # 0071 REVOKEs on `anon`/`authenticated`, which Supabase supplies and a bare PostgreSQL 17
    # cluster does not. Created idempotently as `tests/_import_fixture.build_spine` does.
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    # Both nutrition migrations IN ORDER: 0071 adds `food_aliases`, which `lookup_cached` now
    # reads as REQ-NUT-001 step (1), so a fixture stopping at 0050 no longer matches the code.
    for migration in ("0050_nutrition.sql", "0071_food_and_portion_aliases.sql"):
        body = (root / "migrations" / migration).read_text() \
            .replace("__CORE__", CORE).replace("__OPS__", OPS).replace("config.", f"{CONFIG}.")
        for stmt in split_statements(body):
            cur.execute(stmt)
    return cur


@pytestmark_sql
def test_REQ_NUT_010_the_open_food_facts_host_is_in_the_real_allowlist(sql_connection):
    """The gate this module depends on, proved against the allowlist migration 0050 actually
    seeds — not against a stub that says yes."""
    cur = world(sql_connection.cursor())
    cur.execute(f"select purpose from {CONFIG}.egress_allowlist where host = %s", (off.HOST,))
    row = cur.fetchone()
    assert row is not None, f"{off.HOST} is not allowlisted; RULE-29 refuses the request"
    assert row[0] == "nutrition"
    sql_connection.rollback()


@pytestmark_sql
def test_RULE_29_a_host_outside_the_allowlist_is_refused_before_any_request(sql_connection):
    """The allowlist is a gate, so a test has to prove it says no to something."""
    from lib import egress
    cur = world(sql_connection.cursor())

    def never(*a, **k):
        raise AssertionError("a request was issued to a host outside the allowlist")

    with pytest.raises(egress.PayloadRefused):
        egress.get_json(cur, "https://world.openfoodfacts.example/api/v2/product/1.json",
                        "nutrition:off_product_read", schema=CORE, ops=OPS, config=CONFIG,
                        _transport=never)
    sql_connection.rollback()


@pytestmark_sql
def test_RULE_29_a_privacy_refusal_is_never_reclassified_as_a_network_failure(sql_connection):
    """A RULE-29 refusal recorded as "Open Food Facts was flaky" is a privacy failure filed
    as an operational one, and it would be retried tonight."""
    from lib import egress
    cur = world(sql_connection.cursor())
    with pytest.raises(egress.PayloadRefused):
        off.search_products(cur, "lunch, latitude: the park", schema=CORE, ops=OPS,
                            config=CONFIG,
                            **call_kw(_transport=lambda *a, **k: b'{"products": []}'))
    sql_connection.rollback()


@pytestmark_sql
def test_REQ_NUT_003_the_parsed_row_satisfies_the_real_foods_cache_constraints(sql_connection):
    """The row shape is only right if 0050 accepts it: the `source` CHECK, the positive
    `serving_g` and the `(canonical_name, source, source_id)` key are all in the migration."""
    cur = world(sql_connection.cursor())
    row = off.cache_row(product(serving_quantity=30, serving_quantity_unit="g"),
                        fetched_at=dt.datetime(2026, 9, 9, tzinfo=dt.timezone.utc))

    food_id = off.insert_cache_row(cur, row, schema=CORE)
    assert food_id is not None
    assert off.insert_cache_row(cur, row, schema=CORE) is None      # appended once, not twice

    cur.execute(f"""select source, brand, serving_g, nutrients_per_100g->>'sodium_mg'
                      from {CORE}.foods_cache where food_id = %s""", (food_id,))
    source, brand, serving_g, sodium = cur.fetchone()
    assert (source, brand, float(serving_g)) == ("off_product", "Examplo", 30.0)
    assert float(sodium) == 42.8                    # 0.107 g salt / 2.5 x 1000, the salt path

    # And nutrition.py reads it straight back out through its own cache lookup.
    from tools.engines import nutrition
    cached, method = nutrition.lookup_cached(cur, "Hazelnut Spread", schema=CORE)
    assert method == "off_product"
    assert cached["nutrients_per_100g"]["kcal"] == 539.0
    resolved = nutrition.resolve_item(cur, "Hazelnut Spread", servings=1, schema=CORE,
                                      config=CONFIG)
    assert resolved["method"] == "off_product"
    assert resolved["grams"] == 30.0
    lo, pt, hi = resolved["nutrients"]["kcal"]
    assert lo < pt < hi                                             # REQ-NUT-034, width from the table
    sql_connection.rollback()


@pytestmark_sql
def test_REQ_NUT_036_the_source_name_matches_the_registered_width_and_precedence(sql_connection):
    """`off_product` is one string in three places — 0050's CHECK, the width table and
    nutrition.py's precedence tuple. This module restates it rather than redefining it, and
    this is the test that would fail if the three ever drifted apart."""
    from tools.engines import nutrition
    cur = world(sql_connection.cursor())
    widths = nutrition.interval_widths(cur, CONFIG)
    assert off.SOURCE in widths
    assert widths[off.SOURCE] == (0.90, 1.10)                       # REQ-NUT-036
    assert off.SOURCE in nutrition.SOURCE_PRECEDENCE
    # Last in precedence: a crowd transcription never outranks USDA or Joe (REQ-NUT-001, RULE-10).
    assert nutrition.SOURCE_PRECEDENCE[-1] == off.SOURCE
    sql_connection.rollback()
