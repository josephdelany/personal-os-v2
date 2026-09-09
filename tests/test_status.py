"""Status must not disguise failed/missing heartbeats (REQ-NFR-003/004).

In-memory cursor responses only; no fixture is inserted into a database.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from tools import status


NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


@pytest.mark.parametrize("state,finished,expected", [
    ("error", NOW - timedelta(minutes=1), "NOT OK: error"),
    ("running", None, "NOT OK: running"),
    ("ok", None, "INCOMPLETE"),
    ("ok", NOW - timedelta(hours=48), "STALE"),
    ("ok", NOW + timedelta(minutes=1), "INVALID"),
])
def test_REQ_NFR_004_recent_attempt_does_not_hide_failure(state, finished, expected, capsys):
    cur = Mock()
    started = NOW - timedelta(hours=49) if expected == "STALE" else NOW - timedelta(minutes=2)
    cur.fetchall.return_value = [
        ("keepalive_supabase", started, finished, state, NOW - timedelta(days=3), NOW)
    ]
    assert status.report_liveness(cur) is False
    output = capsys.readouterr().out
    assert expected in output
    assert "[ok]" not in output


def test_REQ_NFR_003_success_requires_recent_terminal_evidence(capsys):
    cur = Mock()
    cur.fetchall.return_value = [
        ("keepalive_supabase", NOW - timedelta(minutes=2), NOW - timedelta(minutes=1),
         "ok", NOW - timedelta(minutes=1), NOW)
    ]
    assert status.report_liveness(cur) is True
    assert "[ok]" in capsys.readouterr().out


def test_REQ_NFR_004_never_run_job_is_visible(capsys):
    cur = Mock()
    cur.fetchall.return_value = [("keepalive_github", None, None, None, None, NOW)]
    assert status.report_liveness(cur) is False
    assert "never  [MISSING]" in capsys.readouterr().out
    query = cur.execute.call_args.args[0]
    assert "LEFT JOIN LATERAL" in query
    for job in ("keepalive_supabase", "keepalive_github", "extract_checkins"):
        assert job in query


def test_REQ_NFR_004_status_exits_nonzero_and_closes_connection(monkeypatch):
    conn = Mock()
    cur = conn.cursor.return_value
    monkeypatch.setattr(status.db, "connect", lambda: conn)
    monkeypatch.setattr(status, "_fetch1", lambda _, q: NOW if q == "select now()" else 0)
    monkeypatch.setattr(status, "report_liveness", lambda *_: False)
    assert status.main() == 1
    assert cur.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)
    conn.close.assert_called_once()
    conn.commit.assert_not_called()
