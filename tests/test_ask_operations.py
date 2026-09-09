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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import pytest

from tests._ask_fixture import ask_cur          # noqa: F401  (pytest fixture)
from tests._sql_fixture import sql_connection   # noqa: F401  (pytest fixture)

AS_OF = dt.date(2026, 9, 8)


def ask(cur, question, as_of=AS_OF):
    cur.execute("SELECT public_pytest.ask(%s, %s)", (question, as_of))
    r = cur.fetchone()[0]
    return r if isinstance(r, dict) else json.loads(r)


def panel(cur, metric, day, value):
    """Upsert, deliberately.

    `tests/fixtures/ask_describe.sql` already seeds `steps` for the last ten days, so
    ON CONFLICT DO NOTHING silently kept the shared fixture's values and every test that
    thought it was setting up a scenario was quietly running against a different one — the
    compare tests split on a threshold no seeded value could cross. A test that cannot see
    which data it is asserting against is not testing anything.
    """
    cur.execute("""INSERT INTO analysis_pytest.panel (day, metric, value, src, code_version)
                   VALUES (%s,%s,%s,'fixture','test')
                   ON CONFLICT (day, metric) DO UPDATE SET value = excluded.value""",
                (day, metric, value))


def stored_result(cur, envelope):
    """The persisted computation behind an answer (REQ-ASK-006: written before narration)."""
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (envelope["question_id"],))
    row = cur.fetchone()
    assert row is not None, f"no computation persisted for {envelope}"
    return row[0] if isinstance(row[0], dict) else json.loads(row[0])


def register_metric(cur, key, display, unit, family="test"):
    cur.execute("""INSERT INTO ask_core_pytest.metric_registry
                     (metric_key, display_name, family, unit, state_class)
                   VALUES (%s,%s,%s,%s,'measurement') ON CONFLICT DO NOTHING""",
                (key, display, family, unit))


# ------------------------------------------------------------------ compare (metric, condition)

def test_REQ_ASK_005_compare_splits_the_outcome_by_a_SECOND_metric(ask_cur):
    """`compare` is cross-metric: the outcome on days when ANOTHER metric qualifies.

    An earlier version split the outcome by its own value — "my steps on days my steps were
    high" — which is a nearly meaningless question that looks exactly as authoritative as the
    right one. The registered arity is metric+condition, and B11's grammar is
    "X on days when Y is high".
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    # HRV is the outcome; steps is the condition metric. On the five high-step days HRV is
    # low, on the five low-step days HRV is high — so splitting by the WRONG metric would
    # produce a visibly different answer.
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)                 # 1000..10000
        panel(cur, "hrv_sdnn_ms", day, 100 - i * 2)        # 98..80

    r = ask(cur, "my hrv on days when my steps are above 5000 last 10 days")
    assert r.get("refusal") is None, r
    cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    stored = cur.fetchone()[0]
    stored = stored if isinstance(stored, dict) else json.loads(stored)

    assert stored["condition_metric"] == "steps", "the split must be by the SECOND metric"
    assert stored["n_a"] == 5 and stored["n_b"] == 5
    assert float(stored["a"]) == 84.0    # HRV median on the 5 high-step days (88,86,84,82,80)
    assert float(stored["b"]) == 94.0    # HRV median on the 5 low-step days (98,96,94,92,90)
    assert stored["lag_days"] == 0
    # REQ-ASK-021: both metrics' coverage is reported, not only the outcome's.
    cur.execute("SELECT coverage FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    coverage = cur.fetchone()[0]
    coverage = coverage if isinstance(coverage, dict) else json.loads(coverage)
    assert set(coverage) == {"hrv_sdnn_ms", "steps"}, coverage


def test_REQ_ASK_005_after_days_shifts_the_outcome_by_one_day(ask_cur):
    """"after days when Y" compares the outcome on the day FOLLOWING a qualifying day.

    Without the shift the operation silently answers the same-day question, and a lagged
    hypothesis would be tested against unlagged data.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    # Steps qualify on exactly one day; HRV is distinctive on the day after it.
    base = AS_OF - dt.timedelta(days=6)
    for i in range(7):
        panel(cur, "steps", base + dt.timedelta(days=i), 9000 if i == 2 else 1000)
        panel(cur, "hrv_sdnn_ms", base + dt.timedelta(days=i), 55 if i == 3 else 40)

    same = ask(cur, "my hrv on days when my steps are above 5000 last 7 days")
    after = ask(cur, "my hrv after days when my steps are above 5000 last 7 days")
    for r, expected_lag, expected_a in ((same, 0, 40.0), (after, 1, 55.0)):
        cur.execute("SELECT result FROM ask_core_pytest.computations WHERE question_id = %s",
                    (r["question_id"],))
        stored = cur.fetchone()[0]
        stored = stored if isinstance(stored, dict) else json.loads(stored)
        assert stored["lag_days"] == expected_lag, stored
        assert float(stored["a"]) == expected_a, stored


def test_REQ_ASK_005_days_with_an_unknown_condition_are_in_neither_group(ask_cur):
    """RULE-07: an unobserved condition day is not a "did not qualify" day.

    Counting it as not-qualifying reads an absence as a negative observation and inflates the
    comparison group. Such days are excluded from both sides and reported as a count, so the
    reader can see how much of the range the comparison actually rests on.

    The condition metric here is `weight_lb`, which the shared fixture does NOT seed into the
    panel — using `steps` would silently inherit ten seeded days and the gaps would not be
    gaps at all. That is exactly how the first version of this test passed while asserting
    something it was not measuring.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "hrv_sdnn_ms", day, 50 + i)
        if i <= 6:                                    # weight observed on 6 of the 10 days
            panel(cur, "weight_lb", day, 150 + i)     # 151..156 -> 3 above 153, 3 below

    stored = stored_result(cur, ask(
        cur, "my hrv on days when my weight is above 153 last 10 days"))
    assert stored["condition_metric"] == "weight_lb", stored
    assert stored["n_a"] == 3 and stored["n_b"] == 3, stored
    assert stored["n_a"] + stored["n_b"] == 6, "the four unobserved days must be in neither group"
    assert stored["n_condition_missing"] == 4, stored


def test_REQ_ASK_022_compare_refuses_when_one_side_of_the_comparison_is_empty(ask_cur):
    """A comparison with an empty side is not a comparison; naming one median against
    nothing invites reading it as a difference."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 100)          # never above 5000
        panel(cur, "hrv_sdnn_ms", day, 50 + i)

    r = ask(cur, "my hrv on days when my steps are above 5000 last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "low_coverage"
    assert r["missing_input"] == "comparison_half"
    assert "would_raise_it" in r


def test_REQ_ASK_004_compare_without_a_second_metric_is_refused(ask_cur):
    """"my steps on days above 50" names no condition metric. Splitting the outcome by its
    own value would answer a different question rather than refuse."""
    cur = ask_cur
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 10)
    r = ask(cur, "my steps on days above 50 last 10 days")
    assert r.get("refusal") is not None, r
    assert r.get("reason") in ("no_condition_metric", "condition_metric_untracked"), r


def test_REQ_ASK_003_compare_with_an_untracked_condition_metric_refuses_with_nearest(ask_cur):
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=10 - i), 50 + i)
    r = ask(cur, "my hrv on days when my blood pressure is above 120 last 10 days")
    assert r["refusal"] == "I do not track that."
    assert r["reason"] == "condition_metric_untracked"
    assert r["nearest"]


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
    # Resolved BEFORE the as-of date. A resolution dated after it is correctly invisible to a
    # question asked earlier — proven separately by the replay test below.
    cur.execute("""UPDATE ask_core_pytest.hypothesis_resolutions
                      SET resolved_at = %s WHERE hypothesis_id = 'h:steps->hrv'""",
                (dt.datetime.combine(AS_OF - dt.timedelta(days=5), dt.time(12),
                                     tzinfo=dt.timezone.utc),))

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


# ------------------------------------------------------------------ direction and replay

def _register_finding(cur, hid, exposure, outcome, status, delta, resolved_on,
                      registered_on=None):
    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
         adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
         resolution_rule, status)
        VALUES (%s,%s,%s,0,'negative','none','["day_of_week"]'::jsonb,
                'quartile_contrast_mannwhitney',%s,%s,'two_look_v2',%s)""",
        (hid, exposure, outcome,
         registered_on or (AS_OF - dt.timedelta(days=60)),
         registered_on or (AS_OF - dt.timedelta(days=60)), status))
    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_resolutions
        (hypothesis_id, resolved_at, status_from, status_to, reason, post_days, delta,
         registered_direction, code_version)
        VALUES (%s,%s,'WATCHING',%s,'promoted_same_sign_q_lt_0_10',40,%s,'negative','resolve-v2')""",
        (hid, dt.datetime.combine(resolved_on, dt.time(12), tzinfo=dt.timezone.utc),
         status, delta))


def _two_metrics(cur):
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)


def test_REQ_ASK_032_a_reverse_direction_finding_does_not_answer_the_question(ask_cur):
    """RULE-19: exposure and outcome are not interchangeable.

    A registered finding that HRV predicts steps does not answer "does steps affect HRV".
    Serving it asserts a relationship the pre-registration never tested — and it is the same
    sentence, with the same tier, so nothing on the surface would reveal the substitution.
    The reverse finding is NAMED as a different available result instead.
    """
    cur = ask_cur
    _two_metrics(cur)
    _register_finding(cur, "h:hrv->steps", "hrv_sdnn_ms", "steps", "PROMOTED",
                      -3.2, AS_OF - dt.timedelta(days=5))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "INSUFFICIENT", r
    assert r["insufficiency_reason"] == "no_finding_in_this_direction"
    assert r["asked"] == "Steps -> HRV"
    assert r["available_instead"] == "HRV -> Steps"
    assert r["available_tier"] == "PROMOTED"
    assert "not interchangeable" in r["note"]

    # Asked in the direction that WAS registered, the same finding answers.
    r2 = ask(cur, "does my hrv affect my steps last 10 days")
    assert r2["tier"] == "PROMOTED", r2


def test_REQ_ASK_030_a_promotion_after_the_as_of_date_cannot_change_a_historical_answer(ask_cur):
    """Bitemporal replay, not a day cutoff on panel rows.

    `hypothesis_register.status` is a mutable column reflecting what is true NOW. Reading it
    means a promotion recorded next month silently rewrites the answer to a question asked
    today, and "what did the system say on D" stops being answerable. The status is taken
    from the latest resolution dated on or before `as_of`.
    """
    cur = ask_cur
    _two_metrics(cur)
    # Registered before as_of, but only RESOLVED to PROMOTED afterwards.
    _register_finding(cur, "h:steps->hrv", "steps", "hrv_sdnn_ms", "PROMOTED",
                      -3.2, AS_OF + dt.timedelta(days=10))
    cur.execute("""INSERT INTO analysis_pytest.contrasts
        (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
         med_hi, med_lo, delta, p_raw, q_fdr, code_version)
        VALUES ('c1',%s,'steps','hrv_sdnn_ms',0,true,40,40,100,100,-5.0,0.001,0.01,'scan-v1')""",
        (AS_OF - dt.timedelta(days=3),))

    asked_now = ask(cur, "does my steps affect my hrv last 10 days")
    assert asked_now["tier"] == "EXPLORATORY", \
        "a resolution dated after as_of must be invisible to a question asked before it"

    # The same question asked after the resolution date does see it. The window is widened so
    # the later as-of still covers the observed days; otherwise the answer refuses for absent
    # data and would prove nothing about the replay filter.
    # Days are added up to the later as-of so coverage does not floor the tier; the point
    # under test is the replay filter, not the coverage gate.
    for i in range(1, 21):
        day = AS_OF + dt.timedelta(days=i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    later = ask(cur, "does my steps affect my hrv last 30 days",
                as_of=AS_OF + dt.timedelta(days=20))
    assert later["tier"] == "PROMOTED", later


def test_REQ_ASK_030_a_hypothesis_registered_after_the_as_of_date_is_invisible(ask_cur):
    """RULE-19's pre-registration is a fact with a date. A hypothesis registered later cannot
    have informed an earlier answer."""
    cur = ask_cur
    _two_metrics(cur)
    _register_finding(cur, "h:late", "steps", "hrv_sdnn_ms", "PROMOTED",
                      -3.2, AS_OF + dt.timedelta(days=1),
                      registered_on=AS_OF + dt.timedelta(days=1))
    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] != "PROMOTED", r


def test_REQ_ASK_032_contrast_never_labels_a_stored_result_with_the_question_range(ask_cur):
    """A multi-year sweep must not be reported as a ten-day calculation.

    `analysis.contrasts` records no window, so the stored number cannot be matched to the
    question's range. The answer therefore discloses what it actually rests on — the observed
    high and low day counts and the run that produced it — rather than borrowing the range
    the question happened to name.
    """
    cur = ask_cur
    _two_metrics(cur)
    cur.execute("""INSERT INTO analysis_pytest.contrasts
        (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
         med_hi, med_lo, delta, p_raw, q_fdr, code_version)
        VALUES ('c1',%s,'steps','hrv_sdnn_ms',0,true,335,336,100,107.5,-7.5,0.001,0.01,'scan-v1')""",
        (dt.date(2026, 9, 7),))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    text = r["answer_text"]
    assert r["tier"] == "EXPLORATORY"
    assert "335 high and 336 low days" in text, text
    assert "the scan run of 2026-09-07" in text, text
    # The question's range must NOT be presented as the contrast's window.
    assert "last 10 days" not in text, text
    assert "2026-08-30" not in text, text
    stored = stored_result(cur, r)
    assert stored["window"] == "the scan run of 2026-09-07"
    assert stored["n_hi"] == 335 and stored["n_lo"] == 336


def test_REQ_ASK_032_contrast_in_only_the_reverse_direction_is_disclosed_not_served(ask_cur):
    cur = ask_cur
    _two_metrics(cur)
    cur.execute("""INSERT INTO analysis_pytest.contrasts
        (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
         med_hi, med_lo, delta, p_raw, q_fdr, code_version)
        VALUES ('c-rev',%s,'hrv_sdnn_ms','steps',0,true,40,40,100,100,-5.0,0.001,0.01,'scan-v1')""",
        (dt.date(2026, 9, 7),))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "no_contrast_computed"
    assert r["reverse_direction_available"] == "HRV -> Steps"
    assert "different question" in r["reverse_note"]


def test_RULE_16_a_coverage_floored_answer_never_uses_higher_tier_language(ask_cur):
    """Language falls with the tier; it never stays behind.

    When coverage floors an answer to INSUFFICIENT (REQ-TIER-017), the old template selection
    fell back to "any template for this op" — so an `effect` answer rendered the
    CONFIRMED_OBSERVATIONAL sentence, "runs {delta} per {driver} step, adjusted for
    {adjustment}": a causal, dose-response claim on an answer the system had just declared it
    could not support. The template is now chosen from the highest tier at or below the
    effective one.
    """
    cur = ask_cur
    _two_metrics(cur)
    _register_finding(cur, "h:steps->hrv", "steps", "hrv_sdnn_ms", "CONFIRMED_OBSERVATIONAL",
                      -3.2, AS_OF - dt.timedelta(days=5))
    # Ten observed days inside a ninety-day window: coverage ~0.11, far under the 0.60 gate.
    r = ask(cur, "does my steps affect my hrv last 90 days")
    assert r["tier"] == "INSUFFICIENT", r
    text = (r.get("answer_text") or "").lower()
    if text:
        for confirmed_only in ("adjusted for", " per ", "runs "):
            assert confirmed_only not in text, \
                f"INSUFFICIENT answer used CONFIRMED language {confirmed_only!r}: {text}"
        for causal in CAUSAL_TERMS:
            assert causal not in text, text


def test_RULE_16_tier_rank_orders_the_ladder(ask_cur):
    """The ordering itself, since every language gate now depends on it."""
    cur = ask_cur
    cur.execute("""SELECT public_pytest._ask_tier_rank('INSUFFICIENT'),
                          public_pytest._ask_tier_rank('DESCRIPTIVE'),
                          public_pytest._ask_tier_rank('EXPLORATORY'),
                          public_pytest._ask_tier_rank('PROMOTED'),
                          public_pytest._ask_tier_rank('CONFIRMED_OBSERVATIONAL'),
                          public_pytest._ask_tier_rank('EXPERIMENTAL'),
                          public_pytest._ask_tier_rank('nonsense')""")
    ins, desc, expl, prom, conf, exp, unknown = cur.fetchone()
    assert ins < desc < expl < prom < conf < exp
    assert unknown == ins, "an unknown tier must rank at the bottom, never above"


# ------------------------------------------------------------------ trend's rolling-28 contract

def test_REQ_ASK_005_trend_reports_the_28_day_rolling_median_at_range_end(ask_cur):
    """B11's registered `trend` contract is the two halves AND the 28-day rolling median.

    The halves answer "did it move across this period"; the rolling figure answers "where is
    it now", which is a different question and the one a reader acts on. The window ends at
    the range end and reaches back 28 days — which may extend BEFORE the requested range, so
    its own day count is reported rather than implied.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    # 40 consecutive days. The last 28 are 60..87, whose median is 73.5. It is NOT rounded to
    # 74: rounding is registry-driven (REQ-NAR-015) and this metric has no registered rounding
    # step, so the median is reported as computed rather than tidied by the narrator.
    for i in range(40):
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=39 - i), 48 + i)

    r = ask(cur, "has my hrv changed last 40 days")
    stored = stored_result(cur, r)
    assert stored["rolling_28_n"] == 28
    assert stored["rolling_28_window_days"] == 28
    assert str(stored["rolling_28_from"]) == str(AS_OF - dt.timedelta(days=27))
    assert str(stored["rolling_28_to"]) == str(AS_OF)
    assert float(stored["rolling_28"]) == 73.5, stored
    assert "the median was 73.5 ms" in r["answer_text"], r["answer_text"]
    # The halves are still reported; the rolling figure adds to them, it does not replace them.
    assert stored["n_first"] == 20 and stored["n_second"] == 20


def test_RULE_06_a_thin_rolling_window_states_the_shortfall_rather_than_a_median(ask_cur):
    """A median of a handful of days must not be presented as a 28-day figure.

    Reporting one anyway is the plausible-value failure RULE-06 exists to prevent: the number
    would be real arithmetic over the wrong window, and nothing in the sentence would say so.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(13):                       # 13 days, one below the 14-day floor
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=12 - i), 50 + i)

    r = ask(cur, "has my hrv changed last 13 days")
    stored = stored_result(cur, r)
    assert stored["rolling_28"] is None, stored
    assert stored["rolling_28_n"] == 13
    assert "too few for a 28-day median" in r["answer_text"]
    # And the sentence names the actual count, so the shortfall is legible.
    assert "only 13 days with data" in r["answer_text"]


def test_REQ_NAR_012_every_numeral_in_the_rolling_clause_traces_to_a_stored_value(ask_cur):
    """The clause is ASSEMBLED from stored numbers, never computed during narration.

    It exists only because the template mechanism has no conditional. Each numeral it emits
    must still appear in the persisted result, or the verifier discards the whole answer —
    which is what happened when an earlier version put a raw date in the template and its
    digits (2026 / 09 / 08) matched no stored value.
    """
    import re
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(40):
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=39 - i), 48 + i)

    r = ask(cur, "has my hrv changed last 40 days")
    assert "did not pass numeral verification" not in r["answer_text"]
    stored = stored_result(cur, r)
    stored_numerals = set()
    for v in stored.values():
        stored_numerals.update(re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", str(v)))
    for numeral in re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", r["answer_text"]):
        assert numeral in stored_numerals, f"{numeral!r} is in the answer but not in the result"


# ------------------------------------------------------------------ executor write separation

LEDGER_TABLES = ("questions", "computations", "render_violations")


def test_REQ_ASK_005_the_executor_writes_only_its_own_ledger(ask_cur):
    """The executor reads the record and writes nothing but the question/computation ledger.

    `ask` cannot run inside a READ ONLY transaction, because it must persist the computation
    BEFORE narration (REQ-ASK-006). So the separation is proven the other way: every mutating
    statement in the function targets one of three ledger tables, and nothing else in the
    database is written by answering a question. A `spend` or `compare` answer must never
    alter `analysis.panel`, `core.atoms` or any registry.
    """
    import re
    cur = ask_cur
    body = (ROOT / "migrations" / "0049_ask_core.sql").read_text()
    fn_start = body.index("CREATE OR REPLACE FUNCTION public.ask(")
    fn = body[fn_start:body.index("$fn$;", fn_start)]

    mutations = re.findall(
        r"\b(insert\s+into|update|delete\s+from)\s+([A-Za-z_.]*[A-Za-z_]+)", fn, re.IGNORECASE)
    assert mutations, "the ledger writes must be findable, or this test proves nothing"
    for verb, target in mutations:
        table = target.rsplit(".", 1)[-1]
        assert table in LEDGER_TABLES, \
            f"the executor performs `{verb} {target}` — only {LEDGER_TABLES} may be written"


def test_REQ_ASK_005_answering_a_question_changes_no_observation(ask_cur):
    """Behavioural counterpart: the record is byte-identical before and after a question.

    The static check above cannot see a write performed through a function `ask` calls; this
    one compares the actual contents of the observation tables across a batch of questions
    covering every operation branch.
    """
    cur = ask_cur
    _two_metrics(cur)
    cur.execute("""INSERT INTO analysis_pytest.contrasts
        (contrast_id, run_date, driver, outcome, lag_days, seeded, n_hi, n_lo,
         med_hi, med_lo, delta, p_raw, q_fdr, code_version)
        VALUES ('c1',%s,'steps','hrv_sdnn_ms',0,true,40,40,100,100,-5.0,0.001,0.01,'scan-v1')""",
        (AS_OF - dt.timedelta(days=1),))

    def snapshot():
        out = {}
        for table in ("analysis_pytest.panel", "analysis_pytest.contrasts",
                      "ask_core_pytest.metric_registry", "ask_core_pytest.atoms",
                      "ask_core_pytest.hypothesis_register", "config_pytest.operations",
                      "config_pytest.ask_templates", "config_pytest.ask_grammar"):
            cur.execute(f"SELECT count(*), coalesce(md5(string_agg(t::text, '|' ORDER BY t::text)), '') "
                        f"FROM {table} t")
            out[table] = cur.fetchone()
        return out

    before = snapshot()
    for question in ("how is my steps last 10 days",
                     "has my steps changed last 10 days",
                     "which weekday is my steps last 10 days",
                     "when did i last log my steps",
                     "how many days my steps above 5 last 10 days",
                     "my hrv on days when my steps are above 5000 last 10 days",
                     "does my steps affect my hrv last 10 days",
                     "how much did i spend at mcdonalds last 10 days",
                     "what is my blood pressure"):
        ask(cur, question)
    after = snapshot()

    assert before == after, "answering a question mutated the record"

    # And the ledger DID grow, so the comparison above is not vacuous.
    cur.execute("SELECT count(*) FROM ask_core_pytest.questions")
    assert cur.fetchone()[0] >= 9


# ------------------------------------------------------------------ search and entity payloads

def _event(cur, day, kind, payload):
    cur.execute("""INSERT INTO public_pytest.events (ts, kind, payload)
                   VALUES (%s,%s,%s::jsonb)""",
                (dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc), kind,
                 json.dumps(payload)))


def _transaction(cur, day, amount, merchant, category="food"):
    cur.execute("""INSERT INTO public_pytest.transactions
                     (ts, amount, currency, merchant, category, source)
                   VALUES (%s,%s,'USD',%s,%s,'test')""",
                (dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc),
                 amount, merchant, category))


def test_REQ_ASK_009_search_returns_the_records_not_only_a_count(ask_cur):
    """A bare count cannot be traced back to anything.

    REQ-ASK-009 requires every rendered numeral to reach a stored result. "12 records mention
    that", with no record identities behind it, is unverifiable by construction — the number
    is real but nothing can be checked against it. The full `search_record` payload is carried
    into the computation.
    """
    cur = ask_cur
    for i in range(3):
        _event(cur, AS_OF - dt.timedelta(days=i), "chrome_visit",
               {"title": "kubernetes networking notes", "domain": "example.com"})

    r = ask(cur, "kubernetes networking")
    assert r["op"] == "search", r
    stored = stored_result(cur, r)
    assert stored["n"] == 3, stored
    assert isinstance(stored["hits"], list) and len(stored["hits"]) == 3, stored
    assert stored["q"], "the executed query text must be stored"
    assert isinstance(stored["by_month"], list)
    assert "3 records" in r["answer_text"]


def test_REQ_ASK_023_a_search_matching_nothing_refuses_rather_than_reporting_zero(ask_cur):
    """RULE-18: absent evidence is disclosed as absent, with what would settle it.

    "0 records mention that" is a number standing in for an answer; the stored refusal form
    says the record holds nothing matching.
    """
    cur = ask_cur
    r = ask(cur, "xylophone thermodynamics")
    assert r["tier"] == "INSUFFICIENT"
    assert r["refusal"] == "We do not have enough to answer this."
    assert r["insufficiency_reason"] == "metric_absent"
    assert r["n"] == 0
    assert "would_raise_it" in r


def test_REQ_ASK_004_entity_is_reachable_and_answers_from_get_entity(ask_cur):
    """The `entity` operation was registered and unreachable.

    `config.operations` listed it from the start, but no grammar pattern routed to it and
    `get_entity` was never called — a registered operation nothing could run. A question
    naming something the record knows as an entity is answered by that entity's own summary,
    not by a text search that happens to mention it.
    """
    cur = ask_cur
    for i in range(4):
        _transaction(cur, AS_OF - dt.timedelta(days=i), -12.50, "Blue Bottle Coffee")

    r = ask(cur, "Blue Bottle Coffee")
    assert r["op"] == "entity", r
    stored = stored_result(cur, r)
    assert stored["entity_type"] == "merchant"
    assert stored["entity_key"] == "Blue Bottle Coffee"
    assert stored["entity"], "the full get_entity response must be carried, not just a summary"
    assert r["tier"] == "DESCRIPTIVE"


def test_REQ_ASK_004_an_unknown_entity_falls_through_to_search(ask_cur):
    """Entity resolution must not swallow a question it cannot answer.

    A name `get_entity` does not know is not an entity answer; it falls through to search,
    which then refuses honestly if nothing matches either.
    """
    cur = ask_cur
    r = ask(cur, "Nonexistent Merchant Ltd")
    assert r.get("op") != "entity", r
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "metric_absent"


def test_REQ_ASK_005_search_and_entity_persist_a_computation_before_narrating(ask_cur):
    """REQ-ASK-006 applies to every operation, including the two that were stubs."""
    cur = ask_cur
    for i in range(2):
        _event(cur, AS_OF - dt.timedelta(days=i), "chrome_visit",
               {"title": "postgres indexes", "domain": "example.com"})
    _transaction(cur, AS_OF, -5.00, "Blue Bottle Coffee")

    for question in ("postgres indexes", "Blue Bottle Coffee"):
        r = ask(cur, question)
        cur.execute("""SELECT count(*) FROM ask_core_pytest.computations
                        WHERE question_id = %s""", (r["question_id"],))
        assert cur.fetchone()[0] == 1, f"{question!r} persisted no computation"
        assert stored_result(cur, r), question
