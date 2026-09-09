"""B11 Ask runtime regressions: focused prerequisites, actual SQL RPC, rollback.

Unimplemented operations/replay/language layer still need their own acceptance
tests. These tests do not claim B11 completion or full-chain compatibility.
"""
import json
import re

import pytest

from tests._ask_fixture import ask_cur
from tests._sql_fixture import sql_connection


def ask(cur, question):
    cur.execute("SELECT public_pytest.ask(%s, DATE '2026-09-08')", (question,))
    result = cur.fetchone()[0]
    return result if isinstance(result, dict) else json.loads(result)


def test_REQ_ASK_003_untracked_metric_returns_refusal_and_nearest(ask_cur):
    answer = ask(ask_cur, "what is my blood pressure")
    assert answer["refusal"] == "I do not track that."
    assert answer["nearest"]
    assert {row["metric"] for row in answer["nearest"]} == {"steps", "weight_lb"}


def test_REQ_ASK_003_panel_only_metric_is_not_treated_as_registered(ask_cur):
    ask_cur.execute("""INSERT INTO analysis_pytest.panel(day, metric, value, src, code_version)
        VALUES (DATE '2026-09-08', 'unregistered_metric', 1, 'fixture', 'test')""")
    answer = ask(ask_cur, "my unregistered metric")
    assert answer["refusal"] == "I do not track that."


def test_REQ_ASK_006_computation_row_exists_before_answer(ask_cur):
    answer = ask(ask_cur, "my steps last 10 days")
    ask_cur.execute("SELECT result, question_id FROM ask_core_pytest.computations WHERE computation_id = %s",
                    (answer["trace"]["computation_id"],))
    stored, question_id = ask_cur.fetchone()
    assert stored == answer["result"]
    assert str(question_id) == answer["question_id"]
    assert answer["result"]["median"] == 55
    assert answer["tier"] == "DESCRIPTIVE"
    assert answer["answer_text"] == (
        "Your Steps was typically 55 steps over the last 10 days "
        "(10 of 10 days with data). Your usual range was 19 to 91."
    )


def test_REQ_ASK_023_absent_metric_returns_absent_form_verbatim(ask_cur):
    answer = ask(ask_cur, "my weight")
    assert answer["refusal"] == "We do not have enough to answer this."
    assert answer["metric"] == "weight_lb"


def test_REQ_ASK_022_low_coverage_answers_at_insufficient(ask_cur):
    answer = ask(ask_cur, "my steps")
    assert answer["tier"] == "INSUFFICIENT"
    assert answer["coverage"]["steps"] < 0.60
    assert answer["would_raise_it"]


def test_REQ_ASK_022_coverage_is_not_rounded_up_across_the_gate(ask_cur):
    ask_cur.execute("""INSERT INTO analysis_pytest.panel(day, metric, value, src, code_version)
        SELECT DATE '2026-09-08' - n, 'steps', 50, 'fixture', 'test'
          FROM generate_series(10, 1198) AS n""")
    answer = ask(ask_cur, "my steps last 2000 days")
    assert answer["result"]["n"] == 1199
    assert answer["coverage"]["steps"] == 0.5995
    assert answer["tier"] == "INSUFFICIENT"


def test_REQ_ASK_002_invalid_range_returns_capability_refusal(ask_cur):
    answer = ask(ask_cur, "my steps last 0 days")
    assert answer["refusal"] == "I cannot compute that."
    assert answer.get("tier") is None


def test_REQ_ASK_028_medical_referral_is_read_from_stored_string(ask_cur):
    answer = ask(ask_cur, "diagnose my symptoms")
    ask_cur.execute("SELECT value FROM config_pytest.strings WHERE key='medical_referral'")
    assert answer["refusal"] == ask_cur.fetchone()[0]


@pytest.mark.parametrize("question,k", [
    ("how many days my steps over 50 last 10 days", 5),
    ("how many days my steps under 50 last 10 days", 4),
    ("how many days my steps above -2 last 10 days", 10),
    ("how many days my steps below 50.5 last 10 days", 5),
    ("how many days my steps over 1,000 last 10 days", 0),
])
def test_REQ_ASK_027_counts_use_condition_threshold_and_natural_frequency(ask_cur, question, k):
    answer = ask(ask_cur, question)
    assert answer["result"]["k"] == k
    assert answer["result"]["n"] == 10
    assert answer["answer_text"] == f"{k} of 10 days over the last 10 days."
    assert all(row["unit"] == "days" for row in answer["numerals"])


def test_REQ_ASK_023_absent_comparison_band_refuses_instead_of_zero_of_zero(ask_cur):
    answer = ask(ask_cur, "how many days my steps above the usual range last 10 days")
    assert answer["refusal"] == "We do not have enough to answer this."
    assert answer["insufficiency_reason"] == "low_coverage"
    assert answer["missing_input"] == "comparison_band"
    assert answer["metric"] == "steps"
    assert "comparison band" in answer["would_raise_it"]
    assert "0 of 0" not in answer.get("answer_text", "")


@pytest.mark.parametrize("direction,expected", [("above", 1), ("below", 1)])
def test_REQ_ASK_021_022_011_band_counts_use_paired_days_and_trace_both_inputs(ask_cur, direction, expected):
    ask_cur.execute("""INSERT INTO analysis_pytest.baselines(day, metric, band_lo, band_hi, code_version)
        SELECT day, metric, 70, 90, 'test' FROM analysis_pytest.panel
         WHERE day >= DATE '2026-09-04'""")
    # Only the requested side is necessary: a missing opposite side is not a
    # reason to throw away an otherwise computable comparison.
    ask_cur.execute("""UPDATE analysis_pytest.baselines SET band_lo = NULL
        WHERE day = DATE '2026-09-08'""")
    answer = ask(ask_cur, f"how many days my steps {direction} the usual range last 10 days")
    denominator = 5 if direction == "above" else 4
    assert answer["result"]["n"] == denominator
    assert answer["result"]["k"] == expected
    assert answer["coverage"]["steps"] == denominator / 10
    assert answer["tier"] == "INSUFFICIENT"
    assert "comparison bands" in answer["would_raise_it"]
    ask_cur.execute("SELECT public_pytest.get_computation(%s::uuid)",
                    (answer["trace"]["computation_id"],))
    trace = ask_cur.fetchone()[0]
    keys = trace["observation_keys"]
    assert len(keys) == denominator * 2
    assert {key["table"] for key in keys} == {"analysis_pytest.panel", "analysis_pytest.baselines"}
    for key in keys:
        assert key["metric"] == "steps"
        assert "2026-09-04" <= key["day"] <= ("2026-09-08" if direction == "above" else "2026-09-07")


@pytest.mark.parametrize("threshold", ["fifty", "50.5.7", "1,00", "NaN", "1e2"])
def test_REQ_ASK_004_unparsed_comparator_is_not_executed_as_another_condition(ask_cur, threshold):
    answer = ask(ask_cur, f"how many days my steps below {threshold} last 10 days")
    assert answer["refusal"] == "I cannot compute that."
    assert answer.get("tier") is None
    ask_cur.execute("SELECT count(*) FROM ask_core_pytest.computations")
    assert ask_cur.fetchone()[0] == 0


def test_REQ_NAR_015_registered_rounding_controls_answer(ask_cur):
    ask_cur.execute("UPDATE config_pytest.domain_metrics SET rounding = 1 WHERE metric = 'steps'")
    answer = ask(ask_cur, "my steps last 10 days")
    assert "55.0 steps" in answer["answer_text"]
    assert "19.0 to 91.0" in answer["answer_text"]


def test_REQ_ASK_009_every_rendered_numeral_resolves_to_persisted_result(ask_cur):
    answer = ask(ask_cur, "my steps last 10 days")
    values = re.findall(r"[-+]?\d+(?:\.\d+)?", answer["answer_text"])
    assert [row["value"] for row in answer["numerals"]] == values
    assert [row["unit"] for row in answer["numerals"]] == ["steps", "days", "days", "days", "steps", "steps"]
    for row in answer["numerals"]:
        assert row["computation_id"] == answer["trace"]["computation_id"]
        assert row["result_keys"]
        assert all(key in answer["result"] for key in row["result_keys"])
    ask_cur.execute("SELECT observation_keys FROM ask_core_pytest.computations WHERE computation_id = %s",
                    (answer["trace"]["computation_id"],))
    keys = ask_cur.fetchone()[0]
    assert len(keys) == 10
    assert keys[0] == {"table": "analysis_pytest.panel", "day": "2026-08-30", "metric": "steps"}
    assert keys[-1]["day"] == "2026-09-08"


def test_REQ_ASK_010_corrupt_template_numeral_is_refused_and_logged(ask_cur):
    ask_cur.execute("""UPDATE config_pytest.ask_templates SET template = template || ' Also 999999.'
        WHERE op = 'describe' AND tier = 'DESCRIPTIVE'""")
    answer = ask(ask_cur, "my steps last 10 days")
    assert "999999" not in answer["answer_text"]
    assert answer["numerals"] == []
    ask_cur.execute("SELECT detail->>'reason' FROM analysis_pytest.render_violations WHERE question_id = %s",
                    (answer["question_id"],))
    assert ask_cur.fetchone()[0] == "untraceable_numeral"


def test_REQ_ASK_011_computation_click_through_returns_plan_result_and_keys(ask_cur):
    answer = ask(ask_cur, "my steps last 10 days")
    ask_cur.execute("SELECT public_pytest.get_computation(%s::uuid)",
                    (answer["trace"]["computation_id"],))
    trace = ask_cur.fetchone()[0]
    assert trace["result"] == answer["result"]
    assert trace["plan"]["metric"] == "steps"
    assert len(trace["observation_keys"]) == 10
    assert trace["code_version"]
    ask_cur.execute("SELECT set_config('request.jwt.claims', '{}', true)")
    with pytest.raises(Exception, match="owner only"):
        ask_cur.execute("SELECT public_pytest.get_computation(%s::uuid)",
                        (answer["trace"]["computation_id"],))


def test_REQ_ASK_025_trend_compares_requested_calendar_halves(ask_cur):
    answer = ask(ask_cur, "has my steps changed last 10 days")
    assert answer["op"] == "trend"
    assert answer["result"]["first"] == 30
    assert answer["result"]["second"] == 80
    assert answer["tier"] == "DESCRIPTIVE"
    # B11's registered `trend` contract is the two halves AND the 28-day rolling median at
    # range end. The fixture holds ten days, so the rolling window is too thin and the
    # sentence says so rather than leaving an empty slot that reads as a missing value.
    assert answer["answer_text"] == (
        "Your Steps ran 80 steps in the second half of the last 10 days "
        "against 30 steps in the first (10 of 10 days with data). "
        "The most recent 28 days hold only 10 days with data, too few for a 28-day median."
    )
    # The envelope is jsonb_strip_nulls'd, so an absent median is an ABSENT key rather than
    # a null — which is the honest encoding: there is no 28-day median here, and a null would
    # invite a reader to treat it as a value that happens to be empty.
    assert "rolling_28" not in answer["result"]
    assert answer["result"]["rolling_28_n"] == 10
    assert answer["result"]["rolling_28_min_days"] == 14


def test_REQ_ASK_023_trend_refuses_if_one_half_has_no_observations(ask_cur):
    answer = ask(ask_cur, "has my steps changed last 30 days")
    assert answer["refusal"] == "We do not have enough to answer this."
    assert answer["insufficiency_reason"] == "low_coverage"
    assert answer["missing_input"] == "comparison_half"


def test_REQ_ASK_025_rhythm_uses_weekday_medians(ask_cur):
    answer = ask(ask_cur, "which weekday my steps last 10 days")
    assert answer["op"] == "rhythm"
    assert answer["result"]["hi_day"] == "Saturday"
    assert answer["result"]["hi"] == 70
    assert answer["result"]["lo_day"] == "Wednesday"
    assert answer["result"]["lo"] == 40


def test_REQ_ASK_011_last_value_and_trace_respect_explicit_date_range(ask_cur):
    answer = ask(ask_cur, "when did i last log steps last month")
    assert answer["op"] == "last"
    assert answer["result"]["day"] == "2026-08-31"
    assert answer["result"]["value"] == 20
    ask_cur.execute("SELECT public_pytest.get_computation(%s::uuid)",
                    (answer["trace"]["computation_id"],))
    keys = ask_cur.fetchone()[0]["observation_keys"]
    assert keys == [{"table": "analysis_pytest.panel", "day": "2026-08-31", "metric": "steps"}]


def test_ADR_0036_ask_refuses_without_owner_jwt(ask_cur):
    ask_cur.execute("SELECT set_config('request.jwt.claims', '{}', true)")
    with pytest.raises(Exception, match="owner only"):
        ask(ask_cur, "my steps")
