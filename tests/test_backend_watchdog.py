"""ADR-0142: the schedule reports checkpoint health, never backend completion."""
import datetime as dt
import fcntl
import json
import plistlib

import pytest

from ops import backend_watchdog as monitor

NOW = dt.datetime(2026, 9, 22, 14, tzinfo=dt.timezone.utc)


def checkpoint(root, **overrides):
    state = {"version": 1, "status": "running", "unit": "audit-unit",
             "updated_at": NOW.isoformat(), "last_progress_at": NOW.isoformat(),
             "next_action": "run acceptance check"}
    state.update(overrides)
    text = monitor.START + "\n```json\n" + json.dumps(state) + "\n```\n" + monitor.END
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs/NEXT_SESSION.md").write_text(text)
    return text


@pytest.mark.parametrize("status,outcome", [
    ("ready", "awaiting_goal"), ("running", "checkpoint_recent"),
    ("held", "external_hold_recorded"),
    ("release_declared", "release_declaration_needs_review")])
def test_ADR_0142_checkpoint_state_never_certifies_release(tmp_path, status, outcome):
    checkpoint(tmp_path, status=status, release_evidence="docs/COMPLETION_AUDIT.md")
    report = monitor.inspect(tmp_path, NOW)
    assert report["outcome"] == outcome
    assert report["release_verified"] is False


def test_ADR_0142_touching_checkpoint_without_progress_still_warns(tmp_path):
    checkpoint(tmp_path, last_progress_at=(NOW - dt.timedelta(hours=2)).isoformat())
    report = monitor.inspect(tmp_path, NOW)
    assert report["outcome"] == "checkpoint_needs_attention"
    assert report["checkpoint_age_seconds"] == 0
    assert report["progress_age_seconds"] == 7200


@pytest.mark.parametrize("change", [
    {"status": "complete"}, {"updated_at": "bad"}, {"version": 2},
    {"updated_at": "2026-09-22T14:00:00"}, {"next_action": ""},
    {"updated_at": "2026-09-23T14:00:00+00:00"},
    {"last_progress_at": "2026-09-23T14:00:00+00:00"},
    {"status": "release_declared"}])
def test_ADR_0142_invalid_control_is_not_healthy(tmp_path, change):
    checkpoint(tmp_path, **change)
    assert monitor.inspect(tmp_path, NOW)["outcome"] == "checkpoint_invalid_or_unreadable"


def test_ADR_0142_missing_or_duplicated_control_is_not_healthy(tmp_path):
    assert monitor.inspect(tmp_path, NOW)["outcome"] == "checkpoint_invalid_or_unreadable"
    text = checkpoint(tmp_path)
    (tmp_path / "docs/NEXT_SESSION.md").write_text(text + text)
    assert monitor.inspect(tmp_path, NOW)["outcome"] == "checkpoint_invalid_or_unreadable"


def test_ADR_0142_monitor_preserves_instructions_and_writes_bounded_private_status(tmp_path):
    text = checkpoint(tmp_path, next_action="PRIVATE-TEXT-DO-NOT-LOG")
    first = monitor.write_status(tmp_path)
    monitor.write_status(tmp_path)
    path = tmp_path / ".local/backend_watchdog/status.json"
    assert json.loads(path.read_text())["outcome"] == first["outcome"]
    assert "PRIVATE-TEXT" not in path.read_text()
    assert path.stat().st_mode & 0o077 == 0
    assert (tmp_path / "docs/NEXT_SESSION.md").read_text() == text
    assert {p.name for p in path.parent.iterdir()} == {"status.json", "monitor.lock"}


def test_ADR_0142_overlapping_monitor_does_not_replace_status(tmp_path):
    checkpoint(tmp_path)
    monitor.write_status(tmp_path)
    directory = tmp_path / ".local/backend_watchdog"
    before = (directory / "status.json").read_bytes()
    with (directory / "monitor.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert monitor.write_status(tmp_path)["outcome"] == "monitor_already_running"
    assert (directory / "status.json").read_bytes() == before


def test_ADR_0142_launchd_runs_only_monitor_with_absolute_paths(tmp_path):
    job = plistlib.loads(plistlib.dumps(monitor.launchd(tmp_path, "/test/python")))
    assert job["ProgramArguments"] == ["/test/python", str(tmp_path / "ops/backend_watchdog.py"),
                                        "--write-status"]
    assert job["StartInterval"] == 900
    assert job["RunAtLoad"] is True
    assert "KeepAlive" not in job
    assert "EnvironmentVariables" not in job
