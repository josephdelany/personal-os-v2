"""B12 §E.3/§G.1: the day reads back, through the command an operator actually runs.

`tools/engines/nutrition_display.py` held sixteen tested display rules and **nothing called
it** — one of the runtime capabilities with no entry point. A green unit suite over an
unreachable module is indistinguishable, from every summary this project produces, from a
working feature; it is the failure ADR-0137 was written about.

So every test here goes through `tools/nutrition_day.py:main()` — the same function the
operator invokes, argument parsing, refusal and exit code included — against atoms that were
STORED by the real write path (`nutrition.resolve_item` → `nutrition.persist_resolution`), on a
disposable server. Nothing asserts a helper in isolation:

  * the numbers come from rows that were written, not from dicts built in this file;
  * the text comes from `nutrition_display`, so a rule changed there changes this output;
  * `main()`'s exit code is asserted, because a refusal nobody can observe is not a refusal.

Every food is invented. No personal data is in this file.
"""
import datetime as dt
import io
import json
import os
import uuid
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools import nutrition_day
from tools.engines import nutrition, nutrition_display as display
from tools.run_migration import split_statements

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds the nutrition migrations in disposable schemas; local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_nutday_pytest"
OPS = "ops_nutday_pytest"
CONFIG = "config_nutday_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql", "0011_ops.sql")
MIGRATIONS = ("0050_nutrition.sql", "0071_food_and_portion_aliases.sql",
              "0074_the_alias_bridge_is_gone.sql")

DAY = dt.date(2026, 9, 11)
WHEN = "2026-09-11 12:30:00+00"


def world(cur):
    """The nutrition migrations over the spine, in disposable schemas, inside a transaction
    that rolls back (RULE-01's ADR-0022 exception)."""
    for schema in (CORE, OPS, CONFIG):
        cur.execute(f"CREATE SCHEMA {schema}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"CREATE TABLE {CONFIG}.strings (key TEXT PRIMARY KEY, value TEXT NOT NULL, "
                f"note TEXT)")
    # 0071 REVOKEs on `anon`/`authenticated`, which Supabase supplies and a bare PostgreSQL 17
    # cluster does not. Created idempotently as `tests/_import_fixture.build_spine` does.
    for role in ("anon", "authenticated", "service_role"):
        cur.execute(f"""DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN;
            END IF;
        END $$""")
    root = Path(__file__).resolve().parents[1]
    for migration in MIGRATIONS:
        body = (root / "migrations" / migration).read_text() \
            .replace("__CORE__", CORE).replace("__OPS__", OPS).replace("config.", f"{CONFIG}.")
        for stmt in split_statements(body):
            cur.execute(stmt)
    return cur


class _Handle:
    """A connection-shaped handle over the fixture's cursor.

    `main()` owns its connection: it opens one, rolls back and closes in a `finally`. A test
    must not let it close the fixture's real connection out from under the rest of the test, so
    `close` and `rollback` are no-ops here. Everything else about the call is the real thing —
    this is not a stub for the command, only for the socket it would have opened.
    """

    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur

    def rollback(self):
        pass

    def close(self):
        pass


def run(cur, *argv):
    """Invoke the real command. Returns (exit_code, stdout)."""
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = nutrition_day.main([*argv, "--schema", CORE], connect=lambda: _Handle(cur))
    return code, buffer.getvalue()


def capture(cur):
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


def store(cur, cap, name, kcal_per_100g, grams, *, source="usda_foundation", brand=None,
          span=None):
    """Resolve and persist one food through the REAL write path, then return what it wrote.

    Not an INSERT of hand-made numbers: the intervals under test have to be the ones
    `resolve_item` computes and `persist_resolution` stores, or this file would be asserting
    against its own arithmetic.
    """
    cache_food(cur, name, source, {"kcal": kcal_per_100g}, serving_g=100.0, brand=brand)
    result = nutrition.resolve_item(cur, name, grams=grams, brand=brand,
                                    sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                    schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, result, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span=span or name, schema=CORE)
    return result


# ================================================================ the command answers

def test_REQ_NUT_043_the_days_bounds_sum_separately_through_the_command(sql_connection):
    """REQ-NUT-043: the day's low is the sum of the lows and its high the sum of the highs.

    Summing the points and putting a band around them would understate the width — portion
    error drifts the same direction all day, so it does not cancel. Asserted against the
    intervals the resolver actually stored, arithmetic done here from those rows.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    a = store(cur, cap, "synthetic oats", 380.0, 100, span="the oats")
    b = store(cur, cap, "synthetic bar", 450.0, 40, span="the bar")

    code, out = run(cur, DAY.isoformat())
    assert code == 0

    lows = a["nutrients"]["kcal"][0] + b["nutrients"]["kcal"][0]
    highs = a["nutrients"]["kcal"][2] + b["nutrients"]["kcal"][2]
    expected = display.render_value(round((lows + highs) / 2.0, 1), round(lows, 1),
                                    round(highs, 1), estimate_method="mixed")["text"]
    assert expected in out, out
    # And the width really is the sum of the widths, not a band around the summed points.
    assert round(highs - lows, 6) == round(
        (a["nutrients"]["kcal"][2] - a["nutrients"]["kcal"][0])
        + (b["nutrients"]["kcal"][2] - b["nutrients"]["kcal"][0]), 6)


def test_REQ_NUT_044_REQ_NUT_063_the_command_never_prints_a_bare_point(sql_connection):
    """The interval is the value, everywhere — summaries included. A day total rendered as one
    number reads like a measurement, which is the single most confidently wrong thing this
    system can produce."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    result = store(cur, cap, "synthetic oats", 380.0, 100)
    low, point, high = result["nutrients"]["kcal"]

    code, out = run(cur, DAY.isoformat())
    assert code == 0
    assert f"({low:g}–{high:g})" in out, "the bounds are shown"
    # The point never stands alone: every line carrying it also carries its interval.
    for line in out.splitlines():
        if f"{round(point):g}" in line and "kcal" in line:
            assert "–" in line, f"a point with no interval: {line!r}"


def test_REQ_NUT_049_rounding_the_day_never_narrows_it(sql_connection):
    """The low floors and the high ceils. Rounding 1,847.4–2,103.6 to 1,850–2,100 removes
    honest uncertainty for tidiness, and every rounding along the chain removes a little more."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    # 137 g of a 383.7 kcal/100 g food gives bounds that are not whole numbers.
    result = store(cur, cap, "synthetic awkward", 383.7, 137)
    low, _, high = result["nutrients"]["kcal"]

    code, out = run(cur, DAY.isoformat())
    assert code == 0
    shown_low, shown_high = display.round_interval(low, high)
    assert shown_low <= low and shown_high >= high, "rounding widened or held, never narrowed"
    assert f"({shown_low:g}–{shown_high:g})" in out


def test_REQ_NUT_026_REQ_NUT_062_an_unresolved_item_is_words_and_is_counted(sql_connection):
    """Two rules at once, because they fail together. An unresolved food is never rendered as
    a number (REQ-NUT-062) — not zero, not a dash — AND the day's total says how many items it
    could not include (REQ-NUT-026), or it looks complete and silently is not.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic oats", 380.0, 100)
    with pytest.raises(nutrition.Unresolved) as e:
        nutrition.resolve_item(cur, "the thing from the deli", grams=150,
                               sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                               schema=CORE, config=CONFIG, ops=OPS)
    nutrition.record_unresolved(cur, e.value, raw_capture_id=cap, subject_day=DAY, schema=CORE)

    code, out = run(cur, DAY.isoformat())
    assert code == 0
    assert "1 resolved item(s), 1 unresolved" in out
    assert "not resolved" in out and "the thing from the deli" in out
    assert "1 item(s) in this day could not be resolved" in out
    # REQ-NUT-062, stated as an absence: the unresolved line carries no figure at all.
    deli = next(l for l in out.splitlines() if "the thing from the deli" in l)
    assert "kcal" not in deli and "0" not in deli


def test_REQ_NUT_047_a_difference_narrower_than_the_interval_is_refused_in_words(sql_connection):
    """A day logged by voice routinely spans hundreds of kcal. Reporting a deficit against it
    is reporting a difference the data cannot see, and the number would be believed."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    result = store(cur, cap, "synthetic oats", 380.0, 100)
    low, point, high = result["nutrients"]["kcal"]

    # A target just inside the day's own width: the difference is real but invisible at it.
    target = point - (high - low) / 2.0
    code, out = run(cur, DAY.isoformat(), "--target", str(target))
    assert code == 0
    assert "cannot resolve that difference" in out

    # And a target far outside it IS reported, so the refusal is a judgement and not a silence.
    code, out = run(cur, DAY.isoformat(), "--target", str(point - (high - low) * 5))
    assert code == 0
    assert "above" in out and "cannot resolve" not in out


def test_RULE_09_no_target_means_no_comparison_rather_than_an_invented_one(sql_connection):
    """A calorie target is a specification about Joe. With none given the command says it was
    not asked to compare, rather than reaching for a plausible 2,000."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic oats", 380.0, 100)

    code, out = run(cur, DAY.isoformat())
    assert code == 0
    assert "no --target was given" in out
    for invented in ("2000", "2,000", "2500", "deficit", "surplus"):
        assert invented not in out.lower(), f"invented a target or a verdict: {invented!r}"


def test_REQ_NUT_046_analysis_restricts_to_the_tight_methods(sql_connection):
    """A voice-logged estimate and a weighed portion are not equally informative, and an
    unweighted correlation treats them as if they were."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic weighed", 380.0, 100)                      # -> weighed
    cache_food(cur, "synthetic portioned", "off_product", {"kcal": 200.0}, serving_g=50.0)
    cur.execute(f"insert into {CORE}.portions (canonical_name, grams, source) "
                f"values ('synthetic portioned', 75, 'portion_table')")
    loose = nutrition.resolve_item(cur, "synthetic portioned",
                                   sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                   schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, loose, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="loose", schema=CORE)
    assert loose["method"] == "portion_table", "the looser method really is looser"

    code, out = run(cur, DAY.isoformat(), "--analysis", "restrict")
    assert code == 0
    assert "analysis (restrict): 1 of 2 item(s) usable" in out, out


def test_REQ_NUT_045_visual_weight_follows_the_method_not_the_magnitude(sql_connection):
    """Weighting by magnitude makes a big number look more certain than a small one, when the
    opposite is usually true."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic small labelled", 450.0, 40, source="usda_branded",
          brand="Examplo", span="small but labelled")
    cache_food(cur, "synthetic large loose", "off_product", {"kcal": 500.0}, serving_g=50.0)
    cur.execute(f"insert into {CORE}.portions (canonical_name, grams, source) "
                f"values ('synthetic large loose', 400, 'portion_table')")
    big = nutrition.resolve_item(cur, "synthetic large loose",
                                 sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                 schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, big, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="large but loose", schema=CORE)

    code, out = run(cur, DAY.isoformat(), "--json")
    assert code == 0
    report = json.loads(out)
    by_name = {i["name"]: i for i in report["items"]}
    assert by_name["small but labelled"]["weight"] == "solid"
    assert by_name["large but loose"]["weight"] == "light"
    assert (by_name["large but loose"]["estimate_method"]
            != by_name["small but labelled"]["estimate_method"])


def test_REQ_NUT_048_REQ_NUT_064_the_command_checks_its_own_framing(sql_connection):
    """No over/under, no pass/fail, no "deficiency". The cheapest place for judgment framing to
    creep back in is a print statement added later by someone who never read the requirement,
    so the check runs over the rendered payload before anything reaches the terminal.

    Proved in both directions: the real output is clean, AND a planted violation is caught and
    turns into a non-zero exit rather than a warning nobody sees.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic oats", 380.0, 100)

    code, out = run(cur, DAY.isoformat(), "--target", "100")
    assert code == 0
    assert nutrition_day.framing_violations(
        nutrition_day.build_report(*nutrition_day.read_day(cur, DAY, schema=CORE),
                                   target=100)) == ()
    for banned in ("over budget", "under budget", "pass", "fail", "deficiency", "on track"):
        assert banned not in out.lower()

    # The planted violation. `check_framing` is the gate, so a report carrying judgment
    # framing must make `main` exit non-zero.
    report = nutrition_day.build_report(*nutrition_day.read_day(cur, DAY, schema=CORE))
    report["unresolved_note"] = "you went over budget today"
    assert nutrition_day.framing_violations(report), "the gate did not catch planted framing"


def test_REQ_NUT_032_every_stored_nutrient_row_carries_an_enumerated_method(sql_connection):
    """REQ-NUT-032 enumerates five values, and until this session the column held none of them
    for a generic source.

    `persist_resolution` stored `resolved["estimate_method"]` — the SOURCE's claim — so a
    Foundation-resolved row carried `usda_foundation` and an Open Food Facts one `off_product`.
    Both are outside the five. That is a requirement violation on its own, and it is also the
    reason `nutrition_display` could not be connected: `TIGHT_METHODS` and `METHOD_WEIGHT`
    speak the enumerated vocabulary, so they matched nothing that had ever been stored —
    REQ-NUT-045's weight fell through to "light" for every row and REQ-NUT-046's restrict mode
    returned an empty set for every day. The absent caller was the symptom; this was the cause.

    Asserted across every resolution shape the resolver can produce, not one sample.
    """
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic weighed", 380.0, 100, span="weighed")
    store(cur, cap, "synthetic branded", 450.0, 40, source="usda_branded", brand="Examplo",
          span="branded")
    cache_food(cur, "synthetic portioned", "off_product", {"kcal": 200.0}, serving_g=50.0)
    cur.execute(f"insert into {CORE}.portions (canonical_name, grams, source) "
                f"values ('synthetic portioned', 75, 'portion_table')")
    loose = nutrition.resolve_item(cur, "synthetic portioned",
                                   sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                   schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, loose, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="portioned", schema=CORE)

    # REQ-NUT-050: a whole serving COUNT against a Branded per-serving gram weight is
    # `labelled` — the label defines what a serving is. No grams are stated here, which is what
    # separates this case from "synthetic branded" above: that one Joe put on a scale, so it is
    # `weighed` however it was sourced (REQ-NUT-035). The two share a width today and the
    # requirements keep them distinct anyway, so calibration can separate them later without a
    # migration; conflating them would spend that separation before it is ever used.
    cache_food(cur, "synthetic counted", "usda_branded", {"kcal": 300.0}, serving_g=40.0,
               brand="Examplo")
    counted = nutrition.resolve_item(cur, "synthetic counted", servings=2,
                                     sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                     schema=CORE, config=CONFIG, ops=OPS)
    assert counted["grams"] == 80.0, "2 servings x the label's 40 g"
    nutrition.persist_resolution(cur, counted, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY, evidence_span="counted", schema=CORE)

    cur.execute(f"""select distinct estimate_method from {CORE}.atoms_current
                     where kind = 'consume' and metric_key is not null""")
    stored = {r[0] for r in cur.fetchall()}
    assert stored <= nutrition.REQ_NUT_032_METHODS, f"outside the enumerated set: {stored}"
    assert stored == {"weighed", "labelled", "portion_table"}, stored

    # The case that was wrong before this change: a branded serving COUNT stored
    # `portion_table`, because the fresh Branded leg reports `estimate_method='usda_branded'`
    # while only the CACHED branded path reported `labelled`. The same food therefore stored a
    # different method depending on whether anyone had asked for it before.
    cur.execute(f"""select distinct estimate_method from {CORE}.atoms_current
                     where evidence_span = 'counted'""")
    assert {r[0] for r in cur.fetchall()} == {"labelled"}, (
        "a whole serving count against a Branded per-serving gram weight is `labelled` "
        "(REQ-NUT-050), not `portion_table`")
    # And a weighed GENERIC food stays `weighed`: weighing removes portion error, not
    # composition error, and a Foundation food's composition is not legally bounded the way a
    # label's is (REQ-NUT-035).
    cur.execute(f"""select distinct estimate_method from {CORE}.atoms_current
                     where evidence_span = 'weighed'""")
    assert {r[0] for r in cur.fetchall()} == {"weighed"}
    # And the source is not lost by the change: it stays on the row the resolution came from.
    cur.execute(f"select distinct source from {CORE}.foods_cache")
    assert {r[0] for r in cur.fetchall()} >= {"usda_foundation", "usda_branded", "off_product"}


def test_REQ_NUT_050_a_branded_serving_count_is_labelled_from_either_path():
    """REQ-NUT-050, and the cached/fresh inconsistency it exposed.

    `resolve_from_cache` sets `estimate_method = 'labelled'` for a cached `usda_branded` row.
    The FRESH Branded leg sets it to `'usda_branded'`. The mapping keyed only on the first, so
    the same food stored `labelled` when it had been seen before and `portion_table` when it had
    not — the interval width a reader sees depending on cache state, which is not a fact about
    the food.

    Asserted against the mapping directly because the two inputs differ only in what the LEG
    reported, and no end-to-end fixture can present both for one food in one run. The end-to-end
    cached case is asserted above; the fresh Branded write path is covered in
    `tests/test_nutrition_usda.py`.
    """
    # Fresh Branded leg: reports its own source name.
    assert nutrition.stored_estimate_method(
        source_claim="usda_branded", grams_stated=False,
        resolved_source="usda_branded") == "labelled"
    # Cached Branded row: REQ-NUT-014 already normalised it to `labelled`.
    assert nutrition.stored_estimate_method(
        source_claim="labelled", grams_stated=False,
        resolved_source="usda_branded") == "labelled"

    # Open Food Facts is deliberately NOT extended. REQ-NUT-050 names the USDA Branded data
    # type; OFF is a crowd-sourced transcription of labels, and `labelled` is one of
    # nutrition_display.TIGHT_METHODS, so promoting it would put a figure nobody can re-check
    # against the product into the tight class (ADR-0106).
    assert nutrition.stored_estimate_method(
        source_claim="off_product", grams_stated=False,
        resolved_source="off_product") == "portion_table"
    # A Foundation food is generic: its declared portion is a portion table, not a label.
    assert nutrition.stored_estimate_method(
        source_claim="usda_foundation", grams_stated=False,
        resolved_source="usda_foundation") == "portion_table"
    # And a weighed generic food keeps `weighed` (REQ-NUT-035).
    assert nutrition.stored_estimate_method(
        source_claim="usda_foundation", grams_stated=True,
        resolved_source="usda_foundation") == "weighed"


def test_REQ_NUT_032_an_unenumerated_method_is_refused_rather_than_stored(sql_connection):
    """The enforcement, not just the mapping. A future resolution shape that produced
    something outside the five would otherwise be discovered the way this one was — by a
    display layer quietly matching nothing, months later."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    result = store(cur, cap, "synthetic oats", 380.0, 100)
    result = dict(result, stored_method="usda_foundation")
    with pytest.raises(ValueError, match="REQ-NUT-032"):
        nutrition.persist_resolution(cur, result, raw_capture_id=cap, occurred_at=WHEN,
                                     subject_day=DAY, evidence_span="another", schema=CORE)


def test_the_day_with_nothing_in_it_is_an_empty_day_and_not_a_zero(sql_connection):
    """An unlogged day is missing data, not a day on which Joe ate nothing. INV: missing is
    not zero."""
    cur = world(sql_connection.cursor())
    code, out = run(cur, DAY.isoformat())
    assert code == 0
    assert "0 resolved item(s)" in out
    # `daily_total` of nothing is 0-0, which is honest ONLY because n_items says it is empty.
    report = nutrition_day.build_report(*nutrition_day.read_day(cur, DAY, schema=CORE))
    assert report["n_resolved"] == 0 and report["n_unresolved"] == 0


def test_only_the_requested_day_is_reported(sql_connection):
    """A total that quietly included yesterday would be wrong in a way nothing on the page
    could show."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic oats", 380.0, 100, span="today's oats")
    other = nutrition.resolve_item(cur, "synthetic oats", grams=100,
                                   sources={"joe": nutrition.CacheLeg(cur, schema=CORE)},
                                   schema=CORE, config=CONFIG, ops=OPS)
    nutrition.persist_resolution(cur, other, raw_capture_id=cap, occurred_at=WHEN,
                                 subject_day=DAY - dt.timedelta(days=1),
                                 evidence_span="yesterday's oats", schema=CORE)

    code, out = run(cur, DAY.isoformat())
    assert code == 0
    assert "today's oats" in out and "yesterday's oats" not in out
    assert "1 resolved item(s)" in out


def test_a_bad_date_is_refused_with_a_nonzero_exit(sql_connection):
    """The refusal is observable. A command that printed a complaint and exited 0 would be
    reported as success by anything scripting it."""
    cur = world(sql_connection.cursor())
    code, _ = run(cur, "the day before yesterday")
    assert code == 2


def test_the_command_issues_no_write(sql_connection):
    """Read-only by construction, asserted rather than promised: the module's own source
    contains no INSERT/UPDATE/DELETE, and a run leaves the tables it read unchanged."""
    cur = world(sql_connection.cursor())
    cap = capture(cur)
    store(cur, cap, "synthetic oats", 380.0, 100)

    def counts():
        out = {}
        for table in ("atoms", "foods_cache", "unresolved_items", "food_aliases"):
            cur.execute(f"select count(*) from {CORE}.{table}")
            out[table] = cur.fetchone()[0]
        return out

    before = counts()
    assert run(cur, DAY.isoformat(), "--target", "2200", "--analysis", "weight")[0] == 0
    assert counts() == before

    # Structural, and over the SQL the module actually executes rather than over its prose —
    # the docstring says the words "INSERT, UPDATE or DELETE" to explain their absence, and a
    # substring scan of the whole file matches its own explanation.
    import ast
    tree = ast.parse(Path(nutrition_day.__file__).read_text())
    def literal(node):
        """The fixed text of a SQL argument. The statements are f-strings — schema names are
        parameters (ADR-0061) — so the interpolations are dropped and the literal parts kept."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            return "".join(v.value for v in node.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
        return None

    statements = [text for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                  and n.func.attr == "execute" and n.args
                  for text in [literal(n.args[0])] if text]
    assert statements, "no SQL found; the scan would pass vacuously"
    for sql in statements:
        head = sql.strip().lower()
        assert head.startswith("select"), f"not a SELECT: {sql[:60]!r}"
        for verb in ("insert into", "update ", "delete from"):
            assert verb not in head, f"{verb!r} in a command documented as read-only"
