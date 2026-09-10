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


def ask(cur, question, as_of=AS_OF, known_at=None):
    """`as_of` bounds subject days; `known_at` bounds knowledge time and defaults to now()."""
    if known_at is None:
        cur.execute("SELECT public_pytest.ask(%s, %s)", (question, as_of))
    else:
        cur.execute("SELECT public_pytest.ask(%s, %s, %s)", (question, as_of, known_at))
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
    """An absent answer is the stored refusal form, and it names the real limitation.

    The draft returned a hardcoded NULL total with a note. It must also say WHY a charge might
    be missing — merchant resolution is not built, so a charge under a different descriptor is
    invisible to this match — rather than implying the record is simply empty.
    """
    cur = ask_cur
    r = ask(cur, "how much did i spend at mcdonalds this year")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "metric_absent"
    assert r["matched_on"] == "mcdonalds"
    assert r["match_method"] == "statement_descriptor_contains"
    assert "merchant resolution is not built" in r["would_raise_it"].lower()
    assert r.get("total") is None and r.get("total_out") is None


def test_REQ_ASK_004_spend_without_a_subject_is_refused(ask_cur):
    cur = ask_cur
    r = ask(cur, "how much did i spend")
    assert r.get("refusal") is not None
    assert r["reason"] == "no_spend_subject"


def _txn_atom(cur, day, amount, descriptor, unit="usd", recorded_at=None):
    """`recorded_at` defaults to the subject day, which is what a real import produces.

    Leaving it at `now()` made every fixture atom "learned today", so a question asked as of
    yesterday correctly excluded them — the RULE-04 cutoff working, on data no real capture
    would look like.
    """
    cur.execute("""INSERT INTO ask_core_pytest.metric_registry
        (metric_key, display_name, family, unit, state_class)
        VALUES ('transaction_amount_usd','Transaction amount','finance','usd','total')
        ON CONFLICT DO NOTHING""")
    cur.execute("SELECT capture_id FROM ask_core_pytest.raw_captures LIMIT 1")
    row = cur.fetchone()
    if row is None:
        cap = uuid.uuid4()
        cur.execute("""INSERT INTO ask_core_pytest.raw_captures
            (capture_id, captured_at, source, trust_level, payload, processing_status)
            VALUES (%s, now(), 'shortcut_text', 'trusted', '{}'::jsonb, 'enriched')""", (cap,))
    else:
        cap = row[0]
    cur.execute("""INSERT INTO ask_core_pytest.atoms
        (raw_capture_id, kind, metric_key, occurred_at, time_precision, subject_day,
         subject_day_rule_version, presence, value_low, value_point, value_high,
         estimate_method, unit, state_class, trust_level, provenance, evidence_span,
         code_version)
        VALUES (%s,'transaction','transaction_amount_usd',%s,'day',%s,'v1-2026-08-23',
                'observed',%s,%s,%s,'measured',%s,'total','trusted','extracted',%s,'t')
        RETURNING id""",
        (cap, dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc), day,
         amount, amount, amount, unit, descriptor))
    atom_id = cur.fetchone()[0]
    cur.execute("UPDATE ask_core_pytest.atoms SET recorded_at = %s WHERE id = %s",
                (recorded_at or dt.datetime.combine(day, dt.time(12), tzinfo=dt.timezone.utc),
                 atom_id))


def test_REQ_ASK_027_spend_separates_outflow_from_inflow_and_never_nets_them(ask_cur):
    """Outflows and inflows are reported separately, never netted here.

    REQ-FIN-050 nets inbound P2P transfers against bar and restaurant spend, but only through
    LINKED `transfers` rows. Netting an arbitrary refund into a total silently changes what
    the number means, and a reader cannot undo it — the $20.75 they see would already have had
    the $25 refund subtracted with nothing saying so.
    """
    cur = ask_cur
    for amount, descriptor in (
            (-12.50, "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS 123"),
            (-8.25,  "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS 456"),
            (25.00,  "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS REFUND"),
            (-40.00, "bank:apple_card;merchant=Shell;descriptor=SHELL OIL")):
        _txn_atom(cur, AS_OF - dt.timedelta(days=1), amount, descriptor)

    r = ask(cur, "how much did i spend at mcdonalds last 10 days")
    assert r.get("refusal") is None, r
    stored = stored_result(cur, r)
    assert float(stored["total_out"]) == 20.75, stored     # the refund is NOT subtracted
    assert stored["n_out"] == 2
    assert float(stored["total_in"]) == 25.00, "the inflow must be reported, not silently dropped"
    assert stored["n_in"] == 1
    assert "20.75" in r["answer_text"]
    assert "25" not in r["answer_text"].replace("20.75", ""), "the total must not be netted"


def test_REQ_ASK_009_spend_states_the_match_method_in_the_answer_itself(ask_cur):
    """The limitation travels with the number.

    This measures charges whose STATEMENT DESCRIPTOR contains the text — not spend at a
    merchant. A McDonald's charge settling as "SQ *MCD 8005551212 CA" is a real charge this
    does not find, so the total is a floor. Merchant resolution is REQ-FIN-070..093 and
    belongs to B14; saying so in the sentence is the difference between a bounded measurement
    and a wrong one (ADR-0062).
    """
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -12.50,
              "bank:apple_card;merchant=McDonalds;descriptor=MCDONALDS 123")
    # The realistic miss: a payment-facilitator descriptor with no resolvable merchant text.
    # B13 writes the merchant column the statement supplied, and for a Square-routed charge
    # that is the DBA string, not "McDonalds".
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -30.00,
              "bank:apple_card;merchant=;descriptor=SQ *MCD 8005551212 CA")

    r = ask(cur, "how much did i spend at mcdonalds last 10 days")
    stored = stored_result(cur, r)
    assert stored["match_method"] == "statement_descriptor_contains"
    # The Square-routed charge is genuinely missed. That is the point: the number is a floor.
    assert float(stored["total_out"]) == 12.50, stored
    assert "matched on the statement descriptor" in r["answer_text"]
    assert "merchant resolution is not built" in r["answer_text"]


def test_REQ_ASK_021_spend_reports_a_weekly_rate_over_the_requested_window(ask_cur):
    """Totals alone do not compare across windows of different length."""
    cur = ask_cur
    for i in range(4):
        _txn_atom(cur, AS_OF - dt.timedelta(days=i), -35.00,
                  "bank:apple_card;merchant=Coffee;descriptor=COFFEE BAR")
    r = ask(cur, "how much did i spend at coffee last 14 days")
    stored = stored_result(cur, r)
    assert float(stored["total_out"]) == 140.00
    assert float(stored["weeks"]) == 2.0
    assert float(stored["per_week"]) == 70.00, stored
    assert "70" in r["answer_text"]


def test_RULE_12_spend_refuses_to_sum_across_currencies(ask_cur):
    """A number summed across units has no meaning.

    `transaction_amount_usd` is the only unit B13's importer writes, so a second unit means an
    importer changed and this query is no longer valid. Converting here would invent a rate.
    """
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -10.00,
              "bank:apple_card;merchant=Cafe;descriptor=CAFE LONDON", unit="usd")
    _txn_atom(cur, AS_OF - dt.timedelta(days=2), -8.00,
              "bank:apple_card;merchant=Cafe;descriptor=CAFE LONDON", unit="gbp")

    r = ask(cur, "how much did i spend at cafe last 10 days")
    assert r["tier"] == "INSUFFICIENT"
    assert r["insufficiency_reason"] == "mixed_currency"
    assert r.get("total_out") is None, "no total may be reported across currencies"
    assert "more than one currency" in r["would_raise_it"]


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
    # An absent median is an ABSENT key in the stored result too, not a null — the same
    # encoding the envelope uses, and for the same reason: a null invites a reader to treat it
    # as a value that happens to be empty.
    assert "rolling_28" not in stored, stored
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


# ------------------------------------------------------------------ replay and isolation

def test_REQ_ASK_030_reexecuting_the_same_question_at_the_same_as_of_is_identical(ask_cur):
    """The same question, same as-of, must produce the same numbers.

    This is the weaker half of replay and it is the half that is actually true today: the
    executor is deterministic over the data it can see. The stronger half — the same answer
    after later data arrives — is NOT proven here and cannot be, because `analysis.panel` is
    rebuilt wholesale by `panel.build` and carries no per-observation `recorded_at`. That is
    OQ-45 and it is named in the checkpoint rather than implied by this test's name.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)

    for question in ("how is my steps last 10 days",
                     "has my steps changed last 10 days",
                     "which weekday is my steps last 10 days",
                     "how many days my steps above 5000 last 10 days",
                     "my hrv on days when my steps are above 5000 last 10 days"):
        first, second = ask(cur, question), ask(cur, question)
        assert first["question_id"] != second["question_id"], "each asking is its own question"
        assert stored_result(cur, first) == stored_result(cur, second), question
        assert first.get("answer_text") == second.get("answer_text"), question
        assert first.get("tier") == second.get("tier"), question


def test_REQ_ASK_030_a_later_observation_changes_a_later_as_of_only(ask_cur):
    """Data recorded for a day AFTER the as-of must not enter an earlier answer.

    `f_daily_panel(as_of)` bounds the panel by subject day, so an observation dated after the
    as-of is invisible. This proves that bound holds; it does NOT prove replay against a
    correction to an EARLIER day, which the panel cannot express (OQ-45).
    """
    cur = ask_cur
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 1000)
    before = stored_result(cur, ask(cur, "how is my steps last 10 days"))

    # A day after the as-of.
    panel(cur, "steps", AS_OF + dt.timedelta(days=1), 999999)
    after = stored_result(cur, ask(cur, "how is my steps last 10 days"))
    assert after == before, "an observation dated after the as-of leaked into the answer"

    # And it IS visible to a question asked later, so the bound is a cutoff, not a filter bug.
    later = stored_result(cur, ask(cur, "how is my steps last 12 days",
                                   as_of=AS_OF + dt.timedelta(days=1)))
    assert float(later["max"]) == 999999.0, later


def test_RULE_29_the_ask_executor_makes_no_outbound_call(ask_cur):
    """Ask is the deterministic path and must not reach the network (RULE-15, RULE-29).

    Personal data leaves this system only through the egress-logged client. A SQL executor
    that could open a socket — via an http extension, `pg_net`, `dblink`, or COPY FROM PROGRAM
    — would be an unlogged egress path sitting directly on the record.
    """
    import re
    body = (ROOT / "migrations" / "0049_ask_core.sql").read_text().lower()
    for capability in ("pg_net", "dblink", "http_get", "http_post", "extensions.http",
                       "copy ", "program ", "pg_read_file", "pg_ls_dir"):
        assert capability not in body, f"the Ask migration references {capability!r}"

    # And no extension beyond the trigram matcher the metric resolver needs.
    extensions = set(re.findall(r"create extension(?: if not exists)?\s+([a-z_]+)", body))
    assert extensions <= {"pg_trgm"}, extensions


# ============================================================ defects found by adversarial review
# Each of these reproduces a case the review EXECUTED against a disposable server. They are
# written from the reported input and output, not from the fix, so a regression reproduces the
# original wrong answer rather than merely failing differently.

def _baseline(cur, metric, day, lo, hi):
    cur.execute("""INSERT INTO analysis_pytest.baselines (day, metric, band_lo, band_hi, code_version)
                   VALUES (%s,%s,%s,%s,'test')
                   ON CONFLICT (day, metric) DO UPDATE SET band_lo = excluded.band_lo,
                                                           band_hi = excluded.band_hi""",
                (day, metric, lo, hi))


def test_REQ_ASK_005_the_band_form_of_compare_answers_instead_of_crashing(ask_cur):
    """Review finding 1: the band form raised 23502 and Joe got a 500, not a refusal.

    The trace joined `analysis.baselines` on the OUTCOME while the band had been evaluated on
    the CONDITION metric. With no baselines for the outcome the join was empty, `jsonb_agg`
    returned NULL, and observation_keys NOT NULL aborted the function — after the answer had
    been computed correctly. No test executed a band-form compare at all, though it is the
    documented default reading and question 15 of the twenty canonical ones.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 21):
        day = AS_OF - dt.timedelta(days=20 - i)
        panel(cur, "steps", day, i * 500)
        panel(cur, "hrv_sdnn_ms", day, 60 if i > 10 else 50)
        _baseline(cur, "steps", day, 1000, 5000)          # bands for the CONDITION metric only

    r = ask(cur, "my hrv on days when my steps are above the usual range last 20 days")
    assert r.get("refusal") is None, r
    stored = stored_result(cur, r)
    assert stored["condition_metric"] == "steps"
    assert stored["n_a"] + stored["n_b"] == 20

    # And the trace is non-empty and names the metric the comparison actually rested on.
    cur.execute("SELECT observation_keys FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    keys = cur.fetchone()[0]
    keys = keys if isinstance(keys, list) else json.loads(keys)
    assert keys, "the trace must not be empty"
    assert any(k.get("metric") == "steps" for k in keys), "the condition metric must be traced"
    # The fixture rebinds schema names, so match the table rather than the full path.
    assert any((k.get("table") or "").endswith(".baselines") for k in keys), keys[:3]
    assert any((k.get("table") or "").endswith(".panel") for k in keys)
    assert {k.get("metric") for k in keys} == {"steps", "hrv_sdnn_ms"}, \
        "both the condition metric and the outcome must be traceable"


def test_RULE_05_a_two_metric_answer_states_the_outcome_unit_not_the_drivers(ask_cur):
    """Review finding 2: "HRV ran 7.5 steps lower" — and persisted as steps.

    The delta is in the OUTCOME's unit; `res.unit` was overwritten with the driver's after the
    branch had set it correctly, so the stored trace confirmed the wrong unit rather than
    correcting it. RULE-05: no number is rendered anywhere without its lane.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    stored = stored_result(cur, r)
    assert stored["unit"] == "ms", stored
    assert "7.5 ms" in r["answer_text"], r["answer_text"]
    assert "7.5 steps" not in r["answer_text"]

    # The numerals payload must agree: day counts are days, not the metric's unit.
    numerals = r.get("numerals") or []
    by_value = {n["value"]: n["unit"] for n in numerals}
    assert by_value.get("7.5") == "ms", numerals
    for count_value in ("335", "336"):
        if count_value in by_value:
            assert by_value[count_value] == "days", numerals


def test_RULE_16_an_insufficient_answer_uses_no_tier_language_at_all(ask_cur):
    """Review finding 3: an INSUFFICIENT answer rendered PROMOTED vocabulary.

    "appears", "provisional", "watched" are all seeded PROMOTED terms. The tier bound was
    written and then defeated three lines later by a fallback that took the LOWEST template for
    the operation — still above INSUFFICIENT. My own test for this asserted only the CONFIRMED
    template's words, so the PROMOTED sentence passed it.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _register_finding(cur, "h:steps->hrv", "steps", "hrv_sdnn_ms", "PROMOTED",
                      -3.2, AS_OF - dt.timedelta(days=5))

    # Ten observed days in a ninety-day window: coverage ~0.11, far under the 0.60 gate.
    for question in ("does my steps affect my hrv last 90 days",
                     "how is my steps last 90 days",
                     "which weekday is my steps last 90 days",
                     "how many days my steps above 5000 last 90 days"):
        r = ask(cur, question)
        if r["tier"] != "INSUFFICIENT" or not r.get("answer_text"):
            continue
        text = r["answer_text"].lower()
        # Every tier's claim vocabulary, not just the CONFIRMED template's.
        for term in ("appears", "provisional", "watched", "consistent with",
                     "adjusted for", " per ", "runs ", "typically", "may reflect"):
            assert term not in text, f"INSUFFICIENT answer used {term!r}: {text}"


def test_REQ_ASK_027_a_multi_clause_condition_is_refused_not_rewritten(ask_cur):
    """Review finding 6: "above 5000 and below 7" answered "above 7" — 20 of 20 where the
    truth was 10, at DESCRIPTIVE tier with no refusal.

    The direction came from the first comparator and the threshold from the last, and nothing
    required them to be the same clause.
    """
    cur = ask_cur
    for i in range(1, 21):
        panel(cur, "steps", AS_OF - dt.timedelta(days=20 - i), i * 500)

    for question in ("how many days my steps above 5000 and below 7 last 20 days",
                     "how many days my steps under 5 and over 100 last 20 days"):
        r = ask(cur, question)
        assert r.get("refusal") is not None, f"{question!r} answered: {r}"
        assert r.get("tier") is None, r

    # The single-clause forms still work.
    ok = ask(cur, "how many days my steps above 5000 last 20 days")
    assert ok.get("refusal") is None and ok["tier"] == "DESCRIPTIVE"


def test_REQ_ASK_004_compare_refuses_a_condition_it_cannot_read(ask_cur):
    """Review finding 6b: `count_days` refused an unreadable condition and `compare` fell
    through to the band form — answering a different question. The shared parser exists so
    the two cannot disagree about one phrase."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
        _baseline(cur, "steps", day, 1000, 5000)

    r = ask(cur, "my hrv on days when my steps are above fifty last 10 days")
    assert r.get("refusal") is not None, r
    assert r["reason"] == "condition_not_readable", r


def test_REQ_ASK_005_compare_refuses_to_split_a_metric_by_itself(ask_cur):
    """Review finding 14: the same-metric split was permitted, and `cov`'s duplicate key
    collapsed so the "both metrics' coverage" contract silently degraded to one."""
    cur = ask_cur
    for i in range(1, 21):
        panel(cur, "steps", AS_OF - dt.timedelta(days=20 - i), i * 500)
    r = ask(cur, "my steps on days when my steps are above 5000 last 20 days")
    assert r.get("refusal") is not None, r
    assert r.get("reason") == "condition_metric_untracked", r


def test_RULE_12_spend_refuses_when_a_matching_charge_has_no_currency(ask_cur):
    """Review finding 9: count(DISTINCT) ignores NULLs, so two unit-less atoms counted as
    ZERO currencies and `coalesce(term,'usd')` invented one — a total labelled usd with no row
    saying so. A missing unit is not agreement."""
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -10.00,
              "bank:x;merchant=Cafe;descriptor=CAFE", unit=None)
    _txn_atom(cur, AS_OF - dt.timedelta(days=2), -10.50,
              "bank:x;merchant=Cafe;descriptor=CAFE", unit=None)

    r = ask(cur, "how much did i spend at cafe last 10 days")
    assert r["tier"] == "INSUFFICIENT", r
    assert r["insufficiency_reason"] == "unit_missing", r
    assert r["charges_without_a_unit"] == 2
    assert r.get("total_out") is None and r.get("currency") is None


def test_RULE_12_spend_treats_the_subject_as_data_not_a_pattern(ask_cur):
    """Review finding 10: "spend on %" matched every charge and reported the lot as that
    merchant's — carrying a caveat saying it may have UNDER-counted."""
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -10.00, "bank:x;merchant=Cab;descriptor=CAB RIDE")
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -500.00, "bank:x;merchant=Car;descriptor=CAR PAYMENT")

    for wildcard in ("%", "ca_", "_a_"):
        r = ask(cur, f"how much did i spend at {wildcard} last 10 days")
        assert r["tier"] == "INSUFFICIENT", f"{wildcard!r} matched something: {r}"
        assert r["insufficiency_reason"] == "metric_absent"

    # A literal substring still works.
    ok = ask(cur, "how much did i spend at car last 10 days")
    assert float(stored_result(cur, ok)["total_out"]) == 500.00


def test_REQ_ASK_022_count_days_remediation_names_the_actual_missing_input(ask_cur):
    """Review finding 11: `condition_match` was declared, never assigned, so the band-form
    remediation text fired for a pure numeric threshold — telling Joe to compute comparison
    bands for a query that uses none."""
    cur = ask_cur
    for i in range(1, 11):
        panel(cur, "steps", AS_OF - dt.timedelta(days=10 - i), i * 1000)

    r = ask(cur, "how many days my steps above 5000 last 90 days")
    if r.get("would_raise_it"):
        assert "comparison band" not in r["would_raise_it"].lower(), \
            f"a threshold query was told to fix bands: {r['would_raise_it']}"


def test_REQ_ASK_030_the_as_of_filter_does_not_depend_on_the_session_timezone(ask_cur):
    """Review finding 5: same question, same as_of, same data — PROMOTED from New York,
    INSUFFICIENT from Tokyo.

    `timestamptz::date` uses whatever timezone the session has. CI runs UTC, the fixture ran
    ET, and every fixture in the suite wrote resolutions at 12:00 UTC — which never crosses a
    date boundary in either zone, which is exactly why "passes under both timezones" did not
    catch it. This one writes 23:30 UTC on the as-of day, where the zones disagree.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_register
        (hypothesis_id, exposure_metric, outcome_metric, lag_days, direction, transformation,
         adjustment_set, test_statistic, preregistered_at, confirmation_data_from,
         resolution_rule, status)
        VALUES ('h:tz','steps','hrv_sdnn_ms',0,'negative','none','["day_of_week"]'::jsonb,
                'quartile_contrast_mannwhitney', %s, %s, 'two_look_v2','PROMOTED')""",
        (AS_OF - dt.timedelta(days=60), AS_OF - dt.timedelta(days=60)))
    # 23:30 UTC on the as-of day: 19:30 ET (same subject day) but 08:30 next-day in Tokyo.
    cur.execute("""INSERT INTO ask_core_pytest.hypothesis_resolutions
        (hypothesis_id, resolved_at, status_from, status_to, reason, post_days, delta,
         registered_direction, code_version)
        VALUES ('h:tz', %s, 'WATCHING','PROMOTED','promoted_same_sign_q_lt_0_10',40,-3.2,
                'negative','resolve-v2')""",
        (dt.datetime.combine(AS_OF, dt.time(23, 30), tzinfo=dt.timezone.utc),))

    tiers = []
    for zone in ("America/New_York", "Asia/Tokyo", "UTC", "America/Los_Angeles"):
        cur.execute(f"set timezone = '{zone}'")
        tiers.append((zone, ask(cur, "does my steps affect my hrv last 10 days")["tier"]))
    cur.execute("set timezone = 'UTC'")
    assert len({t for _, t in tiers}) == 1, f"the answer changed with the session timezone: {tiers}"


def test_REQ_ASK_021_a_two_metric_answer_reports_both_metrics_coverage(ask_cur):
    """Review finding 7: coverage was built for the driver only, so the outcome — the metric
    the delta is about — was neither disclosed nor gated, and the 0.60 floor applied to one
    side of a two-metric operation and not the other."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)              # observed on all 10
        if i <= 4:
            panel(cur, "hrv_sdnn_ms", day, 40 + i)      # observed on 4 of 10
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    cur.execute("SELECT coverage FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    coverage = cur.fetchone()[0]
    coverage = coverage if isinstance(coverage, dict) else json.loads(coverage)
    assert set(coverage) == {"steps", "hrv_sdnn_ms"}, coverage
    assert float(coverage["hrv_sdnn_ms"]) == 0.4, coverage
    # The MINIMUM gates the tier, so the outcome's thin coverage floors the answer.
    assert r["tier"] == "INSUFFICIENT", r


def test_REQ_ASK_021_compare_reports_each_metric_own_coverage_not_the_intersection(ask_cur):
    """Review finding 7b: the intersection was stored under BOTH keys, so a condition metric
    observed on every day read as 0.6 — two meanings of "coverage" in one column, and the
    wrong one feeding the gate."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 21):
        day = AS_OF - dt.timedelta(days=20 - i)
        panel(cur, "steps", day, i * 500)                # observed on all 20
        if i <= 12:
            panel(cur, "hrv_sdnn_ms", day, 40 + i)       # observed on 12 of 20

    r = ask(cur, "my hrv on days when my steps are above 5000 last 20 days")
    cur.execute("SELECT coverage FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    coverage = cur.fetchone()[0]
    coverage = coverage if isinstance(coverage, dict) else json.loads(coverage)
    assert float(coverage["steps"]) == 1.0, coverage
    assert float(coverage["hrv_sdnn_ms"]) == 0.6, coverage


def test_REQ_ASK_030_search_counts_only_hits_inside_the_range_it_names(ask_cur):
    """Review finding 4: `search_record` has no date predicate, so the sentence named a range
    the count did not respect — and one hit was 108 days AFTER the question's as_of."""
    cur = ask_cur
    inside = AS_OF - dt.timedelta(days=5)
    outside_past = AS_OF - dt.timedelta(days=400)
    after_as_of = AS_OF + dt.timedelta(days=108)
    for day in (inside, inside - dt.timedelta(days=1), outside_past, after_as_of):
        _event(cur, day, "chrome_visit",
               {"title": "kubernetes networking notes", "domain": "example.com"})

    r = ask(cur, "kubernetes networking last 90 days")
    stored = stored_result(cur, r)
    assert stored["n"] == 2, stored
    assert stored["n_all_time"] == 4, "the unfiltered count is kept, and labelled as such"
    for hit in stored["hits"]:
        assert str(inside - dt.timedelta(days=1)) <= hit["day"] <= str(AS_OF), hit
    assert "2 records" in r["answer_text"]


def test_REQ_ASK_011_every_operation_persists_a_traceable_observation_set(ask_cur):
    """Review finding 8: spend, search and entity persisted an EMPTY trace.

    REQ-ASK-011 requires click-through "to the underlying observation IDs". For `spend` the
    atom ids are known and were not recorded — which made the one operation whose measure is
    scheduled to be replaced (B14 re-points it at the merchant entity) the one that could not
    be re-traced afterwards. My own persistence test asserted only `count(*) == 1`.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -12.50,
              "bank:x;merchant=Cafe;descriptor=CAFE BAR")
    _event(cur, AS_OF - dt.timedelta(days=1), "chrome_visit",
           {"title": "postgres indexes", "domain": "example.com"})

    for question in ("how is my steps last 10 days",
                     "has my steps changed last 10 days",
                     "which weekday is my steps last 10 days",
                     "when did i last log my steps",
                     "how many days my steps above 5000 last 10 days",
                     "my hrv on days when my steps are above 5000 last 10 days",
                     "how much did i spend at cafe last 10 days",
                     "postgres indexes last 10 days"):
        r = ask(cur, question)
        if r.get("refusal"):
            continue
        cur.execute("""SELECT observation_keys FROM ask_core_pytest.computations
                        WHERE question_id = %s""", (r["question_id"],))
        keys = cur.fetchone()[0]
        keys = keys if isinstance(keys, list) else json.loads(keys)
        assert keys, f"{question!r} persisted an empty trace"
        for key in keys:
            assert key.get("table"), key
            assert key.get("id") or key.get("day"), f"a key must locate a row: {key}"


def test_REQ_ASK_032_the_stored_contrast_result_does_not_carry_the_question_range(ask_cur):
    """Review finding 18: the sentence was corrected and the STORED RESULT still said
    "the last 10 days".

    My test asserted only `answer_text`, so the persisted row went on claiming the very thing
    the sentence had been fixed not to say — and the trace is what an audit reads.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    stored = stored_result(cur, r)
    assert "range_label" not in stored, stored
    assert "days" not in stored, stored
    assert stored["window"] == "the scan run of 2026-09-01"
    blob = json.dumps(stored)
    assert "last 10 days" not in blob, stored

    # The requested range is still recorded — on the plan, where it belongs.
    cur.execute("SELECT plan FROM ask_core_pytest.computations WHERE question_id = %s",
                (r["question_id"],))
    plan = cur.fetchone()[0]
    plan = plan if isinstance(plan, dict) else json.loads(plan)
    assert plan["range"], plan


PROSE_FIELDS = ("rolling_28_clause", "caveat", "note", "reverse_note", "match_method", "summary")


def test_REQ_NAR_012_a_prose_result_field_cannot_certify_its_own_numerals(ask_cur):
    """Review finding 17: the verifier pooled every result value, including assembled PROSE.

    `rolling_28_clause` is stored in `res`, so the check compared the clause against itself and
    could not fail — which means the test that claimed to prove the clause introduces no
    untraced numeral was proving nothing. A prose field's numerals must trace to a SCALAR
    field, exactly like the sentence's.
    """
    import re
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(40):
        panel(cur, "hrv_sdnn_ms", AS_OF - dt.timedelta(days=39 - i), 48 + i)
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -12.50,
              "bank:x;merchant=Cafe;descriptor=CAFE BAR")

    for question in ("has my hrv changed last 40 days",
                     "how much did i spend at cafe last 10 days"):
        r = ask(cur, question)
        if r.get("refusal"):
            continue
        stored = stored_result(cur, r)
        scalar_numerals = set()
        for key, value in stored.items():
            if key in PROSE_FIELDS:
                continue
            scalar_numerals.update(re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", str(value)))
        for key in PROSE_FIELDS:
            for numeral in re.findall(r"[-+]?[0-9]+(?:\.[0-9]+)?", str(stored.get(key, ""))):
                assert numeral in scalar_numerals, (
                    f"{question!r}: {key} carries {numeral!r}, which no scalar field holds — "
                    "the clause would be certifying itself")


def test_RULE_29_the_executor_and_everything_it_calls_make_no_outbound_call(ask_cur):
    """Review finding 18: my earlier test grepped ONE file.

    `ask` calls `search_record` and `get_entity`, so a network capability in either would sit
    on the same path. The installed extension catalogue is checked too, since an http
    extension present in the database is reachable from any function.
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for migration in ("0049_ask_core.sql", "0036_search_record.sql", "0037_get_entity.sql",
                      "0040_movements_api.sql"):
        body = (root / "migrations" / migration).read_text().lower()
        for capability in ("pg_net", "dblink", "http_get", "http_post", "extensions.http",
                           "copy ", "program ", "pg_read_file", "pg_ls_dir"):
            assert capability not in body, f"{migration} references {capability!r}"

    # And nothing network-capable is installed in the database the executor runs in.
    cur = ask_cur
    cur.execute("SELECT extname FROM pg_extension ORDER BY extname")
    installed = {r[0] for r in cur.fetchall()}
    for capability in ("http", "pg_net", "dblink", "postgres_fdw", "file_fdw"):
        assert capability not in installed, f"{capability} is installed and reachable"


def test_REQ_ASK_020_the_registered_tier_ceiling_is_enforced(ask_cur):
    """Review finding 16: `tier_ceiling` was consulted only as a default.

    An `effect` answer backed by a CONFIRMED_OBSERVATIONAL resolution rendered full causal
    dose-response language — "runs X per Y, adjusted for Z" — on an operation the registry
    caps at PROMOTED. The column was a default wearing a ceiling's name (ADR-0065).

    The ceiling is the OPERATION's warrant, not the finding's: the confirmation gate earns
    CONFIRMED for the finding, and a query executor rendering that finding is not that gate.
    The finding's own tier is still disclosed, so nothing is hidden — it is simply not the
    voice the answer speaks in.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _register_finding(cur, "h:confirmed", "steps", "hrv_sdnn_ms", "CONFIRMED_OBSERVATIONAL",
                      -3.2, AS_OF - dt.timedelta(days=5))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    cur.execute("SELECT tier_ceiling FROM config_pytest.operations WHERE op = 'effect'")
    ceiling = cur.fetchone()[0]
    assert r["tier"] == ceiling, r
    assert r["tier"] != "CONFIRMED_OBSERVATIONAL"

    text = r["answer_text"].lower()
    for confirmed_only in ("adjusted for", " per ", "runs "):
        assert confirmed_only not in text, f"CONFIRMED language above the ceiling: {text}"

    # The finding's own strength is disclosed, not hidden — it just is not the answer's voice.
    stored = stored_result(cur, r)
    assert stored["tier_before_ceiling"] == "CONFIRMED_OBSERVATIONAL", stored
    assert stored["tier_ceiling"] == ceiling
    assert stored["status"] == "CONFIRMED_OBSERVATIONAL"


# ============================================================ round-three review findings

def test_REQ_ASK_027_a_negated_condition_is_refused_not_inverted(ask_cur):
    """Round-3 finding 1: "not below 5000" parsed as "below 5000" and answered its opposite.

    The comparator count added in round 2 cannot see negation — one comparator either way — so
    the clause was read as its own inverse, answered 8 where the truth was 12, and the stored
    result RELABELLED it "below 5000" so the trace confirmed the inversion. `compare` swapped
    its two groups the same way. Reading a negated comparison correctly means deciding what
    "not below" does at the boundary; refusing is honest until that is specified.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 21):
        day = AS_OF - dt.timedelta(days=20 - i)
        panel(cur, "steps", day, 500 + i * 500)
        panel(cur, "hrv_sdnn_ms", day, 70 if 500 + i * 500 >= 5000 else 40)

    for question in ("how many days my steps not below 5000 last 20 days",
                     "how many days my steps never above 5000 last 20 days",
                     "my hrv on days when my steps are not above 5000 last 20 days"):
        r = ask(cur, question)
        assert r.get("refusal") is not None, f"{question!r} answered: {r}"
        assert r.get("tier") is None, r

    # The unnegated forms still work and are not collateral damage.
    ok = ask(cur, "how many days my steps above 5000 last 20 days")
    assert ok.get("refusal") is None and ok["tier"] == "DESCRIPTIVE"


def test_RULE_12_the_like_escape_is_correct_under_standard_conforming_strings(ask_cur):
    """Round-3 finding 3: the escape function was wrong and its test passed for the wrong reason.

    With `standard_conforming_strings` on, `'\\\\'` in a SQL literal is TWO backslashes — so the
    first version never escaped a backslash and rewrote `%` as an escaped backslash followed by
    a LIVE wildcard. The over-match test passed only because the resulting pattern demanded a
    literal backslash and therefore matched nothing.
    """
    cur = ask_cur
    cur.execute("SHOW standard_conforming_strings")
    assert cur.fetchone()[0] == "on", "this test is about the on behaviour"

    # The escape must make each metacharacter match itself and nothing else.
    for raw, matches, not_matches in (
            ("coffee_shop", "COFFEE_SHOP DOWNTOWN", "COFFEEXSHOP DOWNTOWN"),
            ("50% off", "50% OFF STORE", "50 ANYTHING OFF STORE")):
        cur.execute("SELECT %s ILIKE '%%' || public_pytest._ask_like_escape(%s) || '%%'",
                    (matches, raw))
        assert cur.fetchone()[0] is True, f"{raw!r} should match {matches!r}"
        cur.execute("SELECT %s ILIKE '%%' || public_pytest._ask_like_escape(%s) || '%%'",
                    (not_matches, raw))
        assert cur.fetchone()[0] is False, f"{raw!r} must not match {not_matches!r}"

    # End to end: the underscore subject finds its charge instead of reporting it absent.
    _txn_atom(cur, AS_OF - dt.timedelta(days=1), -10.00,
              "bank:x;merchant=Coffee;descriptor=COFFEE_SHOP DOWNTOWN")
    r = ask(cur, "how much did i spend at coffee_shop last 10 days")
    assert r.get("refusal") is None, r
    assert float(stored_result(cur, r)["total_out"]) == 10.00


def test_RULE_16_the_insufficient_form_renders_with_no_empty_slot(ask_cur):
    """Round-3 finding 4: the insufficient template read {n} and {days}, which most operations
    do not carry — so it rendered a literal "{n}" to the reader, and for effect/contrast (whose
    `days` is stripped on purpose) the whole answer failed numeral verification and returned
    nothing plus a spurious render_violations row."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    cur.execute("SELECT count(*) FROM analysis_pytest.render_violations")
    violations_before = cur.fetchone()[0]

    for question in ("does my steps affect my hrv last 90 days",
                     "how is my steps last 90 days",
                     "when did i last log my steps",
                     "my hrv on days when my steps are above 5000 last 90 days",
                     "which weekday is my steps last 90 days"):
        r = ask(cur, question)
        if r.get("tier") != "INSUFFICIENT":
            continue
        text = r.get("answer_text") or ""
        assert "{" not in text and "}" not in text, f"unfilled slot in {question!r}: {text}"
        assert "did not pass numeral verification" not in text, f"{question!r}: {text}"
        assert text.strip(), f"{question!r} rendered nothing"

    cur.execute("SELECT count(*) FROM analysis_pytest.render_violations")
    assert cur.fetchone()[0] == violations_before, "a valid answer wrote a violation row"


def test_REQ_ASK_003_the_second_metric_has_the_same_similarity_floor_as_the_first(ask_cur):
    """Round-3 finding 6: "does my steps affect my toenail length" answered about WEIGHT.

    `m2` was checked only for NULL while `_ask_resolve_metric` always returns its top three,
    so an untracked outcome silently became whatever ranked first — at similarity 0.018, in
    confident exploratory language, with the plan recording metric2=weight_lb. REQ-ASK-003's
    "I do not track that" was unreachable for exactly the metric the answer is about.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)
        panel(cur, "hrv_sdnn_ms", day, 40 + i)

    for question in ("does my steps affect my toenail length last 10 days",
                     "does my steps affect my mortgage rate last 10 days"):
        r = ask(cur, question)
        assert r["refusal"] == "I do not track that.", f"{question!r}: {r}"
        assert r["reason"] == "second_metric_unresolved", r
        assert r["nearest"], "the nearest tracked metrics must be disclosed"

    # A tracked outcome still resolves.
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))
    ok = ask(cur, "does my steps affect my hrv last 10 days")
    assert ok.get("refusal") is None, ok


def test_RULE_04_spend_excludes_a_charge_recorded_after_the_as_of(ask_cur):
    """Round-4 finding 2: spend read atoms with a subject-day cutoff and no `recorded_at` one.

    An atom about an old day, recorded today, entered a replay of a question asked before it
    existed — the same total changed from 10.00 to 35.00 for an unchanged question and as_of.
    Unlike the panel case (OQ-45), `atoms.recorded_at` exists and is trigger-set; it was simply
    not used.
    """
    cur = ask_cur
    as_of = AS_OF - dt.timedelta(days=30)
    day = as_of - dt.timedelta(days=5)
    _txn_atom(cur, day, -10.00, "bank:x;merchant=Coffee;descriptor=COFFEE BAR")

    known_then = dt.datetime.combine(as_of, dt.time(23), tzinfo=dt.timezone.utc)
    before = ask(cur, "how much did i spend at coffee last 30 days",
                 as_of=as_of, known_at=known_then)
    assert float(stored_result(cur, before)["total_out"]) == 10.00

    # A charge for the SAME old day, learned today.
    _txn_atom(cur, day, -25.00, "bank:x;merchant=Coffee;descriptor=COFFEE LATE",
              recorded_at=dt.datetime.combine(AS_OF, dt.time(12), tzinfo=dt.timezone.utc))

    after = ask(cur, "how much did i spend at coffee last 30 days",
                as_of=as_of, known_at=known_then)
    assert float(stored_result(cur, after)["total_out"]) == 10.00, \
        "a charge recorded after the as_of must not enter an earlier answer"

    # And it IS visible to a question asked once it was known.
    now = ask(cur, "how much did i spend at coffee last 90 days", as_of=AS_OF)
    assert float(stored_result(cur, now)["total_out"]) == 35.00


def test_REQ_ASK_030_search_discloses_that_it_is_only_subject_day_bounded(ask_cur):
    """`search_record` reads the legacy tables, which carry no per-row `recorded_at`.

    The cutoff cannot be applied there, so the answer says so. An undisclosed replay gap reads
    as a replay guarantee.
    """
    cur = ask_cur
    for i in range(2):
        _event(cur, AS_OF - dt.timedelta(days=i), "chrome_visit",
               {"title": "postgres indexes", "domain": "example.com"})
    r = ask(cur, "postgres indexes last 10 days")
    assert stored_result(cur, r)["point_in_time"] == "subject_day_only"


def test_REQ_ASK_022_the_insufficient_answer_names_the_metric_that_is_short(ask_cur):
    """Round-4 finding 5: it named the metric at FULL coverage.

    `{display}` is always m1 — the driver — so a two-metric answer named the well-observed
    metric, left the short one unnamed, and offered the wrong metric's remedy. REQ-ASK-022 asks
    for the metric with the lowest coverage.
    """
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    for i in range(1, 11):
        day = AS_OF - dt.timedelta(days=10 - i)
        panel(cur, "steps", day, i * 1000)          # observed on all 10
        if i <= 4:
            panel(cur, "hrv_sdnn_ms", day, 40 + i)  # observed on 4 of 10
    _store_contrast(cur, "steps", "hrv_sdnn_ms", 0, delta=-7.5, run_date=dt.date(2026, 9, 1))

    r = ask(cur, "does my steps affect my hrv last 10 days")
    assert r["tier"] == "INSUFFICIENT", r
    text = r.get("answer_text") or ""
    assert "HRV" in text, f"the short metric must be named: {text}"
    assert "Steps" not in text, f"the well-observed metric must not be blamed: {text}"


def test_REQ_ASK_031_a_next_day_question_is_refused_not_answered_at_lag_zero(ask_cur):
    """Round-4 finding 4a. "tomorrow" was in none of the six range-word regexes, so it stayed
    in the metric phrase, diluted trigram similarity below the 0.35 floor, and returned
    "I do not track that" about HRV — which IS tracked. Stripping it would have been worse:
    the contrast lookup orders by abs(lag_days), so the answer would have been the lag-0
    finding rendered against a lag-1 question."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    register_metric(cur, "alcohol_units", "Alcohol", "units")
    r = ask(cur, "does my alcohol affect my hrv tomorrow")
    assert r.get("reason") == "next_day_lag", r
    assert r["refusal"] == "I cannot compute that.", r
    assert r.get("tier") is None, "a capability refusal is not an evidence tier (REQ-ASK-031)"
    assert "I do not track" not in (r.get("refusal") or ""), r
    assert r["nearest"] == ["does my alcohol affect my hrv"], r


def test_REQ_ASK_031_a_time_of_day_question_is_refused_not_answered_whole_day(ask_cur):
    """Round-4 finding 4b, the same defect in the opposite direction. "hrv in the morning"
    scored `checkin_morning_mood` at 0.364 — ABOVE the 0.35 floor — so the answer was
    confident, tiered, and about the wrong metric. The panel's grain is the subject day
    (ADR-0019); no stored row can answer a within-day slice."""
    cur = ask_cur
    register_metric(cur, "hrv_sdnn_ms", "HRV", "ms")
    register_metric(cur, "checkin_morning_mood", "Morning — mood", "1-5")
    r = ask(cur, "how is my hrv in the morning")
    assert r.get("reason") == "time_of_day", r
    assert r.get("metric") != "checkin_morning_mood", "answered about the wrong metric"
    assert r["nearest"] == ["how is my hrv"], r


def test_REQ_ASK_031_a_metric_named_after_a_grammar_verb_is_not_a_causal_question(ask_cur):
    """Round-4 finding 7. The `effect` grammar matched a bare verb anywhere in the question,
    so `checkin_morning_drive`, displayed "Morning — drive", routed to a two-metric causal
    operation. The verb now needs a right-hand side to be a verb."""
    cur = ask_cur
    register_metric(cur, "checkin_morning_drive", "Morning — drive", "1-5")
    for i in range(1, 15):
        panel(cur, "checkin_morning_drive", AS_OF - dt.timedelta(days=14 - i), (i % 5) + 1)
    r = ask(cur, "how is my morning drive")
    assert r.get("metric") == "checkin_morning_drive", r
    assert r.get("op") in (None, "describe"), f"routed to a causal operation: {r.get('op')}"
    assert r.get("reason") != "second_metric_unresolved", r


def test_REQ_ASK_031_a_tracked_metric_whose_name_contains_morning_still_answers(ask_cur):
    """The guard against 4b must not swallow a real metric. Detection is prepositional:
    "IN THE morning" asks for a slice of a day; "morning mood" is the name of a thing."""
    cur = ask_cur
    register_metric(cur, "checkin_morning_mood", "Morning — mood", "1-5")
    for i in range(1, 15):
        panel(cur, "checkin_morning_mood", AS_OF - dt.timedelta(days=14 - i), (i % 5) + 1)
    r = ask(cur, "how is my morning mood")
    assert r.get("reason") != "time_of_day", "refused a question it can answer"
    assert r.get("metric") == "checkin_morning_mood", r


def test_REQ_ASK_030_a_fresh_import_is_visible_at_the_default_as_of(ask_cur):
    """The two clocks. `as_of` defaults to YESTERDAY because today is an incomplete subject
    day, and an import is recorded TODAY. Cutting knowledge at as_of made every freshly
    imported transaction invisible to every default question — bitemporally defensible and
    practically useless. Demonstrated against 1,052 backfilled transactions before this was
    written: the same question returned INSUFFICIENT at one as_of and 1262.14 usd at another,
    purely because the cutoff moved past the moment the rows were written."""
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=3), -40.00,
              "bank:x;merchant=Hannaford;descriptor=HANNAFORD 8229",
              # AFTER the as_of boundary — an import that landed the following morning. Not
              # `now()`: Postgres now() is the TRANSACTION start, so a row written mid-test is
              # timestamped later than it and would be excluded for the wrong reason.
              recorded_at=dt.datetime.combine(AS_OF + dt.timedelta(days=1), dt.time(12),
                                              tzinfo=dt.timezone.utc))
    r = ask(cur, "how much did i spend at hannaford last 30 days")
    assert r["tier"] == "DESCRIPTIVE", r
    assert float(stored_result(cur, r)["total_out"]) == 40.00, r


def test_REQ_ASK_030_a_replay_pinned_before_the_import_does_not_see_it(ask_cur):
    """The other half: the replay clock still works, and is now the only thing that moves it."""
    cur = ask_cur
    _txn_atom(cur, AS_OF - dt.timedelta(days=3), -40.00,
              "bank:x;merchant=Hannaford;descriptor=HANNAFORD 8229",
              recorded_at=dt.datetime.combine(AS_OF + dt.timedelta(days=1), dt.time(12),
                                              tzinfo=dt.timezone.utc))
    r = ask(cur, "how much did i spend at hannaford last 30 days",
            known_at=dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc))
    assert r["tier"] == "INSUFFICIENT", r
