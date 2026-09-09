"""B11 calendar parsing: actual PL/pgSQL, disposable schema, rollback only.

Focused evidence for REQ-ASK-002/005/021. Does not prove the entire Ask RPC or
point-in-time replay. Run with PERSONAL_OS_TEST_SOCKET for local PostgreSQL.
"""
from datetime import date

import pytest

from tests._sql_fixture import sql_connection, migration_function


@pytest.fixture
def cur(sql_connection):
    cur = sql_connection.cursor()
    migration_function(cur, "0049_ask_core.sql", "public._ask_range(")
    return cur


@pytest.mark.parametrize("question,as_of,start,end", [
    ("how is my sleep", "2026-09-08", "2026-06-11", "2026-09-08"),
    ("steps today", "2026-09-08", "2026-09-08", "2026-09-08"),
    ("steps yesterday", "2026-09-08", "2026-09-07", "2026-09-07"),
    ("steps this week", "2026-09-08", "2026-09-07", "2026-09-08"),
    ("steps this week", "2026-09-07", "2026-09-07", "2026-09-07"),
    ("steps last week", "2026-09-08", "2026-08-31", "2026-09-06"),
    ("steps last week", "2026-01-01", "2025-12-22", "2025-12-28"),
    ("steps this month", "2026-09-08", "2026-09-01", "2026-09-08"),
    ("steps last month", "2024-03-12", "2024-02-01", "2024-02-29"),
    ("steps last month", "2025-03-12", "2025-02-01", "2025-02-28"),
    ("steps last month", "2026-01-01", "2025-12-01", "2025-12-31"),
    ("steps this year", "2026-09-08", "2026-01-01", "2026-09-08"),
    ("steps last 1 day", "2026-09-08", "2026-09-08", "2026-09-08"),
    ("steps last 7 days", "2026-09-08", "2026-09-02", "2026-09-08"),
    ("steps last 90 days", "2026-09-08", "2026-06-11", "2026-09-08"),
    ("steps in 2024", "2026-09-08", "2024-01-01", "2024-12-31"),
    ("steps in 2026", "2026-09-08", "2026-01-01", "2026-09-08"),
    ("steps since June", "2026-09-08", "2026-06-01", "2026-09-08"),
    ("steps since December", "2026-09-08", "2025-12-01", "2026-09-08"),
    ("steps since June 2024", "2026-09-08", "2024-06-01", "2026-09-08"),
])
def test_REQ_ASK_002_005_calendar_ranges(cur, question, as_of, start, end):
    cur.execute("SELECT * FROM api_pytest._ask_range(%s, %s::date)", (question, as_of))
    first, last, label = cur.fetchone()
    assert (first, last) == (date.fromisoformat(start), date.fromisoformat(end))
    assert label


@pytest.mark.parametrize("n", [1, 2, 7, 28, 30, 90, 365, 366, 1000])
def test_REQ_ASK_021_last_n_days_has_exact_coverage_denominator(cur, n):
    cur.execute("SELECT d_to - d_from + 1 FROM api_pytest._ask_range(%s, DATE '2026-09-08')",
                (f"steps last {n} days",))
    assert cur.fetchone()[0] == n


@pytest.mark.parametrize("question", [
    "steps last 0 days", "steps last -2 days", "steps last 1.5 days",
    "steps last 99999999999999 days", "steps since tomorrow", "steps since June 2027",
    "steps in 2027", "steps in 0000", "steps last 2147483647 days",
    "steps since June 20270", "steps since June 20", "steps in 20270",
])
def test_REQ_ASK_002_invalid_calendar_range_is_rejected(cur, question):
    with pytest.raises(Exception) as caught:
        cur.execute("SELECT * FROM api_pytest._ask_range(%s, DATE '2026-09-08')", (question,))
    assert caught.value.args[0]["C"] == "22023"
