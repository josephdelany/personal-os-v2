"""M3 — the shared egress and neuron budget (REQ-CAP-035..042; ADR-0063).

Nothing here reaches the network. `lib.egress.call` takes an explicit `_transport` seam so the
budget, screening and logging behaviour is provable without one; the seam is a parameter
rather than a monkeypatch so what is substituted is visible in the signature.
"""
import datetime as dt
import json
import os
import uuid

import pytest

from tests._import_fixture import _statements
from tests._sql_fixture import sql_connection  # noqa: F401  (pytest fixture)
from lib import egress

pytestmark = pytest.mark.skipif(
    not os.environ.get("PERSONAL_OS_TEST_SOCKET"),
    reason="builds a spine from real migrations; disposable local server only "
           "(run via tools/test_local_sql.py)")

CORE = "core_egress_pytest"
OPS = "ops_egress_pytest"
SPINE = ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
         "0011_ops.sql", "0052_neuron_ledger.sql")
MODEL = "@cf/meta/llama-3.1-8b-instruct"


def world(cur):
    cur.execute(f"CREATE SCHEMA {CORE}")
    cur.execute(f"CREATE SCHEMA {OPS}")
    for name in SPINE:
        for stmt in _statements(name, CORE, OPS):
            cur.execute(stmt)
    return cur


def spend(cur, neurons, *, deferred=False, outcome="ok", days_ago=0):
    cur.execute(f"""insert into {CORE}.neuron_ledger
        (model_id, call_kind, estimated_neurons, is_deferred_retry, outcome, called_at)
        values (%s,'plan',%s,%s,%s, now() - (%s || ' days')::interval)""",
        (MODEL, neurons, deferred, outcome, days_ago))


def ok_transport(_model, _body):
    return json.dumps({"result": {"response": "{}"}}).encode()


def test_REQ_CAP_036_audio_cost_is_the_specified_formula():
    """The one arithmetic in the budget, executed rather than approximated."""
    assert egress.audio_neurons(60) == pytest.approx(46.63)
    assert egress.audio_neurons(30) == pytest.approx(23.315)
    assert egress.audio_neurons(0) == 0
    assert egress.audio_neurons(600) == pytest.approx(466.3)


def test_REQ_CAP_037_a_call_that_would_cross_the_soft_ceiling_is_refused(sql_connection):
    """New work stops at 9,000, not at the 10,000 hard cap.

    RULE-28 disqualifies a service that bills on overage; REQ-CAP-042 makes Workers AI's own
    hard fail the enforcement mechanism. Stopping at the soft ceiling is what keeps the system
    from ever discovering the real one.
    """
    cur = world(sql_connection.cursor())
    spend(cur, 8900)
    egress.check_budget(cur, 100, schema=CORE)          # exactly 9000 is allowed
    with pytest.raises(egress.BudgetExceeded) as e:
        egress.check_budget(cur, 101, schema=CORE)
    assert e.value.reason == "soft_ceiling_reached"
    assert e.value.spent == 8900 and e.value.ceiling == 9000
    sql_connection.rollback()


def test_REQ_CAP_039_the_reserved_margin_is_only_for_a_deferred_retry(sql_connection):
    """Without the reservation a busy day starves yesterday's backlog forever: new work always
    arrives first and always wins."""
    cur = world(sql_connection.cursor())
    spend(cur, 9500)
    with pytest.raises(egress.BudgetExceeded) as new_work:
        egress.check_budget(cur, 100, deferred_retry=False, schema=CORE)
    assert new_work.value.reason == "soft_ceiling_reached"

    # The same call, re-processing a deferred capture, may use the margin.
    spent, ceiling = egress.check_budget(cur, 100, deferred_retry=True, schema=CORE)
    assert (spent, ceiling) == (9500, 10000)

    # But not past the hard cap.
    with pytest.raises(egress.BudgetExceeded) as hard:
        egress.check_budget(cur, 600, deferred_retry=True, schema=CORE)
    assert hard.value.reason == "hard_cap_reached"
    sql_connection.rollback()


def test_REQ_CAP_037_the_budget_is_the_UTC_day_and_is_shared_across_consumers(sql_connection):
    """One ledger, one sum. Three consumers each counting their own usage against one shared
    allowance means none of them knows the real total, and the budget is enforced by whichever
    happens to run last."""
    cur = world(sql_connection.cursor())
    for kind, neurons in (("plan", 3000), ("nutrition", 3000), ("transcribe", 2000)):
        cur.execute(f"""insert into {CORE}.neuron_ledger
            (model_id, call_kind, estimated_neurons, outcome)
            values (%s,%s,%s,'ok')""", (MODEL, kind, neurons))
    with pytest.raises(egress.BudgetExceeded):
        egress.check_budget(cur, 1001, schema=CORE)      # 8000 + 1001 > 9000

    # Yesterday's spend does not count against today.
    cur.execute(f"delete from {CORE}.neuron_ledger")
    spend(cur, 8900, days_ago=1)
    spent, _ = egress.check_budget(cur, 100, schema=CORE)
    assert spent == 0, "the gate must be the CURRENT UTC day"
    sql_connection.rollback()


def test_RULE_29_a_log_row_exists_before_the_request_and_survives_a_failure(sql_connection):
    """RULE-29 requires a row for every outbound call, not every successful one.

    Logging afterwards means a call that hangs, crashes the process or errors leaves no trace
    — and those are the calls most worth having a trace of.
    """
    cur = world(sql_connection.cursor())

    def failing_transport(_model, _body):
        raise TimeoutError("upstream timed out")

    with pytest.raises(TimeoutError):
        egress.call(cur, model_id=MODEL, call_kind="plan", payload={"q": "how is my sleep"},
                    estimated_neurons=12, schema=CORE, ops=OPS, _transport=failing_transport)

    cur.execute(f"select destination, purpose, request_bytes from {OPS}.egress_log")
    rows = cur.fetchall()
    assert len(rows) == 1, "the failed call must still be logged"
    assert rows[0][0] == "api.cloudflare.com" and rows[0][1] == "plan"
    assert rows[0][2] > 0

    cur.execute(f"select outcome, estimated_neurons from {CORE}.neuron_ledger")
    outcome, neurons = cur.fetchone()
    assert outcome == "error", "an errored call still spent its neurons"
    assert float(neurons) == 12
    sql_connection.rollback()


def test_REQ_CAP_041_a_failed_call_is_not_retried(sql_connection):
    """A retry doubles the spend against a budget whose whole purpose is to make the ceiling
    reachable exactly once. REQ-CAP-043 says the capture is not lost — the caller defers it."""
    cur = world(sql_connection.cursor())
    calls = []

    def counting_transport(model, body):
        calls.append(model)
        raise ConnectionError("refused")

    with pytest.raises(ConnectionError):
        egress.call(cur, model_id=MODEL, call_kind="plan", payload={"q": "x"},
                    estimated_neurons=5, schema=CORE, ops=OPS, _transport=counting_transport)
    assert len(calls) == 1, "the client must not retry"
    cur.execute(f"select count(*) from {CORE}.neuron_ledger")
    assert cur.fetchone()[0] == 1, "a retry would have doubled the ledger too"
    sql_connection.rollback()


def test_RULE_29_a_payload_carrying_a_coordinate_is_refused_before_any_call(sql_connection):
    """Home coordinates never egress at any precision, so there is no threshold to tune —
    only a refusal. Screening happens before the budget check and before the request."""
    cur = world(sql_connection.cursor())
    calls = []

    def spy(model, body):
        calls.append(model)
        return ok_transport(model, body)

    # The fixture values are deliberately NOT coordinates. What is under test is the key
    # pattern and the pair shape, and `tools/validate_layout.py` fails the build on a
    # 4+-decimal number sharing a line with lat/lon — a lint that exists for exactly the
    # reason this screen does, and which a test fixture has no business evading.
    for payload in ({"prompt": "where was I", "lat": 1.0, "lon": 2.0},
                    {"prompt": "context: 11.11111,-22.22222"},
                    {"prompt": "summarise", "is_home": True},
                    {"nested": {"deep": {"home_lat": 1.0}}}):
        with pytest.raises(egress.PayloadRefused):
            egress.call(cur, model_id=MODEL, call_kind="plan", payload=payload,
                        estimated_neurons=5, schema=CORE, ops=OPS, _transport=spy)

    assert calls == [], "no request may be issued for a refused payload"
    cur.execute(f"select count(*) from {CORE}.neuron_ledger")
    assert cur.fetchone()[0] == 0, "a refused payload must not consume budget"
    cur.execute(f"select count(*) from {OPS}.egress_log")
    assert cur.fetchone()[0] == 0, "nothing left the system, so nothing is logged as having"

    # A payload with no coordinate goes through.
    egress.call(cur, model_id=MODEL, call_kind="plan", payload={"prompt": "how is my sleep"},
                estimated_neurons=5, schema=CORE, ops=OPS, _transport=spy)
    assert calls == [MODEL]
    sql_connection.rollback()


def test_REQ_CAP_038_over_budget_refuses_and_issues_no_request(sql_connection):
    """Over budget is a refusal, never a smaller call and never a wait."""
    cur = world(sql_connection.cursor())
    spend(cur, 9000)
    calls = []
    with pytest.raises(egress.BudgetExceeded):
        egress.call(cur, model_id=MODEL, call_kind="plan", payload={"q": "x"},
                    estimated_neurons=1, schema=CORE, ops=OPS,
                    _transport=lambda m, b: calls.append(m))
    assert calls == []
    cur.execute(f"select count(*) from {OPS}.egress_log")
    assert cur.fetchone()[0] == 0
    sql_connection.rollback()


def test_REQ_CAP_035_a_successful_call_records_its_cost_and_links_its_egress_row(sql_connection):
    cur = world(sql_connection.cursor())
    out = egress.call(cur, model_id=MODEL, call_kind="nutrition",
                      payload={"food": "big mac"}, estimated_neurons=7.5,
                      schema=CORE, ops=OPS, _transport=ok_transport)
    assert out == {"result": {"response": "{}"}}

    cur.execute(f"""select n.model_id, n.call_kind, n.estimated_neurons, n.outcome,
                           e.destination, e.response_bytes
                      from {CORE}.neuron_ledger n
                      join {OPS}.egress_log e on e.egress_id = n.egress_id""")
    model_id, kind, neurons, outcome, destination, response_bytes = cur.fetchone()
    assert (model_id, kind, outcome) == (MODEL, "nutrition", "ok")
    assert float(neurons) == 7.5
    assert destination == "api.cloudflare.com" and response_bytes > 0
    sql_connection.rollback()


def test_REQ_CAP_042_no_paid_usage_path_exists():
    """REQ-CAP-042: no payment method, no paid tier, no billable fallback.

    The enforcement mechanism for $0-recurring is the vendor's hard fail, so a code path that
    could raise the ceiling or switch provider would remove the only thing enforcing it.
    """
    from pathlib import Path
    body = Path(egress.__file__).read_text().lower()
    for forbidden in ("openai", "anthropic", "api.openai", "billing", "paid", "upgrade_plan"):
        assert forbidden not in body, f"lib/egress.py references {forbidden!r}"
    assert egress.HARD_CAP == 10000 and egress.SOFT_CEILING == 9000
    # The only destination.
    assert egress.WORKERS_AI_HOST == "api.cloudflare.com"


def test_RULE_29_every_outbound_request_in_the_repository_is_in_this_module():
    """The property this test's name claims, checked across the repository.

    An earlier version asserted `body.count("urlopen") == 1` while reading only
    `lib/egress.py` — so it proved something about one file and named something about the repo,
    and it broke the moment a second legitimate request appeared here (the source-API GET,
    which is not a model call and consumes no budget). What matters is not how many requests
    this module makes; it is that no OTHER module makes one.

    `tools/validate_layout.py` enforces the same rule on imports; this checks the call sites.
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    callers = re.compile(r"\b(urlopen|requests\.(get|post|put)|httpx\.|aiohttp|socket\.socket)\b")
    # `lib/egress.py` is where the requests belong. The other two CHECK for these names — a
    # file whose job is to detect the pattern necessarily contains it — so excluding them is
    # not a loophole; including them would make the test unable to pass while the checks exist.
    skip = {"lib/egress.py", "tests/test_egress.py", "tools/validate_layout.py"}

    offenders = []
    for path in sorted(root.rglob("*.py")):
        rel = str(path.relative_to(root))
        if rel in skip or rel.startswith((".venv", "node_modules")) or "/__pycache__/" in rel:
            continue
        if callers.search(path.read_text()):
            offenders.append(rel)
    assert offenders == [], f"outbound request outside lib/egress.py: {offenders}"

    # And within this module every request goes through the two logged entry points.
    body = (root / "lib" / "egress.py").read_text()
    # ADR-0146: model transport now refuses redirects through its own opener.
    # Preserve the two-transport inventory rather than counting only the old API.
    assert body.count("urlopen") == 1, "one source API transport"
    assert body.count("opener.open(") == 1, "one redirect-refusing model transport"
    for entry in ("def _post(", "def _get("):
        assert entry in body


def test_RULE_29_screening_catches_the_shapes_a_prompt_actually_carries():
    """The screen runs over the payload as TEXT, not field by field.

    A prompt is assembled from data by code that cannot always know what it picked up, so the
    check has to see the whole structure. The JSON quote is the detail that made an earlier
    version miss every key it existed to catch: the payload is screened as JSON, where a key
    reads `"lat": 40.7`, and a pattern expecting `lat:` matches none of them.
    """
    # Fixture values are not coordinates; the key pattern and the pair shape are what is
    # tested, and the layout lint rightly fails a 4+-decimal number beside a lat/lon word.
    refused = [
        ({"prompt": "where was I", "lat": 1.0, "lon": 2.0}, "quoted json keys"),
        ({"prompt": "context: 11.11111,-22.22222"}, "a bare pair shape in prose"),
        ({"prompt": "summarise", "is_home": True}, "the home flag"),
        ({"nested": {"deep": {"home_lat": 1.0}}}, "a nested home key"),
        ({"prompt": "latitude: 1.5"}, "prose, not a key"),
    ]
    for payload, label in refused:
        with pytest.raises(egress.PayloadRefused):
            egress.screen_payload(payload)

    allowed = [
        {"prompt": "how is my sleep"},
        {"prompt": "I ate 2 burgers, 40.5 grams protein"},   # numbers that are not coordinates
        {"metric": "steps", "value": 10432},
        {"prompt": "the last 90 days"},
    ]
    for payload in allowed:
        egress.screen_payload(payload)      # must not raise; a false refusal is also a defect


def test_RULE_29_the_documented_bypasses_are_all_refused():
    """Round-3 finding 9: six shapes an adversarial review got past the first screen.

    Each is a shape a real prompt could carry, and RULE-29 says home coordinates never egress
    AT ANY PRECISION — so a four-decimal floor was the wrong kind of test entirely. The
    normalised-decimal case is the instructive one: `json.dumps` writes -74.0060 as -74.006,
    so a precision threshold fails on the exact input it was written for.
    """
    bypasses = [
        # The values are NOT real coordinates — the shapes are what is under test, and
        # `validate_layout.py` rightly fails a real one committed to the repository. A trailing
        # zero is kept where it matters: json.dumps writes -45.6780 as -45.678, which is the
        # normalisation that defeated a four-decimal floor.
        ({"points": [[12.3450, -45.6780]]}, "nested list; json.dumps drops the trailing zero"),
        ({"x": 12.34567, "y": -45.67891}, "a pair split across sibling fields"),
        ({"place_x": 12.34567, "place_y": -45.67891}, "keys with unrelated names"),
        ({"note": "12.345,-45.678"}, "three decimals, about 110 metres"),
        ({"note": "\u0031\u0032.34567,-45.67891"}, "unicode escapes, genuinely escaped"),
        ({"note": "12.3456 N, 45.6789 W"}, "hemisphere letters"),
    ]
    for payload, label in bypasses:
        with pytest.raises(egress.PayloadRefused):
            egress.screen_payload(payload)


def test_RULE_29_screening_does_not_refuse_the_payloads_the_system_actually_sends():
    """A false refusal is also a defect: it would make the planner permanently unusable.

    These are the real shapes — an Ask result, a metric reading, a nutrition lookup, a plan.
    """
    for payload in (
            {"median": 73.5, "n": 28, "days": 40, "unit": "ms"},
            {"prompt": "how is my sleep", "metrics": {"steps": "Steps", "hrv_sdnn_ms": "HRV"}},
            {"food": "big mac", "grams": 219.0},
            {"prompt": "I ate 2 burgers, 40.5 grams protein"},
            {"op": "describe", "metric": "steps", "range_phrase": "last 30 days"},
            {"weight_lb": 176.37, "unit": "lb"},
    ):
        egress.screen_payload(payload)
