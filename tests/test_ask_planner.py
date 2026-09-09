"""B11.2 — the language planner (REQ-ASK-004/007/008/012/031; ADR-0064).

No call reaches the network: `plan_question` takes an explicit `transport` seam. What is under
test is the boundary the model sits behind — that it can only choose among registered options,
cannot supply a window the question did not state, contributes no numeral, and that a refusal
is bounded and disclosed rather than a best guess.
"""
import datetime as dt
import json
import os

import pytest

from tests._import_fixture import _statements
from tests._ask_fixture import ask_cur          # noqa: F401  (pytest fixture)
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from tools.engines import ask_planner as planner

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from real migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_plan_pytest"
OPS = "ops_plan_pytest"
CONFIG = "config_plan_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
         "0011_ops.sql", "0052_neuron_ledger.sql")


def world(cur):
    cur.execute(f"CREATE SCHEMA {CORE}")
    cur.execute(f"CREATE SCHEMA {OPS}")
    cur.execute(f"CREATE SCHEMA {CONFIG}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    cur.execute(f"""CREATE TABLE {CONFIG}.operations (
        op TEXT PRIMARY KEY, arity TEXT NOT NULL, description TEXT NOT NULL,
        tier_ceiling TEXT NOT NULL)""")
    cur.execute(f"""INSERT INTO {CONFIG}.operations VALUES
        ('describe','metric','d','DESCRIPTIVE'), ('trend','metric','d','DESCRIPTIVE'),
        ('rhythm','metric','d','DESCRIPTIVE'), ('last','metric','d','DESCRIPTIVE'),
        ('count_days','metric,condition','d','DESCRIPTIVE'),
        ('compare','metric,condition','d','DESCRIPTIVE'),
        ('contrast','metric,metric','d','EXPLORATORY'),
        ('effect','metric,metric','d','PROMOTED'), ('spend','entity','d','DESCRIPTIVE')""")
    for key, display in (("steps", "Steps"), ("hrv_sdnn_ms", "HRV"), ("weight_lb", "Weight")):
        cur.execute(f"""INSERT INTO {CORE}.metric_registry
            (metric_key, display_name, family, unit, state_class)
            VALUES (%s,%s,'test','u','measurement') ON CONFLICT DO NOTHING""", (key, display))
    return cur


def responder(*plans):
    """A transport returning each plan in turn, in the Workers AI envelope shape."""
    queue = list(plans)

    def transport(_model, _body):
        payload = queue.pop(0) if queue else queue
        return json.dumps({"result": {"response": json.dumps(payload)}}).encode()
    return transport


def opts(cur):
    return planner.registry_options(cur, CORE, CONFIG)


# ------------------------------------------------------------------ the registry is the limit

def test_REQ_ASK_004_an_operation_outside_the_registry_is_refused_with_the_nearest(sql_connection):
    """The model cannot invent an operation, and the refusal discloses what exists.

    REQ-ASK-031 wants the nearest registered options, not a bare refusal: a question
    unanswerable as posed still gets the partial disclosure RULE-18 requires.
    """
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    with pytest.raises(planner.PlanRefused) as e:
        planner.validate({"op": "forecast", "metric": "steps"},
                         "what will my steps be", operations, metrics)
    assert e.value.reason == "operation_not_registered"
    assert e.value.nearest, "the nearest registered operations must be disclosed"
    assert set(e.value.nearest) <= set(operations)
    sql_connection.rollback()


def test_REQ_ASK_003_a_metric_outside_the_registry_is_refused_with_the_nearest(sql_connection):
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    with pytest.raises(planner.PlanRefused) as e:
        planner.validate({"op": "describe", "metric": "blood_pressure"},
                         "how is my blood pressure", operations, metrics)
    assert e.value.reason == "metric_not_registered"
    assert set(e.value.nearest) <= set(metrics)
    sql_connection.rollback()


def test_REQ_ASK_012_a_field_the_model_invented_is_refused_not_dropped(sql_connection):
    """An invented field means the model answered a different question.

    Silently dropping unknown keys would let a plan carrying `"multiply_by": 2` execute as
    though it had not — the arithmetic would simply be absent from the record of what was asked.
    """
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    with pytest.raises(planner.PlanRefused) as e:
        planner.validate({"op": "describe", "metric": "steps", "multiply_by": 2},
                         "how is my steps", operations, metrics)
    assert "plan_has_unknown_fields" in e.value.reason
    assert "multiply_by" in e.value.reason
    sql_connection.rollback()


# ------------------------------------------------------------------ RULE-13: windows are not the model's

def test_RULE_13_the_model_cannot_supply_a_window_the_question_did_not_state(sql_connection):
    """Extraction is reading; selection is choosing a window definition.

    RULE-13 makes window definitions fixed data, never model output at query time. HEARTS
    (ICML 2026) found code execution fixes arithmetic but NOT temporal reasoning, with models
    falling back on heuristics as temporal complexity rises — so a model asked "how is my
    sleep recently" will happily choose 90 days, and that choice would be invisible in the
    answer.
    """
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    with pytest.raises(planner.PlanRefused) as e:
        planner.validate({"op": "describe", "metric": "steps", "range_phrase": "last 90 days"},
                         "how is my steps recently", operations, metrics)
    assert e.value.reason == "range_not_stated_in_question"

    # A range the question DID state is extraction, and is kept.
    clean = planner.validate({"op": "describe", "metric": "steps", "range_phrase": "last 30 days"},
                             "how is my steps last 30 days", operations, metrics)
    assert clean["range_phrase"] == "last 30 days"

    # A question with no range gets no range from the plan; the executor's default applies.
    clean2 = planner.validate({"op": "describe", "metric": "steps"},
                              "how is my steps", operations, metrics)
    assert "range_phrase" not in clean2
    sql_connection.rollback()


def test_RULE_13_a_stated_range_is_recovered_even_if_the_model_omits_it(sql_connection):
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    clean = planner.validate({"op": "describe", "metric": "steps"},
                             "how is my steps last 14 days", operations, metrics)
    assert clean["range_phrase"] == "last 14 days"
    sql_connection.rollback()


def test_RULE_11_the_plan_carries_no_numeral_of_the_models_own(sql_connection):
    """REQ-ASK-012: the language layer performs no arithmetic and contributes no numeral.

    The plan is rendered back into a question the deterministic executor already parses, so
    the only numbers reaching an answer are ones the executor computed and stored.
    """
    import re
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    clean = planner.validate({"op": "describe", "metric": "steps", "range_phrase": "last 30 days"},
                             "how is my steps last 30 days", operations, metrics)
    question = planner.to_question(clean, metrics)
    for numeral in re.findall(r"\d+", question):
        assert numeral in "how is my steps last 30 days", \
            f"the planner introduced the numeral {numeral!r}"
    sql_connection.rollback()


# ------------------------------------------------------------------ iteration cap and budget

def test_REQ_ASK_008_the_iteration_cap_is_five_and_the_limit_is_a_refusal(sql_connection):
    """A bounded loop that ends in a refusal, not a best guess.

    The cap of 5 is REQ-ASK-008's and the spec notes it is not sourced from research — so it
    is a stated choice, and what matters is that reaching it refuses rather than executing
    whatever the last attempt produced.
    """
    cur = world(sql_connection.cursor())
    bad = {"op": "forecast", "metric": "steps"}
    transport = responder(*[bad] * 10)
    with pytest.raises(planner.PlanRefused) as e:
        planner.plan_question(cur, "what will my steps be", schema=CORE, ops=OPS,
                              config=CONFIG, transport=transport)
    assert e.value.reason.startswith("iteration_cap_reached")
    assert "operation_not_registered" in e.value.reason
    cur.execute(f"select count(*) from {CORE}.neuron_ledger where call_kind = 'plan'")
    assert cur.fetchone()[0] == planner.MAX_ITERATIONS, "every attempt must be on the ledger"
    sql_connection.rollback()


def test_REQ_ASK_008_a_later_attempt_can_succeed_within_the_cap(sql_connection):
    cur = world(sql_connection.cursor())
    transport = responder({"op": "nonsense"},
                          {"op": "describe", "metric": "not_a_metric"},
                          {"op": "describe", "metric": "hrv_sdnn_ms"})
    plan, question, attempts = planner.plan_question(
        cur, "how is my hrv", schema=CORE, ops=OPS, config=CONFIG, transport=transport)
    assert attempts == 3
    assert plan == {"op": "describe", "metric": "hrv_sdnn_ms"}
    assert question == "how is my HRV"
    cur.execute(f"select count(*) from {CORE}.neuron_ledger")
    assert cur.fetchone()[0] == 3, "each attempt is a call and each call is on the ledger"
    sql_connection.rollback()


def test_RULE_15_an_exhausted_budget_propagates_so_the_caller_degrades(sql_connection):
    """Nothing may require the model to be available.

    The planner does not swallow a budget refusal and does not substitute its own answer; it
    lets the refusal reach the caller, whose deterministic path always works.
    """
    from lib import egress
    cur = world(sql_connection.cursor())
    cur.execute(f"""insert into {CORE}.neuron_ledger (model_id, call_kind, estimated_neurons, outcome)
                    values ('m','plan',9000,'ok')""")
    with pytest.raises(egress.BudgetExceeded):
        planner.plan_question(cur, "how is my hrv", schema=CORE, ops=OPS, config=CONFIG,
                              transport=responder({"op": "describe", "metric": "hrv_sdnn_ms"}))
    cur.execute(f"select count(*) from {OPS}.egress_log")
    assert cur.fetchone()[0] == 0, "no request may be issued over budget"
    sql_connection.rollback()


def test_RULE_29_the_prompt_carries_only_the_question_and_the_registry(sql_connection):
    """No coordinate, no mood value, no other lens's data — the restriction REQ-FIN-092 places
    on the categorizer's prompt, for the same reason."""
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    prompt = planner.build_prompt("how is my hrv last 7 days", operations, metrics)
    body = json.dumps(prompt)
    assert "how is my hrv last 7 days" in body
    assert "hrv_sdnn_ms" in body and "describe" in body
    # Nothing else about Joe.
    for leaked in ("lat", "home", "mood", "occurred_at", "value_point", "evidence_span"):
        assert leaked not in body.lower(), f"the prompt carries {leaked!r}"


def test_REQ_ASK_004_every_rendered_plan_is_a_question_the_executor_already_parses(sql_connection):
    """The plan selects among questions the deterministic path can answer.

    That is what keeps RULE-11 true by construction: the model's whole influence is WHICH
    registered question gets asked, never how it is computed.
    """
    cur = world(sql_connection.cursor())
    operations, metrics = opts(cur)
    for op, extra in (("describe", {}), ("trend", {}), ("rhythm", {}), ("last", {}),
                      ("count_days", {"condition": "above 5000"}),
                      ("compare", {"condition_metric": "hrv_sdnn_ms"}),
                      ("effect", {"condition_metric": "hrv_sdnn_ms"}),
                      ("spend", {"entity": "coffee"})):
        plan = {"op": op, "metric": "steps", **extra}
        clean = planner.validate(plan, "how is my steps last 10 days", operations, metrics)
        question = planner.to_question(clean, metrics)
        assert question and question.strip(), op
        assert "None" not in question, f"{op} rendered a null slot: {question!r}"
    sql_connection.rollback()


# ------------------------------------------------------------------ the client's fallback order

# The Ask fixture's own schema names, so the client is exercised against the real executor.
ASK_SCHEMAS = dict(api="public_pytest", schema="ask_core_pytest",
                   ops="ops_pytest", config="config_pytest")


def _client_world(cur):
    """The Ask executor plus the neuron ledger, in the Ask fixture's disposable schemas."""
    from tests._ask_fixture import rebind
    from tools.run_migration import split_statements
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    cur.execute("CREATE SCHEMA IF NOT EXISTS ops_pytest")
    # 0011 carries ops.egress_log, which 0052's ledger references. The Ask fixture does not
    # install it (Ask itself never egresses), so the client's world adds it here rather than
    # widening a fixture other tests depend on.
    for name in ("0011_ops.sql", "0052_neuron_ledger.sql"):
        for stmt in split_statements((root / "migrations" / name).read_text()):
            cur.execute(rebind(stmt))
    return cur


def test_RULE_15_the_deterministic_path_answers_first_and_no_model_is_called(ask_cur):
    """Most questions never reach a model. The planner is an improvement, not a dependency.

    A question the grammar already parses must not spend a neuron, and the envelope must say
    which path produced it — a reader who cannot tell whether a model was involved cannot
    judge the answer.
    """
    from tools import ask as ask_client
    cur = _client_world(ask_cur)
    calls = []

    envelope, provenance = ask_client.answer(
        cur, "how is my steps last 10 days", dt.date(2026, 9, 8),
        transport=lambda m, b: calls.append(m), **ASK_SCHEMAS)
    assert provenance == "deterministic"
    assert envelope.get("answer_text")
    assert calls == [], "a question the grammar parses must not call the model"
    cur.execute("select count(*) from ask_core_pytest.neuron_ledger")
    assert cur.fetchone()[0] == 0


def test_RULE_15_a_planner_failure_leaves_the_deterministic_refusal_intact(ask_cur):
    """The planner path must never be worse than not having a planner.

    An unreachable model, an exhausted budget or no registered plan within the cap all leave
    the original deterministic refusal standing, annotated with why the planner did not help.
    """
    from tools import ask as ask_client
    cur = _client_world(ask_cur)

    def unreachable(_model, _body):
        raise ConnectionError("no route to host")

    envelope, provenance = ask_client.answer(
        cur, "zzz unmappable gibberish", dt.date(2026, 9, 8), transport=unreachable,
        **ASK_SCHEMAS)
    assert provenance == "deterministic_after_planner_refused"
    assert envelope.get("refusal"), "the deterministic refusal must survive"
    assert envelope["planner"]["used"] is False
    assert envelope["planner"]["reason"] == "ConnectionError"


def test_REQ_ASK_003_the_planner_is_not_asked_to_rephrase_a_true_refusal(ask_cur):
    """"I do not track that" is a true answer about the record.

    Asking a model to rephrase it would turn an honest refusal into a different question that
    happens to have data — which is the most useful-looking way to be wrong.
    """
    from tools import ask as ask_client
    cur = _client_world(ask_cur)
    calls = []

    envelope, provenance = ask_client.answer(
        cur, "what is my blood pressure", dt.date(2026, 9, 8),
        transport=lambda m, b: calls.append(m), **ASK_SCHEMAS)
    assert envelope["refusal"] == "I do not track that."
    assert provenance == "deterministic"
    assert calls == [], "an untracked metric must not be handed to the planner"


def test_RULE_15_a_thin_coverage_refusal_is_not_handed_to_the_planner(ask_cur):
    """A question the grammar understood and the record cannot answer is already answered.

    Rephrasing it would change the question rather than the answer — and would produce a
    confident-looking result for a question Joe did not ask.
    """
    from tools import ask as ask_client
    cur = _client_world(ask_cur)
    calls = []
    # "last 300 days" is understood; the fixture holds ten days, so coverage refuses.
    envelope, provenance = ask_client.answer(
        cur, "has my steps changed last 300 days", dt.date(2026, 9, 8),
        transport=lambda m, b: calls.append(m), **ASK_SCHEMAS)
    assert envelope.get("refusal"), envelope
    assert provenance == "deterministic"
    assert calls == [], "an understood question must not be handed to the planner"


def test_REQ_ASK_007_a_planned_answer_records_that_it_was_planned(ask_cur):
    """Provenance is a fact about the answer, not a footnote.

    A reader who cannot tell whether a model was involved cannot judge the answer. The
    envelope carries the plan, the question actually executed, and the attempt count.
    """
    from tools import ask as ask_client
    cur = _client_world(ask_cur)
    # A phrasing no grammar pattern claims — it carries none of the trigger words, so the
    # executor falls through to search, matches nothing, and the planner maps it to `describe`.
    question = "walking totals please"
    transport = responder({"op": "describe", "metric": "steps"})
    envelope, provenance = ask_client.answer(
        cur, question, dt.date(2026, 9, 8), transport=transport, **ASK_SCHEMAS)

    assert provenance == "planned", envelope
    assert envelope["planner"]["used"] is True
    assert envelope["planner"]["plan"] == {"op": "describe", "metric": "steps"}
    assert envelope["planner"]["asked_as"] == "how is my Steps"
    assert envelope["planner"]["original_question"] == question
    assert envelope.get("answer_text"), "the planned question must actually be answered"

    # REQ-ASK-012: the numbers came from the executor, not the model. The plan carries none.
    import re
    assert not re.search(r"\d", json.dumps(envelope["planner"]["plan"]))
