"""B12: a resolved interval becomes a retrievable atom, and an unresolved item becomes a row.

`tests/test_nutrition_integration.py` proves the cascade is on the execution path — which legs
were called, what reached `ops.egress_log`, what landed in `foods_cache`. It stops at the point
where `resolve_item` returns numbers. This file covers the step after that, which is the one
that decides whether any of it is readable: **an interval that never becomes an atom is a
calculation nobody can retrieve.**

That is the same failure the cascade had — sixteen passing tests and no caller — moved one
stage downstream, so it is tested here rather than assumed:

  * `persist_resolution` writes one `consume` atom per nutrient, keyed to the item's own
    capture (INV-1), interval intact (RULE-08), `provenance = 'inferred'` (RULE-05), and the
    row is then visible through `atoms_current` — the view every downstream reader uses.
  * `record_unresolved` writes an `unresolved_items` row, and does not write a second one when
    the nightly pass sees the same item again.
  * Re-running resolution does not double a day's calories, and Joe's correction still outranks
    every source the second time through (RULE-10).

Every schema here is a throwaway name and the transaction always rolls back (RULE-01's ADR-0022
exception). Every food is invented; none of this is Joe's data.
"""
import json
import os
import uuid
from pathlib import Path

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import nutrition
from tools.run_migration import split_statements

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds migration 0050 in disposable schemas; local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_nutper_pytest"
OPS = "ops_nutper_pytest"
CONFIG = "config_nutper_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")

DAY = "2026-09-09"
WHEN = "2026-09-09 12:30:00+00"


def world(cur):
    """Migration 0050 verbatim over the spine, in disposable schemas."""
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


def cache_food(cur, name, source, nutrients, serving_g=None, brand=None):
    cur.execute(f"""insert into {CORE}.foods_cache
        (canonical_name, source, source_id, brand, nutrients_per_100g, serving_g)
        values (%s,%s,%s,%s,%s::jsonb,%s)""",
        (name, source, name, brand, json.dumps(nutrients), serving_g))


def cache_leg(cur):
    """The cache leg alone: no network leg is registered, so nothing can reach a socket."""
    return {"joe": nutrition.CacheLeg(cur, schema=CORE)}


def current_atoms(cur, metric=None):
    """What a downstream reader sees. `atoms_current` is the view the panel and `ask` read."""
    sql = (f"select metric_key, value_low, value_point, value_high, estimate_method, unit, "
           f"provenance, subject_day from {CORE}.atoms_current where kind = 'consume' "
           f"and metric_key is not null")
    params = []
    if metric:
        sql += " and metric_key = %s"
        params.append(metric)
    cur.execute(sql + " order by metric_key", params)
    return list(cur.fetchall())          # the driver returns a tuple; callers compare to []


# ================================================================ REQ-NUT-014 at the cache

def test_REQ_NUT_014_a_cached_branded_row_without_a_brand_owner_is_refused(sql_connection):
    """A `labelled` claim with nothing to re-check it against is a defect, not a resolution.

    `nutrition_cascade.resolve` enforces this for a network `usda_branded` match, but that check
    is keyed on the LEG NAME and the cache leg is registered as `joe` — so a cached branded row
    walked straight past it. `foods_cache.brand` is nullable, so the row is storable, and the
    result was `estimate_method='labelled'` with `brand_owner=None` while `labelled` is one of
    `nutrition_display.TIGHT_METHODS`. ADR-0106: such a match raises rather than resolving.

    The query below carries NO brand, which is what makes it reachable: `lookup_cached` only
    applies its REQ-NUT-016 brand filter when the QUERY is branded.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "probe cereal", "usda_branded", {"kcal": 380.0}, serving_g=40, brand=None)

    with pytest.raises(ValueError, match="REQ-NUT-014"):
        nutrition.resolve_item(cur, "probe cereal", servings=1, sources=cache_leg(cur),
                               schema=CORE, config=CONFIG)
    sql_connection.rollback()


def test_REQ_NUT_014_a_cached_branded_row_with_its_brand_owner_still_resolves(sql_connection):
    """The guard rejects the missing referent, not the branded path itself."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "probe cereal", "usda_branded", {"kcal": 380.0}, serving_g=40,
               brand="Examplo")

    out = nutrition.resolve_item(cur, "probe cereal", servings=1, sources=cache_leg(cur),
                                 schema=CORE, config=CONFIG)
    assert out["estimate_method"] == "labelled"
    # REQ-NUT-014's referent survives to the caller. `resolve_item` carries it as `brand`; the
    # leg's own key is `brand_owner`, and only one of the two names reaches the result.
    assert out["brand"] == "Examplo"
    sql_connection.rollback()


# ================================================================ resolved -> retrievable

def test_REQ_NUT_034_INV_1_a_resolved_interval_becomes_a_retrievable_atom(sql_connection):
    """The step that makes the numbers readable, and every property that must survive it.

    A point value here would be a lie about precision (RULE-08), an `extracted` provenance would
    claim the calorie was observed in the capture rather than inferred from a reference
    (RULE-05/INV-5), and an atom pointing at no capture would break INV-1. The read is through
    `atoms_current`, because that is the view the panel and `ask` actually use — writing a row
    no view returns would be the same failure as a cascade with no caller.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    cache_food(cur, "probe porridge", "off_product",
               {"kcal": 370.0, "protein_g": 11.0}, serving_g=50, brand=None)

    out = nutrition.resolve_item(cur, "probe porridge", grams=100, sources=cache_leg(cur),
                                 schema=CORE, config=CONFIG)
    written = nutrition.persist_resolution(
        cur, out, raw_capture_id=cap, occurred_at=WHEN, subject_day=DAY,
        evidence_span="probe porridge", schema=CORE)
    assert sorted(written) == ["kcal", "protein_g"]

    rows = {r[0]: r for r in current_atoms(cur)}
    assert set(rows) == {"kcal", "protein_g"}

    key, low, point, high, method, unit, provenance, subject_day = rows["kcal"]
    assert low < point < high, "the interval collapsed to a point (RULE-08)"
    assert (float(low), float(point), float(high)) == tuple(
        float(v) for v in out["nutrients"]["kcal"])
    assert provenance == "inferred", "a looked-up calorie is not extracted from the capture"
    assert unit == "kcal", "the unit came from somewhere other than the registry"
    assert str(subject_day) == DAY

    # INV-1: the atom traces to the capture the phrase was uttered in.
    cur.execute(f"""select count(*) from {CORE}.atoms a
                     join {CORE}.raw_captures rc on rc.capture_id = a.raw_capture_id
                    where a.metric_key = 'kcal'""")
    assert cur.fetchone()[0] == 1
    sql_connection.rollback()


def test_REQ_NUT_040_an_absent_nutrient_stays_absent_rather_than_becoming_zero(sql_connection):
    """The cached row carries no protein. RULE-06: no atom, rather than an atom saying zero —
    a zero is the claim that the food contained no protein, which nothing established."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    cache_food(cur, "probe oil", "off_product", {"kcal": 884.0}, serving_g=14)

    out = nutrition.resolve_item(cur, "probe oil", grams=14, sources=cache_leg(cur),
                                 schema=CORE, config=CONFIG)
    nutrition.persist_resolution(cur, out, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="probe oil", schema=CORE)

    assert [r[0] for r in current_atoms(cur)] == ["kcal"]
    assert current_atoms(cur, "protein_g") == []
    sql_connection.rollback()


def test_ADR_0135_re_running_resolution_does_not_double_the_days_calories(sql_connection):
    """Resolution is re-run: a nightly pass sweeps the same days and REQ-NUT-008 re-fetches a
    stale row. A doubled daily total is not obviously wrong on inspection, which is exactly what
    makes it dangerous — so the second pass must write nothing."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    cache_food(cur, "probe porridge", "off_product", {"kcal": 370.0}, serving_g=50)

    for expected in (["kcal"], []):
        out = nutrition.resolve_item(cur, "probe porridge", grams=100, sources=cache_leg(cur),
                                     schema=CORE, config=CONFIG)
        written = nutrition.persist_resolution(
            cur, out, raw_capture_id=cap, occurred_at=WHEN, subject_day=DAY,
            evidence_span="probe porridge", schema=CORE)
        assert written == expected

    cur.execute(f"select count(*) from {CORE}.atoms where metric_key = 'kcal'")
    assert cur.fetchone()[0] == 1, "the second pass doubled the day"
    sql_connection.rollback()


def test_ADR_0135_two_separate_captures_of_the_same_food_both_count(sql_connection):
    """The other half of the dedupe, and the reason it is keyed on the capture and not the day:
    two coffees on one day are two coffees. A dedupe keyed on (day, item) would silently drop
    the second one and under-report every repeated food."""
    cur = world(sql_connection.cursor())
    cache_food(cur, "probe coffee", "off_product", {"kcal": 2.0}, serving_g=240)

    for _ in range(2):
        cap = capture(cur)                      # a separate capture: a separate coffee
        out = nutrition.resolve_item(cur, "probe coffee", grams=240, sources=cache_leg(cur),
                                     schema=CORE, config=CONFIG)
        nutrition.persist_resolution(cur, out, raw_capture_id=cap, occurred_at=WHEN,
                                     subject_day=DAY, evidence_span="probe coffee", schema=CORE)

    cur.execute(f"select count(*) from {CORE}.atoms where metric_key = 'kcal'")
    assert cur.fetchone()[0] == 2
    sql_connection.rollback()


# ================================================================ RULE-10 through a re-run

def test_RULE_10_joes_correction_still_outranks_the_source_on_the_second_pass(sql_connection):
    """REQ-NUT §D.4: a correction is permanent, and permanence is a claim about the NEXT run.

    Joe records the portion he actually eats. The cached source row keeps its own serving size,
    and a resolver that re-derived grams from that serving on the second pass would quietly
    undo his correction — the failure RULE-10 exists to prevent, and one that leaves no trace
    because both numbers are plausible.
    """
    cur = world(sql_connection.cursor())
    cache_food(cur, "probe granola", "off_product", {"kcal": 400.0}, serving_g=45)
    cur.execute(f"""insert into {CORE}.portions (canonical_name, grams, source, note)
                    values ('probe granola', 90, 'joe', 'what he actually pours')""")

    first = nutrition.resolve_item(cur, "probe granola", sources=cache_leg(cur),
                                   schema=CORE, config=CONFIG)
    second = nutrition.resolve_item(cur, "probe granola", sources=cache_leg(cur),
                                    schema=CORE, config=CONFIG)

    assert first["grams"] == 90.0, "his portion was not used"
    assert second["grams"] == first["grams"], "the correction did not survive the re-run"
    assert first["method"] == second["method"] == "joe"
    assert second["nutrients"]["kcal"] == first["nutrients"]["kcal"]

    # And it is his portion that drove the number, not the source's 45 g serving.
    assert float(second["nutrients"]["kcal"][1]) == pytest.approx(360.0)
    sql_connection.rollback()


# ================================================================ unresolved is a stored fact

def test_REQ_NUT_024_an_unresolved_item_becomes_a_row_and_not_a_number(sql_connection):
    """Nothing in the cache, and no other leg registered. The item is recorded as a question,
    with no nutrient atom anywhere — REQ-NUT-040's gap that stays a gap."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)

    with pytest.raises(nutrition.Unresolved) as exc:
        nutrition.resolve_item(cur, "probe unknown thing", sources=cache_leg(cur),
                               schema=CORE, config=CONFIG)

    item_id = nutrition.record_unresolved(cur, exc.value, raw_capture_id=cap,
                                          subject_day=DAY, schema=CORE)
    assert item_id is not None

    cur.execute(f"""select item_text, resolved_at, tried from {CORE}.unresolved_items""")
    item_text, resolved_at, tried = cur.fetchone()
    assert item_text == "probe unknown thing"
    assert resolved_at is None, "an unresolved item was written as already resolved"
    tried = json.loads(tried) if isinstance(tried, str) else tried
    assert tried["reason"] == "no_source_available"
    assert tried["review_reason"] is None, (
        "nothing could be ASKED, so this is an operations problem and does not belong on "
        "Joe's review list (REQ-NUT-024)")

    assert current_atoms(cur) == [], "an unresolved item produced a nutrient atom"
    sql_connection.rollback()


def test_REQ_NUT_027_a_nightly_re_run_does_not_grow_the_review_list(sql_connection):
    """The same sandwich seen again tonight is the same open question, not a second one. A list
    that grows by one row per night for one unresolved item is a list Joe stops reading."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)

    for expect_written in (True, False):
        with pytest.raises(nutrition.Unresolved) as exc:
            nutrition.resolve_item(cur, "probe unknown thing", sources=cache_leg(cur),
                                   schema=CORE, config=CONFIG)
        item_id = nutrition.record_unresolved(cur, exc.value, raw_capture_id=cap,
                                              subject_day=DAY, schema=CORE)
        assert (item_id is not None) is expect_written

    cur.execute(f"select count(*) from {CORE}.unresolved_items")
    assert cur.fetchone()[0] == 1
    sql_connection.rollback()
