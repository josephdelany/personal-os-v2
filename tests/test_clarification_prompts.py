"""REQ-REC-015's second half: the clarification prompt, subject to cadence and dismissal.

REQ-REC-015 ends "...with any user prompt subject to existing cadence and dismissal rules".
The first half — return the evidence that would distinguish the alternatives, or say none was
identified — was built in migration 0069. This file tests the connection from that to
`core.prompt_dispatch` (migration 0009), which had no writer of any kind and whose own comment
said "wired when prompts exist".

The decision logic is pure and is tested without a database: whether Joe gets asked must be
answerable without one, because every rule in it is about restraint and restraint is what gets
quietly dropped when a rule is hard to test. The SQL half then proves the queries that feed it.
"""
import datetime as dt
import os
import re

import pytest

from tests._sql_fixture import ROOT, sql_connection  # noqa: F401  (pytest fixture)
from tools.run_migration import split_statements
from ops import clarification_prompts as cp

CORE = "clarify_core_pytest"
CONFIG = "config_clarify_pytest"
OPS = "ops_clarify_pytest"
TODAY = dt.date(2026, 9, 11)


# --------------------------------------------------------------------------- pure decisions

def question(family="meal", day=TODAY, evidence=("a card charge at the same hour",),
             alternatives=2, event_id="e1"):
    return {"event_id": event_id, "event_family": family, "subject_day": day,
            "discriminating_evidence": list(evidence), "alternatives": alternatives,
            "knowledge_time": None}


def test_REQ_REC_015_a_question_with_discriminating_evidence_is_asked():
    planned, suppressed = cp.decide([question()], {}, TODAY)
    assert len(planned) == 1 and not suppressed
    assert planned[0]["subject"] == "clarify:meal:2026-09-11"


def test_RULE_27_a_dismissed_prompt_is_never_repeated():
    """Never. Not after a cooldown and not in a different wording.

    RULE-27 says never repeat a dismissed prompt, and a cooldown is a repeat with a delay. The
    dismissal is read from EVERY row for the subject rather than the latest, so a later row in
    any other state cannot bury it.
    """
    q = question()
    history = {cp.subject_for(q): {"states": {"seen_declined", "expired"},
                                   "last_state": "expired", "last_scheduled_day": None}}
    planned, suppressed = cp.decide([q], history, TODAY)
    assert planned == []
    assert suppressed[0]["reason"] == "dismissed"


def test_RULE_27_one_prompt_per_subject_per_day():
    q = question()
    history = {cp.subject_for(q): {"states": {"expired"}, "last_state": "expired",
                                   "last_scheduled_day": TODAY}}
    planned, suppressed = cp.decide([q], history, TODAY)
    assert planned == []
    assert suppressed[0]["reason"] == "already_today"


def test_RULE_27_an_expired_prompt_may_be_asked_again_on_a_later_day():
    """`expired` is neither dismissal nor an answer: it was asked, went unseen, and the
    question is still open. The per-day rule is what stops it becoming a nag."""
    q = question()
    history = {cp.subject_for(q): {"states": {"expired"}, "last_state": "expired",
                                   "last_scheduled_day": TODAY - dt.timedelta(days=3)}}
    planned, suppressed = cp.decide([q], history, TODAY)
    assert len(planned) == 1 and not suppressed


def test_REQ_REC_015_an_unanswered_prompt_is_not_duplicated():
    """Asking twice about one unanswered question is the likelier of the two duplications."""
    q = question()
    for state in ("pending", "delivered_unseen", "partial"):
        history = {cp.subject_for(q): {"states": {state}, "last_state": state,
                                       "last_scheduled_day": TODAY - dt.timedelta(days=2)}}
        planned, suppressed = cp.decide([q], history, TODAY)
        assert planned == [], f"{state} was re-asked"
        assert suppressed[0]["reason"] == "already_open"


def test_REQ_REC_015_an_answered_question_is_not_asked_again():
    q = question()
    history = {cp.subject_for(q): {"states": {"answered"}, "last_state": "answered",
                                   "last_scheduled_day": TODAY - dt.timedelta(days=5)}}
    planned, suppressed = cp.decide([q], history, TODAY)
    assert planned == [] and suppressed[0]["reason"] == "answered"


def test_RULE_27_two_reconstructions_of_the_same_question_produce_one_prompt():
    """The subject key is the QUESTION, not the row.

    REQ-REC-011 makes revision append-only, so a better reconstruction of Tuesday's meal is a
    NEW event_id for the same open question. Keying the prompt on the event_id would ask Joe
    about Tuesday again every time the engine changed its mind — the nag RULE-27 forbids,
    arriving through a technicality.
    """
    a = question(event_id="older")
    b = question(event_id="newer")
    planned, suppressed = cp.decide([a, b], {}, TODAY)
    assert len(planned) == 1
    assert [s["reason"] for s in suppressed] == ["already_today"]


def test_RULE_27_the_daily_budget_is_shared_and_not_a_second_number():
    """Three, from `vision_and_prompts.MAX_SCHEDULED_PROMPTS_PER_DAY`.

    There is one prompt budget, not one per feature: B16's meal prompts and these draw on the
    same attention, and a per-feature ceiling is how a system arrives at nine prompts a day
    while every component believes it is under its limit.
    """
    from tools.engines import vision_and_prompts
    assert cp.MAX_SCHEDULED_PROMPTS_PER_DAY is vision_and_prompts.MAX_SCHEDULED_PROMPTS_PER_DAY
    days = [TODAY - dt.timedelta(days=n) for n in range(5)]
    qs = [question(day=d, event_id=f"e{n}") for n, d in enumerate(days)]
    planned, suppressed = cp.decide(qs, {}, TODAY)
    assert len(planned) == cp.MAX_SCHEDULED_PROMPTS_PER_DAY
    assert [s["reason"] for s in suppressed] == ["daily_budget", "daily_budget"]


def test_RULE_27_prompts_already_scheduled_today_consume_the_same_budget():
    qs = [question(day=TODAY - dt.timedelta(days=n), event_id=f"e{n}") for n in range(3)]
    planned, suppressed = cp.decide(qs, {}, TODAY, issued_today=2)
    assert len(planned) == 1
    assert [s["reason"] for s in suppressed] == ["daily_budget", "daily_budget"]
    planned, suppressed = cp.decide(qs, {}, TODAY, issued_today=99)
    assert planned == []


def test_REQ_REC_015_the_oldest_question_is_asked_first():
    """Oldest subject day first, because Joe's memory is the perishable evidence here.

    A question asked six weeks late is a question asked of a person who no longer knows.
    Ranking by the engine's own score instead would put its confidence ahead of the only input
    that expires.
    """
    qs = [question(day=TODAY, event_id="new"),
          question(day=TODAY - dt.timedelta(days=30), event_id="old"),
          question(day=TODAY - dt.timedelta(days=10), event_id="mid")]
    planned, _ = cp.decide(qs, {}, TODAY)
    assert [p["event_id"] for p in planned] == ["old", "mid", "new"]


# --------------------------------------------------------------------------- the SQL half

def rebind(sql):
    return re.sub(r"\bconfig\.", f"{CONFIG}.",
                  sql.replace("__CORE__", CORE).replace("__OPS__", OPS))


@pytest.fixture
def world(sql_connection):
    if not os.environ.get("PERSONAL_OS_TEST_SOCKET"):
        pytest.skip("builds schemas from migration DDL; disposable local server only "
                    "(run via tools/test_local_sql.py)")
    cur = sql_connection.cursor()
    for schema in (CORE, CONFIG, OPS):
        cur.execute(f"CREATE SCHEMA {schema}")
    for role in ("anon", "authenticated", "service_role"):
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        if cur.fetchone() is None:
            cur.execute(f"CREATE ROLE {role} NOLOGIN")
    for filename in ("0002_metric_registry.sql", "0004_raw_captures.sql", "0005_atoms.sql",
                     "0009_prompt_dispatch.sql", "0011_ops.sql", "0051_file_import.sql",
                     "0054_inferred_events.sql"):
        for statement in split_statements((ROOT / "migrations" / filename).read_text()):
            cur.execute(rebind(statement))
    # 0069's two columns and their constraint, which is what makes a question a question.
    for statement in split_statements(
            (ROOT / "migrations" / "0069_discriminating_evidence.sql").read_text()):
        if "inferred_events" in statement and "FUNCTION" not in statement.upper():
            cur.execute(rebind(statement))
    cur.execute(f"""INSERT INTO {CONFIG}.reconstruction_methods
        (method_key, method_version, event_family, required_evidence, permissible_outputs,
         temporal_specification, note)
        VALUES ('meal_from_charge', 1, 'meal', ARRAY['transaction'], ARRAY['occurred'],
                'interval', 'a card charge at a food merchant')""")
    return cur


def event(cur, **kw):
    base = dict(event_family="meal", method_key="meal_from_charge", method_version=1,
                event_time_from="2026-09-01T18:00:00Z", event_time_to="2026-09-01T19:00:00Z",
                subject_day="2026-09-01", tier="EXPLORATORY", presence="occurred",
                author="engine")
    base.update(kw)
    cols = ", ".join(base)
    cur.execute(f"INSERT INTO {CORE}.inferred_events ({cols}) "
                f"VALUES ({', '.join(['%s'] * len(base))}) RETURNING event_id",
                tuple(base.values()))
    return cur.fetchone()[0]


ALTS = '[{"label": "a takeaway"}, {"label": "a sit-down meal"}]'


def test_REQ_REC_015_only_open_questions_with_something_that_would_settle_them(world):
    """Four rows that must NOT produce a prompt, and one that must."""
    cur = world
    asked = event(cur, alternatives=ALTS,
                  discriminating_evidence=["a photograph at 18:30"],
                  subject_day="2026-09-02")
    # No alternatives at all: nothing is in doubt.
    event(cur, no_alternative_generator=True, subject_day="2026-09-03")
    # Alternatives, but the engine has already concluded nothing would settle them. Asking
    # would be asking Joe to do the engine's work (0069 makes that an answer, not a blank).
    event(cur, alternatives=ALTS, no_discriminating_evidence=True, subject_day="2026-09-04")
    # Concluded not to have happened.
    event(cur, alternatives=ALTS, discriminating_evidence=["x"], presence="did_not_occur",
          subject_day="2026-09-05")
    # Superseded: not the current interpretation.
    superseded = event(cur, alternatives=ALTS, discriminating_evidence=["y"],
                       subject_day="2026-09-06")
    event(cur, alternatives=ALTS, discriminating_evidence=["y"], subject_day="2026-09-06",
          supersedes=superseded)

    rows = cp.open_questions(cur, CORE)
    families = {(r["event_family"], r["subject_day"].isoformat()) for r in rows}
    assert ("meal", "2026-09-02") in families
    assert ("meal", "2026-09-03") not in families
    assert ("meal", "2026-09-04") not in families
    assert ("meal", "2026-09-05") not in families
    # The superseding row IS current and does appear; the superseded one must not.
    assert len([r for r in rows if r["subject_day"].isoformat() == "2026-09-06"]) == 1
    assert str(asked) in {r["event_id"] for r in rows}


def test_REQ_REC_015_a_scheduled_prompt_is_not_a_delivered_one(world):
    """`delivered_at` stays NULL. A row means the question is DUE, never that Joe was asked.

    There is no delivery channel: REQ-CAP-092 names Web Push and Web Push is not built. The
    table has two columns precisely so these two facts cannot be merged, and merging them is
    how a system comes to believe it asked a question it never asked.
    """
    cur = world
    event(cur, alternatives=ALTS, discriminating_evidence=["a photograph at 18:30"])
    questions = cp.open_questions(cur, CORE)
    planned, _ = cp.decide(questions, {}, dt.date(2026, 9, 11))
    at = cp.next_occurrence(cur, "09:00")
    ids = cp.schedule_prompts(cur, planned, at, CORE)

    assert len(ids) == 1
    cur.execute(f"select subject, response_state, delivered_at, responded_at, scheduled_for "
                f"from {CORE}.prompt_dispatch")
    subject, state, delivered, responded, scheduled = cur.fetchone()
    assert subject == "clarify:meal:2026-09-01"
    assert state == "pending"
    assert delivered is None and responded is None
    cur.execute("select now()")
    assert scheduled > cur.fetchone()[0], "a prompt was scheduled in the past"


def test_RULE_27_a_second_run_on_the_same_day_schedules_nothing(world):
    """The end-to-end restraint: read, decide, write, then do it all again."""
    cur = world
    event(cur, alternatives=ALTS, discriminating_evidence=["a photograph at 18:30"])
    cur.execute("select (now() at time zone 'America/New_York')::date")
    today = cur.fetchone()[0]

    questions = cp.open_questions(cur, CORE)
    history = cp.dispatch_history(cur, CORE, [cp.subject_for(q) for q in questions])
    planned, _ = cp.decide(questions, history, today, cp.issued_on(cur, today, CORE))
    cp.schedule_prompts(cur, planned, cp.next_occurrence(cur, "09:00"), CORE)
    assert len(planned) == 1

    history = cp.dispatch_history(cur, CORE, [cp.subject_for(q) for q in questions])
    again, suppressed = cp.decide(questions, history, today, cp.issued_on(cur, today, CORE))
    assert again == []
    assert suppressed[0]["reason"] in ("already_open", "already_today")
    cur.execute(f"select count(*) from {CORE}.prompt_dispatch")
    assert cur.fetchone()[0] == 1


def test_RULE_27_a_dismissal_recorded_in_the_table_stops_the_next_run(world):
    cur = world
    event(cur, alternatives=ALTS, discriminating_evidence=["a photograph at 18:30"])
    cur.execute("select (now() at time zone 'America/New_York')::date")
    today = cur.fetchone()[0]
    questions = cp.open_questions(cur, CORE)
    subject = cp.subject_for(questions[0])
    cur.execute(f"""insert into {CORE}.prompt_dispatch
                     (subject, scheduled_for, delivered_at, response_state)
                    values (%s, now() - interval '10 days', now() - interval '10 days',
                            'seen_declined')""", (subject,))

    history = cp.dispatch_history(cur, CORE, [subject])
    planned, suppressed = cp.decide(questions, history, today, cp.issued_on(cur, today, CORE))
    assert planned == []
    assert suppressed[0]["reason"] == "dismissed"
