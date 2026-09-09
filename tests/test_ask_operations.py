"""B11.1 — the operations that were placeholders, and the requirement IDs that had no test.

`compare`, `contrast` and `spend` were shipped as stubs in the migration 0049 draft: `compare`
was routed into the effect branch (a different question with a different answer shape),
`contrast` returned `delta: NULL` into a template that renders "ran {delta} lower", and `spend`
returned a hardcoded NULL total. The handoff said explicitly that they must be replaced, not
shipped. These tests are what replacing them means.
"""
import datetime as dt
import json
import uuid

import pytest

from tests._ask_fixture import ask_cur          # noqa: F401  (pytest fixture)
from tests._sql_fixture import sql_connection   # noqa: F401  (pytest fixture)

AS_OF = dt.date(2026, 9, 8)


def ask(cur, question, as_of=AS_OF):
    cur.execute("SELECT public_pytest.ask(%s, %s)", (question, as_of))
    r = cur.fetchone()[0]
    return r if isinstance(r, dict) else json.loads(r)


def panel(cur, metric, day, value):
    cur.execute("""INSERT INTO analysis_pytest.panel (day, metric, value, src, code_version)
                   VALUES (%s,%s,%s,'fixture','test') ON CONFLICT DO NOTHING""",
                (day, metric, value))


def register_metric(cur, key, display, unit, family="test"):
    cur.execute("""INSERT INTO ask_core_pytest.metric_registry
                     (metric_key, display_name, family, unit, state_class)
                   VALUES (%s,%s,%s,%s,'measurement') ON CONFLICT DO NOTHING""",
                (key, display, family, unit))


# ------------------------------------------------------------------ compare (metric, condition)

def test_REQ_ASK_005_compare_splits_the_metric_by_a_numeric_condition(ask_cur):
    """`compare` is metric+condition: the metric on days meeting it against the days that do not.

    The draft routed `compare` into the effect/contrast branch, which resolves a *second metric*
    and looks for a finding. That is a different operation, so `compare` could never return the
    shape `config.operations` says it returns.
    """
    cur = ask_cur
    for i in range(1, 11):                      # steps 10,20,...,100 on ten consecutive days
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)

    r = ask(cur, "my steps on days above 50 last 10 days")
    assert r.get("refusal") is None, r
    res = r["result"] if "result" in r else None
    # The envelope carries the answer; the stored computation carries the numbers.
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    stored = cur.fetchone()[0]
    stored = stored if isinstance(stored, dict) else json.loads(stored)
    assert stored["n_a"] == 5 and stored["n_b"] == 5, stored
    assert float(stored["a"]) == 80.0            # median of 60,70,80,90,100
    assert float(stored["b"]) == 30.0            # median of 10,20,30,40,50
    assert stored["condition"] == "above 50"
    assert r["tier"] == "DESCRIPTIVE"
    assert "80" in r["answer_text"] and "30" in r["answer_text"]


def test_REQ_ASK_022_compare_refuses_when_one_side_of_the_comparison_is_empty(ask_cur):
    """A comparison with an empty side is not a comparison.

    Rendering one median against nothing invites reading it as a difference. The refusal names
    which side is missing and what would raise it.
    """
    cur = ask_cur
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)

    r = ask(cur, "my steps on days above 1000 last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "low_coverage"
    assert r["missing_input"] == "comparison_half"
    assert r["condition"] == "above 1000"
    assert "would_raise_it" in r


def test_REQ_ASK_004_compare_refuses_an_unparseable_condition(ask_cur):
    """An unsupported comparison must refuse, not quietly become the band form.

    Falling through to "above the usual range" would answer a question nobody asked, with a
    number that looks exactly as authoritative as the right one.
    """
    cur = ask_cur
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
    r = ask(cur, "my steps on days above fifty last 10 days")
    assert r.get("refusal") is not None
    assert "nearest" in r


# ------------------------------------------------------------------ contrast reads the stored computation

def _store_contrast(cur, driver, outcome, lag, delta, run_date, q=0.01, code="scan-v1"):
    cur.execute("""INSERT INTO analysis_pytest.contrasts
        (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
         med_hi, med_lo, delta, p_raw, q_fdr, code_version)
        VALUES (%s,%s,%s,%s,%s,true,40,40,100,100,%s,0.001,%s,%s)""",
        (f"{driver}|{outcome}|{lag}|{run_date}", run_date, driver, outcome, lag, delta, q, code))


def test_REQ_ASK_032_contrast_reads_the_stored_computation_and_never_recomputes_it(ask_cur):
    """RULE-12: the quartile contrast has exactly one owner — the weekly scan engine.

    `ask` renders that stored row. Recomputing it in plpgsql would be a second definition of
    the same number: the scan's version carries the Mann-Whitney p, the BH q and the weekday
    partialling this function cannot reproduce, so the two would differ silently.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 7))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    stored = cur.fetchone()[0]
    stored = stored if isinstance(stored, dict) else json.loads(stored)

    assert r["tier"] == "EXPLORATORY", "no registered finding -> exploratory, never causal"
    assert float(stored["delta"]) == 7.5
    assert stored["direction"] == "lower"
    assert stored["owner"].endswith(".contrasts"), stored["owner"]
    assert stored["owner_code_version"] == "scan-v1"
    assert str(stored["computed_on"]) == "2026-09-07"
    # The rendered sentence must carry the exploratory hedge, not a causal verb.
    assert "exploratory" in r["answer_text"].lower()
    for causal in (" causes ", " caused ", " because "):
        assert causal not in r["answer_text"].lower()


def test_REQ_ASK_032_no_stored_contrast_is_a_documented_gap_not_a_null_delta(ask_cur):
    """The draft returned `delta: NULL` into "ran {delta} lower" — a sentence asserting a
    difference nobody measured. Absence must refuse instead."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 40 + i)

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "no_contrast_computed"
    assert "answer_text" not in r or "None" not in str(r.get("answer_text", ""))
    assert "would_raise_it" in r


def test_REQ_ASK_030_contrast_respects_the_as_of_date(ask_cur):
    """RULE-04 / REQ-ASK-030: a question asked as of D must not read a contrast computed after D.

    Point-in-time correctness is the whole reason `as_of` is a parameter; a stored computation
    from a later scan run is exactly the kind of after-the-fact knowledge that must not leak
    into an earlier answer.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 40 + i)
    # Computed AFTER the as-of date.
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 30))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "no_contrast_computed"

    # The same question once a run exists on or before the as-of date does answer.
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-4.0, run_date=dt.date(2026, 9, 1))
    r2 = ask(cur, "does my steps affect my hrv last 10 days")
    assert r2["tier"] == "EXPLORATORY"
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (r2["question_id"],))
    stored = cur.fetchone()[0]
    stored = stored if isinstance(stored, dict) else json.loads(stored)
    assert float(stored["delta"]) == 4.0, "the later run must not have been read"


def test_REQ_ASK_020_a_registered_finding_raises_the_tier_above_exploratory(ask_cur):
    """REQ-ASK-020: the tier is the operation's ceiling, and `effect` takes the finding's."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
         adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
         resolution_rule, status)
        VALUES ('h:steps->hrv', 'steps', 'hrv_sdnn_ms', 0, 'negative', 'none',
                '["day_of_week"]'::jsonb, 'quartile_contrast_mannwhitney',
                now() - interval '60 days', now() - interval '60 days',
                'two_look_v2', 'PROMOTED')""")
    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_resolutions
        (hypothesis_id, status_from, status_to, reason, post_days, delta,
         registered_direction, code_version)
        VALUES ('h:steps->hrv', 'WATCHING', 'PROMOTED', 'promoted_same_sign_q_lt_0_10',
                40, -3.2, 'negative', 'resolve-v2')""")

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "PROMOTED", r
    assert "provisional" in r["answer_text"].lower()
    # A PROMOTED finding is not a causal claim (RULE-16 / REQ-ASK-032).
    assert "adjusted for" not in r["answer_text"].lower()


# ------------------------------------------------------------------ spend

def test_REQ_ASK_023_spend_with_no_transactions_refuses_and_says_what_would_fix_it(ask_cur):
    """The draft returned a hardcoded NULL total with a note. An absent answer must be the
    stored refusal form, and it must name the action that would produce the data."""
    cur = ask_cur
    r = ask(cur, "how much did i spend at mcdonalds this year")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "metric_absent"
    assert r["entity"] == "mcdonalds"
    assert "import_drop" in r["would_raise_it"]
    assert r.get("total") is None, "no total may be reported when there is no data"


def test_REQ_ASK_027_spend_totals_only_money_out_and_traces_to_transaction_atoms(ask_cur):
    """Spend is the sum of outflows over the range, matched on the statement descriptor.

    Inbound transfers are excluded: a $20 refund is not negative spending, and netting is
    REQ-FIN-050's job with linked transfers, not something to do by accident here.
    """
    cur = ask_cur
    cap = uuid.uuid4()
    cur.execute("""INSERT INTO ask_core_pytest.raw_captures
        (capture_id, captured_at, source, trust_level, payload, processing_status)
        VALUES (%s, now(), 'shortcut_text', 'trusted', '{}'::jsonb, 'enriched')""", (cap,))
    cur.execute("""INSERT INTO ask_core_pytest.metric_registry
        (metric_key, display_name, family, unit, state_class)
        VALUES ('transaction_amount_usd','Transaction amount','finance','usd','total')
        ON CONFLICT DO NOTHING""")
    rows = [(-12.50, "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS 123"),
            (-8.25,  "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS 456"),
            (25.00,  "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS REFUND"),
            (-40.00, "bank:apple_card;merchant=Shell;descriptor=SHELL OIL")]
    for i, (amount, span) in enumerate(rows):
        cur.execute("""INSERT INTO ask_core_pytest.atoms
            (raw_capture_id, kind, metric_key, occurred_at, time_precision, subject_day,
             subject_day_rule_version, presence, value_low, value_point, value_high,
             estimate_method, unit, state_class, trust_level, provenance, evidence_span,
             code_version)
            VALUES (%s,'transaction','transaction_amount_usd',%s,'day',%s,'v1-2026-08-23',
                    'observed',%s,%s,%s,'measured','usd','total','trusted','extracted',%s,'t')""",
            (cap, dt.datetime.combine(AS_OF - dt.timedelta(days=i), dt.time(12), tzinfo=dt.timezone.utc),
             AS_OF - dt.timedelta(days=i), amount, amount, amount, span))

    r = ask(cur, "how much did i spend at mcdonalds last 10 days")
    assert r.get("refusal") is None, r
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    stored = cur.fetchone()[0]
    stored = stored if isinstance(stored, dict) else json.loads(stored)
    assert float(stored["total"]) == 20.75, stored     # 12.50 + 8.25; refund and Shell excluded
    assert stored["n"] == 2
    assert stored["entity"] == "mcdonalds"
    assert "20.75" in r["answer_text"]


# ------------------------------------------------------------------ tier vocabulary and the grammar

# Terms that would state a causal relation. RULE-16 permits these only at CONFIRMED and above;
# a DESCRIPTIVE or EXPLORATORY answer containing one is a claim the evidence does not support.
CAUSAL_TERMS = ("causes", "caused", "because", "leads to", "makes your", "due to",
                "increases your", "decreases your", "improves your", "worsens")
CONFIRMED_ONLY = ("adjusted for", " per ")


def test_REQ_NAR_020_answer_vocabulary_stays_within_the_tier(ask_cur):
    """RULE-16 / REQ-NAR-020: a claim rendered in language above its tier fails the build.

    The check is on the language actually produced, not on the template in isolation: a
    template is only correct in the tier it is served at, and `effect` has one template per
    tier precisely so the verb changes with the evidence.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    checked = 0
    for question in ("how is my steps last 10 days",
                     "is my steps improving last 10 days",
                     "which weekday is my steps last 10 days",
                     "how many days my steps above 50 last 10 days",
                     "my steps on days above 50 last 10 days",
                     "does my steps affect my hrv last 10 days"):
        r = ask(cur, question)
        text = (r.get("answer_text") or "").lower()
        if not text:
            continue
        checked += 1
        tier = r["tier"]
        for term in CAUSAL_TERMS:
            assert term not in text, f"{tier} answer used causal term {term!r}: {text}"
        if tier not in ("CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL"):
            for term in CONFIRMED_ONLY:
                assert term not in text, f"{tier} answer used confirmed-only {term!r}: {text}"
        if tier == "EXPLORATORY":
            assert "exploratory" in text, f"an exploratory answer must say so: {text}"
    assert checked >= 5, "the fixture must actually exercise several tiers"


def test_REQ_NAR_020_every_seeded_template_is_inside_its_own_tier_vocabulary(ask_cur):
    """No stored template may contain a term reserved for a higher tier.

    This checks the templates directly, so a template added later cannot smuggle a causal verb
    into a DESCRIPTIVE answer without a test failing — the linter's job, applied to its source.
    """
    cur = ask_cur
    cur.execute("SELECT op, tier, template FROM config_pytest.ask_templates ORDER BY op, tier")
    rows = cur.fetchall()
    assert rows, "the templates must be seeded"
    for op, tier, template in rows:
        low = template.lower()
        for term in CAUSAL_TERMS:
            assert term not in low, f"{op}/{tier} template uses causal term {term!r}"
        if tier not in ("CONFIRMED_OBSERVATIONAL", "EXPERIMENTAL"):
            for term in CONFIRMED_ONLY:
                assert term not in low, f"{op}/{tier} template uses confirmed-only {term!r}"


# Twenty questions Joe would actually ask, and the operation each must map to. This is the
# grammar's acceptance fixture: the mapping is the contract between how he phrases a question
# and which registered operation runs, and nothing outside `config.operations` may run at all
# (REQ-ASK-004).
CANONICAL_QUESTIONS = [
    ("how is my sleep", "describe"),
    ("what is my steps", "describe"),
    ("show me my weight", "describe"),
    ("my hrv last 30 days", "describe"),
    ("is my sleep improving", "trend"),
    ("has my weight changed this year", "trend"),
    ("is my steps going up", "trend"),
    ("my hrv over time", "trend"),
    ("which weekday is my steps highest", "rhythm"),
    ("what day of the week is my sleep worst", "rhythm"),
    ("when did i last log my weight", "last"),
    ("last time i recorded my hrv", "last"),
    ("how many days my steps above 10000", "count_days"),
    ("how many days was my sleep below the usual range", "count_days"),
    ("my sleep on days when i drink", "compare"),
    ("my hrv on the days my steps are above 10000", "compare"),
    ("does alcohol affect my hrv", "effect"),
    ("do my steps drive my sleep", "effect"),
    ("how much did i spend at mcdonalds this year", "spend"),
    ("how much have i spent on coffee", "spend"),
]


@pytest.mark.parametrize("question,expected_op", CANONICAL_QUESTIONS)
def test_ADR_0053_grammar_maps_twenty_canonical_questions_to_expected_ops(ask_cur, question, expected_op):
    """The grammar lives in `config.ask_grammar`, so this reads it rather than the code."""
    cur = ask_cur
    cur.execute("""SELECT g.op FROM config_pytest.ask_grammar g
                    WHERE %s ~ g.pattern ORDER BY g.priority LIMIT 1""", (question,))
    row = cur.fetchone()
    got = row[0] if row else "search"
    assert got == expected_op, f"{question!r} mapped to {got!r}, expected {expected_op!r}"
    # And whatever it mapped to must be a registered operation (REQ-ASK-004).
    cur.execute("SELECT 1 FROM config_pytest.operations WHERE op = %s", (got,))
    assert cur.fetchone() is not None, f"{got!r} is not in config.operations"


def test_REQ_ASK_004_an_operation_outside_the_registry_can_never_run(ask_cur):
    """Every op the grammar can select is registered, so nothing unregistered is reachable."""
    cur = ask_cur
    cur.execute("""SELECT g.op FROM config_pytest.ask_grammar g
                    WHERE g.op NOT IN (SELECT op FROM config_pytest.operations)""")
    assert list(cur.fetchall()) == [], "the grammar can select an unregistered operation"
    cur.execute("""SELECT t.op FROM config_pytest.ask_templates t
                    WHERE t.op NOT IN (SELECT op FROM config_pytest.operations)""")
    assert list(cur.fetchall()) == [], "a template exists for an unregistered operation"
